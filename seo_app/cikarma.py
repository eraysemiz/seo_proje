"""HTML'den SEO denetimi icin gerekli verilerin cikarilmasi."""
import json
import os
import re
import zlib
from urllib.parse import unquote, urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

ALT_LIMIT = 12          # bir sayfada modelden en fazla kac gorsel icin alt metin istenir
IMZA_BOYUTU = 64        # icerik benzerligi icin saklanan en kucuk parmak izi sayisi (bottom-k MinHash)
SERP_GENISLIK = 580     # arama sonucunda kesilmeden gorunen yaklasik baslik genisligi (px, Arial 20 px)


def url_anahtari(u):
    """Karsilastirma icin adres: sema, 'www.' oneki ve sondaki '/' farklari yok sayilir."""
    p = urlparse(urldefrag(u or "")[0])
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return host + (p.path.rstrip("/") or "") + ("?" + p.query if p.query else "")


def ayni_site(host_a, host_b):
    """www. oneki disinda ayni host mu (alt alan adlari ayri site sayilir)."""
    yalin = lambda h: (h or "").lower()[4:] if (h or "").lower().startswith("www.") else (h or "").lower()
    return yalin(host_a) == yalin(host_b)


def sayfa_basligi(soup):
    """Sayfanin <title> etiketi; satir ici <svg> icindeki <title> (simge aciklamasi) sayilmaz."""
    for t in soup.find_all("title"):
        if t.find_parent("svg") is None:
            return t
    return None


def meta_aciklama_etiketi(soup):
    """name="description" etiketini buyuk/kucuk harf farkini yok sayarak bulur."""
    return soup.find("meta", attrs={"name": re.compile(r"^\s*description\s*$", re.I)})


# Arial 20 px karakter genislikleri (yaklasik); Google masaustu sonuclarinda baslik bu yazi tipiyle
# yaklasik 580-600 px'te kesilir. Karakter sayisi "WWW" ile "iii" arasindaki farki goremez.
_DAR = set("ijlı.,;:!|'İI")
_ORTA_DAR = set("frt-()[]/ ")
_GENIS = set("mwMW%@")


def baslik_piksel(metin):
    toplam = 0.0
    for c in metin or "":
        if c in _DAR:
            toplam += 4.5
        elif c in _ORTA_DAR:
            toplam += 6.0
        elif c in _GENIS:
            toplam += 16.5
        elif c.isupper():
            toplam += 13.0
        else:
            toplam += 10.5
    return round(toplam)


def icerik_imzasi(metin):
    """5 kelimelik parcalarin (shingle) CRC32 ozetlerinden en kucuk IMZA_BOYUTU tanesi.
    Iki sayfanin imzasi karsilastirilarak icerik benzerligi (Jaccard) tahmin edilir."""
    k = kelimeler(metin)
    if len(k) < 5:
        return []
    ozetler = {zlib.crc32(" ".join(k[i:i + 5]).encode("utf-8")) for i in range(len(k) - 4)}
    return sorted(ozetler)[:IMZA_BOYUTU]


def imza_benzerligi(a, b):
    """Bottom-k MinHash ile Jaccard tahmini (0-1). Imzalardan biri bossa 0."""
    if not a or not b:
        return 0.0
    birlesim = sorted(set(a) | set(b))[:IMZA_BOYUTU]
    ortak = set(a) & set(b)
    return sum(1 for h in birlesim if h in ortak) / len(birlesim)


def tr_lower(x):
    return x.replace("İ", "i").replace("I", "ı").lower()


def kokler(metin):
    """Metindeki 5+ harfli kelimelerin ilk 5 harfi (Turkce ek farklarini yumusatir)."""
    return {w[:5] for w in re.findall(r"[a-zçğıöşüâîû0-9]+", tr_lower(metin)) if len(w) >= 5}


def kelimeler(metin):
    """Metni Turkce kucuk harfe cevirip kelimelere ayirir."""
    return re.findall(r"[a-zçğıöşüâîû0-9]+", tr_lower(metin))


# her sayfada bulunabilecek genel SEO/kurum sozcukleri (sadakat denetiminde sayilmaz)
GENEL_KOKLER = {"resmi", "sites", "anasa", "sayfa", "hizme", "bilgi", "haber", "duyur", "kurum", "hakkı"}


