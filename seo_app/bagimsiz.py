"""Bagimsiz olcum: Google PageSpeed Insights (Lighthouse) SEO puani ve Core Web Vitals.

Aracin kendi puani (kurallar.puan) kendi kurallariyla kendi basarisini olctugu icin
donguseldir. Lighthouse SEO puani bundan bagimsiz bir karsilastirma noktasi saglar.
Ayni istekte performans kategorisi de alinir: gercek kullanici (CrUX saha) verisi varsa
LCP, INP ve CLS ondan, yoksa laboratuvar olcumunden (LCP, CLS, INP yerine TBT) okunur.

Sinirlar:
  - API yalnizca internetten erisilebilen canli adresleri olcer; duzeltilmis HTML yerel bir
    dosya oldugu icin "sonra" puani bu yontemle alinamaz. localhost ve ozel ag adresleri
    (127.0.0.1, 10.x, 192.168.x, tek parcali makine adlari vb.) icin API hic cagrilmaz:
    Google bu adreslere ulasamaz, her istek ~17 sn bekleyip FAILED_DOCUMENT_REQUEST doner.
  - Anahtarsiz kullanimda Google'in paylasimli gunluk kotasi cabuk dolar (HTTP 429).
    Ucretsiz bir API anahtari PSI_API_ANAHTARI ortam degiskenine yazilarak kullanilabilir.
"""
import ipaddress
import os
from urllib.parse import urlsplit

import requests

from .kurallar import cozum_yolu

PSI_ADRESI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# web.dev esikleri: (iyi, kotu) -> iyi altinda sorun yok, ikisi arasi "iyilestirilmeli", kotu ustu "kotu"
CWV_ESIKLERI = {"lcp_ms": (2500, 4000), "inp_ms": (200, 500), "cls": (0.1, 0.25), "tbt_ms": (200, 600)}
AGIR_SAYFA_BAYT = 3 * 1024 * 1024


def _gizle(metin, anahtar):
    """Hata mesajlari istek adresini (key=... dahil) icerebilir; anahtar rapora sizmasin."""
    return metin.replace(anahtar, "***") if anahtar else metin


def _saha_verisi(veri):
    """CrUX saha verisi: once sayfa, yoksa alan adi (origin) geneli. Bulunamazsa None."""
    for anahtar, kapsam in (("loadingExperience", "sayfa"), ("originLoadingExperience", "alan adı")):
        m = (veri.get(anahtar) or {}).get("metrics") or {}
        lcp = (m.get("LARGEST_CONTENTFUL_PAINT_MS") or {}).get("percentile")
        inp = (m.get("INTERACTION_TO_NEXT_PAINT") or {}).get("percentile")
        cls = (m.get("CUMULATIVE_LAYOUT_SHIFT_SCORE") or {}).get("percentile")
        if lcp is not None or inp is not None or cls is not None:
            return {"kaynak": "saha (" + kapsam + ", 75. yüzdelik)", "lcp_ms": lcp, "inp_ms": inp,
                    "cls": None if cls is None else cls / 100}
    return None


def yerel_adres_mi(url):
    """Adres internetten erisilemeyen bir makineyi mi gosteriyor? (localhost, loopback, ozel ag,
    link-local, tek parcali makine adi ya da .local/.localhost/.internal alan adi). DNS sorgusu
    yapilmaz; yalnizca adresin kendisine bakilir."""
    ana = (urlsplit(url if "//" in url else "//" + url).hostname or "").rstrip(".").lower()
    if not ana:
        return False
    try:
        ip = ipaddress.ip_address(ana)
    except ValueError:
        return "." not in ana or ana.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa"))
    return not ip.is_global


