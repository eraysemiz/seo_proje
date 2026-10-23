"""Canli erisim denetimleri.

Sayfanin HTML'inden gorulebilen denetimlere ek olarak, site canli erisildiginde
burada tanimli site katmani denetimleri calisir:
  - robots.txt      : var mi, gecerli mi, sitemap bildiriyor mu, sayfayi engelliyor mu
  - sitemap.xml     : erisilebilir mi, gecerli XML mi, kac adres iceriyor, sayfa listede mi
  - HTTPS           : sema, http->https yonlendirmesi, sertifika suresi, HSTS, durum kodu
  - hiz / boyut     : TTFB, indirme suresi, HTML boyutu, sikistirma, dis kaynak sayisi
  - yapisal veri    : JSON-LD, mikroveri, viewport, Open Graph, Twitter Card, hreflang, favicon

Etik not: arac varsayilan olarak robots.txt kurallarina uyar ve istekler arasinda
bekleme uygular; akademik bir denetim araci olarak kendini tanitir.
"""
import gzip
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import requests

from .cikarma import url_anahtari  # noqa: F401  (canli.url_anahtari olarak da kullanilir)
from .kurallar import cozum_yolu

AJAN_BELIRTECI = "DU-SEO-Denetim"     # robots.txt'de bu araca ozel kural yazilabilir
KULLANICI_AJANI = ("Mozilla/5.0 (compatible; " + AJAN_BELIRTECI + "/1.0; akademik arastirma; "
                   "+https://www.duzce.edu.tr/)")
VARSAYILAN_ZAMAN_ASIMI = 15
EN_FAZLA_SITEMAP = 10          # robots.txt adaylari ve dizin alt dosyalari dahil en fazla kac sitemap acilsin
SITEMAP_BOYUT_SINIRI = 50 * 1024 * 1024   # sitemaps.org siniri: 50 MB (sikistirilmamis)
TOHUM_SINIRI = 2000            # taramaya tohum olarak saklanan en fazla sitemap adresi
EN_FAZLA_SITEMAP_URL = 50000   # sayim siniri

def _kodlamalar():
    """Sunucudan yalnizca cozebilecegimiz sikistirma bicimlerini iste. br (brotli),
    urllib3 bir brotli paketi (brotli/brotlicffi) bulabildiginde desteklenir; paket yoksa
    istenmez, aksi halde sunucu br gonderir ve HTML bozuk okunurdu."""
    try:
        from urllib3.util.request import ACCEPT_ENCODING
        destek = {k.strip() for k in ACCEPT_ENCODING.split(",")}
    except ImportError:
        destek = {"gzip", "deflate"}
    return ", ".join(k for k in ("gzip", "deflate", "br") if k in destek)


_oturum = requests.Session()
_oturum.headers.update({"User-Agent": KULLANICI_AJANI,
                        "Accept-Encoding": _kodlamalar(),
                        "Accept-Language": "tr,en;q=0.8"})

# dogrulamasiz yeniden deneme yapildiginda urllib3'un her istekte uyari basmasini engeller
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except (ImportError, AttributeError):
    pass

# ayni site icin robots/sitemap/sertifika sonuclari tekrar indirilmesin diye onbellek
_onbellek = {}


def _al(adres, zaman_asimi, stream=False, yonlendir=True, olcum=None):
    """Tek bir GET istegi. Sertifika dogrulamasi basarisiz olursa denetimin tamamen
    durmamasi icin dogrulamasiz yeniden dener; (yanit, ssl_hatasi) dondurur.
    ssl_hatasi dolu donerse sayfa indirilmistir ama sertifika zinciri guvenilmezdir.
    olcum sozlugu verilirse basarili denemenin baslangic zamani 'basla' anahtarina yazilir;
    boylece basarisiz ilk denemenin suresi hiz olcumune karismaz."""
    try:
        if olcum is not None:
            olcum["basla"] = time.time()
        return _oturum.get(adres, timeout=zaman_asimi, stream=stream,
                           allow_redirects=yonlendir, verify=True), None
    except requests.exceptions.SSLError as e:
        if olcum is not None:
            olcum["basla"] = time.time()
        yanit = _oturum.get(adres, timeout=zaman_asimi, stream=stream,
                            allow_redirects=yonlendir, verify=False)
        return yanit, str(e)[:300]


