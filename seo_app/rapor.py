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
    tur_ciddiyeti = {s["sorun"]: s.get("ciddiyet") for s in ozet}
    sayfalar = []
    for k in kayitlar:
        sorunlar = sorted(k.get("sorunlar") or [], key=lambda s: -CIDDIYET_AGIRLIK.get(s.get("ciddiyet"), 0))
        p = {"k": k, "sorunlar": sorunlar}
        if yonetici:
            # yonetici modu: sayfanin listeleri bulgu durumlarindan (tarama geneli bulgular dahil); aktif ve
            # cozulen ayri; ciddiyet ve ayrinti baslangic kaydindan
            kayit_sorunu = {s["sorun"]: s for s in sorunlar}
            bs, takma = [], []
            for b in yonetici["sayfa_bulgulari"].get(k.get("ad"), []):
                if b.get("site_ayari"):          # site geneli ayarlar bir kez, ayri bolumde gosterilir
                    continue
                if b.get("takma"):               # asil bulguya bagli: orada sayilir ve gosterilir
                    takma.append(b)
                    continue
                s = kayit_sorunu.get(b["sorun"], {})
                bs.append(dict(b, ciddiyet=s.get("ciddiyet") or tur_ciddiyeti.get(b["sorun"]), ayrinti=s.get("ayrinti")))
            bs.sort(key=lambda b: -CIDDIYET_AGIRLIK.get(b["ciddiyet"], 0))
            p.update(aktif=[b for b in bs if b["aktif"]], cozulen=[b for b in bs if not b["aktif"]],
                     sayac=yonetici["sayfalar"].get(k.get("ad")), takma=takma)
        sayfalar.append(p)
    sayac = {c: sum(s["sayfa_sayisi"] for s in ozet if s["ciddiyet"] == c) for c in ("yuksek", "orta", "dusuk")}
    ort_sonra = _ortalama([(k.get("sonra_puanlar") or {}).get("sayfa") for k in gecerli])
    if yonetici:                     # yonetici modunda "sonra" kopya HTML degil, son yeniden taramanin olcumu
        son = [a for a in yonetici["asamalar"] if a["olculdu"] and a["ad"] != "baslangic"]
        ort_sonra = son[-1]["puanlar"]["sayfa"] if son else None
        # sorun turu basina: kac sayfada aktif, kac sayfada cozuldu (bulgu durumlarindan); site geneli
        # ayarlar kendi bolumunde bir kez gosterilir
        site_kodlari = {s["sorun"] for s in yonetici["site_ayarlari"]}
        ozet = [dict(s, **yonetici["tur_sayaclari"].get(s["sorun"], {"aktif": s["sayfa_sayisi"], "cozulen": 0}))
                for s in ozet if s["sorun"] not in site_kodlari]
        for s in yonetici["site_ayarlari"]:
            s["ciddiyet"] = tur_ciddiyeti.get(s["sorun"])
    return _ortam.get_template("rapor_cikti.html").render(
        baslik=baslik, tarih=time.strftime("%d.%m.%Y %H:%M"), kayitlar=kayitlar, gecerli=gecerli, sayfalar=sayfalar,
        ozet=ozet, bulgular=list(bulgular), sayac=sayac, ACIKLAMA=ACIKLAMA, DUZELTME=DUZELTME,
        CIDDIYET_ADI=CIDDIYET_ADI, kategori_etiketi=kategori_etiketi, yonetici=yonetici,
        ort_once=_ortalama([(k.get("once_puanlar") or {}).get("sayfa") for k in gecerli]),
        ort_sonra=ort_sonra,
        ort_site=_ortalama([(k.get("once_puanlar") or {}).get("site") for k in gecerli]))
