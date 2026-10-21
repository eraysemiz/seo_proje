"""Bagimsiz olcum: Google PageSpeed Insights (Lighthouse) SEO puani.

Aracin kendi puani (kurallar.puan) kendi kurallariyla kendi basarisini olctugu icin
donguseldir. Lighthouse SEO puani bundan bagimsiz bir karsilastirma noktasi saglar.

Sinirlar:
  - API yalnizca internetten erisilebilen canli adresleri olcer; duzeltilmis HTML yerel bir
    dosya oldugu icin "sonra" puani bu yontemle alinamaz.
  - Anahtarsiz kullanimda Google'in paylasimli gunluk kotasi cabuk dolar (HTTP 429).
    Ucretsiz bir API anahtari PSI_API_ANAHTARI ortam degiskenine yazilarak kullanilabilir.
"""
import os

import requests

PSI_ADRESI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def pagespeed_seo(url, anahtar=None, strateji="mobile", zaman_asimi=120):
    """Bir adresin Lighthouse SEO puanini (0-100) ve basarisiz SEO denetimlerini dondurur.
    Hata durumunda istisna firlatmaz; 'hata' alani doldurulur."""
    anahtar = anahtar or os.environ.get("PSI_API_ANAHTARI")
    parametreler = {"url": url, "category": "SEO", "strategy": strateji}
    if anahtar:
        parametreler["key"] = anahtar
    sonuc = {"kaynak": "pagespeed_insights", "strateji": strateji, "seo_puani": None,
             "basarisiz_denetimler": [], "lighthouse_surumu": None, "hata": None}
    try:
        r = requests.get(PSI_ADRESI, params=parametreler, timeout=zaman_asimi)
        veri = r.json()
    except (requests.RequestException, ValueError) as e:
        sonuc["hata"] = type(e).__name__ + ": " + str(e)[:200]
        return sonuc
    if r.status_code != 200 or "error" in veri:
        hata = veri.get("error", {}) if isinstance(veri, dict) else {}
        sonuc["hata"] = "HTTP " + str(r.status_code) + ": " + str(hata.get("message", ""))[:200]
        return sonuc
    try:
        lr = veri["lighthouseResult"]
        seo = lr["categories"]["seo"]
        sonuc["seo_puani"] = round(seo["score"] * 100) if seo.get("score") is not None else None
        kimlikler = {a["id"] for a in seo.get("auditRefs", [])}
        sonuc["basarisiz_denetimler"] = sorted(k for k, v in lr.get("audits", {}).items()
                                               if k in kimlikler and v.get("score") == 0)
        sonuc["lighthouse_surumu"] = lr.get("lighthouseVersion")
    except (KeyError, TypeError) as e:
        sonuc["hata"] = "beklenmeyen yanit bicimi: " + type(e).__name__
    return sonuc