def onbellek_temizle():
    _onbellek.clear()
    _baglanti_onbellegi.clear()
    _yoklama_onbellegi.clear()


# --------------------------------------------------------------------- adres
def normalize(u):
    """Kullanicinin yazdigi adresi tam bir URL'ye cevirir."""
    u = (u or "").strip()
    if not u:
        return ""
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u.lstrip("/")
    return urldefrag(u)[0]


def kok(u):
    p = urlparse(u)
    return p.scheme + "://" + p.netloc


# ---------------------------------------------------------------- sayfa cekme
def _metne_cevir(yanit):
    """Sunucu karakter kodlamasini bildirmediyse icerikten tahmin eder (Turkce sayfalar icin onemli)."""
    kodlama = yanit.encoding
    if not kodlama or kodlama.lower() == "iso-8859-1":
        if "charset=" not in (yanit.headers.get("Content-Type") or "").lower():
            kodlama = yanit.apparent_encoding or "utf-8"
    try:
        return yanit.content.decode(kodlama, errors="replace")
    except (LookupError, TypeError):
        return yanit.content.decode("utf-8", errors="replace")


YONLENDIRME_KODLARI = (301, 302, 303, 307, 308)
GECICI_YONLENDIRME = (302, 303, 307)
EN_FAZLA_YONLENDIRME = 10


def _link_basligi(deger):
    """HTTP Link basligi -> [{"url", "rel", "hreflang"}] (canonical ve hreflang icin)."""
    try:
        return [{k: v for k, v in b.items() if k in ("url", "rel", "hreflang")}
                for b in requests.utils.parse_header_links(deger)] if deger else []
    except (ValueError, AttributeError):
        return []


def sayfa_getir(url, zaman_asimi=VARSAYILAN_ZAMAN_ASIMI, izin=None, ssl_zorunlu=False):
    """Sayfayi indirir ve hiz/boyut olcumlerini toplar.
    Yonlendirmeler tek tek izlenir: izin(adres) verilirse her ara adres icin sorulur (robots.txt'nin
    yasakladigi bir ara adres istenmez), dongu ve EN_FAZLA_YONLENDIRME asimi ayri hata turu olarak
    doner. ttfb_ms yalnizca son yanitin basliklarinin gelis suresidir; yonlendirmeler yonlendirme_ms.
    ssl_zorunlu: sertifika dogrulanamazsa dogrulamasiz yeniden denenmez, hata dondurulur."""
    olcum, zincir, gorulen = {}, [], {url}
    adres, ssl_hatasi, yonlendirme, ilk_basla = url, None, 0.0, None

    def _hata(tur, mesaj):
        return {"basarili": False, "hata": mesaj, "hata_turu": tur, "url": url, "son_url": adres,
                "yonlendirme_zinciri": zincir}
    try:
        while True:
            if ssl_zorunlu:
                olcum["basla"] = time.time()
                yanit, ssl_h = _oturum.get(adres, timeout=zaman_asimi, stream=True, allow_redirects=False), None
            else:
                yanit, ssl_h = _al(adres, zaman_asimi, stream=True, yonlendir=False, olcum=olcum)
            ilk_basla = ilk_basla or olcum["basla"]
            ssl_hatasi = ssl_hatasi or ssl_h
            hedef = yanit.headers.get("Location") if yanit.status_code in YONLENDIRME_KODLARI else None
            if not hedef:
                break
            yanit.close()
            yonlendirme += yanit.elapsed.total_seconds()
            zincir.append(str(yanit.status_code) + " " + adres)
            sonraki = urldefrag(urljoin(adres, hedef.strip()))[0]
            if sonraki in gorulen:
                return _hata("yonlendirme_dongusu", "Yönlendirme döngüsü: " + " → ".join(
                    [z.split(" ", 1)[1] for z in zincir] + [sonraki])[:400])
            if len(zincir) >= EN_FAZLA_YONLENDIRME:
                return _hata("cok_fazla_yonlendirme", str(len(zincir)) + " yönlendirmeden sonra durduruldu")
            if izin and not izin(sonraki):
                r = _hata("robots_engeli", "robots.txt bu ara adresin taranmasına izin vermiyor: " + sonraki)
                r["robots_engeli"] = sonraki
                return r
            gorulen.add(sonraki)
            adres = sonraki
        govde = yanit.content              # tam indirme
        toplam = time.time() - ilk_basla
    except requests.exceptions.SSLError as e:
        return _hata("ssl", "Sertifika doğrulanamadı: " + str(e)[:300])
    except requests.RequestException as e:
        return {"basarili": False, "hata": type(e).__name__ + ": " + str(e), "url": url}
    ttfb = yanit.elapsed.total_seconds()
    html = _metne_cevir(yanit)
    return {
        "basarili": True,
        "url": url,
        "ssl_hatasi": ssl_hatasi,
        "son_url": adres,
        "durum_kodu": yanit.status_code,
        "yonlendirme_sayisi": len(zincir),
        "yonlendirme_zinciri": zincir,
        "ttfb_ms": round(ttfb * 1000),
        "yonlendirme_ms": round(yonlendirme * 1000),
        "toplam_ms": round(toplam * 1000),
        "boyut_bayt": len(govde),
        "icerik_kodlama": yanit.headers.get("Content-Encoding"),
        "icerik_turu": yanit.headers.get("Content-Type"),
        "hsts": yanit.headers.get("Strict-Transport-Security"),
        "x_robots_tag": yanit.headers.get("X-Robots-Tag"),
        "refresh": yanit.headers.get("Refresh"),
        "link_basligi": _link_basligi(yanit.headers.get("Link")),
        "html": html,
    }