def pagespeed_seo(url, anahtar=None, strateji="mobile", zaman_asimi=120):
    """Bir adresin Lighthouse SEO puanini (0-100), basarisiz SEO denetimlerini, performans puanini
    ve Core Web Vitals degerlerini dondurur. Hata durumunda istisna firlatmaz; 'hata' alani doldurulur.
    Yerel/ozel ag adreslerinde API cagrilmaz; 'atlandi' True olur."""
    anahtar = anahtar or os.environ.get("PSI_API_ANAHTARI")
    parametreler = [("url", url), ("category", "SEO"), ("category", "PERFORMANCE"), ("strategy", strateji)]
    if anahtar:
        parametreler.append(("key", anahtar))
    sonuc = {"kaynak": "pagespeed_insights", "strateji": strateji, "seo_puani": None,
             "basarisiz_denetimler": [], "lighthouse_surumu": None, "performans_puani": None,
             "cwv": None, "hata": None}
    if yerel_adres_mi(url):
        sonuc.update(atlandi=True, hata="yerel ya da özel ağ adresi; PageSpeed yalnızca internetten "
                                        "erişilebilen adresleri ölçebilir")
        return sonuc
    try:
        r = requests.get(PSI_ADRESI, params=parametreler, timeout=zaman_asimi)
        veri = r.json()
    except (requests.RequestException, ValueError) as e:
        sonuc["hata"] = type(e).__name__ + ": " + _gizle(str(e), anahtar)[:200]
        return sonuc
    if r.status_code != 200 or "error" in veri:
        hata = veri.get("error", {}) if isinstance(veri, dict) else {}
        sonuc["hata"] = "HTTP " + str(r.status_code) + ": " + _gizle(str(hata.get("message", "")), anahtar)[:200]
        return sonuc
    try:
        lr = veri["lighthouseResult"]
        seo = lr["categories"]["seo"]
        sonuc["seo_puani"] = round(seo["score"] * 100) if seo.get("score") is not None else None
        kimlikler = {a["id"] for a in seo.get("auditRefs", [])}
        denetimler = lr.get("audits", {})
        sonuc["basarisiz_denetimler"] = sorted(k for k, v in denetimler.items()
                                               if k in kimlikler and v.get("score") == 0)
        sonuc["lighthouse_surumu"] = lr.get("lighthouseVersion")
        perf = lr["categories"].get("performance") or {}
        if perf.get("score") is not None:
            sonuc["performans_puani"] = round(perf["score"] * 100)
        sayi = lambda kimlik: (denetimler.get(kimlik) or {}).get("numericValue")
        lab = {"kaynak": "laboratuvar (Lighthouse)", "lcp_ms": sayi("largest-contentful-paint"),
               "inp_ms": None, "cls": sayi("cumulative-layout-shift"), "tbt_ms": sayi("total-blocking-time")}
        saha = _saha_verisi(veri)
        cwv = {**lab, **{k: v for k, v in (saha or {}).items() if v is not None}} if saha else lab
        cwv["toplam_bayt"] = sayi("total-byte-weight")
        if any(cwv.get(k) is not None for k in ("lcp_ms", "inp_ms", "cls", "tbt_ms", "toplam_bayt")):
            sonuc["cwv"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in cwv.items()}
    except (KeyError, TypeError) as e:
        sonuc["hata"] = "beklenmeyen yanıt biçimi: " + type(e).__name__
    return sonuc


def _seviye(deger, esik):
    if deger is None:
        return None
    iyi, kotu = esik
    return "orta" if deger > kotu else "dusuk" if deger > iyi else None


def cwv_sorunlari(olcum):
    """PageSpeed olcumunden performans bulgulari (site katmani). Saha verisi yoksa INP yerine
    laboratuvardaki Total Blocking Time kullanilir; bu ayrintida belirtilir."""
    cwv = (olcum or {}).get("cwv") or {}
    sorunlar = []

    def add(kod, ciddiyet, ayrinti):
        sorunlar.append({"sorun": kod, "ciddiyet": ciddiyet, "ayrinti": ayrinti, "katman": "site",
                         "cozum_yolu": cozum_yolu(kod)})
    kaynak = cwv.get("kaynak", "")
    s = _seviye(cwv.get("lcp_ms"), CWV_ESIKLERI["lcp_ms"])
    if s:
        add("cwv_lcp_yavas", s, f"LCP {cwv['lcp_ms'] / 1000:.1f} sn · {kaynak}")
    if cwv.get("inp_ms") is not None:
        s = _seviye(cwv["inp_ms"], CWV_ESIKLERI["inp_ms"])
        if s:
            add("cwv_inp_yavas", s, f"INP {round(cwv['inp_ms'])} ms · {kaynak}")
    else:
        s = _seviye(cwv.get("tbt_ms"), CWV_ESIKLERI["tbt_ms"])
        if s:
            add("cwv_inp_yavas", s, f"TBT {round(cwv['tbt_ms'])} ms · laboratuvar (INP saha verisi yok)")
    s = _seviye(cwv.get("cls"), CWV_ESIKLERI["cls"])
    if s:
        add("cwv_cls_yuksek", s, f"CLS {cwv['cls']:.2f} · {kaynak}")
    if (cwv.get("toplam_bayt") or 0) > AGIR_SAYFA_BAYT:
        add("sayfa_agir", "dusuk", f"{cwv['toplam_bayt'] / 1048576:.1f} MB")
    return sorunlar
