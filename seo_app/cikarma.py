"""HTML'den SEO denetimi icin gerekli verilerin cikarilmasi."""
import json
import os
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

ALT_LIMIT = 12          # bir sayfada modelden en fazla kac gorsel icin alt metin istenir


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


def dosya_adi(src):
    return os.path.basename(unquote(src.split("?")[0]))[:60]


def extract(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    meta = soup.find("meta", attrs={"name": "description"})
    body = soup.body or soup
    imgs = gorseller(soup)                 # noscript silinmeden once, apply_fixes ile ayni sira
    for t in body(["script", "style", "noscript"]):
        t.decompose()
    text = re.sub(r"\s+", " ", body.get_text(" ", strip=True))
    h1_metinleri = [h.get_text(strip=True) for h in soup.find_all("h1")]
    # alt niteligi hic olmayan gorsel eksiktir; alt="" ise dekoratif gorsel icin bilincli
    # ve gecerli bir tercihtir (WCAG), eksik sayilmaz
    eksik = [(n, i) for n, i in enumerate(imgs) if i.get("alt") is None]
    sonuc = {
        "lang": (soup.html.get("lang") if soup.html else None),
        "title": soup.title.get_text(strip=True) if soup.title else None,
        "meta_description": meta.get("content", "").strip() if meta else None,
        "canonical": bool(soup.find("link", rel="canonical")),
        "h1": [t for t in h1_metinleri if t],          # yalnizca metni olan H1'ler sayilir
        "h1_bos_sayisi": sum(1 for t in h1_metinleri if not t),
        "h2": [h.get_text(strip=True) for h in soup.find_all("h2")][:5],
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
    icerik_metni = icerik.get_text(" ", strip=True)
    sonuc["icerik_kokleri"] = kokler(icerik_metni)          # odak terim denetimi icin (title haric)
    sonuc["kelime_kokleri"] = kokler(" ".join([
        icerik_metni, sonuc["title"] or "", sonuc["meta_description"] or "", " ".join(sonuc["h1"])]))
    sonuc["sayfa_kelimeleri"] = set(kelimeler(" ".join([
        sonuc["title"] or "", sonuc["meta_description"] or "", " ".join(sonuc["h1"])])))
    return sonuc


def yapisal_veri(html):
    """Yapisal veri, mobil uyum ve paylasim etiketleri (tamami sayfanin HTML'inden gorulebilir)."""
    soup = BeautifulSoup(html, "lxml")
    jsonld, jsonld_hata, turler = 0, 0, []
    for s in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        jsonld += 1
        try:
            veri = json.loads(s.string or s.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            jsonld_hata += 1
            continue
        for nesne in (veri if isinstance(veri, list) else [veri]):
            if isinstance(nesne, dict) and nesne.get("@type"):
                t = nesne["@type"]
                turler += t if isinstance(t, list) else [t]
    vp = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
    og = [m.get("property") for m in soup.find_all("meta", attrs={"property": re.compile(r"^og:", re.I)})]
    tw = [m.get("name") for m in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:", re.I)})]
    robots_meta = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    # karisik icerik: sayfanin yukledigi kaynaklardan http:// ile gelenler (baglantilar sayilmaz)
    kaynak_adresleri = ([t.get("src") for t in soup.find_all(["img", "script", "iframe", "source", "video", "audio"])] +
                        [l.get("href") for l in soup.find_all("link", rel=lambda v: v and "stylesheet" in v)])
    return {
        "baslik_seviyeleri": [int(h.name[1]) for h in soup.find_all(re.compile(r"^h[1-6]$"))],
        "http_kaynak_sayisi": sum(1 for a in kaynak_adresleri if a and a.strip().lower().startswith("http://")),
        "jsonld_sayisi": jsonld,
        "jsonld_hatali": jsonld_hata,
        "schema_turleri": sorted(set(str(t) for t in turler))[:10],
        "mikroveri": bool(soup.find(attrs={"itemscope": True})),
        "viewport": vp.get("content") if vp else None,
        "og_etiketleri": sorted(set(x for x in og if x)),
        "twitter_etiketleri": sorted(set(x for x in tw if x)),
        "hreflang": [l.get("hreflang") for l in soup.find_all("link", attrs={"hreflang": True})][:10],
        "favicon": bool(soup.find("link", attrs={"rel": re.compile(r"icon", re.I)})),
        "robots_meta": robots_meta.get("content") if robots_meta else None,
        "dis_kaynak_sayisi": (len(soup.find_all("img")) +
                              len(soup.find_all("script", src=True)) +
                              len(soup.find_all("link", rel=lambda v: v and "stylesheet" in v)) +
                              len(soup.find_all("iframe"))),
    }