# ------------------------------------------------------------------- robots
def robots_bilgisi(site_koku, zaman_asimi=VARSAYILAN_ZAMAN_ASIMI):
    anahtar = ("robots", site_koku)
    if anahtar in _onbellek:
        return _onbellek[anahtar]
    adres = site_koku + "/robots.txt"
    bilgi = {"adres": adres, "var": False, "durum_kodu": None, "satir_sayisi": 0,
             "sitemapler": [], "tum_siteyi_engelliyor": False, "ilk_satirlar": "",
             "hata": None, "_parser": None}
    try:
        y, _ = _al(adres, zaman_asimi)
        bilgi["durum_kodu"] = y.status_code
        metin = _metne_cevir(y)
        tur = (y.headers.get("Content-Type") or "").lower()
        # bazi siteler eksik sayfa yerine HTML hata sayfasi dondurur; bunu robots sayma
        html_mi = metin.lstrip()[:200].lower().startswith(("<!doctype", "<html")) or "text/html" in tur
        if y.status_code == 200 and not html_mi:
            bilgi["var"] = True
            bilgi["satir_sayisi"] = len([s for s in metin.splitlines() if s.strip()])
            bilgi["sitemapler"] = [m.strip() for m in
                                   re.findall(r"(?im)^\s*sitemap\s*:\s*(\S+)", metin)]
            p = RobotFileParser()
            p.parse(metin.splitlines())
            bilgi["_parser"] = p
            bilgi["tum_siteyi_engelliyor"] = not p.can_fetch("*", site_koku + "/")
            bilgi["ilk_satirlar"] = "\n".join(metin.splitlines()[:25])
        elif y.status_code == 200 and html_mi:
            bilgi["hata"] = "robots.txt yerine HTML sayfa dönüyor"
    except requests.RequestException as e:
        bilgi["hata"] = type(e).__name__ + ": " + str(e)
    _onbellek[anahtar] = bilgi
    return bilgi


def sayfa_engelli_mi(robots, url, ajan="*"):
    """ajan='*' arama motorlari icin genel durumu (SEO bulgusu), ajan=AJAN_BELIRTECI ise
    bu aracin kendisinin taramaya izinli olup olmadigini (etik uyum) sorar."""
    p = robots.get("_parser")
    return bool(p) and not p.can_fetch(ajan, url)


# ------------------------------------------------------------------ sitemap
def _xml_coz(ham):
    if ham[:2] == b"\x1f\x8b":                    # gzip ile sikistirilmis sitemap
        ham = gzip.decompress(ham)
    return ElementTree.fromstring(ham)


def _etiket(e):
    return e.tag.split("}")[-1]


def _sinirli_oku(yanit, sinir):
    """Yanit govdesini en fazla 'sinir' bayt okur; asarsa None (dev sitemap bellegi doldurmasin)."""
    if not hasattr(yanit, "iter_content"):
        return yanit.content
    parcalar, toplam = [], 0
    for p in yanit.iter_content(1 << 16):
        toplam += len(p)
        if toplam > sinir:
            yanit.close()
            return None
        parcalar.append(p)
    return b"".join(parcalar)


