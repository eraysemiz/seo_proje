"""Bulgu turlerinin duzeltme kategorisi: tek yapilandirma.

Her sorun kodu uc kategoriden birine girer:
  kural -> "Kural çözer": deterministik bir kuralla guvenle duzeltilir (yonetici modunda toplu onayla).
  yz    -> "YZ önerir": yerel model (ya da sezgisel bir yontem) oneri uretir; insan onayi gerekir.
           Yapisal kararlar (canonical, noindex, yonlendirme, hreflang, robots) "yuksek" risklidir.
  elle  -> "Elle düzeltilir": sunucu/barindirma, HTTPS, gercek gorsel uretimi, site disi SEO gibi
           yapay zekanin kapsami disindaki isler; yalnizca raporda oneri olarak kalir.

Kategori bir onerinin nasil uretildigini anlatir; onay gerekip gerekmedigini guven puani belirler
(guven.py): esigi gecen oneriler otomatik onayli gelir, gecmeyenler ve indekslemeyi daraltanlar onaya duser.

Bu modul yalnizca gosterim ve yonetici modu icindir. kurallar.cozum_yolu analiz akisini (modele
hangi sorunlarin gidecegini ve cozum oranlarini) belirler ve degismez; standart modun analizi ve
puanlari bu yapilandirmadan etkilenmez.
"""
from .kurallar import ACIKLAMA, DUZELTME

KATEGORI_ADI = {"kural": "Kural çözer", "yz": "YZ önerir", "elle": "Elle düzeltilir"}
RISK_ADI = {"dusuk": "düşük risk", "yuksek": "yüksek risk"}

# kod: (kategori, risk). Listede olmayan kodlar "elle" kabul edilir.
KATEGORI = {
    # --- Kural çözer ---
    "html_lang_yok": ("kural", "dusuk"), "charset_yok": ("kural", "dusuk"),
    "viewport_yok": ("kural", "dusuk"), "viewport_sorunlu": ("kural", "dusuk"),
    "h1_birden_fazla": ("kural", "dusuk"), "og_etiketleri_yok": ("kural", "dusuk"),
    "og_gorsel_yok": ("kural", "dusuk"), "twitter_card_yok": ("kural", "dusuk"),
    "kirik_ic_link": ("kural", "dusuk"), "ic_link_yonlendirme": ("kural", "dusuk"),
    "gorsel_boyut_yok": ("kural", "dusuk"), "gorsel_lazy_yok": ("kural", "dusuk"),
    "ilk_gorsel_lazy": ("kural", "dusuk"), "canonical_goreli": ("kural", "dusuk"),
    "ic_nofollow": ("kural", "dusuk"), "bos_baslik": ("kural", "dusuk"),
    "robots_sitemap_bildirilmemis": ("kural", "dusuk"), "sitemap_hatali_adres": ("kural", "dusuk"),
    "sayfa_sitemapte_yok": ("kural", "dusuk"), "sitemap_olu_adres": ("kural", "dusuk"),
    "sitemap_yonlendirme": ("kural", "dusuk"), "render_engelleyen_kaynak": ("kural", "dusuk"),
    # --- YZ önerir: icerik ---
    "title_yok": ("yz", "dusuk"), "title_kisa": ("yz", "dusuk"), "title_uzun": ("yz", "dusuk"),
    "title_genis": ("yz", "dusuk"), "title_tekrar": ("yz", "dusuk"), "title_h1_uyumsuz": ("yz", "dusuk"),
    "title_icerikle_uyumsuz": ("yz", "dusuk"),
    "meta_description_yok": ("yz", "dusuk"), "meta_description_kisa": ("yz", "dusuk"),
    "meta_description_uzun": ("yz", "dusuk"), "meta_tekrar": ("yz", "dusuk"),
    "h1_yok": ("yz", "dusuk"), "h1_bos": ("yz", "dusuk"), "h1_tekrar": ("yz", "dusuk"),
    "img_alt_eksik": ("yz", "dusuk"), "icerik_az": ("yz", "dusuk"),
    "yapisal_veri_yok": ("yz", "dusuk"), "yapisal_veri_gecersiz": ("yz", "dusuk"),
    "yapisal_veri_eksik_alan": ("yz", "dusuk"), "schema_kurum_turu_yok": ("yz", "dusuk"),
    "yetim_sayfa": ("yz", "dusuk"), "derin_sayfa": ("yz", "dusuk"), "ic_baglanti_yok": ("yz", "dusuk"),
    "bos_baglanti_metni": ("yz", "dusuk"), "genel_baglanti_metni": ("yz", "dusuk"),
    # --- YZ önerir: yapisal kararlar (yuksek risk) ---
    "canonical_yok": ("yz", "yuksek"), "canonical_capraz": ("yz", "yuksek"), "canonical_bos": ("yz", "yuksek"),
    "canonical_coklu": ("yz", "yuksek"), "noindex": ("yz", "yuksek"), "sayfa_nofollow": ("yz", "yuksek"),
    "noindex_canonical_catismasi": ("yz", "yuksek"), "noindex_sitemapte": ("yz", "yuksek"),
    "meta_refresh": ("yz", "yuksek"), "js_yonlendirme": ("yz", "yuksek"),
    "hreflang_gecersiz": ("yz", "yuksek"), "hreflang_x_default_yok": ("yz", "yuksek"),
    "hreflang_kendine_referans_yok": ("yz", "yuksek"), "hreflang_donus_yok": ("yz", "yuksek"),
    "icerik_tekrar": ("yz", "yuksek"), "icerik_benzer": ("yz", "yuksek"),
    "robots_sayfayi_engelliyor": ("yz", "yuksek"), "robots_tum_siteyi_engelliyor": ("yz", "yuksek"),
}

