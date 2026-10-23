"""Yonetici modu: bulgulardan yapilandirilmis degisiklik plani, onizleme (diff) ve guvenli uygulama.

Her degisiklik bir sozluktur:
  id, kategori (kural|yz), risk (dusuk|yuksek), bulgu (sorun kodu), url, dosya, konum (satir/sutun),
  eski, yeni (okunur ozet), gerekce, kaynaklar (RAG), etki (yuksek riskte), uretici (kural|sezgisel|model),
  parcalar ([{bas, son, eski, yeni}] — dosya metnindeki tam konumlar), duzenleme (duzenlenebilir
  degerlerde yeniden kurma bilgisi), yer_tutucu, dogrulama ({gecti, neden}), durum.
Plan asamasinda siteye hicbir sey yazilmaz. Uygulama yalnizca onaylanan degisiklikleri, plan
sirasindaki dosya hash'i degismemisse ve degisiklik HTML/XML/JSON-LD gecerliligini bozmuyorsa yazar.
"""
import difflib
import html
import json
import re
import struct
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import requests

from . import html_konum as hk
from . import kategoriler as kat
from .cikarma import extract, url_anahtari
from .kurallar import hreflang_gecerli_mi
from .yazma import YolGuvenligiHatasi, ozet_hash
from .yz_oneri import PARAGRAF_GOREVI, YZHatasi, dogrula_jsonld, dogrula_metin, jsonld_gorevi, metin_gorevi

KULLANICI_AJANI = "SEO-Denetim-Yonetici/1.0"
TARAMA_GENELI = ("title_tekrar", "meta_tekrar", "h1_tekrar", "icerik_tekrar", "icerik_benzer", "yetim_sayfa",
                 "derin_sayfa", "hreflang_donus_yok")
# ayni sayfada uretim sirasi: once karakter kodlamasi/viewport (head basina eklenir), sonra digerleri
ONCELIK = ["charset_yok", "viewport_yok", "viewport_sorunlu", "html_lang_yok", "title", "meta", "h1"]


class Atla(Exception):
    """Bu bulgu icin otomatik oneri uretilemedi; neden raporlanir."""


# ------------------------------------------------------------------ adres <-> dosya
def _goreli(url, temel_url):
    p, t = urlsplit(url), urlsplit(temel_url)
    if p.scheme not in ("http", "https") or p.netloc.lower() != t.netloc.lower():
        return None
    taban = (t.path or "/").rstrip("/")
    yol = unquote(p.path or "/")
    if yol != taban and not yol.startswith(taban + "/"):
        return None
    return yol[len(taban):].lstrip("/")


def dosya_yolu(url, temel_url, dosyalar):
    """Adresin site kokundeki dosyasi (harf duyarli). Dosyaya karsilik gelmeyen adres icin None."""
    goreli = _goreli(url, temel_url)
    if goreli is None:
        return None
    adaylar = [goreli + "index.html"] if goreli == "" or goreli.endswith("/") else \
        [goreli, goreli + ".html", goreli + "/index.html"]
    return next((a for a in adaylar if a in dosyalar), None)


def dosyadan_url(dosya, temel_url):
    taban = temel_url.rstrip("/") + "/"
    if dosya == "index.html":
        return taban
    if dosya.endswith("/index.html"):
        return taban + dosya[:-len("index.html")]
    return taban + dosya