def sitemap_bilgisi(site_koku, robots, zaman_asimi=VARSAYILAN_ZAMAN_ASIMI):
    """robots.txt'de bildirilen sitemapleri, yoksa /sitemap.xml adresini dener."""
    anahtar = ("sitemap", site_koku)
    if anahtar in _onbellek:
        return _onbellek[anahtar]
    # robots.txt'de goreli yazilmis sitemap adresi site kokune gore cozulur
    adaylar = [urljoin(site_koku + "/", a) for a in (robots.get("sitemapler") or [])] or [site_koku + "/sitemap.xml"]
    bilgi = {"adaylar": adaylar, "var": False, "gecerli": False, "tur": None,
             "url_sayisi": 0, "alt_sitemap_sayisi": 0, "lastmod_var": False,
             "acilan": [], "adresler": set(), "tohumlar": [], "hatali_adresler": [], "cok_buyuk": [],
             "hata": None}
    acilacak, acilan_sayi = list(adaylar), 0

    def _hatali(adres, neden):
        bilgi["hata"] = bilgi["hata"] or (adres + " -> " + neden)
        bilgi["hatali_adresler"].append(adres + " (" + neden + ")")
    while acilacak and acilan_sayi < EN_FAZLA_SITEMAP:
        adres = acilacak.pop(0)
        acilan_sayi += 1
        try:
            y, _ = _al(adres, zaman_asimi, stream=True)
            if y.status_code != 200:
                _hatali(adres, str(y.status_code))
                continue
            ham = _sinirli_oku(y, SITEMAP_BOYUT_SINIRI)
            if ham is None:
                bilgi["var"] = True
                bilgi["cok_buyuk"].append(adres + " (50 MB üstü)")
                continue
            kok_e = _xml_coz(ham)
            bilgi["var"] = True
            bilgi["acilan"].append(adres)
            bilgi["gecerli"] = True
            etiket = _etiket(kok_e)
            bilgi["tur"] = "dizin" if etiket == "sitemapindex" else "urlset"
            dosya_url = 0
            for cocuk in kok_e:
                loc = cocuk.find("{*}loc")
                if loc is None or not (loc.text or "").strip():
                    continue
                adres_c = loc.text.strip()
                if etiket == "sitemapindex":
                    bilgi["alt_sitemap_sayisi"] += 1
                    acilacak.append(adres_c)
                else:
                    if len(bilgi["adresler"]) < EN_FAZLA_SITEMAP_URL:
                        bilgi["adresler"].add(url_anahtari(adres_c))
                    if len(bilgi["tohumlar"]) < TOHUM_SINIRI:
                        bilgi["tohumlar"].append(adres_c)
                    bilgi["url_sayisi"] += 1
                    dosya_url += 1
                    if cocuk.find("{*}lastmod") is not None:
                        bilgi["lastmod_var"] = True
            if dosya_url > 50000:
                bilgi["cok_buyuk"].append(adres + " (" + str(dosya_url) + " adres)")
        except ElementTree.ParseError as e:
            _hatali(adres, "XML çözülemedi: " + str(e)[:80])
        except (requests.RequestException, OSError, gzip.BadGzipFile, EOFError) as e:
            _hatali(adres, type(e).__name__)
    # acilma sinirina takilan alt sitemap kaldiysa adres listesi eksiktir; "sayfa listede yok"
    # sonucu bu durumda guvenilir degildir
    bilgi["tam_okundu"] = not acilacak and bilgi["url_sayisi"] <= EN_FAZLA_SITEMAP_URL
    _onbellek[anahtar] = bilgi
    return bilgi


# ---------------------------------------------------------------- HTTPS / TLS
def _der_coz(der):
    """DER bicimindeki bir sertifikayi sozluge cevirir (yalnizca standart kutuphane ile).
    Python surumleri arasinda zincir API'si degistigi icin basarisizlikta None doner."""
    import os as _os
    import tempfile
    try:
        pem = ssl.DER_cert_to_PEM_cert(der)
        f = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False, encoding="ascii")
        try:
            f.write(pem)
            f.close()
            return ssl._ssl._test_decode_cert(f.name)
        finally:
            _os.unlink(f.name)
    except (AttributeError, OSError, ValueError, ssl.SSLError):
        return None


