"""Tek dosyalik HTML rapor (internet ve sunucu gerektirmez; e-postayla gonderilebilir, yazdirilabilir).

Flask'in zaten bagimliligi olan Jinja2 ile sablonlar/rapor_cikti.html islenir; degerler
otomatik kacislanir. Rapor tarama sonunda her site klasorune rapor.html olarak yazilir ve
arayuzden /api/html ile indirilebilir.
"""
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import kategoriler as kat
from .kurallar import ACIKLAMA, CIDDIYET_AGIRLIK, DUZELTME

_ortam = Environment(loader=FileSystemLoader(str(Path(__file__).resolve().parent / "sablonlar")),
                     autoescape=select_autoescape(["html"]))
CIDDIYET_ADI = {"yuksek": "yüksek", "orta": "orta", "dusuk": "düşük", "bilgi": "bilgi"}
# rapor tek dosyalik ve betiksizdir; kategori aciklamasi title niteligiyle (fare ustunde) gosterilir
KATEGORI_IPUCU = {
    "kural": "Deterministik bir kuralla güvenle düzeltilir (lang, charset, viewport, kırık iç bağlantı, görsel boyutu, "
             "robots.txt/sitemap). Yönetici modunda toplu onaylanabilir.",
    "yz": "Yerel model ya da sezgisel bir yöntem öneri üretir; insan onayı gerekir. Canonical, noindex, yönlendirme ve "
          "hreflang gibi yapısal kararlar yüksek risklidir.",
    "elle": "Yapay zekânın kapsamı dışında (sunucu/barındırma, HTTPS, önbellek, gerçek görsel, site dışı SEO); "
            "yalnızca öneri olarak raporlanır.",
}


def kategori_etiketi(kod):
    k = kat.kategori(kod)
    return {"ad": kat.KATEGORI_ADI[k] + (" · yüksek risk" if kat.risk(kod) == "yuksek" else ""),
            "ipucu": KATEGORI_IPUCU[k]}


def _ortalama(degerler):
    degerler = [d for d in degerler if d is not None]
    return round(sum(degerler) / len(degerler)) if degerler else None


def html_rapor(kayitlar, ozet, bulgular=(), baslik="SEO denetimi", yonetici=None):
    """yonetici: yalnizca yonetici modu klasorlerinde verilir (yonetici._analiz_raporunu_guncelle);
    her sorunun guncel durumu, guncel sayfa puani ve asama metrikleri gosterilir."""
    gecerli = [k for k in kayitlar if not k.get("hata") and not k.get("atlandi") and k.get("once_puanlar")]
    sayfalar = []
    for k in kayitlar:
        sorunlar = sorted(k.get("sorunlar") or [], key=lambda s: -CIDDIYET_AGIRLIK.get(s.get("ciddiyet"), 0))
        sayfalar.append({"k": k, "sorunlar": sorunlar})
    sayac = {c: sum(s["sayfa_sayisi"] for s in ozet if s["ciddiyet"] == c) for c in ("yuksek", "orta", "dusuk")}
    ort_sonra = _ortalama([(k.get("sonra_puanlar") or {}).get("sayfa") for k in gecerli])
    if yonetici:                     # yonetici modunda "sonra" kopya HTML degil, son yeniden taramanin olcumu
        son = [a for a in yonetici["asamalar"] if a["olculdu"] and a["ad"] != "baslangic"]
        ort_sonra = son[-1]["puanlar"]["sayfa"] if son else None
    return _ortam.get_template("rapor_cikti.html").render(
        baslik=baslik, tarih=time.strftime("%d.%m.%Y %H:%M"), kayitlar=kayitlar, gecerli=gecerli, sayfalar=sayfalar,
        ozet=ozet, bulgular=list(bulgular), sayac=sayac, ACIKLAMA=ACIKLAMA, DUZELTME=DUZELTME,
        CIDDIYET_ADI=CIDDIYET_ADI, kategori_etiketi=kategori_etiketi, yonetici=yonetici,
        ort_once=_ortalama([(k.get("once_puanlar") or {}).get("sayfa") for k in gecerli]),
        ort_sonra=ort_sonra,
        ort_site=_ortalama([(k.get("once_puanlar") or {}).get("site") for k in gecerli]))
