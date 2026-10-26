"""Duzeltme guven puani (0-1) ve otomatik onay karari: tek yapilandirma.

Her degisiklige plan uretilirken bir guven puani ve (varsa) dusuk guven nedenleri yazilir:
  - kural (deterministik): kural basina sabit deger (KURAL_GUVENI); yan etkisi olabilecek kurallar dusuk
  - sezgisel (yapisal kararlar): kanita gore (SEZGISEL_GUVENI; ureticiler gerekirse kendi degerini verir)
  - model (dil modeli): alan basina taban (MODEL_TABANI), dogrulamadan ilk denemede gecemeyip yeniden
    denenmesi, onerideki kelimelerin kaynakta (sayfa metni + bilgi tabani) gecme orani ve uzun serbest
    metin olmasi puani dusurur. Dogrulamadan gecmeyen oneri hic uygulanamaz (guven 0).
Esigi (ESIK, ayarlar: oto_esik) gecen degisiklikler otomatik onayli gelir; altindakiler onaya duser.
Su degisiklikler guvenden bagimsiz HER ZAMAN onaya duser (zorunlu_onay): [doğrulanmalı] yer tutucusu
iceren (uydurma riski), sayfayi baska bir sayfaya baglayip dizinden dusuren (canonical birlestirme),
indekslemeyi/taramayi kapatan (noindex, nofollow, Disallow ekleyen) ve dosya icerigini silen degisiklikler.
"""
import re

from .cikarma import GENEL_KOKLER, kokler

ESIK = 0.8

KURAL_GUVENI = {
    "_": 0.95,
    "gorsel_boyut_yok": 0.98,          # boyut gorsel dosyasinin kendisinden okunur
    "kirik_ic_link": 0.9,              # karsiligi olmayan kirik baglanti kaldirilir (metin korunur)
    "yapisal_veri_gecersiz": 0.9,      # yalnizca JSON sozdizimi onarilir; degerler degismez
    "sitemap_yonlendirme": 0.92,
    "ic_nofollow": 0.88, "bos_baslik": 0.88, "gorsel_lazy_yok": 0.9,
    # Google icin baslik sayisi belirleyici degil (SEO Baslangic Rehberi); yalnizca erisilebilirlik icin,
    # bu yuzden esigin altinda: otomatik uygulanmaz, onay ister
    "h1_birden_fazla": 0.6,
    "kullanici_baglantisi_isaretsiz": 0.9,   # yalnizca rel niteligine ugc nofollow eklenir
    "render_engelleyen_kaynak": 0.6,   # defer betiklerin calisma anini degistirir
    "blank_noopener_yok": 0.95,        # yalnizca rel'e noopener eklenir; gezinme degismez
    "schema_kurum_logo_yok": 0.85,     # logo adresi sayfadaki "logo" adli gorselden alinir
    "schema_sosyal_profil_yok": 0.85,  # profiller sayfanin kendi verdigi sosyal medya baglantilaridir
    "breadcrumb_yok": 0.85,            # adlar ust sayfalarin H1/title'indan, yol adresten
}
KURAL_NEDENI = {
    "render_engelleyen_kaynak": "defer betiklerin çalışma anını değiştirir; satır içi betikler bunlara bağlıysa sayfa bozulabilir",
}
SEZGISEL_NEDENI = {
    "robots_bilinmeyen_yonerge": "yönerge adı en yakın tanınan adla düzeltildi; düzeltilen satır tarama davranışını değiştirir",
}
SEZGISEL_GUVENI = {
    "_": 0.85,
    "h1_yok": 0.92,                    # sayfanin gorunen basligi H1 yapilir, yeni metin yok
    "canonical_yok": 0.9, "canonical_bos": 0.85, "canonical_coklu": 0.85,
    "hreflang_gecersiz": 0.9, "hreflang_kendine_referans_yok": 0.88, "hreflang_x_default_yok": 0.85,
    "hreflang_donus_yok": 0.85,
    "robots_sayfayi_engelliyor": 0.85, # yalnizca sitemap'te olup baglanti alan sayfanin tam eslesen kurali
    "noindex": 0.82, "sayfa_nofollow": 0.82,
    "yetim_sayfa": 0.85, "derin_sayfa": 0.8,
    "meta_refresh": 0.7,
    "robots_bilinmeyen_yonerge": 0.6, "robots_kaynak_engelliyor": 0.85,
}
MODEL_TABANI = {"title": 0.92, "meta_description": 0.92, "h1": 0.92, "img_alt": 0.88, "baglanti_metni": 0.9,
                "jsonld": 0.85, "paragraf": 0.7}