# ------------------------------------------------------------------ gorsel boyutu
def gorsel_boyutu(veri, ad=""):
    """(genislik, yukseklik) ya da None. PNG, GIF, JPEG, WebP ve SVG desteklenir."""
    try:
        if veri[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", veri[16:24])
        if veri[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", veri[6:10])
        if veri[:2] == b"\xff\xd8":
            i = 2
            while i < len(veri) - 9:
                if veri[i] != 0xFF:
                    i += 1
                    continue
                isaret = veri[i + 1]
                if isaret in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    y, g = struct.unpack(">HH", veri[i + 5:i + 9])
                    return g, y
                i += 2 + struct.unpack(">H", veri[i + 2:i + 4])[0]
        if veri[:4] == b"RIFF" and veri[8:12] == b"WEBP":
            if veri[12:16] == b"VP8X":
                return 1 + int.from_bytes(veri[24:27], "little"), 1 + int.from_bytes(veri[27:30], "little")
            if veri[12:16] == b"VP8 ":
                g, y = struct.unpack("<HH", veri[26:30])
                return g & 0x3FFF, y & 0x3FFF
        if ad.lower().endswith(".svg") or veri.lstrip()[:4] in (b"<svg", b"<?xm"):
            bas = veri[:2000].decode("utf-8", "replace")
            g = re.search(r'<svg[^>]*\swidth="(\d+(?:\.\d+)?)(?:px)?"', bas)
            y = re.search(r'<svg[^>]*\sheight="(\d+(?:\.\d+)?)(?:px)?"', bas)
            if g and y:
                return round(float(g.group(1))), round(float(y.group(1)))
            vb = re.search(r'viewBox="[\d.\s-]+?\s([\d.]+)\s([\d.]+)"', bas)
            if vb:
                return round(float(vb.group(1))), round(float(vb.group(2)))
    except (struct.error, ValueError, IndexError):
        return None
    return None


# ------------------------------------------------------------------ plan baglami
class Sayfa:
    def __init__(self, dosya, metin, url, kayit):
        self.dosya, self.metin, self.url, self.kayit = dosya, metin, url, kayit or {}
        self.ogeler = hk.tara(metin)
        self.d = extract(metin)
        html_ogesi = hk.ilk(self.ogeler, "html")
        self.dil = ((html_ogesi.nitelik("lang") if html_ogesi else None) or "").strip()

    def head(self):
        return hk.ilk(self.ogeler, "head")

    def main(self):
        return hk.ilk(self.ogeler, "main")


class Plan:
    def __init__(self, adaptor, temel_url, dil="tr", yz=None, gunluk=None, oturum=None):
        self.adaptor, self.temel_url, self.dil, self.yz = adaptor, temel_url.rstrip("/") + "/", dil, yz
        self.yaz = gunluk or (lambda m: None)
        self.dosyalar = set(adaptor.listele())
        self.metinler, self.sayfalar = {}, {}
        self.degisiklikler, self.elle, self.atlanan, self.ek_bulgular = [], [], [], []
        self.kaynak_metinleri = {}
        self.oturum = oturum or requests.Session()
        self.oturum.headers["User-Agent"] = KULLANICI_AJANI
        self._durum_onbellek = {}
        self.gorulen = set()

    # --- dosyalar
    def metin(self, dosya):
        if dosya not in self.metinler:
            self.metinler[dosya] = self.adaptor.oku(dosya).decode("utf-8")
        return self.metinler[dosya]

    def sayfa(self, dosya, url=None, kayit=None):
        if dosya not in self.sayfalar:
            self.sayfalar[dosya] = Sayfa(dosya, self.metin(dosya), url or dosyadan_url(dosya, self.temel_url), kayit)
        return self.sayfalar[dosya]

    def url_dosya(self, url):
        return dosya_yolu(url, self.temel_url, self.dosyalar)

    def durum_kodu(self, url):
        if url not in self._durum_onbellek:
            try:
                r = self.oturum.get(url, timeout=10, allow_redirects=True)
                self._durum_onbellek[url] = (r.status_code, r.url)
            except requests.RequestException:
                self._durum_onbellek[url] = (None, url)
        return self._durum_onbellek[url]

    # --- degisiklik kaydi
    def ekle(self, bulgu, dosya, parcalar, eski, yeni, gerekce, uretici, url=None, kategori=None, risk=None,
             duzenleme=None, kaynaklar=(), yer_tutucu=False, dogrulama=None, etki=None):
        metin = self.metin(dosya)
        parcalar = sorted(parcalar, key=lambda p: p[0])
        satir, sutun = hk.satir_sutun(metin, parcalar[0][0])
        kategori = kategori or kat.kategori(bulgu)
        risk = risk or kat.risk(bulgu)
        d = {"id": "D%03d" % (len(self.degisiklikler) + 1), "kategori": kategori, "risk": risk, "bulgu": bulgu,
             "bulgu_aciklamasi": kat.aciklama(bulgu), "url": url or dosyadan_url(dosya, self.temel_url),
             "dosya": dosya, "konum": {"satir": satir, "sutun": sutun}, "eski": eski, "yeni": yeni,
             "gerekce": gerekce, "kaynaklar": list(kaynaklar), "uretici": uretici,
             "etki": etki if etki is not None else (kat.ETKI.get(bulgu, "") if risk == "yuksek" else ""),
             "onay_turu": "toplu" if kategori == "kural" else "tekil",
             "parcalar": [{"bas": b, "son": s, "eski": metin[b:s], "yeni": y} for b, s, y in parcalar],
             "duzenleme": duzenleme, "yer_tutucu": bool(yer_tutucu),
             "dogrulama": dogrulama or {"gecti": True, "neden": ""}}
        d["durum"] = "oneriliyor" if d["dogrulama"]["gecti"] else "gecersiz"
        self.degisiklikler.append(d)
        return d

    def atla(self, bulgu, url, neden, kategori=None):
        anahtar = (bulgu, url, neden)
        if anahtar not in self.gorulen:
            self.gorulen.add(anahtar)
            self.atlanan.append({"bulgu": bulgu, "bulgu_aciklamasi": kat.aciklama(bulgu), "url": url,
                                 "kategori": kategori or kat.kategori(bulgu), "neden": neden})


# ------------------------------------------------------------------ yardimcilar
def _kacis(metin, nitelik=False):
    return html.escape(metin, quote=nitelik)


def _head_basi(s):
    """Yeni meta etiketlerinin eklenecegi yer: <head> acilis etiketinin hemen sonu."""
    h = s.head()
    if h is None:
        raise Atla("sayfada <head> yok")
    return h.bas_son


def _head_sonu(s):
    h = s.head()
    if h is None or h.kap_bas is None:
        raise Atla("sayfada kapanan bir <head> yok")
    return h.kap_bas


def _main_sonu(s):
    m = s.main()
    if m is None or m.kap_bas is None:
        raise Atla("sayfada <main> bölümü yok")
    return m.kap_bas


def _girinti_once(metin, konum):
    """Satir sonuna ekleme yapilacaksa yeni satir ile baslat."""
    return "\n" if konum > 0 and metin[konum - 1] != "\n" else ""


def _bag_hedefi(s, href):
    return urljoin(s.url, html.unescape(href or ""))


def _kanoniklar(s):
    return hk.bul(s.ogeler, "link", lambda o: "canonical" in (o.nitelik("rel") or "").lower().split())


def _href_bicimi(eski_href, yeni_url):
    """Yeni adresi eski bagla ayni bicimde yazar (koke gore ya da tam adres)."""
    p = urlsplit(yeni_url)
    if eski_href.startswith(("http://", "https://")):
        return yeni_url
    return p.path + ("?" + p.query if p.query else "")


def _sayfa_metni(s, sinir=1500):
    return " ".join(filter(None, [s.d.get("title"), s.d.get("meta_description"), " ".join(s.d.get("h1") or []),
                                  (s.d.get("icerik_ozeti") or s.d.get("text_sample") or "")[:sinir]]))


def _sayfa_verisi(p, s, ek=None):
    veri = {"site_adi": s.d.get("site_adi"), "adres": s.url, "title": s.d.get("title"),
            "meta_description": s.d.get("meta_description"), "h1": s.d.get("h1"), "h2": (s.d.get("h2") or [])[:8],
            "icerik_ozeti": (s.d.get("icerik_ozeti") or s.d.get("text_sample") or "")[:1200]}
    veri.update(ek or {})
    return veri


def _ilgili_sayfalar(p, s, n=3):
    """Ince icerigi genisletirken kullanilacak, sitede konusu en yakin sayfalarin ozetleri."""
    kendi = set(s.d.get("kelime_kokleri") or ())
    adaylar = []
    for dosya in sorted(p.dosyalar):
        if not dosya.endswith(".html") or dosya == s.dosya:
            continue
        try:
            diger = p.sayfa(dosya)
        except (UnicodeDecodeError, YolGuvenligiHatasi):
            continue
        ortak = len(kendi & set(diger.d.get("kelime_kokleri") or ()))
        if (diger.d.get("icerik_kelime_sayisi") or 0) >= 100:
            adaylar.append((ortak, dosya, diger))
    adaylar.sort(key=lambda x: (-x[0], x[1]))
    return [{"adres": d.url, "baslik": d.d.get("title"), "ozet": (d.d.get("icerik_ozeti") or "")[:700]}
            for _, _, d in adaylar[:n]]


# ------------------------------------------------------------------ Kural çözer
def kural_charset(p, s, b):
    if re.search(r"<meta[^>]+charset=", s.metin, re.I):
        raise Atla("sayfada zaten charset bildirimi var")
    konum = _head_basi(s)
    p.ekle("charset_yok", s.dosya, [(konum, konum, '\n<meta charset="utf-8">')], "(yok)", '<meta charset="utf-8">',
           "Karakter kodlaması bildirimi <head>'in başında olmalı; sunucu başlığı değişse de Türkçe karakterler "
           "doğru görünür.", "kural", url=s.url)


def kural_viewport(p, s, b):
    if b["sorun"] == "viewport_sorunlu":
        v = hk.ilk(s.ogeler, "meta", lambda o: (o.nitelik("name") or "").lower() == "viewport")
        if v is None:
            raise Atla("viewport etiketi bulunamadı")
        n = hk.nitelik_konumlari(v).get("content")
        if not n:
            raise Atla("viewport etiketinde content yok")
        yeni = "width=device-width, initial-scale=1"
        p.ekle("viewport_sorunlu", s.dosya, [(n[2], n[3], yeni)], n[4], yeni,
               "Yakınlaştırmayı engelleyen ya da sabit genişlik veren viewport ayarı standart değere çevrildi.",
               "kural", url=s.url)
        return
    if re.search(r'<meta[^>]+name=["\']viewport', s.metin, re.I):
        raise Atla("sayfada zaten viewport var")
    charset = hk.ilk(s.ogeler, "meta", lambda o: o.nitelik("charset") is not None)
    konum = charset.bas_son if charset is not None else _head_basi(s)     # charset bildirimi ilk kalir
    etiket = '<meta name="viewport" content="width=device-width, initial-scale=1">'
    p.ekle("viewport_yok", s.dosya, [(konum, konum, "\n" + etiket)], "(yok)", etiket,
           "Mobil cihazlarda sayfanın ekran genişliğine uyması için viewport gerekir.", "kural", url=s.url)


def kural_lang(p, s, b):
    h = hk.ilk(s.ogeler, "html")
    if h is None:
        raise Atla("sayfada <html> etiketi yok")
    if h.nitelik("lang"):
        raise Atla("lang zaten var")
    konum = hk.nitelik_ekleme_konumu(h)
    p.ekle("html_lang_yok", s.dosya, [(konum, konum, f' lang="{p.dil}"')], h.ham, h.ham[:-1] + f' lang="{p.dil}">',
           "Sayfanın dili arama motorlarına ve ekran okuyuculara bildirilir.", "kural", url=s.url)


def kural_h1(p, s, b):
    h1ler = [o for o in hk.bul(s.ogeler, "h1") if re.sub(r"<[^>]+>", "", hk.ic_metin(s.metin, o)).strip()]
    if len(h1ler) < 2:
        raise Atla("birden fazla metinli H1 bulunamadı")
    parcalar = [(a, z, "h2") for o in h1ler[1:] for a, z in hk.etiket_adi_konumlari(o)]
    eski = " | ".join(s.metin[o.bas:o.kap_son] for o in h1ler[1:])
    p.ekle("h1_birden_fazla", s.dosya, parcalar, eski, eski.replace("<h1", "<h2").replace("</h1", "</h2"),
           "İlk H1 korunur, sonraki ana başlıklar H2 yapılır; görünür metin değişmez.", "kural", url=s.url)


def _baglar_hedefe(p, s, hedef_url):
    return [o for o in hk.bul(s.ogeler, "a", lambda o: o.nitelik("href"))
            if url_anahtari(_bag_hedefi(s, o.nitelik("href"))) == url_anahtari(hedef_url)]


def kural_kirik_link(p, s, b):
    kiriklar = (s.kayit.get("baglanti_denetimi") or {}).get("kirik_ic") or []
    if not kiriklar:
        raise Atla("kırık bağlantı ayrıntısı yok")
    site_adresleri = {urlsplit(dosyadan_url(f, p.temel_url)).path.lower(): dosyadan_url(f, p.temel_url)
                      for f in p.dosyalar if f.endswith(".html")}
    for kirik in kiriklar:
        baglar = _baglar_hedefe(p, s, kirik)
        if not baglar:
            p.atla("kirik_ic_link", s.url, "kırık adrese giden bağlantı dosyada bulunamadı: " + kirik)
            continue
        dogru = site_adresleri.get(urlsplit(kirik).path.lower())
        for o in baglar:
            n = hk.nitelik_konumlari(o)["href"]
            if dogru and url_anahtari(dogru) != url_anahtari(kirik):
                yeni = _href_bicimi(n[4], dogru)
                p.ekle("kirik_ic_link", s.dosya, [(n[2], n[3], yeni)], n[4], yeni,
                       f"{n[4]} 404 veriyor; sitede yalnızca harf farkıyla eşleşen {urlsplit(dogru).path} sayfası var.",
                       "kural", url=s.url)
            elif o.kap_bas is not None:
                metin = re.sub(r"<[^>]+>", "", hk.ic_metin(s.metin, o)).strip()
                p.ekle("kirik_ic_link", s.dosya, [(o.bas, o.bas_son, ""), (o.kap_bas, o.kap_son, "")],
                       s.metin[o.bas:o.kap_son], metin,
                       f"{n[4]} 404 veriyor ve sitede karşılığı olan bir sayfa yok; bağlantı kaldırıldı, metin korundu.",
                       "kural", url=s.url)


def kural_link_yonlendirme(p, s, b):
    adresler = (s.kayit.get("baglanti_denetimi") or {}).get("yonlendirilen_ic") or []
    if not adresler:
        raise Atla("yönlendirilen bağlantı ayrıntısı yok")
    for adres in adresler:
        kod, son = p.durum_kodu(adres)
        if kod != 200 or url_anahtari(son) == url_anahtari(adres):
            p.atla("ic_link_yonlendirme", s.url, f"yönlendirmenin son adresi doğrulanamadı: {adres}")
            continue
        for o in _baglar_hedefe(p, s, adres):
            n = hk.nitelik_konumlari(o)["href"]
            yeni = _href_bicimi(n[4], son)
            p.ekle("ic_link_yonlendirme", s.dosya, [(n[2], n[3], yeni)], n[4], yeni,
                   f"{n[4]} yönlendirmeden geçerek {urlsplit(son).path} adresine gidiyor; bağlantı doğrudan son adrese verildi.",
                   "kural", url=s.url)


def _gorseller(s):
    return [o for o in hk.bul(s.ogeler, "img") if o.nitelik("src") and not o.nitelik("src").startswith("data:")]


def kural_gorsel_boyut(p, s, b):
    eklenen = 0
    for o in _gorseller(s):
        if o.nitelik("width") is not None and o.nitelik("height") is not None:
            continue
        dosya = p.url_dosya(urljoin(s.url, o.nitelik("src")))
        boyut = gorsel_boyutu(p.adaptor.oku(dosya), dosya) if dosya else None
        if not boyut:
            p.atla("gorsel_boyut_yok", s.url, "görsel boyutu okunamadı: " + o.nitelik("src"))
            continue
        ek = (f' width="{boyut[0]}"' if o.nitelik("width") is None else "") + \
             (f' height="{boyut[1]}"' if o.nitelik("height") is None else "")
        konum = hk.nitelik_ekleme_konumu(o)
        p.ekle("gorsel_boyut_yok", s.dosya, [(konum, konum, ek)], o.ham, o.ham[:konum - o.bas] + ek + o.ham[konum - o.bas:],
               f"Görselin gerçek boyutu ({boyut[0]}×{boyut[1]}) dosyasından okundu; tarayıcı yer ayırır, düzen kaymaz.",
               "kural", url=s.url)
        eklenen += 1
    if not eklenen:
        raise Atla("boyutu eklenecek görsel bulunamadı")


def kural_lazy(p, s, b):
    g = _gorseller(s)
    if b["sorun"] == "ilk_gorsel_lazy":
        if not g or (g[0].nitelik("loading") or "").lower() != "lazy":
            raise Atla("ilk görsel tembel yüklenmiyor")
        n = hk.nitelik_konumlari(g[0])["loading"]
        p.ekle("ilk_gorsel_lazy", s.dosya, [(n[0], n[1], "")], g[0].ham, g[0].ham.replace(s.metin[n[0]:n[1]], ""),
               "İlk ekrandaki ana görsel tembel yüklenirse LCP gecikir.", "kural", url=s.url)
        return
    for o in g[3:]:
        if o.nitelik("loading") is None:
            konum = hk.nitelik_ekleme_konumu(o)
            p.ekle("gorsel_lazy_yok", s.dosya, [(konum, konum, ' loading="lazy"')], o.ham,
                   o.ham[:konum - o.bas] + ' loading="lazy"' + o.ham[konum - o.bas:],
                   "İlk ekran dışındaki görsel kaydırılınca yüklenir.", "kural", url=s.url)


def _head_ekle(p, s, bulgu, etiketler, gerekce, uretici="kural", **k):
    konum = _head_sonu(s)
    eklenti = _girinti_once(s.metin, konum) + "\n".join(etiketler) + "\n"
    return p.ekle(bulgu, s.dosya, [(konum, konum, eklenti)], "(yok)", "\n".join(etiketler), gerekce, uretici,
                  url=s.url, **k)


def kural_og(p, s, b):
    if b["sorun"] == "twitter_card_yok":
        _head_ekle(p, s, "twitter_card_yok", ['<meta name="twitter:card" content="summary">'],
                   "Paylaşımlarda özet kartı gösterilir.")
        return
    etiketler = []
    if b["sorun"] == "og_etiketleri_yok":
        if s.d.get("title"):
            etiketler.append(f'<meta property="og:title" content="{_kacis(s.d["title"], True)}">')
        if s.d.get("meta_description"):
            etiketler.append(f'<meta property="og:description" content="{_kacis(s.d["meta_description"], True)}">')
        etiketler.append(f'<meta property="og:url" content="{_kacis(s.url, True)}">')
    gorsel = next((urljoin(s.url, o.nitelik("src")) for o in _gorseller(s)
                   if not o.nitelik("src").lower().endswith((".svg", ".ico", ".gif"))), None)
    if gorsel:
        etiketler.append(f'<meta property="og:image" content="{_kacis(gorsel, True)}">')
    elif b["sorun"] == "og_gorsel_yok":
        raise Atla("sayfada paylaşım görseli olabilecek bir raster görsel yok")
    _head_ekle(p, s, b["sorun"], etiketler, "Open Graph değerleri sayfanın mevcut title, meta ve görselinden türetildi.")


def kural_canonical_goreli(p, s, b):
    k = next(iter(_kanoniklar(s)), None)
    if k is None:
        raise Atla("canonical bulunamadı")
    n = hk.nitelik_konumlari(k)["href"]
    yeni = urljoin(s.url, n[4])
    p.ekle("canonical_goreli", s.dosya, [(n[2], n[3], yeni)], n[4], yeni, "Göreli canonical tam adrese çevrildi.",
           "kural", url=s.url)


def kural_ic_nofollow(p, s, b):
    for o in hk.bul(s.ogeler, "a", lambda o: "nofollow" in (o.nitelik("rel") or "").lower().split()):
        hedef = _bag_hedefi(s, o.nitelik("href"))
        if _goreli(hedef, p.temel_url) is None:
            continue
        n = hk.nitelik_konumlari(o)["rel"]
        kalan = " ".join(t for t in n[4].split() if t.lower() != "nofollow")
        parca = (n[2], n[3], kalan) if kalan else (n[0], n[1], "")
        p.ekle("ic_nofollow", s.dosya, [parca], s.metin[n[0]:n[1]], kalan or "(rel kaldırıldı)",
               "Site içi bağlantıda nofollow sayfalar arası değer aktarımını keser.", "kural", url=s.url)


def kural_bos_baslik(p, s, b):
    for o in [x for x in s.ogeler if x.etiket in ("h2", "h3", "h4", "h5", "h6")]:
        if o.kap_bas is not None and not re.sub(r"<[^>]+>", "", hk.ic_metin(s.metin, o)).strip():
            p.ekle("bos_baslik", s.dosya, [(o.bas, o.kap_son, "")], s.metin[o.bas:o.kap_son], "(kaldırıldı)",
                   "Metni olmayan başlık etiketi belge yapısını bozar.", "kural", url=s.url)


# --- robots.txt ve sitemap.xml
def _satir_araligi(metin, bas, son):
    """[bas, son) araligini iceren satirlarin tamami (sondaki satir sonu dahil)."""
    a = metin.rfind("\n", 0, bas) + 1
    z = metin.find("\n", son)
    return a, (len(metin) if z == -1 else z + 1)


def kural_robots_sitemap(p, b, robots):
    metin = p.metin(robots)
    for m in re.finditer(r"(?im)^sitemap:\s*(\S+)\s*$", metin):
        adres = urljoin(p.temel_url, m.group(1))
        kod, _ = p.durum_kodu(adres)
        if kod is not None and kod < 400:
            continue
        a, z = _satir_araligi(metin, m.start(), m.end())
        p.ekle("sitemap_hatali_adres", robots, [(a, z, "")], metin[a:z].rstrip("\n"), "(satır kaldırıldı)",
               f"robots.txt'deki {m.group(1)} adresi {kod or 'erişilemez'} döndürüyor; diğer Sitemap satırları korunur.",
               "kural", url=urljoin(p.temel_url, "robots.txt"))


def kural_robots_bildir(p, b, robots):
    if "sitemap.xml" not in p.dosyalar:
        raise Atla("sitede sitemap.xml yok")
    metin = p.metin(robots)
    satir = "Sitemap: " + p.temel_url + "sitemap.xml"
    p.ekle("robots_sitemap_bildirilmemis", robots, [(len(metin), len(metin), _girinti_once(metin, len(metin)) + satir + "\n")],
           "(yok)", satir, "Sitemap'in yeri robots.txt'de bildirilir.", "kural", url=urljoin(p.temel_url, "robots.txt"))


def _sitemap_kayitlari(metin):
    return [(m.start(), m.end(), html.unescape(m.group(1).strip()))
            for m in re.finditer(r"<url>\s*<loc>(.*?)</loc>.*?</url>", metin, re.S)]


def kural_sitemap_ekle(p, url, kayit):
    if "sitemap.xml" not in p.dosyalar:
        raise Atla("sitede sitemap.xml yok")
    if urlsplit(url).query:
        raise Atla("parametreli adres sitemap'e eklenmez")
    dosya = p.url_dosya(url)
    if not dosya:
        raise Atla("adres sitede bir dosyaya karşılık gelmiyor (sunucu tarafında üretiliyor)")
    if (kayit.get("durum_kodu") or 200) >= 300 or kayit.get("hata_sayfasi"):
        raise Atla("sayfa başarılı (200) yanıt vermiyor")
    s = p.sayfa(dosya, url, kayit)
    if re.search(r'name=["\']robots["\'][^>]*noindex', s.metin, re.I):
        raise Atla("sayfa noindex; sitemap'e eklenmez")
    kanonik = next(iter(_kanoniklar(s)), None)
    if kanonik and url_anahtari(urljoin(url, kanonik.nitelik("href") or "")) != url_anahtari(url):
        raise Atla("sayfanın canonical'ı başka bir adresi gösteriyor")
    metin = p.metin("sitemap.xml")
    konum = metin.find("</urlset>")
    if konum == -1:
        raise Atla("sitemap.xml'de </urlset> bulunamadı")
    satir = f"  <url><loc>{_kacis(url)}</loc></url>"
    p.ekle("sayfa_sitemapte_yok", "sitemap.xml", [(konum, konum, satir + "\n")], "(yok)", satir,
           "Sayfa 200 dönüyor, noindex değil ve canonical'ı kendisini gösteriyor; sitemap'e eklendi.", "kural", url=url)


def kural_sitemap_cikar(p, url, kod):
    if "sitemap.xml" not in p.dosyalar:
        raise Atla("sitede sitemap.xml yok")
    metin = p.metin("sitemap.xml")
    for bas, son, loc in _sitemap_kayitlari(metin):
        if url_anahtari(loc) == url_anahtari(url):
            a, z = _satir_araligi(metin, bas, son)
            p.ekle("sitemap_olu_adres", "sitemap.xml", [(a, z, "")], metin[a:z].rstrip("\n"), "(kayıt kaldırıldı)",
                   f"Adres {kod} durum kodu döndürüyor; sitemap'te yalnızca erişilebilir sayfalar listelenmeli.",
                   "kural", url=url)
            return
    raise Atla("adres sitemap.xml'de bulunamadı")


# ------------------------------------------------------------------ YZ önerir: sezgisel (yapisal kararlar)
def yz_canonical(p, s, b, hedef=None, gerekce=None):
    kendi = dosyadan_url(s.dosya, p.temel_url)
    hedef = hedef or kendi
    kanoniklar = _kanoniklar(s)
    if not kanoniklar:
        etiket = f'<link rel="canonical" href="{_kacis(hedef, True)}">'
        _head_ekle(p, s, b["sorun"], [etiket], gerekce or "Sayfaya parametresiz, kendi adresini gösteren canonical eklendi.",
                   uretici="sezgisel", duzenleme=None)
        return
    if b["sorun"] == "canonical_coklu" and len(kanoniklar) > 1:
        parcalar = [(o.bas, o.bas_son, "") for o in kanoniklar[1:]]
        p.ekle(b["sorun"], s.dosya, parcalar, " | ".join(o.ham for o in kanoniklar[1:]), "(fazla canonical'lar kaldırıldı)",
               "İlk canonical korunur, diğerleri kaldırılır.", "sezgisel", url=s.url)
        return
    n = hk.nitelik_konumlari(kanoniklar[0]).get("href")
    if n is None:
        raise Atla("canonical etiketinde href yok")
    if url_anahtari(urljoin(s.url, n[4])) == url_anahtari(hedef):
        raise Atla("canonical zaten önerilen adresi gösteriyor")
    if gerekce is None:
        kod, _ = p.durum_kodu(urljoin(s.url, n[4])) if n[4] else (None, None)
        gerekce = (f"Canonical {n[4] or '(boş)'} adresini gösteriyor" +
                   (f" ve bu adres {kod} döndürüyor" if kod and kod >= 400 else "") +
                   "; sayfanın kendi özgün içeriği olduğu için canonical sayfanın kendi adresine çevrildi.")
    p.ekle(b["sorun"], s.dosya, [(n[2], n[3], hedef)], n[4] or "(boş)", hedef, gerekce, "sezgisel", url=s.url)


def _robots_meta(s):
    return [o for o in hk.bul(s.ogeler, "meta", lambda o: (o.nitelik("name") or "").lower() in ("robots", "googlebot"))]


def yz_robots_meta(p, s, b):
    hedef_token = "noindex" if b["sorun"] == "noindex" else "nofollow"
    yenisi = "index" if hedef_token == "noindex" else "follow"
    for o in _robots_meta(s):
        n = hk.nitelik_konumlari(o).get("content")
        if not n:
            continue
        tokenler = [t.strip() for t in n[4].split(",") if t.strip()]
        if not any(t.lower() in (hedef_token, "none") for t in tokenler):
            continue
        yeni_t = []
        for t in tokenler:
            if t.lower() == hedef_token:
                yeni_t.append(yenisi)
            elif t.lower() == "none":
                yeni_t.append("nofollow" if hedef_token == "noindex" else "noindex")
            else:
                yeni_t.append(t)
        yeni = ", ".join(yeni_t)
        p.ekle(b["sorun"], s.dosya, [(n[2], n[3], yeni)], n[4], yeni,
               f"meta robots '{n[4]}' içeriyor; sayfa içerik olarak indekslenmesi beklenen bir sayfa "
               f"(sitemap'te ve site içinden bağlantılı). '{hedef_token}' yönergesi kaldırıldı.", "sezgisel", url=s.url)
        return
    raise Atla(hedef_token + " meta etiketinde değil (X-Robots-Tag sunucu başlığı olabilir; elle)")


def yz_meta_refresh(p, s, b):
    o = hk.ilk(s.ogeler, "meta", lambda o: (o.nitelik("http-equiv") or "").lower() == "refresh")
    if o is None:
        raise Atla("meta refresh HTML'de değil (Refresh sunucu başlığı olabilir; elle)")
    p.ekle("meta_refresh", s.dosya, [(o.bas, o.bas_son, "")], o.ham, "(kaldırıldı)",
           "Meta refresh kaldırılır; kalıcı taşıma gerekiyorsa sunucuda 301 tanımlanmalıdır.", "sezgisel", url=s.url)


def _hreflanglar(s):
    return hk.bul(s.ogeler, "link", lambda o: "alternate" in (o.nitelik("rel") or "").lower().split()
                  and o.nitelik("hreflang") is not None)


def yz_hreflang(p, s, b):
    kod = b["sorun"]
    linkler = _hreflanglar(s)
    kendi = dosyadan_url(s.dosya, p.temel_url)
    if kod == "hreflang_gecersiz":
        for o in linkler:
            deger = o.nitelik("hreflang")
            if hreflang_gecerli_mi(deger):
                continue
            parcalar = deger.split("-")
            yeni = (parcalar[0].lower() + "-GB") if len(parcalar) == 2 and parcalar[1].upper() == "UK" else parcalar[0].lower()
            if not hreflang_gecerli_mi(yeni):
                p.atla(kod, s.url, "geçerli bir karşılık önerilemedi: " + deger)
                continue
            n = hk.nitelik_konumlari(o)["hreflang"]
            p.ekle(kod, s.dosya, [(n[2], n[3], yeni)], deger, yeni,
                   f"'{deger}' geçerli bir ISO dil-bölge kodu değil; doğru yazım '{yeni}'.", "sezgisel", url=s.url)
        return
    dil = s.dil or p.dil
    if kod == "hreflang_kendine_referans_yok":
        etiket = f'<link rel="alternate" hreflang="{_kacis(dil, True)}" href="{_kacis(kendi, True)}">'
        _head_ekle(p, s, kod, [etiket], f"hreflang kümesine sayfanın kendisi ({dil}) eklendi.", uretici="sezgisel")
        return
    if kod == "hreflang_x_default_yok":
        varsayilan = next((o.nitelik("href") for o in linkler if (o.nitelik("hreflang") or "").lower().startswith(p.dil)), None)
        if dil.lower().startswith(p.dil):
            varsayilan = kendi
        varsayilan = urljoin(s.url, varsayilan) if varsayilan else p.temel_url
        etiket = f'<link rel="alternate" hreflang="x-default" href="{_kacis(varsayilan, True)}">'
        _head_ekle(p, s, kod, [etiket], f"Dili eşleşmeyen kullanıcılar için x-default olarak {varsayilan} gösterildi "
                                        f"(sitenin varsayılan dili: {p.dil}).", uretici="sezgisel")


def yz_hreflang_donus(p, kayit, kayitlar_url):
    """A sayfasi B'yi hreflang ile gosteriyor ama B A'yi gostermiyor: B'ye A icin donus baglantisi eklenir."""
    a_url = kayit.get("site_url") or kayit.get("ad")
    a_dosya = p.url_dosya(a_url)
    if not a_dosya:
        raise Atla("sayfa sitede bir dosyaya karşılık gelmiyor")
    a = p.sayfa(a_dosya, a_url, kayit)
    a_dil = a.dil or p.dil
    for h in kayit.get("hreflang_baglantilari") or []:
        b_url = urljoin(a_url, h.get("href") or "")
        if url_anahtari(b_url) == url_anahtari(a_url):
            continue
        b_dosya = p.url_dosya(b_url)
        if not b_dosya:
            continue
        b = p.sayfa(b_dosya, b_url, kayitlar_url.get(url_anahtari(b_url)))
        if any(url_anahtari(urljoin(b_url, o.nitelik("href") or "")) == url_anahtari(a_url) for o in _hreflanglar(b)):
            continue
        etiket = f'<link rel="alternate" hreflang="{_kacis(a_dil, True)}" href="{_kacis(dosyadan_url(a_dosya, p.temel_url), True)}">'
        _head_ekle(p, b, "hreflang_donus_yok", [etiket],
                   f"{a_url} bu sayfayı hreflang ile gösteriyor; karşılıklılık için bu sayfaya {a_dil} sürümüne dönüş "
                   "bağlantısı eklendi.", uretici="sezgisel")


def yz_baglanti_ekle(p, hedef_url, kaynak_dosya, bulgu, gerekce, onek):
    hedef_dosya = p.url_dosya(hedef_url)
    if not hedef_dosya:
        raise Atla("adres sitede bir dosyaya karşılık gelmiyor")
    h = p.sayfa(hedef_dosya, hedef_url)
    metin = (h.d.get("h1") or [None])[0] or (h.d.get("title") or "").split("|")[0].strip()
    if not metin:
        raise Atla("hedef sayfanın başlığı yok; bağlantı metni üretilemedi")
    k = p.sayfa(kaynak_dosya)
    if _baglar_hedefe(p, k, hedef_url):
        raise Atla("kaynak sayfa zaten bu sayfaya bağlantı veriyor")
    konum = _main_sonu(k)
    yol = urlsplit(dosyadan_url(hedef_dosya, p.temel_url)).path
    parca = f'<p>{onek} <a href="{_kacis(yol, True)}">{_kacis(metin)}</a></p>'
    p.ekle(bulgu, kaynak_dosya, [(konum, konum, parca + "\n")], "(yok)", parca, gerekce, "sezgisel", url=hedef_url,
           duzenleme={"parca": 0, "onek": f'<p>{onek} <a href="{_kacis(yol, True)}">', "sonek": "</a></p>\n",
                      "kacis": "html", "alan": "baglanti_metni", "deger": metin})


def _hub_dosyasi(p, url):
    """Yetim sayfa icin bag verecek sayfa: ust klasorun dizin sayfasi, yoksa ana sayfa."""
    goreli = _goreli(url, p.temel_url) or ""
    parcalar = goreli.rstrip("/").split("/")[:-1]
    while parcalar:
        aday = "/".join(parcalar) + "/index.html"
        if aday in p.dosyalar:
            return aday
        parcalar.pop()
    return "index.html" if "index.html" in p.dosyalar else None


def _robots_engeli(p, url):
    """Robots nedeniyle atlanan sayfa icin robots.txt'deki tam eslesen Disallow satiri."""
    if "robots.txt" not in p.dosyalar:
        raise Atla("sitede robots.txt yok")
    metin = p.metin("robots.txt")
    yol = urlsplit(url).path
    for m in re.finditer(r"(?im)^disallow:\s*(\S+)\s*$", metin):
        if m.group(1) == yol:
            a, z = _satir_araligi(metin, m.start(), m.end())
            p.ekle("robots_sayfayi_engelliyor", "robots.txt", [(a, z, "")], metin[a:z].rstrip("\n"), "(satır kaldırıldı)",
                   f"{yol} sitemap'te listelenip site içinden bağlantı alırken robots.txt ile taramaya kapatılmış; "
                   "çelişki Disallow satırı kaldırılarak giderildi.", "sezgisel", url=url)
            return
    raise Atla("sayfayı engelleyen kural tek bir sayfaya ait değil (genel desen); elle gözden geçirin")


# ------------------------------------------------------------------ YZ önerir: model
def _model_yok(p):
    if p.yz is None:
        raise Atla("dil modeli seçilmedi; YZ önerisi üretilmedi")


def _kaynak_kaydet(p, anahtar, *metinler):
    p.kaynak_metinleri[anahtar] = " ".join(m for m in metinler if m)
    return anahtar


def _model_metni(p, s, alan, kodlar, gorev, ek_veri=None, kaynak_ek=""):
    _model_yok(p)
    try:
        cevap = p.yz.iste(gorev, s.d, kodlar, _sayfa_verisi(p, s, ek_veri), dil=s.dil or p.dil)
    except YZHatasi as e:
        raise Atla("model önerisi alınamadı: " + str(e))
    deger = cevap["deger"] if isinstance(cevap["deger"], str) else json.dumps(cevap["deger"], ensure_ascii=False)
    deger = deger.strip().strip('"').strip()
    kaynak = _kaynak_kaydet(p, f"{s.dosya}#{alan}", _sayfa_metni(s, 4000), kaynak_ek, cevap["kaynak_metni"])
    gecti, neden, yer = dogrula_metin(alan, deger, p.kaynak_metinleri[kaynak], s.dil or p.dil, s.d)
    return deger, cevap, kaynak, {"gecti": gecti, "neden": neden}, yer


def yz_title(p, s, kodlar, digerleri=()):
    ek = ("Başlık şu sayfaların başlıklarından açıkça farklı olmalı: " + "; ".join(digerleri)) if digerleri else ""
    deger, cevap, kaynak, dog, yer = _model_metni(p, s, "title", kodlar, metin_gorevi("title", ek))
    t = hk.ilk(s.ogeler, "title")
    if t is not None and t.kap_bas is not None and (s.head() is None or t.bas < s.head().kap_bas):
        parca, eski = (t.bas_son, t.kap_bas, _kacis(deger)), hk.ic_metin(s.metin, t)
        duz = {"parca": 0, "onek": "", "sonek": "", "kacis": "html"}
    else:
        konum = _head_basi(s)
        parca, eski = (konum, konum, "\n<title>" + _kacis(deger) + "</title>"), "(yok)"
        duz = {"parca": 0, "onek": "\n<title>", "sonek": "</title>", "kacis": "html"}
    duz.update({"alan": "title", "dogrulama": {"tur": "metin", "kaynak": kaynak, "dil": s.dil or p.dil}, "deger": deger})
    p.ekle(kodlar[0], s.dosya, [parca], eski, deger, cevap["gerekce"], "model", url=s.url, duzenleme=duz,
           kaynaklar=cevap["kaynaklar"], yer_tutucu=yer, dogrulama=dog)


def yz_meta(p, s, kodlar, digerleri=()):
    ek = ("Açıklama şu sayfaların açıklamalarından açıkça farklı olmalı: " + "; ".join(digerleri)) if digerleri else ""
    deger, cevap, kaynak, dog, yer = _model_metni(p, s, "meta_description", kodlar, metin_gorevi("meta_description", ek))
    m = hk.ilk(s.ogeler, "meta", lambda o: (o.nitelik("name") or "").lower() == "description")
    if m is not None and "content" in hk.nitelik_konumlari(m):
        n = hk.nitelik_konumlari(m)["content"]
        parca, eski = (n[2], n[3], _kacis(deger, True)), n[4]
        duz = {"parca": 0, "onek": "", "sonek": "", "kacis": "nitelik"}
    else:
        t = hk.ilk(s.ogeler, "title")
        konum = t.kap_son if t is not None and t.kap_son else _head_basi(s)
        parca, eski = (konum, konum, '\n<meta name="description" content="' + _kacis(deger, True) + '">'), "(yok)"
        duz = {"parca": 0, "onek": '\n<meta name="description" content="', "sonek": '">', "kacis": "nitelik"}
    duz.update({"alan": "meta_description", "dogrulama": {"tur": "metin", "kaynak": kaynak, "dil": s.dil or p.dil},
                "deger": deger})
    p.ekle(kodlar[0], s.dosya, [parca], eski, deger, cevap["gerekce"], "model", url=s.url, duzenleme=duz,
           kaynaklar=cevap["kaynaklar"], yer_tutucu=yer, dogrulama=dog)


def yz_h1(p, s, kodlar, digerleri=()):
    m = s.main()
    if "h1_yok" in kodlar and m is not None:
        # sayfa basligi baska bir etiketle (ornegin <p class="sayfa-basligi">) yazilmissa H1'e cevrilir
        aday = next((o for o in s.ogeler if o.bas > m.bas and o.ust is m and o.kap_bas is not None), None)
        if aday is not None and re.search(r"ba[sş]l[iı][kğg]|title|heading", aday.nitelik("class") or "", re.I):
            metin = re.sub(r"<[^>]+>", "", hk.ic_metin(s.metin, aday)).strip()
            if metin:
                parcalar = [(a, z, "h1") for a, z in hk.etiket_adi_konumlari(aday)]
                eski = s.metin[aday.bas:aday.kap_son]
                yeni = metne_uygula(eski, [(a - aday.bas, z - aday.bas, y) for a, z, y in parcalar])
                p.ekle("h1_yok", s.dosya, parcalar, eski, yeni,
                       f"Sayfanın görünen başlığı ('{metin}') <{aday.etiket}> ile yazılmış; "
                       "aynı metin H1 olarak işaretlendi, yeni metin üretilmedi.", "sezgisel", url=s.url)
                return
    ek = ("Başlık şu sayfanın H1'inden farklı olmalı ve bu sayfanın amacını (bilgi/ürün) yansıtmalı: " +
          "; ".join(digerleri)) if digerleri else ""
    deger, cevap, kaynak, dog, yer = _model_metni(p, s, "h1", kodlar, metin_gorevi("h1", ek))
    h1 = next((o for o in hk.bul(s.ogeler, "h1") if o.kap_bas is not None), None)
    if h1 is not None:
        parca, eski = (h1.bas_son, h1.kap_bas, _kacis(deger)), hk.ic_metin(s.metin, h1)
        duz = {"parca": 0, "onek": "", "sonek": "", "kacis": "html"}
    else:
        if m is None:
            raise Atla("sayfada <main> yok; H1'in yeri belirlenemedi")
        konum = m.bas_son
        parca, eski = (konum, konum, "\n<h1>" + _kacis(deger) + "</h1>"), "(yok)"
        duz = {"parca": 0, "onek": "\n<h1>", "sonek": "</h1>", "kacis": "html"}
    duz.update({"alan": "h1", "dogrulama": {"tur": "metin", "kaynak": kaynak, "dil": s.dil or p.dil}, "deger": deger})
    p.ekle(kodlar[0], s.dosya, [parca], eski, deger, cevap["gerekce"], "model", url=s.url, duzenleme=duz,
           kaynaklar=cevap["kaynaklar"], yer_tutucu=yer, dogrulama=dog)


def yz_alt(p, s, b):
    _model_yok(p)
    eksikler = [o for o in _gorseller(s) if o.nitelik("alt") is None]
    if not eksikler:
        raise Atla("alt metni eksik görsel bulunamadı")
    for o in eksikler:
        oncesi = re.sub(r"<[^>]+>", " ", s.metin[max(0, o.bas - 600):o.bas])
        sonrasi = re.sub(r"<[^>]+>", " ", s.metin[o.bas_son:o.bas_son + 400])
        baglam = " ".join((oncesi.split()[-40:] + ["[GÖRSEL]"] + sonrasi.split()[:30]))
        ek = {"gorsel_dosya_adi": Path(urlsplit(o.nitelik("src")).path).name, "gorsel_cevresindeki_metin": baglam}
        try:
            deger, cevap, kaynak, dog, yer = _model_metni(
                p, s, "img_alt", ["img_alt_eksik"],
                metin_gorevi("img_alt", "Yalnızca dosya adından ve görselin çevresindeki metinden anlaşılanı yaz."),
                ek_veri=ek, kaynak_ek=baglam + " " + ek["gorsel_dosya_adi"].replace("-", " "))
        except Atla as e:
            p.atla("img_alt_eksik", s.url, str(e))
            continue
        konum = hk.nitelik_ekleme_konumu(o)
        duz = {"parca": 0, "onek": ' alt="', "sonek": '"', "kacis": "nitelik", "alan": "img_alt",
               "dogrulama": {"tur": "metin", "kaynak": kaynak, "dil": s.dil or p.dil}, "deger": deger}
        p.ekle("img_alt_eksik", s.dosya, [(konum, konum, f' alt="{_kacis(deger, True)}"')], o.ham, deger,
               cevap["gerekce"], "model", url=s.url, duzenleme=duz, kaynaklar=cevap["kaynaklar"], yer_tutucu=yer,
               dogrulama=dog)


def paragraf_html(deger):
    return "".join("<p>" + _kacis(" ".join(par.split())) + "</p>\n" for par in re.split(r"\n\s*\n", deger.strip()) if par.strip())


def yz_paragraf(p, s, b):
    konum = _main_sonu(s)
    ilgili = _ilgili_sayfalar(p, s)
    ek = {"DIGER_SAYFALARDAN": ilgili}
    deger, cevap, kaynak, dog, yer = _model_metni(
        p, s, "paragraf", [b["sorun"]], PARAGRAF_GOREVI, ek_veri=ek,
        kaynak_ek=" ".join(x["ozet"] + " " + (x["baslik"] or "") for x in ilgili))
    duz = {"parca": 0, "onek": "", "sonek": "", "kacis": "paragraf", "alan": "paragraf",
           "dogrulama": {"tur": "metin", "kaynak": kaynak, "dil": s.dil or p.dil}, "deger": deger}
    p.ekle(b["sorun"], s.dosya, [(konum, konum, paragraf_html(deger))], "(yok)", deger, cevap["gerekce"], "model",
           url=s.url, duzenleme=duz, kaynaklar=cevap["kaynaklar"], yer_tutucu=yer, dogrulama=dog)


def _jsonld_bloklari(s):
    sonuc = []
    for o in hk.bul(s.ogeler, "script", lambda o: "ld+json" in (o.nitelik("type") or "").lower()):
        icerik = hk.ic_metin(s.metin, o)
        try:
            veri = json.loads(icerik)
        except json.JSONDecodeError:
            veri = None
        sonuc.append((o, icerik, veri))
    return sonuc


def yz_jsonld(p, s, b):
    _model_yok(p)
    kod = b["sorun"]
    bloklar = _jsonld_bloklari(s)
    hedef, mevcut, tur = None, None, None
    if kod == "yapisal_veri_gecersiz":
        hedef = next((x for x in bloklar if x[2] is None), None)
        if hedef is None:
            raise Atla("geçersiz JSON-LD bloğu bulunamadı")
        mevcut = hedef[1]
        m = re.search(r'"@type"\s*:\s*"([A-Za-z]+)"', mevcut)
        tur = m.group(1) if m else "WebPage"
    elif kod == "yapisal_veri_eksik_alan":
        from .cikarma import SCHEMA_ZORUNLU, URUN_EN_AZ_BIRI
        for x in bloklar:
            if isinstance(x[2], dict):
                t = str(x[2].get("@type"))
                eksik = [a for a in SCHEMA_ZORUNLU.get(t, ()) if not x[2].get(a)]
                if eksik or (t == "Product" and not any(x[2].get(a) for a in URUN_EN_AZ_BIRI)):
                    hedef, mevcut, tur = x, x[1], t
                    break
        if hedef is None:
            raise Atla("eksik alanlı JSON-LD bloğu bulunamadı")
    elif kod == "schema_kurum_turu_yok":
        tur = "Organization"
    else:
        tur = "WebPage"
    ek = {"MEVCUT_BLOK": mevcut} if mevcut else {}
    logo = next((urljoin(s.url, o.nitelik("src")) for o in _gorseller(s) if "logo" in (o.nitelik("src") or "").lower()), None)
    if logo:
        ek["logo_adresi"] = logo
    try:
        cevap = p.yz.iste(jsonld_gorevi(tur, mevcut), s.d, [kod], _sayfa_verisi(p, s, ek), dil=s.dil or p.dil)
    except YZHatasi as e:
        raise Atla("model önerisi alınamadı: " + str(e))
    kaynak = _kaynak_kaydet(p, f"{s.dosya}#jsonld", _sayfa_metni(s, 4000), mevcut or "", logo or "",
                            cevap["kaynak_metni"])
    turler = ["Organization", "OnlineStore", "Store", "LocalBusiness", "Corporation"] if tur == "Organization" else [tur]
    gecti, neden, yer, nesne = dogrula_jsonld(cevap["deger"], turler, p.kaynak_metinleri[kaynak],
                                             p.temel_url.rstrip("/"), s.dil or p.dil)
    deger = json.dumps(nesne if nesne is not None else cevap["deger"], ensure_ascii=False, indent=2)
    dogrulama = {"tur": "jsonld", "kaynak": kaynak, "turler": turler, "dil": s.dil or p.dil}
    if hedef is not None:
        o = hedef[0]
        parca, eski = (o.bas_son, o.kap_bas, "\n" + deger + "\n"), mevcut.strip()
        duz = {"parca": 0, "onek": "\n", "sonek": "\n", "kacis": "json", "alan": "jsonld", "dogrulama": dogrulama,
               "deger": deger}
    else:
        konum = _head_sonu(s)
        onek = '<script type="application/ld+json">\n'
        parca, eski = (konum, konum, onek + deger + "\n</script>\n"), "(yok)"
        duz = {"parca": 0, "onek": onek, "sonek": "\n</script>\n", "kacis": "json", "alan": "jsonld",
               "dogrulama": dogrulama, "deger": deger}
    p.ekle(kod, s.dosya, [parca], eski, deger, cevap["gerekce"], "model", url=s.url, duzenleme=duz,
           kaynaklar=cevap["kaynaklar"], yer_tutucu=yer, dogrulama={"gecti": gecti, "neden": neden})


# ------------------------------------------------------------------ plan uretimi
SAYFA_URETICI = {
    "charset_yok": kural_charset, "viewport_yok": kural_viewport, "viewport_sorunlu": kural_viewport,
    "html_lang_yok": kural_lang, "h1_birden_fazla": kural_h1, "kirik_ic_link": kural_kirik_link,
    "ic_link_yonlendirme": kural_link_yonlendirme, "gorsel_boyut_yok": kural_gorsel_boyut,
    "gorsel_lazy_yok": kural_lazy, "ilk_gorsel_lazy": kural_lazy, "og_etiketleri_yok": kural_og,
    "og_gorsel_yok": kural_og, "twitter_card_yok": kural_og, "canonical_goreli": kural_canonical_goreli,
    "ic_nofollow": kural_ic_nofollow, "bos_baslik": kural_bos_baslik,
    "canonical_yok": yz_canonical, "canonical_capraz": yz_canonical, "canonical_bos": yz_canonical,
    "canonical_coklu": yz_canonical, "noindex": yz_robots_meta, "sayfa_nofollow": yz_robots_meta,
    "meta_refresh": yz_meta_refresh, "hreflang_gecersiz": yz_hreflang, "hreflang_x_default_yok": yz_hreflang,
    "hreflang_kendine_referans_yok": yz_hreflang, "img_alt_eksik": yz_alt, "icerik_az": yz_paragraf,
    "yapisal_veri_gecersiz": yz_jsonld, "yapisal_veri_eksik_alan": yz_jsonld, "yapisal_veri_yok": yz_jsonld,
    "schema_kurum_turu_yok": yz_jsonld,
}
TITLE_KODLARI = ("title_yok", "title_kisa", "title_uzun", "title_genis", "title_h1_uyumsuz", "title_icerikle_uyumsuz")
META_KODLARI = ("meta_description_yok", "meta_description_kisa", "meta_description_uzun")
H1_KODLARI = ("h1_yok",)
ATLAMA_NEDENI = {
    "noindex_sitemapte": "noindex önerisine bağlı: noindex kaldırılırsa çelişki de ortadan kalkar",
    "noindex_canonical_catismasi": "önce noindex ve canonical kararlarından birini verin; ilgili önerilere bakın",
    "js_yonlendirme": "yönlendirme bir betiğin içinde; betiği otomatik değiştirmek güvenli değil",
    "h1_bos": "metinsiz H1 çoğunlukla logo içerir; elle gözden geçirin",
}


def plan_uret(kayitlar, tarama_bulgulari, adaptor, temel_url, dil="tr", yz=None, gunluk=None, oturum=None):
    """Bulgulardan degisiklik plani. Siteye yazmaz. Plan sozlugu dondurur."""
    p = Plan(adaptor, temel_url, dil, yz, gunluk, oturum)
    yaz = p.yaz
    kayitlar_url = {}
    for k in kayitlar:
        if not (k.get("hata") or k.get("atlandi")):
            kayitlar_url.setdefault(url_anahtari(k.get("site_url") or k.get("ad")), k)
    # her dosya bir kez, adresi dosyasina yonlendirmesiz gelen kayitla islenir
    islenen, sayfa_kayitlari = set(), []
    for k in kayitlar:
        if k.get("hata"):
            continue
        url = k.get("site_url") or k.get("ad")
        if k.get("atlandi"):
            if "robots" in (k.get("atlandi") or ""):
                p.ek_bulgular.append({"sorun": "robots_sayfayi_engelliyor", "url": k["ad"]})
                try:
                    _robots_engeli(p, k["ad"])
                except Atla as e:
                    p.atla("robots_sayfayi_engelliyor", k["ad"], str(e))
            continue
        dosya = p.url_dosya(url)
        yonlendirme = url_anahtari(k.get("ad")) != url_anahtari(url)
        if dosya is None or dosya in islenen or yonlendirme or urlsplit(k.get("ad") or "").query:
            # dosyaya karsilik gelmeyen ya da ayni dosyanin baska adresi: yalnizca elle/site bulgulari raporlanir
            sayfa_kayitlari.append((k, None))
            continue
        islenen.add(dosya)
        sayfa_kayitlari.append((k, dosya))

    for k, dosya in sayfa_kayitlari:
        url = k.get("site_url") or k.get("ad")
        sorunlar = [b for b in k.get("sorunlar") or [] if b["sorun"] not in TARAMA_GENELI]
        if dosya is None:
            for b in sorunlar:
                if kat.kategori(b["sorun"]) == "elle":
                    _elle_ekle(p, b["sorun"], k.get("ad"))
                elif b.get("katman") == "sayfa":
                    p.atla(b["sorun"], k.get("ad"), "adres sitede ayrı bir dosyaya karşılık gelmiyor "
                                                    "(yönlendirme, parametreli adres ya da sunucu tarafında üretilen sayfa)")
            if (k.get("durum_kodu") or 0) >= 400 and "sitemap.xml" in p.dosyalar and \
                    any(url_anahtari(loc) == url_anahtari(k["ad"]) for _, _, loc in _sitemap_kayitlari(p.metin("sitemap.xml"))):
                # hata kodu donen adres sitemap'te listeleniyorsa (kesif kaynagi ne olursa olsun)
                p.ek_bulgular.append({"sorun": "sitemap_olu_adres", "url": k["ad"]})
                try:
                    kural_sitemap_cikar(p, k["ad"], k.get("durum_kodu"))
                except Atla as e:
                    p.atla("sitemap_olu_adres", k["ad"], str(e))
            continue
        try:
            s = p.sayfa(dosya, url, k)
        except UnicodeDecodeError:
            p.atla("dosya", url, "dosya UTF-8 olarak okunamadı")
            continue
        yaz("Öneriler hazırlanıyor: " + url)
        kodlar = [b["sorun"] for b in sorunlar]
        # yonetici modunun dosya duzeyindeki ek denetimi: charset bildirimi
        if not re.search(r"<meta[^>]+charset=", s.metin, re.I):
            p.ek_bulgular.append({"sorun": "charset_yok", "url": url})
            sorunlar.insert(0, {"sorun": "charset_yok", "katman": "sayfa"})
        sira = {kod: i for i, kod in enumerate(ONCELIK)}
        sorunlar.sort(key=lambda b: sira.get(b["sorun"], len(ONCELIK)))
        model_alanlari = {"title": [c for c in kodlar if c in TITLE_KODLARI],
                          "meta": [c for c in kodlar if c in META_KODLARI],
                          "h1": [c for c in kodlar if c in H1_KODLARI]}
        for b in sorunlar:
            kod = b["sorun"]
            kategori = kat.kategori(kod)
            if kategori == "elle":
                _elle_ekle(p, kod, url, b.get("katman"))
                continue
            if kod in TITLE_KODLARI + META_KODLARI + H1_KODLARI:
                continue                              # alan basina tek oneri asagida uretilir
            if b.get("katman") == "site" and kod in ("sitemap_hatali_adres", "robots_sitemap_bildirilmemis"):
                if ("site", kod) in p.gorulen:
                    continue
                p.gorulen.add(("site", kod))
                try:
                    if "robots.txt" not in p.dosyalar:
                        raise Atla("sitede robots.txt yok")
                    (kural_robots_sitemap if kod == "sitemap_hatali_adres" else kural_robots_bildir)(p, b, "robots.txt")
                except Atla as e:
                    p.atla(kod, url, str(e))
                continue
            if kod == "sayfa_sitemapte_yok":
                try:
                    kural_sitemap_ekle(p, url, k)
                except Atla as e:
                    p.atla(kod, url, str(e))
                continue
            uretici = SAYFA_URETICI.get(kod)
            if uretici is None:
                p.atla(kod, url, ATLAMA_NEDENI.get(kod, "bu bulgu türü için otomatik öneri üreticisi yok"))
                continue
            try:
                uretici(p, s, b)
            except Atla as e:
                p.atla(kod, url, str(e))
            except YolGuvenligiHatasi as e:
                p.atla(kod, url, "yol güvenliği: " + str(e))
        for alan, fonk in (("title", yz_title), ("meta", yz_meta), ("h1", yz_h1)):
            if model_alanlari[alan]:
                try:
                    fonk(p, s, model_alanlari[alan])
                except Atla as e:
                    for kod in model_alanlari[alan]:
                        p.atla(kod, url, str(e))

    _tarama_geneli(p, kayitlar, kayitlar_url, tarama_bulgulari)
    return {
        "hedef": {"adaptor": adaptor.tanim(), "temel_url": p.temel_url, "dil": dil},
        "zaman": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": getattr(yz, "model", None),
        "dosya_hashleri": {d: ozet_hash(adaptor.oku(d)) for d in sorted({x["dosya"] for x in p.degisiklikler})},
        "degisiklikler": p.degisiklikler, "elle": p.elle, "atlanan": p.atlanan, "ek_bulgular": p.ek_bulgular,
        "kaynak_metinleri": p.kaynak_metinleri,
    }


def _elle_ekle(p, kod, url, katman=None):
    for e in p.elle:
        if e["bulgu"] == kod:
            if url not in e["sayfalar"]:
                e["sayfalar"].append(url)
            return
    p.elle.append({"bulgu": kod, "bulgu_aciklamasi": kat.aciklama(kod), "katman": katman,
                   "duzeltme": kat.duzeltme_metni(kod), "sayfalar": [url]})


def _tarama_geneli(p, kayitlar, kayitlar_url, bulgular):
    """Sayfalar arasi bulgular: tekrarlar, yetim/derin sayfalar, hreflang donusu."""
    for g in bulgular or []:
        kod = g["sorun"]
        sayfalar = g.get("sayfalar") or []
        if kod in ("title_tekrar", "meta_tekrar", "h1_tekrar", "icerik_tekrar", "icerik_benzer"):
            # grubun ilk sayfasi (tarama sirasiyla) korunur; ayni dosyanin farkli adresleri tek sayilir
            dosyalar = []
            for a in sayfalar:
                k = kayitlar_url.get(url_anahtari(a))
                url = (k or {}).get("site_url") or a
                dosya = p.url_dosya(url)
                if dosya and dosya not in [d for d, _ in dosyalar] and not urlsplit(a).query and \
                        url_anahtari(url) == url_anahtari(a):
                    dosyalar.append((dosya, url))
            if len(dosyalar) < 2:
                for a in sayfalar:
                    p.atla(kod, a, "tekrar eden adresler aynı dosyaya ait (yönlendirme ya da parametre); "
                                   "canonical/yönlendirme önerilerine bakın")
                continue
            ilk_dosya, ilk_url = dosyalar[0]
            ilk_sayfa = p.sayfa(ilk_dosya, ilk_url)
            for dosya, url in dosyalar[1:]:
                s = p.sayfa(dosya, url, kayitlar_url.get(url_anahtari(url)))
                try:
                    if kod == "title_tekrar":
                        yz_title(p, s, ["title_tekrar"], [ilk_sayfa.d.get("title") or ""])
                    elif kod == "meta_tekrar":
                        yz_meta(p, s, ["meta_tekrar"], [ilk_sayfa.d.get("meta_description") or ""])
                    elif kod == "h1_tekrar":
                        yz_h1(p, s, ["h1_tekrar"], [" / ".join(ilk_sayfa.d.get("h1") or [])])
                    else:
                        yz_canonical(p, s, {"sorun": kod}, hedef=dosyadan_url(ilk_dosya, p.temel_url),
                                     gerekce=f"Sayfa metni {ilk_url} ile {'aynı' if kod == 'icerik_tekrar' else 'büyük ölçüde aynı'}; "
                                             "kopya sayfa canonical ile asıl sayfaya bağlandı. Sayfayı özgünleştirmeyi "
                                             "planlıyorsanız reddedin.")
                except Atla as e:
                    p.atla(kod, url, str(e))
        elif kod in ("yetim_sayfa", "derin_sayfa"):
            for a in sayfalar:
                try:
                    if kod == "yetim_sayfa":
                        hub = _hub_dosyasi(p, a)
                        if not hub:
                            raise Atla("bağlantı verecek bir dizin sayfası bulunamadı")
                        yz_baglanti_ekle(p, a, hub, kod, "Sayfa sitemap'te olduğu halde hiçbir sayfadan bağlantı "
                                                          f"almıyor; üst dizin sayfasından ({hub}) bağlantı verildi.",
                                         "İlgili yazı:")
                    else:
                        if "index.html" not in p.dosyalar:
                            raise Atla("ana sayfa dosyası yok")
                        yz_baglanti_ekle(p, a, "index.html", kod, "Sayfa ana sayfadan 3'ten fazla tıklama uzakta; "
                                                                  "ana sayfadan doğrudan bağlantı verildi.",
                                         "Öne çıkan:")
                except Atla as e:
                    p.atla(kod, a, str(e))
        elif kod == "hreflang_donus_yok":
            for a in sayfalar:
                k = kayitlar_url.get(url_anahtari(a))
                try:
                    if not k:
                        raise Atla("sayfanın tarama kaydı yok")
                    yz_hreflang_donus(p, k, kayitlar_url)
                except Atla as e:
                    p.atla(kod, a, str(e))


# ------------------------------------------------------------------ onizleme
def metne_uygula(metin, parcalar):
    """Parcalari (bas, son, yeni) sondan basa uygular; konumlar ozgun metne goredir."""
    for bas, son, yeni in sorted(parcalar, key=lambda x: (-x[0], -x[1])):
        metin = metin[:bas] + yeni + metin[son:]
    return metin


def _parcalar(d):
    return [(x["bas"], x["son"], x["yeni"]) for x in d["parcalar"]]


def degisiklik_diff(d, metin, baglam=2):
    yeni = metne_uygula(metin, _parcalar(d))
    return "".join(difflib.unified_diff(metin.splitlines(keepends=True), yeni.splitlines(keepends=True),
                                        fromfile="a/" + d["dosya"], tofile="b/" + d["dosya"], n=baglam))


def onizleme_diff(plan, oku):
    """Kategoriye gore gruplu onizleme. oku(dosya) -> metin."""
    satirlar = []
    for kategori in ("kural", "yz"):
        grup = [d for d in plan["degisiklikler"] if d["kategori"] == kategori]
        satirlar.append("#" * 78 + f"\n# {kat.KATEGORI_ADI[kategori]} — {len(grup)} değişiklik\n" + "#" * 78 + "\n")
        for d in grup:
            uyari = " · YÜKSEK RİSK" if d["risk"] == "yuksek" else ""
            durum = "" if d["durum"] == "oneriliyor" else f" · UYGULANAMAZ ({d['dogrulama']['neden']})"
            yer = " · YER TUTUCU: değer doldurulmadan uygulanamaz" if d["yer_tutucu"] else ""
            satirlar.append(f"\n# {d['id']} [{kat.KATEGORI_ADI[d['kategori']]}{uyari}{durum}{yer}] {d['bulgu']} — "
                            f"{d['url']}\n# Gerekçe: {d['gerekce']}\n")
            if d.get("etki"):
                satirlar.append(f"# Olası etki: {d['etki']}\n")
            if d.get("kaynaklar"):
                satirlar.append("# Kaynaklar: " + ", ".join(k["id"] for k in d["kaynaklar"]) + "\n")
            satirlar.append(degisiklik_diff(d, oku(d["dosya"])))
    return "".join(satirlar)


# ------------------------------------------------------------------ uygulama
def _deger_kacis(deger, kacis):
    if kacis == "html":
        return _kacis(deger)
    if kacis == "nitelik":
        return _kacis(deger, True)
    if kacis == "paragraf":
        return paragraf_html(deger)
    return deger


def duzenle(d, deger, plan):
    """Kullanicinin duzenledigi degeri dogrular ve parcayi yeniden kurar. (gecerli, neden)."""
    duz = d.get("duzenleme")
    if not duz:
        return False, "bu değişiklik düzenlenemez"
    dog = duz.get("dogrulama") or {}
    kaynak = plan.get("kaynak_metinleri", {}).get(dog.get("kaynak"), "")
    if duz["alan"] == "jsonld":
        gecti, neden, yer, nesne = dogrula_jsonld(deger, dog.get("turler"), kaynak,
                                                 plan["hedef"]["temel_url"].rstrip("/"), dog.get("dil", "tr"))
        if gecti:
            deger = json.dumps(nesne, ensure_ascii=False, indent=2)
    elif duz["alan"] == "baglanti_metni":
        gecti, neden, yer = dogrula_metin("baglanti_metni", deger, deger, dog.get("dil", "tr"))
    else:
        gecti, neden, yer = dogrula_metin(duz["alan"], deger, kaynak + " " + deger if dog.get("serbest") else kaynak,
                                          dog.get("dil", "tr"))
    if not gecti:
        return False, neden
    d["parcalar"][duz["parca"]]["yeni"] = duz["onek"] + _deger_kacis(deger, duz["kacis"]) + duz["sonek"]
    d["yeni"], d["yer_tutucu"], d["duzenlendi"] = deger, yer, True
    return True, ""


def _jsonld_sayilari(metin):
    gecerli = gecersiz = 0
    for icerik in re.findall(r"<script[^>]+ld\+json[^>]*>(.*?)</script>", metin, re.S | re.I):
        try:
            json.loads(icerik)
            gecerli += 1
        except json.JSONDecodeError:
            gecersiz += 1
    return gecerli, gecersiz


def gecerlilik_bozuluyor_mu(dosya, once, sonra):
    """Degisiklik belgeyi bozuyorsa neden, bozmuyorsa '' dondurur."""
    if dosya.endswith(".xml"):
        try:
            ET.fromstring(sonra.encode("utf-8"))
        except ET.ParseError as e:
            return "XML geçersiz hale geliyor: " + str(e)
        return ""
    if dosya.endswith((".html", ".htm")):
        if hk.yapi_hatalari(sonra) > hk.yapi_hatalari(once):
            return "HTML yapısı bozuluyor (kapanmamış ya da eşleşmeyen etiket)"
        g1, h1 = _jsonld_sayilari(once)
        g2, h2 = _jsonld_sayilari(sonra)
        if h2 > h1 or g2 < g1:
            return "JSON-LD bloğu geçersiz hale geliyor ya da geçerli bir blok kayboluyor"
    return ""


def kararlari_coz(plan, kararlar):
    """Her degisiklik icin uygulanacak mi? Durum ve neden yazar. Onaylananlarin listesini dondurur."""
    kararlar = kararlar or {}
    tek = kararlar.get("kararlar") or {}
    onaylanan = []
    for d in plan["degisiklikler"]:
        k = tek.get(d["id"]) or {}
        if d["durum"] == "gecersiz":
            d["durum_nedeni"] = "doğrulamadan geçmedi: " + d["dogrulama"]["neden"]
            continue
        if k.get("karar") == "ret":
            d["durum"], d["durum_nedeni"] = "reddedildi", "kullanıcı reddetti"
            continue
        onay = k.get("karar") == "onay" or (d["kategori"] == "kural" and kararlar.get("kural_hepsi"))
        if not onay:
            d["durum"], d["durum_nedeni"] = "onay_bekliyor", "onay verilmedi; uygulanmadı"
            continue
        if d["risk"] == "yuksek" and not k.get("risk_onay"):
            d["durum"], d["durum_nedeni"] = "onay_bekliyor", "yüksek riskli öneri için ayrıca risk onayı verilmedi"
            continue
        if k.get("deger") is not None and k.get("deger") != d.get("yeni"):
            gecti, neden = duzenle(d, k["deger"], plan)
            if not gecti:
                d["durum"], d["durum_nedeni"] = "basarisiz", "düzenlenen değer doğrulamadan geçmedi: " + neden
                continue
        elif d.get("uretici") == "model" and d.get("duzenleme"):
            # model ciktisi uygulama aninda guncel dogrulama kurallarindan yeniden gecer
            gecti, neden = duzenle(d, d["duzenleme"].get("deger", d.get("yeni")), plan)
            d.pop("duzenlendi", None)
            if not gecti:
                d["durum"], d["durum_nedeni"] = "basarisiz", "doğrulamadan geçmedi: " + neden
                continue
        if d.get("yer_tutucu"):
            d["durum"], d["durum_nedeni"] = "basarisiz", "[doğrulanmalı: …] yer tutucusu doldurulmadan uygulanamaz"
            continue
        onaylanan.append(d)
    return onaylanan


def uygula(plan, kararlar, adaptor, yedek_klasoru, gunluk_yolu):
    """Onaylanan degisiklikleri uygular. Once sitenin tam yedegi alinir. Ozet dondurur."""
    hedef = plan["hedef"]["adaptor"]
    if adaptor.tanim() != hedef:
        raise YolGuvenligiHatasi("Plan başka bir hedef için üretilmiş: " + json.dumps(hedef, ensure_ascii=False))
    onaylanan = kararlari_coz(plan, kararlar)
    gunluk = Path(gunluk_yolu)
    gunluk.parent.mkdir(parents=True, exist_ok=True)

    def kaydet(d, durum, neden="", **ek):
        d["durum"], d["durum_nedeni"] = durum, neden
        with gunluk.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"zaman": time.strftime("%Y-%m-%d %H:%M:%S"), "id": d["id"], "dosya": d["dosya"],
                                "kategori": d["kategori"], "bulgu": d["bulgu"], "durum": durum, "neden": neden, **ek},
                               ensure_ascii=False) + "\n")

    for d in plan["degisiklikler"]:
        if d not in onaylanan:
            kaydet(d, d["durum"], d.get("durum_nedeni", ""))
    if not onaylanan:
        return {"yedek": None, "uygulanan": 0, "dosyalar": {}}
    manifest = adaptor.yedekle(yedek_klasoru)     # yazmadan once tam yedek
    dosyalar = {}
    for dosya in sorted({d["dosya"] for d in onaylanan}):
        grup = sorted((d for d in onaylanan if d["dosya"] == dosya), key=lambda d: int(d["id"][1:]))
        try:
            ham = adaptor.oku(dosya)
        except (OSError, YolGuvenligiHatasi) as e:
            for d in grup:
                kaydet(d, "basarisiz", "dosya okunamadı: " + str(e))
            continue
        if ozet_hash(ham) != plan["dosya_hashleri"].get(dosya):
            for d in grup:
                kaydet(d, "basarisiz", "dosya plandan sonra değişmiş; öneriler eski içeriğe göre")
            continue
        ozgun = metin = ham.decode("utf-8")
        dolu = []                                     # uygulanmis parcalar: (bas, son, uzunluk farki), ozgun konumlarla
        for d in grup:
            parcalar = _parcalar(d)
            if any(ozgun[a:b] != x["eski"] for (a, b, _), x in zip(parcalar, d["parcalar"])):
                kaydet(d, "basarisiz", "değiştirilecek metin dosyada beklenen konumda değil")
                continue
            if _cakisiyor(parcalar, [(a, b) for a, b, _ in dolu]):
                kaydet(d, "basarisiz", "aynı bölgeyi değiştiren başka bir onaylı öneriyle çakışıyor")
                continue
            # parca konumlari ozgun metne goredir; daha once uygulanan parcalarin kaydirmasi eslenir
            esli = []
            for a, b, y in parcalar:
                ea = _esle(a, dolu, bitis=False)
                esli.append((ea, ea if a == b else _esle(b, dolu, bitis=True), y))   # ekleme: bas = son
            aday = metne_uygula(metin, esli)
            neden = gecerlilik_bozuluyor_mu(dosya, metin, aday)
            if neden:
                kaydet(d, "basarisiz", neden)
                continue
            metin = aday
            dolu += [(a, b, len(y) - (b - a)) for a, b, y in parcalar]
            d["_uygulanacak"] = True
        uygulananlar = [d for d in grup if d.pop("_uygulanacak", False)]
        if not uygulananlar:
            continue
        yeni = metin.encode("utf-8")
        try:
            adaptor.yaz(dosya, yeni)
        except (OSError, YolGuvenligiHatasi) as e:
            for d in uygulananlar:
                kaydet(d, "basarisiz", "dosyaya yazılamadı: " + str(e))
            continue
        dosyalar[dosya] = {"once": ozet_hash(ham), "sonra": ozet_hash(yeni),
                           "diff": "".join(difflib.unified_diff(ozgun.splitlines(keepends=True),
                                                                metin.splitlines(keepends=True),
                                                                fromfile="a/" + dosya, tofile="b/" + dosya, n=2))}
        for d in uygulananlar:
            kaydet(d, "uygulandi", "", once=ozet_hash(ham), sonra=ozet_hash(yeni))
    return {"yedek": str(yedek_klasoru), "yedek_dosya_sayisi": len(manifest),
            "uygulanan": sum(1 for d in plan["degisiklikler"] if d["durum"] == "uygulandi"), "dosyalar": dosyalar}


def _esle(konum, dolu, bitis):
    """Ozgun metindeki konumun, uygulanmis parcalardan sonraki karsiligi. Ayni noktaya yapilan
    eklemeler: baslangic konumu onceki eklemenin arkasina, bitis konumu onune dusurulur."""
    kayma = 0
    for a, b, fark in dolu:
        if b < konum or (b == konum and (a < b or not bitis)):
            kayma += fark
    return konum + kayma


def _cakisiyor(parcalar, dolu):
    """Yeni parcalar daha once uygulanan bir aralikla kesisiyor mu? Ayni noktaya ekleme kesisme sayilmaz."""
    for a, b, _ in parcalar:
        for x, y in dolu:
            if a == b or x == y:                      # bos aralik (ekleme): yalnizca bir degisimin icine dusuyorsa
                if (a == b and x < a < y) or (x == y and a < x < b):
                    return True
                continue
            if a < y and x < b:
                return True
    return False