# Yuksek riskli onerilerle birlikte gosterilen olasi etki
ETKI = {
    "canonical_yok": "Canonical, arama motoruna hangi adresin dizine alınacağını söyler. Yanlış adres seçilirse sayfa dizinden düşebilir.",
    "canonical_capraz": "Sayfa gerçekten başka bir sayfanın kopyasıysa canonical'ı kendisine çevirmek kopya içeriği dizine sokar; asıl sayfaysa doğru düzeltmedir.",
    "canonical_bos": "Canonical'ın gösterdiği adres dizine alınacak adres olarak yorumlanır.",
    "canonical_coklu": "Fazla canonical'lar silinir; kalan adres dizine alınacak adres olur.",
    "noindex": "noindex kaldırılırsa sayfa arama sonuçlarında görünmeye başlar. Sayfanın gizli kalması gerekiyorsa uygulamayın.",
    "sayfa_nofollow": "nofollow kaldırılırsa arama motoru sayfadaki bağlantıları izler ve değer aktarır.",
    "noindex_canonical_catismasi": "Çelişkiyi gidermek için iki yönergeden biri kaldırılır; hangisinin kaldırılacağı sayfanın dizinde kalıp kalmayacağını belirler.",
    "noindex_sitemapte": "Sayfa ya sitemap'ten çıkarılır ya da noindex kaldırılır; ikisi farklı sonuç verir.",
    "meta_refresh": "Meta refresh kaldırılırsa ziyaretçiler artık otomatik yönlendirilmez; kalıcı taşımalarda sunucuda 301 tanımlanmalıdır.",
    "js_yonlendirme": "JavaScript yönlendirmesi kaldırılırsa ziyaretçiler otomatik yönlendirilmez.",
    "hreflang_gecersiz": "hreflang kodu değişirse arama motoru sayfayı farklı dil/bölge kullanıcılarına gösterebilir.",
    "hreflang_x_default_yok": "x-default, dili eşleşmeyen kullanıcılara gösterilecek sürümü belirler.",
    "hreflang_kendine_referans_yok": "hreflang kümesine sayfanın kendisi eklenir; küme tutarlı değilse arama motoru tüm hreflang bilgisini yok sayabilir.",
    "hreflang_donus_yok": "Karşı sayfaya geri dönüş bağlantısı eklenir; iki sayfa birbirinin dil sürümü olarak eşleşir.",
    "icerik_tekrar": "Kopya sayfa canonical ile asıl sayfaya bağlanır; kopya sayfa dizinden düşer.",
    "icerik_benzer": "Benzer sayfa canonical ile asıl sayfaya bağlanır; benzer sayfa dizinden düşer. Sayfa özgünleştirilecekse uygulamayın.",
    "robots_sayfayi_engelliyor": "robots.txt kuralı değişirse sayfa taranmaya başlar.",
    "robots_tum_siteyi_engelliyor": "robots.txt değişirse tüm site taranmaya açılır.",
}

# Yalnizca yonetici modunun dosya duzeyindeki denetimlerinde uretilen kodlar
EK_ACIKLAMA = {
    "sitemap_olu_adres": "Sitemap'te hata kodu (4xx/5xx) döndüren bir adres listeleniyor",
}
EK_DUZELTME = {
    "sitemap_olu_adres": "Hata kodu döndüren adresi sitemap'ten çıkarın.",
}


def kategori(kod):
    return KATEGORI.get(kod, ("elle", "dusuk"))[0]


def risk(kod):
    return KATEGORI.get(kod, ("elle", "dusuk"))[1]


def aciklama(kod):
    return ACIKLAMA.get(kod) or EK_ACIKLAMA.get(kod) or kod


def duzeltme_metni(kod):
    return DUZELTME.get(kod) or EK_DUZELTME.get(kod) or ""


def kategori_tablosu():
    """Arayuz ve rapor icin: {kod: {kategori, risk, etki}} (bilinen tum kodlar)."""
    kodlar = set(ACIKLAMA) | set(KATEGORI) | set(EK_ACIKLAMA)
    return {k: {"kategori": kategori(k), "risk": risk(k), "etki": ETKI.get(k, "")} for k in sorted(kodlar)}