def gorseller(soup):
    """Sayfadaki gorseller, belge sirasiyla (noscript/script icindeki yedekler haric).
    Cikarma ve uygulama ayni listeyi kullanir; boylece gorsel sira numaralari eslesir."""
    return [i for i in soup.find_all("img") if i.find_parent(["noscript", "script"]) is None]


def gercek_src(img):
    """Tembel yuklemede (lazy-load) src yer tutucudur; asil adres data-src'dedir."""
    return img.get("data-src") or img.get("data-lazy-src") or img.get("src", "")


def _baglam(img):
    """Gorselin etrafindaki metinsel ipuclari (model gorseli goremez)."""
    parca = []
    if img.get("srcset") and not img.get("data-src"):
        parca.append("srcset: " + dosya_adi(img["srcset"].split(",")[0].split()[0]))
    for k in ("title", "aria-label"):
        if img.get(k): parca.append(f"{k}: {img[k][:60]}")
    a = img.find_parent("a")
    if a:
        t = a.get_text(" ", strip=True)
        if t: parca.append("baglanti metni: " + t[:60])
        if a.get("href"): parca.append("baglanti: " + a["href"][:80])
    fig = img.find_parent("figure")
    if fig and fig.find("figcaption"):
        parca.append("aciklama: " + fig.find("figcaption").get_text(" ", strip=True)[:80])
    return "; ".join(parca)[:220]


# title icinde site adini sayfa adindan ayiran yaygin isaretler ("Sayfa | Site", "Site - Sayfa")
BASLIK_AYRACI = re.compile(r"\s+[|\-–—:·]\s+")


def site_adi_bul(soup, title, govde=""):
    """Sitenin adini sayfanin kendi verisinden bulur: og:site_name, application-name ya da
    title'in ayracla ayrilmis ilk/son parcasi. Bulunamazsa None (uydurulmaz)."""
    for ad in ("og:site_name", "application-name"):
        m = soup.find("meta", attrs={"property": ad}) or soup.find("meta", attrs={"name": ad})
        if m and m.get("content", "").strip():
            return m["content"].strip()[:80]
    # "Anasayfa", "Home" gibi genel sayfa adlari site adi olamaz. Kalan adaylardan sayfa metninde
    # (logo, alt bilgi, telif satiri) daha sik gecen secilir; esitlikte son parca, cunku marka
    # genellikle sonda yazilir ("Erkek Giyim Modelleri | AVVA")
    parcalar = [p.strip() for p in BASLIK_AYRACI.split(title or "") if p.strip()]
    if len(parcalar) >= 2:
        adaylar = [p for p in (parcalar[-1], parcalar[0]) if tr_lower(p) not in GENEL_SAYFA_ADLARI]
        if adaylar:
            return max(adaylar, key=lambda p: govde.count(tr_lower(p)))[:80]
    return None


GENEL_SAYFA_ADLARI = {"anasayfa", "ana sayfa", "home", "homepage", "hoş geldiniz", "hos geldiniz", "giriş", "index"}


def _baglanti_listelerini_ayikla(kok):
    """Metni neredeyse tamamen baglantilardan olusan listeleri (menu, kisayol, alt bilgi) cikarir.
    Yalnizca modele ve getirme sorgusuna giden ozet icin kullanilir; sadakat kokleri etkilenmez."""
    for liste in kok.find_all(["ul", "ol"]):
        metin = liste.get_text(" ", strip=True)
        bag = " ".join(a.get_text(" ", strip=True) for a in liste.find_all("a"))
        if metin and len(bag) >= 0.7 * len(metin):
            liste.decompose()


def dosya_adi(src):
    return os.path.basename(unquote(src.split("?")[0]))[:60]