def sertifika_bilgisi(host, port=443):
    anahtar = ("sertifika", host)
    if anahtar in _onbellek:
        return _onbellek[anahtar]
    bilgi = {"dogrulandi": None, "gecerli": None, "kalan_gun": None, "veren": None,
             "bitis": None, "zincir_eksik": False, "zincir": [], "hata": None}

    def _baglan(dogrula):
        baglam = ssl.create_default_context() if dogrula else ssl._create_unverified_context()
        with socket.create_connection((host, port), timeout=10) as s:
            with baglam.wrap_socket(s, server_hostname=host) as ss:
                zincir = []
                if hasattr(ss, "get_unverified_chain"):     # Python 3.13+
                    for c in (ss.get_unverified_chain() or []):
                        # surume gore ya Certificate nesnesi ya da ham DER bayt dizisi doner
                        bilgi_c = c.get_info() if hasattr(c, "get_info") else _der_coz(c)
                        if bilgi_c:
                            zincir.append(bilgi_c)
                return ss.getpeercert(), zincir

    def _ad(alanlar):
        d = dict(x[0] for x in (alanlar or ()))
        return d.get("commonName") or d.get("organizationName")

    try:
        try:
            sert, zincir = _baglan(True)
            bilgi["dogrulandi"] = True
        except (ssl.SSLError, ssl.CertificateError) as e:
            # dogrulama basarisiz: sertifikanin kendisini yine de okuyup nedenini tespit et
            bilgi["dogrulandi"] = False
            bilgi["hata"] = type(e).__name__ + ": " + str(e)
            sert, zincir = _baglan(False)
        bitis = datetime.strptime(sert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        bilgi["kalan_gun"] = (bitis - datetime.now(timezone.utc)).days
        bilgi["bitis"] = bitis.date().isoformat()
        bilgi["veren"] = _ad(sert.get("issuer"))
        bilgi["zincir"] = [_ad(c.get("subject")) for c in zincir]
        # sunucunun gonderdigi zincirde yaprak sertifikanin vereni yoksa ara sertifika eksiktir
        if len(zincir) > 1 and bilgi["veren"] and bilgi["veren"] not in bilgi["zincir"][1:]:
            bilgi["zincir_eksik"] = True
        elif len(zincir) == 1 and bilgi["dogrulandi"] is False:
            bilgi["zincir_eksik"] = True
        bilgi["gecerli"] = bool(bilgi["dogrulandi"]) and bilgi["kalan_gun"] > 0
    except (ssl.SSLError, ssl.CertificateError, OSError, ValueError, KeyError) as e:
        bilgi["gecerli"] = False
        bilgi["hata"] = bilgi["hata"] or (type(e).__name__ + ": " + str(e))
    _onbellek[anahtar] = bilgi
    return bilgi


def http_yonlendirme(site_koku, zaman_asimi=VARSAYILAN_ZAMAN_ASIMI):
    """http:// adresinin https:// adresine yonlendirilip yonlendirilmedigini olcer."""
    host = urlparse(site_koku).netloc
    anahtar = ("http_yon", host)
    if anahtar in _onbellek:
        return _onbellek[anahtar]
    bilgi = {"yonlendiriyor": None, "hedef": None, "durum_kodu": None, "hata": None}
    try:
        y = _oturum.get("http://" + host + "/", timeout=zaman_asimi, allow_redirects=False)
        bilgi["durum_kodu"] = y.status_code
        hedef = y.headers.get("Location")
        bilgi["hedef"] = hedef
        bilgi["yonlendiriyor"] = bool(hedef and urljoin("http://" + host + "/", hedef).startswith("https://"))
    except requests.RequestException as e:
        bilgi["hata"] = type(e).__name__ + ": " + str(e)
    _onbellek[anahtar] = bilgi
    return bilgi


# --------------------------------------------------------------- ana denetim
def canli_denetim(getirme, zaman_asimi=VARSAYILAN_ZAMAN_ASIMI):
    """Indirilmis bir sayfa icin site katmani denetimlerini calistirir.
    (sorunlar, bilgi) dondurur; sorunlarin tamami katman='site' etiketlidir."""
    sorunlar = []

    def add(kod, ciddiyet, ayrinti=""):
        sorunlar.append({"sorun": kod, "ciddiyet": ciddiyet, "ayrinti": ayrinti,
                         "katman": "site", "cozum_yolu": cozum_yolu(kod)})

    # sayfa hic indirilemediyse icerik tabanli denetimler anlamsizdir; yanlis bulgu uretme
    if not getirme.get("basarili"):
        # yonlendirme dongusu ve asiri uzun zincir "erisilemedi" yerine kendi koduyla raporlanir
        kod = getirme.get("hata_turu") if getirme.get("hata_turu") in ("yonlendirme_dongusu",
                                                                       "cok_fazla_yonlendirme") else "erisilemedi"
        add(kod, "yuksek", getirme.get("hata", ""))
        return sorunlar, {"son_url": getirme.get("url"), "hata": getirme.get("hata"),
                          "yonlendirme_zinciri": getirme.get("yonlendirme_zinciri")}

    son_url = getirme.get("son_url") or getirme["url"]
    site_koku = kok(son_url)
    p = urlparse(son_url)

    # --- durum kodu ve yonlendirme
    durum = getirme.get("durum_kodu")
    if durum and durum >= 400:
        add("hata_durum_kodu", "yuksek", str(durum))
    elif durum and 300 <= durum < 400:
        add("gecersiz_yonlendirme", "yuksek", str(durum) + ", Location başlığı yok")
    if getirme.get("yonlendirme_sayisi", 0) > 1:
        add("uzun_yonlendirme_zinciri", "dusuk", str(getirme["yonlendirme_sayisi"]) + " yönlendirme")
    gecici = [z for z in getirme.get("yonlendirme_zinciri") or [] if z.split(" ", 1)[0] in map(str, GECICI_YONLENDIRME)]
    if gecici:
        add("gecici_yonlendirme", "dusuk", gecici[0][:160])
    if getirme.get("refresh"):
        add("meta_refresh", "orta", "Refresh başlığı: " + str(getirme["refresh"])[:120])

    # --- HTTPS ve sertifika
    sertifika = None
    if p.scheme != "https":
        add("https_yok", "yuksek", son_url)
    else:
        sertifika = sertifika_bilgisi(p.hostname)
        kalan = sertifika.get("kalan_gun")
        # gecerlilik suresi ve zincir butunlugu birbirinden bagimsiz iki sorundur
        if kalan is not None and kalan <= 0:
            add("sertifika_suresi_dolmus", "yuksek", "bitiş " + str(sertifika.get("bitis")))
        elif kalan is not None and kalan < 30:
            add("sertifika_yakinda_bitiyor", "orta", str(kalan) + " gün, bitiş " + str(sertifika.get("bitis")))
        # Isletim sisteminin sertifika deposu eksik ara sertifikayi onbellekten tamamlayabilir;
        # bu yuzden olcut, yaygin bir istemcinin (requests + certifi kok deposu) dogrulayip
        # dogrulayamadigidir. Tarayicilar sorunu gizler, kati istemciler ve bazi botlar baglanamaz.
        if sertifika.get("zincir_eksik") or getirme.get("ssl_hatasi"):
            ayrinti = ("sunucu, yaprak sertifikanın vereni olan '" + str(sertifika.get("veren")) +
                       "' ara sertifikasını göndermiyor") if sertifika.get("zincir_eksik") else \
                      "standart kök sertifika deposuyla doğrulanamadı"
            add("sertifika_zinciri_eksik", "yuksek", ayrinti)
        elif sertifika.get("dogrulandi") is False:
            add("sertifika_dogrulanamadi", "yuksek", (sertifika.get("hata") or "")[:160])
        if not getirme.get("hsts"):
            add("hsts_yok", "dusuk")
    yonlendirme = http_yonlendirme(site_koku, zaman_asimi)
    if yonlendirme.get("yonlendiriyor") is False:
        add("https_yonlendirme_yok", "orta", "durum " + str(yonlendirme.get("durum_kodu")))

    # --- robots.txt
    robots = robots_bilgisi(site_koku, zaman_asimi)
    if not robots["var"]:
        add("robots_okunamadi" if robots["hata"] else "robots_yok", "orta",
            robots["hata"] or ("durum " + str(robots["durum_kodu"])))
    else:
        if robots["tum_siteyi_engelliyor"]:
            add("robots_tum_siteyi_engelliyor", "yuksek")
        elif sayfa_engelli_mi(robots, son_url):
            add("robots_sayfayi_engelliyor", "yuksek", son_url)
        if not robots["sitemapler"]:
            add("robots_sitemap_bildirilmemis", "dusuk")

    # --- sitemap
    sitemap = sitemap_bilgisi(site_koku, robots, zaman_asimi)
    if not sitemap["var"]:
        add("sitemap_yok", "orta", sitemap.get("hata") or "")
    elif not sitemap["gecerli"]:
        add("sitemap_gecersiz", "orta", sitemap.get("hata") or "")
    elif sitemap["url_sayisi"] == 0 and sitemap["alt_sitemap_sayisi"] == 0:
        add("sitemap_bos", "orta")
    elif sitemap["adresler"] and sitemap["tam_okundu"]:
        if url_anahtari(son_url) not in sitemap["adresler"]:
            add("sayfa_sitemapte_yok", "dusuk")
    if sitemap["var"] and sitemap.get("hatali_adresler"):
        add("sitemap_hatali_adres", "dusuk", ", ".join(sitemap["hatali_adresler"][:3])[:200])
    if sitemap.get("cok_buyuk"):
        add("sitemap_cok_buyuk", "orta", ", ".join(sitemap["cok_buyuk"][:2])[:200])
    sitemapte = (url_anahtari(son_url) in sitemap["adresler"]) if sitemap.get("adresler") else None

    # --- hiz ve boyut
    ttfb = getirme.get("ttfb_ms") or 0
    if ttfb > 2500:
        add("cok_yavas_yanit", "orta", "TTFB " + str(ttfb) + " ms")
    elif ttfb > 1000:
        add("yavas_yanit", "dusuk", "TTFB " + str(ttfb) + " ms")
    if not getirme.get("icerik_kodlama"):
        add("sikistirma_yok", "dusuk")
    boyut_kb = round((getirme.get("boyut_bayt") or 0) / 1024)
    if boyut_kb > 500:
        add("html_cok_buyuk", "dusuk", str(boyut_kb) + " KB")

    # yapisal veri, viewport ve paylasim etiketleri HTML'den gorulebildigi icin
    # sayfa katmaninda (kurallar.ek_html_denetimi) denetlenir; burada tekrarlanmaz.
    # Yalnizca yanit basligindan gelen robots yonergeleri burada ele alinir.
    xrt = x_robots_yonergeleri(getirme.get("x_robots_tag"))
    if xrt & {"noindex", "none"}:
        add("noindex", "yuksek", "X-Robots-Tag: " + str(getirme.get("x_robots_tag")))
    if xrt & {"nofollow", "none"}:
        add("sayfa_nofollow", "orta", "X-Robots-Tag: " + str(getirme.get("x_robots_tag")))

    bilgi = {"site_koku": site_koku, "son_url": son_url,
             "durum_kodu": durum, "yonlendirme_zinciri": getirme.get("yonlendirme_zinciri"),
             "ttfb_ms": getirme.get("ttfb_ms"), "yonlendirme_ms": getirme.get("yonlendirme_ms"),
             "toplam_ms": getirme.get("toplam_ms"),
             "boyut_kb": boyut_kb, "sikistirma": getirme.get("icerik_kodlama"),
             "hsts": bool(getirme.get("hsts")),
             "sertifika": sertifika,
             "http_yonlendirme": yonlendirme,
             "robots": {k: v for k, v in robots.items() if k != "_parser"},
             "sitemap": {**{k: v for k, v in sitemap.items() if k not in ("adresler", "tohumlar")},
                         "adres_ornegi": sorted(sitemap["adresler"])[:3]},
             "sitemapte": sitemapte,
             "x_robots_yonergeleri": sorted(xrt)}
    return sorunlar, bilgi


def x_robots_yonergeleri(deger):
    """X-Robots-Tag degerindeki genel ve googlebot'a ozel yonergeler.
    'googlebot: noindex' gibi bota ozel satirlar ve 'unavailable_after: tarih' ayrilir."""
    sonuc = set()
    for satir in re.split(r",(?=\s*[a-z_-]+\s*:)|\n", (deger or "").lower()):
        ajan, _, yonergeler = satir.rpartition(":") if re.match(r"^\s*[a-z_-]+\s*:", satir) else ("", "", satir)
        ajan = ajan.strip()
        if ajan in ("", "googlebot", "robots", "*"):
            sonuc |= {y.strip() for y in yonergeler.split(",") if y.strip()}
        elif ajan.startswith("unavailable_after"):
            continue
    return sonuc


# ------------------------------------------------------------ yumusak 404
_yoklama_onbellegi = {}


def yumusak_404_yoklama(url, zaman_asimi=VARSAYILAN_ZAMAN_ASIMI, izin=None):
    """Sayfanin bulundugu klasorde var olmasi neredeyse imkansiz rastgele bir adres ister. Sunucu 200
    donerse bulunamayan adresler icin hata kodu vermiyor demektir. Klasor basina tek istek (onbellekli).
    Durum kodunu (ya da istenemediyse None) dondurur; izin(adres) False ise (robots.txt) istek yapilmaz."""
    from secrets import token_hex
    p = urlparse(url)
    klasor = p.path.rsplit("/", 1)[0] + "/"
    anahtar = (p.scheme, p.netloc.lower(), klasor)
    if anahtar not in _yoklama_onbellegi:
        adres = p._replace(path=klasor + "yok-" + token_hex(6) + ".html", query="", fragment="").geturl()
        kod = None
        if izin is None or izin(adres):
            try:
                kod = _oturum.get(adres, timeout=zaman_asimi, allow_redirects=True).status_code
            except requests.RequestException:
                kod = None
        _yoklama_onbellegi[anahtar] = kod
    return _yoklama_onbellegi[anahtar]


# ------------------------------------------------------------ baglanti denetimi
_baglanti_onbellegi = {}


def baglanti_durumu(adres, zaman_asimi=10):
    """Bir baglanti/gorsel adresinin durumu: once HEAD, sunucu desteklemezse GET (govde okunmaz).
    Sonuc taramanin tamaminda onbellekte tutulur; ayni adres iki kez istenmez.
    Is parcaciklarindan cagrildigi icin ortak oturum yerine her istek kendi baglantisini acar."""
    if adres in _baglanti_onbellegi:
        return _baglanti_onbellegi[adres]
    basliklar = {"User-Agent": KULLANICI_AJANI, "Accept-Language": "tr,en;q=0.8"}
    sonuc = {"durum": None, "son_url": adres, "yonlendirme": 0, "boyut": None, "hata": None}
    try:
        try:
            y = requests.head(adres, headers=basliklar, timeout=zaman_asimi, allow_redirects=True)
        except requests.exceptions.SSLError:
            y = requests.head(adres, headers=basliklar, timeout=zaman_asimi, allow_redirects=True, verify=False)
        if y.status_code in (403, 405, 501) or y.status_code >= 500:
            # HEAD'i desteklemeyen ya da yanlis yanitlayan sunucular icin GET ile dogrula
            with requests.get(adres, headers=basliklar, timeout=zaman_asimi, allow_redirects=True,
                              stream=True, verify=False) as g:
                y = g
        sonuc.update({"durum": y.status_code, "son_url": y.url, "yonlendirme": len(y.history),
                      "boyut": int(y.headers["Content-Length"]) if (y.headers.get("Content-Length") or "").isdigit()
                      else None})
    except requests.RequestException as e:
        sonuc["hata"] = type(e).__name__
    _baglanti_onbellegi[adres] = sonuc
    return sonuc


def baglantilari_denetle(adresler, zaman_asimi=10, bekleme=0.25, izin=None, es_zamanli=4):
    """Adresleri host'a gore gruplayip denetler: farkli host'lar paralel, ayni host'a istekler sirayla
    ve aralarinda 'bekleme' saniye ile gider (sunucuyu yormamak icin). izin(adres) False donerse
    (robots.txt) adres istenmez, durumu None kalir. {adres: durum} dondurur."""
    from concurrent.futures import ThreadPoolExecutor
    gruplar = {}
    for a in dict.fromkeys(adresler):
        gruplar.setdefault(urlparse(a).netloc, []).append(a)

    def _host_isle(liste):
        sonuc = {}
        for i, a in enumerate(liste):
            if izin and not izin(a):
                sonuc[a] = {"durum": None, "son_url": a, "yonlendirme": 0, "boyut": None, "hata": "robots.txt"}
                continue
            onbellekte = a in _baglanti_onbellegi
            sonuc[a] = baglanti_durumu(a, zaman_asimi)
            if not onbellekte and bekleme and i < len(liste) - 1:
                time.sleep(bekleme)
        return sonuc
    sonuclar = {}
    if not gruplar:
        return sonuclar
    with ThreadPoolExecutor(max_workers=min(es_zamanli, len(gruplar))) as havuz:
        for parca in havuz.map(_host_isle, gruplar.values()):
            sonuclar.update(parca)
    return sonuclar
