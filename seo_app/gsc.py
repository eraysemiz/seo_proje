"""Google Search Console 'Sayfalar' disa aktarimini (CSV) okuyup bulgulari trafige gore onceliklendirme.

API ya da hesap baglantisi yoktur (bulut servisi gerekmez): Search Console > Performans > Sayfalar >
Disa aktar > CSV ile alinan dosya okunur. Turkce ve Ingilizce sutun adlari taninir:
  sayfa: "En çok tıklanan sayfalar" / "Top pages" / "Page"
  "Tıklamalar" / "Clicks", "Gösterimler" / "Impressions", "TO" / "CTR", "Konum" / "Position"
Oncelik puani = gosterim x sayfadaki sorunlarin ciddiyet agirligi: cok gosterim alan sayfadaki yuksek
ciddiyetli sorun once gelir.
"""
import csv
import io
import re
from pathlib import Path
from urllib.parse import urlsplit

SUTUN = {
    "sayfa": ("en çok tıklanan sayfalar", "sayfalar", "sayfa", "top pages", "page", "pages"),
    "tiklama": ("tıklamalar", "tıklama", "clicks"),
    "gosterim": ("gösterimler", "gösterim", "impressions"),
    "ctr": ("to", "tıklama oranı", "ctr"),
    "konum": ("konum", "ortalama konum", "position"),
}
CIDDIYET_AGIRLIGI = {"kritik": 4, "yuksek": 3, "orta": 2, "dusuk": 1}


def adres_anahtari(url):
    """Sema, www ve sondaki egik cizgiden bagimsiz adres anahtari."""
    p = urlsplit((url or "").strip())
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return host + (p.path.rstrip("/") or "") + ("?" + p.query if p.query else "")


def _sayi(metin):
    m = (metin or "").strip().replace("%", "").replace(" ", "")
    if not m:
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", m):          # 1.234 binlik ayracli
        m = m.replace(".", "")
    m = m.replace(",", ".")
    try:
        return float(m)
    except ValueError:
        return None


def oku(yol_ya_da_metin):
    """{adres anahtari: {"url", "tiklama", "gosterim", "ctr", "konum"}}. Taninmayan bicimde ValueError."""
    metin = Path(yol_ya_da_metin).read_text(encoding="utf-8-sig") if "\n" not in str(yol_ya_da_metin) \
        else str(yol_ya_da_metin)
    ayrac = ";" if metin.split("\n", 1)[0].count(";") > metin.split("\n", 1)[0].count(",") else ","
    okuyucu = csv.reader(io.StringIO(metin), delimiter=ayrac)
    baslik = [b.strip().lower() for b in next(okuyucu, [])]
    konum = {}
    for ad, adlar in SUTUN.items():
        konum[ad] = next((i for i, b in enumerate(baslik) if b in adlar), None)
    if konum["sayfa"] is None or konum["gosterim"] is None:
        raise ValueError("Search Console 'Sayfalar' CSV'si tanınmadı (sayfa ve gösterim sütunu gerekli): " +
                         ", ".join(baslik))
    sonuc = {}
    for satir in okuyucu:
        if len(satir) <= konum["sayfa"] or not satir[konum["sayfa"]].startswith("http"):
            continue
        kayit = {"url": satir[konum["sayfa"]].strip()}
        for ad in ("tiklama", "gosterim", "ctr", "konum"):
            kayit[ad] = _sayi(satir[konum[ad]]) if konum[ad] is not None and konum[ad] < len(satir) else None
        sonuc[adres_anahtari(kayit["url"])] = kayit
    return sonuc


def oncelik(rapor, gsc):
    """Tarama raporundaki her sayfa icin trafik ve sorun agirligi. Puan sirasiyla liste dondurur."""
    satirlar = []
    for k in rapor:
        url = k.get("url") or k.get("ad")
        g = gsc.get(adres_anahtari(url)) or {}
        sorunlar = k.get("sorunlar") or []
        agirlik = sum(CIDDIYET_AGIRLIGI.get(s.get("ciddiyet"), 1) for s in sorunlar)
        gosterim = g.get("gosterim") or 0
        satirlar.append({"url": url, "gosterim": gosterim, "tiklama": g.get("tiklama") or 0, "ctr": g.get("ctr"),
                         "konum": g.get("konum"), "sorun_sayisi": len(sorunlar), "sorun_agirligi": agirlik,
                         "oncelik_puani": round(gosterim * agirlik, 1), "gsc_eslesti": bool(g),
                         "en_ciddi_sorunlar": [s["sorun"] for s in sorted(
                             sorunlar, key=lambda s: -CIDDIYET_AGIRLIGI.get(s.get("ciddiyet"), 1))[:5]]})
    return sorted(satirlar, key=lambda s: (-s["oncelik_puani"], -s["sorun_agirligi"]))