def extract(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    meta = meta_aciklama_etiketi(soup)
    baslik_etiketi = sayfa_basligi(soup)
    body = soup.body or soup
    imgs = gorseller(soup)                 # noscript silinmeden once, apply_fixes ile ayni sira
    for t in body(["script", "style", "noscript"]):
        t.decompose()
    text = re.sub(r"\s+", " ", body.get_text(" ", strip=True))
    h1_metinleri = [h.get_text(strip=True) for h in soup.find_all("h1")]
    baslik = baslik_etiketi.get_text(strip=True) if baslik_etiketi else None
    # alt niteligi hic olmayan gorsel eksiktir; alt="" ise dekoratif gorsel icin bilincli
    # ve gecerli bir tercihtir (WCAG), eksik sayilmaz
    eksik = [(n, i) for n, i in enumerate(imgs) if i.get("alt") is None]
    sonuc = {
        "lang": (soup.html.get("lang") if soup.html else None),
        "title": baslik,
        "site_adi": site_adi_bul(soup, baslik, tr_lower(text)),
        "meta_description": meta.get("content", "").strip() if meta else None,
        "canonical": bool(canonical_etiketleri(soup)),
        "h1": [t for t in h1_metinleri if t],          # yalnizca metni olan H1'ler sayilir
        "h1_bos_sayisi": sum(1 for t in h1_metinleri if not t),
        "h2": [h.get_text(strip=True) for h in soup.find_all("h2")][:5],
        "h3": [t for t in (h.get_text(strip=True) for h in soup.find_all("h3")) if t][:5],
        "img_total": len(imgs),
        "img_no_alt": [{"sira": n, "src": gercek_src(i)} for n, i in eksik],
        "img_bos_alt": sum(1 for i in imgs if i.get("alt") is not None and not i["alt"].strip()),
        "img_baglam": {n: _baglam(i) for n, i in eksik},
        "word_count": len(text.split()),
        "text_sample": text[:800],
    }
    # Sadakat denetiminin dayandigi kelime kokleri yalnizca icerik bolgesinden alinir:
    # menu ve alt bilgi baglantilari ("Basari Siralamalari" gibi) modelin uydurdugu bir
    # iddiayi "sayfada geciyor" gibi gostermesin. Yukaridaki alanlar hesaplandiktan sonra
    # gezinme bolumleri cikarilir.
    icerik = body.find("main") or body.find("article")
    if icerik is None:
        for t in body.find_all(["nav", "header", "footer", "aside"]):
            t.decompose()
        icerik = body
    icerik_metni = re.sub(r"\s+", " ", icerik.get_text(" ", strip=True))
    # ince icerik olcutu menu/alt bilgi disindaki metindir; sayfalar arasi benzerlik de buradan
    sonuc["icerik_kelime_sayisi"] = len(icerik_metni.split())
    sonuc["icerik_imzasi"] = icerik_imzasi(icerik_metni)
    # icerik_ozeti: modele ve bilgi getirme sorgusuna giden ozet (menu/alt bilgi ve baglanti
    # listeleri ayiklanmis icerik bolgesi); bos kalirsa daha genis metne donulur
    sonuc["icerik_kokleri"] = kokler(icerik_metni)          # odak terim denetimi icin (title haric)
    sonuc["kelime_kokleri"] = kokler(" ".join([
        icerik_metni, sonuc["title"] or "", sonuc["meta_description"] or "", " ".join(sonuc["h1"]),
        sonuc["site_adi"] or ""]))
    sonuc["sayfa_kelimeleri"] = set(kelimeler(" ".join([
        sonuc["title"] or "", sonuc["meta_description"] or "", " ".join(sonuc["h1"]), sonuc["site_adi"] or ""])))
    # kokler hesaplandiktan sonra baglanti listeleri ayiklanir; ozet sayfanin asil metnine odaklanir
    _baglanti_listelerini_ayikla(icerik)
    ozet = re.sub(r"\s+", " ", icerik.get_text(" ", strip=True))
    sonuc["icerik_ozeti"] = (ozet if len(ozet) >= 200 else icerik_metni if len(icerik_metni) >= 200 else text)[:1200]
    return sonuc


# Google'in zengin sonuc icin istedigi zorunlu alanlar (ozet; tam liste Search Central belgelerinde).
# Product icin bu alanlardan en az biri gerekir: offers, review, aggregateRating.
SCHEMA_ZORUNLU = {
    "Article": ("headline",), "NewsArticle": ("headline",), "BlogPosting": ("headline",),
    "Product": ("name",), "Event": ("name", "startDate", "location"),
    "Organization": ("name",), "LocalBusiness": ("name", "address"),
    "BreadcrumbList": ("itemListElement",), "FAQPage": ("mainEntity",),
    "Recipe": ("name", "image"), "JobPosting": ("title", "datePosted", "description", "hiringOrganization"),
    "Course": ("name", "description"), "VideoObject": ("name", "thumbnailUrl", "uploadDate"),
    "Review": ("itemReviewed", "author"),
}
URUN_EN_AZ_BIRI = ("offers", "review", "aggregateRating")


def _schema_nesneleri(veri):
    """JSON-LD'deki ust duzey nesneler; @graph dizisindekiler de acilir (Yoast, Rank Math)."""
    if isinstance(veri, list):
        for x in veri:
            yield from _schema_nesneleri(x)
    elif isinstance(veri, dict):
        if veri.get("@type"):
            yield veri
        yield from _schema_nesneleri(veri.get("@graph") or [])


def _schema_eksikleri(nesne):
    turler = nesne["@type"] if isinstance(nesne["@type"], list) else [nesne["@type"]]
    eksik = []
    for t in turler:
        for alan in SCHEMA_ZORUNLU.get(str(t), ()):
            if nesne.get(alan) in (None, "", [], {}):
                eksik.append(str(t) + ": " + alan)
        if str(t) == "Product" and not any(nesne.get(a) for a in URUN_EN_AZ_BIRI):
            eksik.append("Product: offers/review/aggregateRating")
    return eksik


def canonical_etiketleri(soup):
    """rel degeri buyuk/kucuk harf farkiyla da yazilmis olabilir ("Canonical")."""
    return [l for l in soup.find_all("link", rel=True)
            if "canonical" in [r.lower() for r in (l.get("rel") or [])]]


def meta_refresh_coz(icerik):
    """'5; url=/yeni' -> (5.0, '/yeni'). Hedef yoksa (yalnizca yenileme) hedef None."""
    m = re.match(r"""\s*(\d+(?:\.\d+)?)?\s*[;,]?\s*(?:url\s*=\s*)?['"]?([^'"]*)['"]?\s*$""", icerik or "", re.I)
    if not m:
        return None, None
    sure = float(m.group(1)) if m.group(1) else 0.0
    return sure, (m.group(2).strip() or None)


# yalnizca kisa satir ici betiklerdeki location atamasi yonlendirme sayilir; uzun betiklerde bu
# ifadeler genellikle tiklama gibi bir olaya baglidir
JS_YONLENDIRME = re.compile(r"""(?:window|document|top|self)\.location(?:\.href)?\s*=\s*['"]|"""
                            r"""location\.(?:replace|assign)\s*\(\s*['"]|location\.href\s*=\s*['"]""")
GENEL_BAGLANTI_METINLERI = {
    "tıklayın", "tıklayınız", "buraya tıklayın", "buraya tıklayınız", "tıkla", "buraya", "burada", "devamı",
    "devamını oku", "devamını okuyun", "daha fazla", "detaylar", "detay", "ayrıntılar", "incele", "link",
    "click here", "here", "read more", "more", "learn more", "details", "this"}
ESKI_GORSEL = ("jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff")


def baglantilari_cikar(soup, taban):
    """Sayfadaki <a href> baglantilari: mutlak adres, metin, nofollow ve ic/dis bilgisi.
    <base href> varsa goreli adresler ona gore cozulur."""
    base = soup.find("base", href=True)
    if base:
        taban = urljoin(taban, base["href"].strip())
    host = urlparse(taban).hostname
    sonuc = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or re.match(r"^(javascript|mailto|tel|data|sms|ftp):", href, re.I):
            continue
        adres = urldefrag(urljoin(taban, href))[0]
        p = urlparse(adres)
        if p.scheme not in ("http", "https") or not p.hostname:
            continue
        metin = a.get_text(" ", strip=True) or " ".join(
            i.get("alt", "").strip() for i in a.find_all("img") if i.get("alt")) or \
            (a.get("aria-label") or a.get("title") or "").strip()
        rel = [r.lower() for r in (a.get("rel") or [])]
        sonuc.append({"adres": adres, "metin": re.sub(r"\s+", " ", metin)[:120],
                      "nofollow": "nofollow" in rel, "ic": ayni_site(p.hostname, host)})
    return sonuc


def _gorsel_ayrintilari(soup, taban):
    sonuc = []
    for n, i in enumerate(gorseller(soup)):
        src = (gercek_src(i) or "").strip()
        veri_uri = src.startswith("data:")
        dosya = urlparse(src).path.rsplit("/", 1)[-1] if src and not veri_uri else ""
        uzanti = dosya.rsplit(".", 1)[-1].lower() if "." in dosya else ""
        resim = i.find_parent("picture")
        modern_kaynak = bool(resim and resim.find("source", attrs={"type": re.compile(r"webp|avif", re.I)}))
        sonuc.append({
            "sira": n,
            "src": urljoin(taban, src) if (taban and src and not veri_uri) else src,
            "veri_uri": veri_uri,
            "lazy": (i.get("loading") or "").lower() == "lazy" or bool(i.get("data-src") or i.get("data-lazy-src")),
            "boyut_var": bool(i.get("width") and i.get("height")),
            "uzanti": uzanti,
            "eski_format": uzanti in ESKI_GORSEL and not modern_kaynak,
        })
    return sonuc


def _srcset_adresleri(deger):
    return [p.strip().split()[0] for p in (deger or "").split(",") if p.strip()]


def yapisal_veri(html, sayfa_url=None, link_basligi=None):
    """Yapisal veri, indekslenebilirlik, mobil uyum, paylasim etiketleri, baglanti ve gorsel bilgisi.
    Tamami sayfanin HTML'inden gorulebilir. sayfa_url verilirse goreli adresler cozulur ve
    baglantilar ic/dis olarak ayrilir. link_basligi: HTTP Link basligindan cozulmus liste
    ([{"url", "rel", "hreflang"}]); canonical ve hreflang basliktan da bildirilebilir."""
    soup = BeautifulSoup(html, "lxml")
    taban = sayfa_url or ""
    jsonld, jsonld_hata, turler, eksikler = 0, 0, [], []
    for s in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        jsonld += 1
        try:
            veri = json.loads(s.string or s.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            jsonld_hata += 1
            continue
        if isinstance(veri, dict) and not veri.get("@context"):
            eksikler.append("@context")
        for nesne in _schema_nesneleri(veri):
            t = nesne["@type"]
            turler += t if isinstance(t, list) else [t]
            eksikler += _schema_eksikleri(nesne)
    vp = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
    og = [m.get("property") for m in soup.find_all("meta", attrs={"property": re.compile(r"^og:", re.I)})]
    tw = [m.get("name") for m in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:", re.I)})]
    # robots ve googlebot meta etiketlerinin tamami (birden fazla olabilir; Google hepsini birlestirir)
    robots_etiketleri = [(m["name"].strip().lower(), (m.get("content") or "").strip())
                         for m in soup.find_all("meta", attrs={"name": re.compile(r"^\s*(robots|googlebot)\s*$", re.I)})]
    yonergeler = {d.strip().lower() for _, c in robots_etiketleri for d in c.split(",") if d.strip()}
    refresh = soup.find("meta", attrs={"http-equiv": re.compile(r"^\s*refresh\s*$", re.I)})
    refresh_sure, refresh_hedef = meta_refresh_coz(refresh.get("content")) if refresh else (None, None)
    canonicallar = [{"href": (l.get("href") or "").strip(), "head": l.find_parent("head") is not None,
                     "kaynak": "html"} for l in canonical_etiketleri(soup)]
    hreflanglar = [{"kod": (l.get("hreflang") or "").strip(), "href": urljoin(taban, (l.get("href") or "").strip())}
                   for l in soup.find_all("link", attrs={"hreflang": True})]
    for b in link_basligi or []:
        rel = (b.get("rel") or "").lower().split()
        if "canonical" in rel:
            canonicallar.append({"href": b.get("url", ""), "head": True, "kaynak": "http"})
        if "alternate" in rel and b.get("hreflang"):
            hreflanglar.append({"kod": b["hreflang"], "href": urljoin(taban, b.get("url", ""))})
    # karisik icerik: sayfanin yukledigi kaynaklardan http:// ile gelenler (baglantilar sayilmaz);
    # srcset ve satir ici stil/stil blogu icindeki url(...) adresleri de kaynaktir
    stiller = " ".join([t.get("style", "") for t in soup.find_all(style=True)] +
                       [t.get_text() for t in soup.find_all("style")])
    kaynak_adresleri = ([t.get("src") for t in soup.find_all(["img", "script", "iframe", "source", "video", "audio", "embed"])] +
                        [l.get("href") for l in soup.find_all("link", rel=lambda v: v and "stylesheet" in v)] +
                        [a for t in soup.find_all(["img", "source"], srcset=True) for a in _srcset_adresleri(t["srcset"])] +
                        re.findall(r"""url\(\s*['"]?(http://[^'")\s]+)""", stiller))
    satir_ici = [s.get_text() for s in soup.find_all("script") if not s.get("src") and
                 not (s.get("type") or "").lower().endswith(("json", "template"))]
    js_yonlendirme = any(len(b) < 500 and JS_YONLENDIRME.search(b) for b in satir_ici)
    basliklar = soup.find_all(re.compile(r"^h[1-6]$"))
    # icerigi JavaScript ile olusan sayfa iskeleti: govdede neredeyse hic metin yok ama uygulama kok
    # ogesi ya da cok sayida betik var (React/Vue/Angular). Bu bir tahmindir; kesin sonuc icin render gerekir
    govde_metni = ""
    if soup.body:
        kopya = BeautifulSoup(str(soup.body), "lxml")
        for t in kopya(["script", "style", "noscript", "template"]):
            t.decompose()
        govde_metni = kopya.get_text(" ", strip=True)
    uygulama_koku = bool(soup.find(id=re.compile(r"^(root|app|__next|__nuxt|svelte)$")) or soup.find(attrs={"ng-app": True}))
    js_iskelet = bool(soup.body) and len(govde_metni.split()) < 50 and \
        (uygulama_koku or len(soup.find_all("script", src=True)) >= 5)
    return {
        "baslik_seviyeleri": [int(h.name[1]) for h in basliklar],
        "bos_baslik_sayisi": sum(1 for h in basliklar if h.name != "h1" and not h.get_text(strip=True)),
        "http_kaynak_sayisi": sum(1 for a in kaynak_adresleri if a and a.strip().lower().startswith("http://")),
        "jsonld_sayisi": jsonld,
        "jsonld_hatali": jsonld_hata,
        "schema_turleri": sorted(set(str(t) for t in turler))[:10],
        "schema_eksikleri": sorted(set(eksikler))[:10],
        "mikroveri": bool(soup.find(attrs={"itemscope": True})),
        "viewport": vp.get("content") if vp else None,
        "og_etiketleri": sorted(set(x for x in og if x)),
        "twitter_etiketleri": sorted(set(x for x in tw if x)),
        "hreflang": [h["kod"] for h in hreflanglar][:10],
        "hreflang_baglantilari": hreflanglar[:50],
        "favicon": bool(soup.find("link", attrs={"rel": re.compile(r"icon", re.I)})),
        # tum robots/googlebot iceriklerinin birlesimi (rapor ve geriye uyumluluk icin)
        "robots_meta": ", ".join(c for _, c in robots_etiketleri) or None,
        "robots_etiketleri": robots_etiketleri,
        "robots_yonergeleri": sorted(yonergeler),
        "meta_refresh": ({"sure": refresh_sure, "hedef": urljoin(taban, refresh_hedef)}
                         if refresh and refresh_hedef else None),
        "js_yonlendirme": js_yonlendirme,
        "js_iskelet": js_iskelet,
        "canonicallar": canonicallar,
        "baglantilar": baglantilari_cikar(soup, taban) if taban else [],
        "gorseller": _gorsel_ayrintilari(soup, taban),
        "dis_kaynak_sayisi": (len(soup.find_all("img")) +
                              len(soup.find_all("script", src=True)) +
                              len(soup.find_all("link", rel=lambda v: v and "stylesheet" in v)) +
                              len(soup.find_all("iframe"))),
    }
