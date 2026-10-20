"""Onerilerin HTML'e islenmesi ve model gerektirmeyen (deterministik) duzeltmeler."""
from bs4 import BeautifulSoup


def apply_fixes(html, fixes):
    """Modelden gelen ve dogrulamadan gecen onerileri HTML'e yazar."""
    soup = BeautifulSoup(html, "lxml")
    for f in fixes:
        v = f["yeni_deger"].strip()
        if not v:
            continue
        if f["alan"] == "title":
            if soup.title:
                soup.title.string = v
            elif soup.head:
                tag = soup.new_tag("title")
                tag.string = v
                soup.head.append(tag)
        elif f["alan"] == "meta_description":
            tag = soup.find("meta", attrs={"name": "description"})
            if tag:
                tag["content"] = v
            elif soup.head:
                soup.head.append(soup.new_tag("meta", attrs={"name": "description", "content": v}))
        elif f["alan"] == "h1":
            if not soup.find("h1") and soup.body:
                tag = soup.new_tag("h1")
                tag.string = v
                soup.body.insert(0, tag)
        elif f["alan"] == "img_alt":
            for img in soup.find_all("img"):
                if img.get("src") == f.get("hedef_src", f.get("hedef")) and not (img.get("alt") or "").strip():
                    img["alt"] = v
    return str(soup)


def kural_duzelt(html, kodlar, site_url, dil):
    """Model gerektirmeyen, belirli (deterministik) duzeltmeler.
    (yeni_html, uygulananlar) dondurur."""
    soup = BeautifulSoup(html, "lxml")
    uygulanan = []
    if "canonical_yok" in kodlar and site_url and soup.head:
        soup.head.append(soup.new_tag("link", rel="canonical", href=site_url))
        uygulanan.append("canonical_eklendi: " + site_url)
    if "html_lang_yok" in kodlar and soup.html:
        soup.html["lang"] = dil
        uygulanan.append("html_lang_eklendi: " + dil)
    if "h1_birden_fazla" in kodlar:
        h1ler = soup.find_all("h1")
        for h in h1ler[1:]:
            h.name = "h2"
        uygulanan.append("h1_fazlalari_h2_yapildi: " + str(max(len(h1ler) - 1, 0)))
    if "viewport_yok" in kodlar and soup.head:
        soup.head.insert(0, soup.new_tag("meta", attrs={
            "name": "viewport", "content": "width=device-width, initial-scale=1"}))
        uygulanan.append("viewport_eklendi")
    if "og_etiketleri_yok" in kodlar and soup.head:
        # Open Graph etiketleri duzeltilmis title/meta degerlerinden turetilir; yeni bilgi uretilmez
        baslik = soup.title.get_text(strip=True) if soup.title else None
        md = soup.find("meta", attrs={"name": "description"})
        aciklama = md.get("content") if md else None
        eklenen = []
        if baslik:
            soup.head.append(soup.new_tag("meta", attrs={"property": "og:title", "content": baslik}))
            eklenen.append("og:title")
        if aciklama:
            soup.head.append(soup.new_tag("meta", attrs={"property": "og:description", "content": aciklama}))
            eklenen.append("og:description")
        if site_url:
            soup.head.append(soup.new_tag("meta", attrs={"property": "og:url", "content": site_url}))
            eklenen.append("og:url")
        if eklenen:
            soup.head.append(soup.new_tag("meta", attrs={"property": "og:type", "content": "website"}))
            uygulanan.append("og_etiketleri_eklendi: " + ", ".join(eklenen + ["og:type"]))
    return str(soup), uygulanan
