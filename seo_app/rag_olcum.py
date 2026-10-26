"""Bilgi getirme (RAG) kalitesinin olcumu.

Modelin degistirebildigi dort alan (title, meta_description, h1, img_alt) icin, bir sayfanin
sorunlarindan "beklenen alanlar" cikar; getirilen parcalarin bu alanlari kapsayip kapsamadigi
ve ilgisiz parca getirip getirmedigi olculur. Altin etiket elle konmaz, sorun kodlarindan
turetilir (kurallar.ALAN_SORUN); bu yuzden bilgi tabaninin surumu degisse de olcum karsilastirilabilir.
"""
import re

from .kurallar import ALAN_SORUN, IZINLI_ALANLAR

# her sayfada yararli olan genel yonergeler (abartili dil, anahtar kelime yigma vb.) ilgili sayilir.
# Eski bilgi tabaninin konu adlari da eslenir, boylece eski ve yeni surum ayni olcekte olculur.
GENEL_KONULAR = {"genel", "anahtar_kelime_yigma", "yapay_zeka_icerik_riski", "icerik_kalitesi_eeat"}


# Sorun bazinda altin parcalar (bilgi_tabani.json kimlikleri). Bir sorun icin bu parcalardan
# en az biri secildiyse o sorun "isabetli" sayilir. Eski (b01..b20) bilgi tabaninda tanimsizdir.
# 26 Ekim: Google SEO Baslangic Rehberi parcalari (t06, m06, g06, g07) konularinin altin kumesine eklendi;
# bu tarihten onceki olcumlerle sorun isabeti dogrudan karsilastirilamaz (ALTIN_SURUM rapora yazilir).
ALTIN_SURUM = "2026-10-26-rehber"
ALTIN_PARCALAR = {
    "title_yok": {"t01", "t03", "t06"},
    "title_kisa": {"t02", "t03", "t06"},
    "title_uzun": {"t02", "t04", "t05", "t06"},
    "meta_description_yok": {"m01", "m03", "m06"},
    "meta_description_kisa": {"m02", "m03", "m05", "m06"},
    "meta_description_uzun": {"m02", "m04", "m06"},
    "h1_yok": {"h01", "h03"},
    "img_alt_eksik": {"g01", "g02", "g03", "g06", "g07"},
}


def beklenen_alanlar(sorun_kodlari):
    return [a for a in IZINLI_ALANLAR if any(k in sorun_kodlari for k in ALAN_SORUN[a])]


def parca_alani(parca):
    return parca.get("alan") or parca.get("konu") or ""


def sorun_isabeti(secilenler, sorun_kodlari):
    """Altin parcasi tanimli sorunlardan, en az bir altin parcasi secilenlerin orani. Tanimsizsa None."""
    kimlikler = {str(p.get("id")) for p in secilenler}
    tanimli = [k for k in sorun_kodlari if k in ALTIN_PARCALAR]
    # eski bilgi tabaninin kimlikleri b01..b20; altin parcalar yalnizca yeni surum icin tanimli
    if not tanimli or not any(re.fullmatch(r"[tmhgns]\d\d", x) for x in kimlikler):
        return None
    return sum(1 for k in tanimli if ALTIN_PARCALAR[k] & kimlikler) / len(tanimli)


def olc(secilenler, beklenen):
    """Tek bir sayfanin getirme olcumu.
    kapsama : beklenen alanlardan en az bir parcayla kapsananlarin orani
    isabet  : getirilen parcalardan ilgili olanlarin orani (beklenen alan ya da genel yonerge)
    mrr     : beklenen alana ait ilk parcanin sirasinin tersi (1 = ilk sirada)"""
    alanlar = [parca_alani(p) for p in secilenler]
    ilgili = [a in beklenen or a in GENEL_KONULAR for a in alanlar]
    ilk = next((i for i, a in enumerate(alanlar) if a in beklenen), None)
    return {
        "kapsama": (len(set(alanlar) & set(beklenen)) / len(beklenen)) if beklenen else 1.0,
        "isabet": (sum(ilgili) / len(alanlar)) if alanlar else 0.0,
        "mrr": 1.0 / (ilk + 1) if ilk is not None else 0.0,
        "parca_sayisi": len(alanlar),
    }


def ortalama(olcumler):
    if not olcumler:
        return {}
    sonuc = {}
    for k in olcumler[0]:
        degerler = [o[k] for o in olcumler if o.get(k) is not None]
        sonuc[k] = round(sum(degerler) / len(degerler), 3) if degerler else None
    return sonuc