MODEL_NEDENI = {"paragraf": "uzun, modelin ürettiği serbest metin; yayımlamadan önce okunmalı",
                "jsonld": "yapısal veri modelce yeniden yazıldı"}
YENIDEN_DENEME_CEZASI = 0.12          # kirpilan oneride de uygulanir (kirpma yalnizca marka eki/cumle atar)
DAYANAK_ESIGI = 0.75                  # onerideki icerik kelimelerinin kaynakta gecme orani
KAPATAN = re.compile(r"\b(noindex|nofollow|none)\b|^\s*disallow\s*:", re.I | re.M)


def _dayanak(deger, kaynak_metin):
    """Onerideki (genel olmayan) kelime koklerinin kaynakta gecme orani; olculemezse None."""
    k = kokler(deger or "") - GENEL_KOKLER
    if not k or not kaynak_metin:
        return None
    return len(k & kokler(kaynak_metin)) / len(k)


def zorunlu_onay_nedeni(d, kendi_url=None):
    """Guvenden bagimsiz insan onayi gerektiren degisiklik mi? Nedeni ya da '' dondurur."""
    if d.get("yer_tutucu"):
        return "[doğrulanmalı] yer tutucusu var; değer elle doldurulmalı"
    if d["bulgu"] in ("icerik_tekrar", "icerik_benzer"):
        return "sayfa canonical ile başka sayfaya bağlanıyor; bu sayfa dizinden düşer"
    for p in d.get("parcalar") or []:
        eklenen = KAPATAN.findall(p.get("yeni") or "")
        if eklenen and len(eklenen) > len(KAPATAN.findall(p.get("eski") or "")):
            return "indekslemeyi ya da taramayı kapatan bir yönerge ekleniyor"
        if p.get("eski") and not (p.get("yeni") or "").strip() and len(p["eski"]) > 2000:
            return "büyük bir içerik bloğu siliniyor"
    return ""


def degerlendir(d, kaynak_metin=None, guven=None, nedenler=None):
    """d'ye guven, guven_nedenleri ve zorunlu_onay yazar."""
    nedenler = list(nedenler or [])
    if not d["dogrulama"]["gecti"]:
        g = 0.0
        nedenler.append("doğrulamadan geçmedi: " + d["dogrulama"]["neden"])
    elif guven is not None:
        g = guven
    elif d["uretici"] == "kural":
        g = KURAL_GUVENI.get(d["bulgu"], KURAL_GUVENI["_"])
        if d["bulgu"] in KURAL_NEDENI:
            nedenler.append(KURAL_NEDENI[d["bulgu"]])
    elif d["uretici"] == "sezgisel":
        g = SEZGISEL_GUVENI.get(d["bulgu"], SEZGISEL_GUVENI["_"])
        if d["bulgu"] in SEZGISEL_NEDENI:
            nedenler.append(SEZGISEL_NEDENI[d["bulgu"]])
    else:
        alan = (d.get("duzenleme") or {}).get("alan", "")
        g = MODEL_TABANI.get(alan, 0.85)
        if alan in MODEL_NEDENI:
            nedenler.append(MODEL_NEDENI[alan])
        if d["dogrulama"].get("kirpildi"):
            g -= YENIDEN_DENEME_CEZASI
            nedenler.append("model uzunluk sınırını iki denemede de aştı; öneri marka eki/son cümle atılarak kısaltıldı")
        elif d.get("deneme", 1) > 1:
            g -= YENIDEN_DENEME_CEZASI
            nedenler.append("ilk öneri doğrulamadan geçmedi; ikinci denemede geçti")
        if alan != "jsonld":
            oran = _dayanak(d.get("yeni"), kaynak_metin)
            if oran is not None and oran < DAYANAK_ESIGI:
                g -= round((DAYANAK_ESIGI - oran) * 0.6, 3)
                nedenler.append(f"önerideki kelimelerin %{round(100 * (1 - oran))}'i kaynakta (sayfa + bilgi tabanı) geçmiyor")
    d["guven"] = round(max(0.0, min(1.0, g)), 2)
    d["guven_nedenleri"] = nedenler
    d["zorunlu_onay"] = zorunlu_onay_nedeni(d)
    return d


def otomatik_mi(d, esik=ESIK):
    """Degisiklik insan onayi beklemeden uygulanabilir mi?"""
    return (d["dogrulama"]["gecti"] and not d.get("zorunlu_onay") and not d.get("yer_tutucu")
            and d.get("guven", 0) >= esik)
