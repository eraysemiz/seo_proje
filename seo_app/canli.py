"""Canli erisim denetimleri.

Cevrimdisi (kaydedilmis HTML) modunda yalnizca sayfa katmani denetlenebilir.
Site canli olarak erisilebildiginde burada tanimli ek denetimler calisir:
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

from .kurallar import cozum_yolu

KULLANICI_AJANI = ("Mozilla/5.0 (compatible; DU-SEO-Denetim/1.0; akademik arastirma; "
                   "+https://www.duzce.edu.tr/)")
VARSAYILAN_ZAMAN_ASIMI = 15
EN_FAZLA_SITEMAP = 3           # sitemap dizininde en fazla kac alt dosya acilsin
EN_FAZLA_SITEMAP_URL = 50000   # sayim siniri

_oturum = requests.Session()
_oturum.headers.update({"User-Agent": KULLANICI_AJANI,
                        "Accept-Encoding": "gzip, deflate",
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


def sayfa_getir(url, zaman_asimi=VARSAYILAN_ZAMAN_ASIMI):
    """Sayfayi indirir ve hiz/boyut olcumlerini toplar.
    ttfb_ms yalnizca son (yonlendirme sonrasi) yanitin istek gonderiminden basliklarin
    gelisine kadar gecen suredir; yonlendirmeler yonlendirme_ms olarak ayri raporlanir."""
    olcum = {}
    try:
        yanit, ssl_hatasi = _al(url, zaman_asimi, stream=True, olcum=olcum)
        govde = yanit.content              # tam indirme
        toplam = time.time() - olcum["basla"]
    except requests.RequestException as e:
        return {"basarili": False, "hata": type(e).__name__ + ": " + str(e), "url": url}
    ttfb = yanit.elapsed.total_seconds()
    yonlendirme = sum(h.elapsed.total_seconds() for h in yanit.history)
    html = _metne_cevir(yanit)
    return {
        "basarili": True,
        "url": url,
        "ssl_hatasi": ssl_hatasi,
        "son_url": yanit.url,
        "durum_kodu": yanit.status_code,
        "yonlendirme_sayisi": len(yanit.history),
        "yonlendirme_zinciri": [str(h.status_code) + " " + h.url for h in yanit.history],
        "ttfb_ms": round(ttfb * 1000),
        "yonlendirme_ms": round(yonlendirme * 1000),
        "toplam_ms": round(toplam * 1000),
        "boyut_bayt": len(govde),
        "icerik_kodlama": yanit.headers.get("Content-Encoding"),
        "icerik_turu": yanit.headers.get("Content-Type"),
        "hsts": yanit.headers.get("Strict-Transport-Security"),
        "x_robots_tag": yanit.headers.get("X-Robots-Tag"),
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
            bilgi["hata"] = "robots.txt yerine HTML sayfa donuyor"
    except requests.RequestException as e:
        bilgi["hata"] = type(e).__name__ + ": " + str(e)
    _onbellek[anahtar] = bilgi
    return bilgi


def sayfa_engelli_mi(robots, url):
    p = robots.get("_parser")
    return bool(p) and not p.can_fetch("*", url)


# ------------------------------------------------------------------ sitemap
def _xml_coz(ham):
    if ham[:2] == b"\x1f\x8b":                    # gzip ile sikistirilmis sitemap
        ham = gzip.decompress(ham)
    return ElementTree.fromstring(ham)


def _etiket(e):
    return e.tag.split("}")[-1]


def sitemap_bilgisi(site_koku, robots, zaman_asimi=VARSAYILAN_ZAMAN_ASIMI):
    """robots.txt'de bildirilen sitemapleri, yoksa /sitemap.xml adresini dener."""
    anahtar = ("sitemap", site_koku)
    if anahtar in _onbellek:
        return _onbellek[anahtar]
    adaylar = list(robots.get("sitemapler") or []) or [site_koku + "/sitemap.xml"]
    bilgi = {"adaylar": adaylar, "var": False, "gecerli": False, "tur": None,
             "url_sayisi": 0, "alt_sitemap_sayisi": 0, "lastmod_var": False,
             "acilan": [], "adresler": set(), "hata": None}
    acilacak, acilan_sayi = list(adaylar), 0
    while acilacak and acilan_sayi < EN_FAZLA_SITEMAP:
        adres = acilacak.pop(0)
        acilan_sayi += 1
        try:
            y, _ = _al(adres, zaman_asimi)
            if y.status_code != 200:
                bilgi["hata"] = bilgi["hata"] or (adres + " -> " + str(y.status_code))
                continue
            bilgi["var"] = True
            bilgi["acilan"].append(adres)
            kok_e = _xml_coz(y.content)
            bilgi["gecerli"] = True
            etiket = _etiket(kok_e)
            bilgi["tur"] = "dizin" if etiket == "sitemapindex" else "urlset"
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
                        bilgi["adresler"].add(urldefrag(adres_c)[0].rstrip("/"))
                    bilgi["url_sayisi"] += 1
                    if cocuk.find("{*}lastmod") is not None:
                        bilgi["lastmod_var"] = True
        except ElementTree.ParseError as e:
            bilgi["hata"] = "XML cozulemedi: " + str(e)
        except (requests.RequestException, OSError, gzip.BadGzipFile) as e:
            bilgi["hata"] = type(e).__name__ + ": " + str(e)
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
        add("erisilemedi", "yuksek", getirme.get("hata", ""))
        return sorunlar, {"son_url": getirme.get("url"), "hata": getirme.get("hata")}

    son_url = getirme.get("son_url") or getirme["url"]
    site_koku = kok(son_url)
    p = urlparse(son_url)

    # --- durum kodu ve yonlendirme
    durum = getirme.get("durum_kodu")
    if durum and durum >= 400:
        add("hata_durum_kodu", "yuksek", str(durum))
    if getirme.get("yonlendirme_sayisi", 0) > 1:
        add("uzun_yonlendirme_zinciri", "dusuk", str(getirme["yonlendirme_sayisi"]) + " yonlendirme")

    # --- HTTPS ve sertifika
    sertifika = None
    if p.scheme != "https":
        add("https_yok", "yuksek", son_url)
    else:
        sertifika = sertifika_bilgisi(p.hostname)
        kalan = sertifika.get("kalan_gun")
        # gecerlilik suresi ve zincir butunlugu birbirinden bagimsiz iki sorundur
        if kalan is not None and kalan <= 0:
            add("sertifika_suresi_dolmus", "yuksek", "bitis " + str(sertifika.get("bitis")))
        elif kalan is not None and kalan < 30:
            add("sertifika_yakinda_bitiyor", "orta", str(kalan) + " gun, bitis " + str(sertifika.get("bitis")))
        # Isletim sisteminin sertifika deposu eksik ara sertifikayi onbellekten tamamlayabilir;
        # bu yuzden olcut, yaygin bir istemcinin (requests + certifi kok deposu) dogrulayip
        # dogrulayamadigidir. Tarayicilar sorunu gizler, kati istemciler ve bazi botlar baglanamaz.
        if sertifika.get("zincir_eksik") or getirme.get("ssl_hatasi"):
            ayrinti = ("sunucu, yaprak sertifikanin vereni olan '" + str(sertifika.get("veren")) +
                       "' ara sertifikasini gondermiyor") if sertifika.get("zincir_eksik") else \
                      "standart kok sertifika deposuyla dogrulanamadi"
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
    elif sitemap["adresler"] and sitemap["tur"] == "urlset":
        if urldefrag(son_url)[0].rstrip("/") not in sitemap["adresler"]:
            add("sayfa_sitemapte_yok", "dusuk")

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
    # Yalnizca yanit basligindan gelen noindex burada ele alinir.
    if "noindex" in (getirme.get("x_robots_tag") or "").lower():
        add("noindex", "yuksek", "X-Robots-Tag: " + str(getirme.get("x_robots_tag")))

    bilgi = {"site_koku": site_koku, "son_url": son_url,
             "durum_kodu": durum, "yonlendirme_zinciri": getirme.get("yonlendirme_zinciri"),
             "ttfb_ms": getirme.get("ttfb_ms"), "yonlendirme_ms": getirme.get("yonlendirme_ms"),
             "toplam_ms": getirme.get("toplam_ms"),
             "boyut_kb": boyut_kb, "sikistirma": getirme.get("icerik_kodlama"),
             "hsts": bool(getirme.get("hsts")),
             "sertifika": sertifika,
             "http_yonlendirme": yonlendirme,
             "robots": {k: v for k, v in robots.items() if k != "_parser"},
             "sitemap": {**{k: v for k, v in sitemap.items() if k != "adresler"},
                         "adres_ornegi": sorted(sitemap["adresler"])[:3]}}
    return sorunlar, bilgi
