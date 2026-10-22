"""Tek dosyalik HTML rapor (internet ve sunucu gerektirmez; e-postayla gonderilebilir, yazdirilabilir).

Flask'in zaten bagimliligi olan Jinja2 ile sablonlar/rapor_cikti.html islenir; degerler
otomatik kacislanir. Rapor tarama sonunda her site klasorune rapor.html olarak yazilir ve
arayuzden /api/html ile indirilebilir.
"""
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .kurallar import ACIKLAMA, CIDDIYET_AGIRLIK, DUZELTME

_ortam = Environment(loader=FileSystemLoader(str(Path(__file__).resolve().parent / "sablonlar")),
                     autoescape=select_autoescape(["html"]))
CIDDIYET_ADI = {"yuksek": "yüksek", "orta": "orta", "dusuk": "düşük", "bilgi": "bilgi"}
COZUM_ADI = {"model": "model çözer", "kural": "kural çözer", "elle": "elle düzeltilir"}


def _ortalama(degerler):
    degerler = [d for d in degerler if d is not None]
    return round(sum(degerler) / len(degerler)) if degerler else None


def html_rapor(kayitlar, ozet, bulgular=(), baslik="SEO denetimi"):
    gecerli = [k for k in kayitlar if not k.get("hata") and not k.get("atlandi") and k.get("once_puanlar")]
    sayfalar = []
    for k in kayitlar:
        sorunlar = sorted(k.get("sorunlar") or [], key=lambda s: -CIDDIYET_AGIRLIK.get(s.get("ciddiyet"), 0))
        sayfalar.append({"k": k, "sorunlar": sorunlar})
    sayac = {c: sum(s["sayfa_sayisi"] for s in ozet if s["ciddiyet"] == c) for c in ("yuksek", "orta", "dusuk")}
    return _ortam.get_template("rapor_cikti.html").render(
        baslik=baslik, tarih=time.strftime("%d.%m.%Y %H:%M"), kayitlar=kayitlar, gecerli=gecerli, sayfalar=sayfalar,
        ozet=ozet, bulgular=list(bulgular), sayac=sayac, ACIKLAMA=ACIKLAMA, DUZELTME=DUZELTME,
        CIDDIYET_ADI=CIDDIYET_ADI, COZUM_ADI=COZUM_ADI,
        ort_once=_ortalama([(k.get("once_puanlar") or {}).get("sayfa") for k in gecerli]),
        ort_sonra=_ortalama([(k.get("sonra_puanlar") or {}).get("sayfa") for k in gecerli]),
        ort_site=_ortalama([(k.get("once_puanlar") or {}).get("site") for k in gecerli]))
