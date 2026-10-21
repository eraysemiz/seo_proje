"""Kural tabanli (modelsiz) SEO denetimi ve puanlama.

Sorunlar iki katmanda toplanir:
  katman="sayfa" -> sayfanin HTML'inden gorulebilir
  katman="site"  -> yalnizca canli erisimde olculebilir (robots.txt, sitemap, HTTPS, hiz...)
Model yalnizca sayfa katmanindaki belirli alanlar icin oneri uretir; site katmani
kural tabanli duzeltme veya elle mudahale gerektirir.
"""
import re
from collections import defaultdict

from .cikarma import GENEL_KOKLER, kokler

# modelin degistirmesine izin verilen alanlar
IZINLI_ALANLAR = ("title", "meta_description", "h1", "img_alt")
# modelsiz, belirli (deterministik) olarak duzeltilebilen sorunlar
KURAL_SORUNLARI = ("canonical_yok", "html_lang_yok", "h1_birden_fazla", "viewport_yok", "og_etiketleri_yok")
# her alan hangi kural sorunlariyla iliskili (gereksiz degisikligi yakalamak icin)
ALAN_SORUN = {"title": ("title_yok", "title_kisa", "title_uzun"),
              "meta_description": ("meta_description_yok", "meta_description_kisa", "meta_description_uzun"),
              "h1": ("h1_yok",), "img_alt": ("img_alt_eksik",)}

CIDDIYET_AGIRLIK = {"yuksek": 15, "orta": 8, "dusuk": 3}

ACIKLAMA = {
    "title_yok": "Sayfa başlığı (title) yok",
    "title_kisa": "Sayfa başlığı çok kısa (30 karakterden az)",
    "title_uzun": "Sayfa başlığı çok uzun (60 karakterden fazla)",
    "meta_description_yok": "Meta açıklama yok",
    "meta_description_kisa": "Meta açıklama çok kısa (70 karakterden az)",
    "meta_description_uzun": "Meta açıklama çok uzun (160 karakterden fazla)",
    "h1_yok": "Sayfada H1 başlığı yok",
    "h1_birden_fazla": "Sayfada birden fazla H1 var",
    "h1_bos": "Metni olmayan H1 var (boş ya da yalnızca görsel içeriyor)",
    "img_alt_eksik": "Bazı görsellerde alt metni yok",
    "canonical_yok": "Canonical (asıl adres) etiketi yok",
    "html_lang_yok": "html etiketinde dil (lang) bilgisi yok",
    "icerik_az": "Metin içeriği az (300 kelimeden az)",
    # --- site katmani ---
    "robots_yok": "robots.txt dosyası bulunamadı",
    "robots_okunamadi": "robots.txt okunamadı veya hatalı",
    "robots_tum_siteyi_engelliyor": "robots.txt tüm siteyi aramaya kapatıyor",
    "robots_sayfayi_engelliyor": "robots.txt bu sayfanın taranmasını engelliyor",
    "robots_sitemap_bildirilmemis": "robots.txt içinde Sitemap satırı yok",
    "sitemap_yok": "sitemap.xml bulunamadı",
    "sitemap_gecersiz": "sitemap.xml okunamıyor veya geçerli XML değil",
    "sitemap_bos": "sitemap.xml içinde adres yok",
    "sayfa_sitemapte_yok": "Bu sayfa sitemap içinde listelenmemiş",
    "https_yok": "Site HTTPS kullanmıyor",
    "https_yonlendirme_yok": "http adresi https adresine yönlendirilmiyor",
    "sertifika_suresi_dolmus": "SSL sertifikasının süresi dolmuş",
    "sertifika_zinciri_eksik": "Sunucu eksik/yanlış ara sertifika gönderiyor (katı istemciler bağlanamaz)",
    "sertifika_dogrulanamadi": "SSL sertifikası doğrulanamadı",
    "erisilemedi": "Sayfaya canlı olarak erişilemedi",
    "sertifika_yakinda_bitiyor": "SSL sertifikasının süresinin dolmasına 30 günden az kaldı",
    "uzun_yonlendirme_zinciri": "Adres birden fazla yönlendirmeden geçiyor",
    "hata_durum_kodu": "Sunucu başarılı olmayan bir durum kodu döndürdü",
    "hsts_yok": "HSTS (Strict-Transport-Security) başlığı yok",
    "yavas_yanit": "Sunucu yanıt süresi yüksek (TTFB 1 saniyeden fazla)",
    "cok_yavas_yanit": "Sunucu yanıt süresi çok yüksek (TTFB 2,5 saniyeden fazla)",
    # brotli paketi kuruluysa gzip/deflate/br, degilse gzip/deflate istenir (canli._kodlamalar)
    "sikistirma_yok": "Yanıt sıkıştırılmamış (gzip/deflate/br ile istendi, sıkıştırılmadı)",
    "html_cok_buyuk": "HTML belgesi çok büyük (500 KB üstü)",
    "cok_fazla_kaynak": "Sayfa çok sayıda dış kaynak yüklüyor (100 üstü)",
    "viewport_yok": "Mobil uyum için viewport meta etiketi yok",
    "yapisal_veri_yok": "Yapısal veri (schema.org/JSON-LD) yok",
    "yapisal_veri_gecersiz": "JSON-LD yapısal verisi okunamıyor",
    "og_etiketleri_yok": "Open Graph (og:) paylaşım etiketleri yok",
    "twitter_card_yok": "Twitter Card etiketi yok",
    "favicon_yok": "Favicon (site simgesi) tanımlanmamış",
    "noindex": "Sayfa noindex ile aramaya kapatılmış",
    # --- baslik yapisi, uluslararasilastirma, yapisal veri turu, guvenlik ---
    "baslik_atlamasi": "Başlık hiyerarşisinde seviye atlanıyor (örneğin H1'den H3'e)",
    "hreflang_gecersiz": "hreflang değeri geçerli bir dil/bölge kodu değil",
    "hreflang_x_default_yok": "hreflang kullanılıyor ama x-default tanımlı değil",
    "schema_kurum_turu_yok": "Yapısal veri var ama kurum türü (Organization/CollegeOrUniversity) yok",
    "karisik_icerik": "HTTPS sayfa http:// üzerinden kaynak yüklüyor (karışık içerik)",
    # --- odak terim tutarliligi ---
    "title_h1_uyumsuz": "Sayfa başlığı (title) ile H1 ortak hiçbir anahtar terim içermiyor",
    "title_icerikle_uyumsuz": "Sayfa başlığındaki terimler sayfa içeriğinde geçmiyor",
    # --- sayfalar arasi (tarama geneli) ---
    "title_tekrar": "Aynı sayfa başlığı (title) başka sayfalarda da kullanılıyor",
    "meta_tekrar": "Aynı meta açıklama başka sayfalarda da kullanılıyor",
    "h1_tekrar": "Aynı H1 başlığı başka sayfalarda da kullanılıyor",
}

KURUM_SCHEMA_TURLERI = {"Organization", "EducationalOrganization", "CollegeOrUniversity",
                        "GovernmentOrganization", "School", "Hospital", "MedicalOrganization"}
HREFLANG_DESENI = re.compile(r"^(x-default|[a-z]{2,3}(-[a-z]{4})?(-([a-z]{2}|\d{3}))?)$", re.I)


def cozum_yolu(kod: str) -> str:
    """Sorunun nasil cozulebilecegi: model (dil modeli metin uretir),
    kural (kod ile belirli bicimde duzeltilir) veya elle (insan/sunucu mudahalesi)."""
    if any(kod in kodlar for kodlar in ALAN_SORUN.values()):
        return "model"
    if kod in KURAL_SORUNLARI:
        return "kural"
    return "elle"


def rule_checks(d: dict) -> list:
    """Sayfa katmani temel denetimi. Modele yalnizca bu listedeki sorunlar gonderilir."""
    issues = []
    def add(kod, ciddiyet, ayrinti=""):
        issues.append({"sorun": kod, "ciddiyet": ciddiyet, "ayrinti": ayrinti,
                       "katman": "sayfa", "cozum_yolu": cozum_yolu(kod)})
    t = d["title"]
    if not t: add("title_yok", "yuksek")
    elif len(t) < 30: add("title_kisa", "orta", f"{len(t)} karakter")
    elif len(t) > 60: add("title_uzun", "orta", f"{len(t)} karakter")
    m = d["meta_description"]
    if not m: add("meta_description_yok", "yuksek")
    elif len(m) < 70: add("meta_description_kisa", "orta", f"{len(m)} karakter")
    elif len(m) > 160: add("meta_description_uzun", "orta", f"{len(m)} karakter")
    if len(d["h1"]) == 0: add("h1_yok", "yuksek")
    elif len(d["h1"]) > 1: add("h1_birden_fazla", "orta", f"{len(d['h1'])} adet")
    if d.get("h1_bos_sayisi"): add("h1_bos", "dusuk", f"{d['h1_bos_sayisi']} adet metinsiz H1")
    if d["img_no_alt"]: add("img_alt_eksik", "orta", f"{len(d['img_no_alt'])}/{d['img_total']} görsel")
    if not d["canonical"]: add("canonical_yok", "dusuk")
    if not d["lang"]: add("html_lang_yok", "dusuk")
    if d["word_count"] < 300: add("icerik_az", "dusuk", f"{d['word_count']} kelime")
    return issues


def ek_html_denetimi(yv: dict, sayfa_url=None) -> list:
    """Yapisal veri, mobil uyum, paylasim etiketleri, baslik yapisi ve karisik icerik denetimi.
    Tamami sayfanin HTML'inden gorulebilir; modele gonderilmez.
    sayfa_url verilirse ve https ise karisik icerik denetimi de yapilir."""
    issues = []
    def add(kod, ciddiyet, ayrinti=""):
        issues.append({"sorun": kod, "ciddiyet": ciddiyet, "ayrinti": ayrinti,
                       "katman": "sayfa", "cozum_yolu": cozum_yolu(kod)})
    if not yv["viewport"]:
        add("viewport_yok", "orta")
    if yv["jsonld_sayisi"] == 0 and not yv["mikroveri"]:
        add("yapisal_veri_yok", "dusuk")
    elif yv["jsonld_hatali"]:
        add("yapisal_veri_gecersiz", "dusuk", str(yv["jsonld_hatali"]) + " blok")
    if not yv["og_etiketleri"]:
        add("og_etiketleri_yok", "dusuk")
    if not yv["twitter_etiketleri"]:
        add("twitter_card_yok", "dusuk")
    if not yv["favicon"]:
        add("favicon_yok", "dusuk")
    if yv["dis_kaynak_sayisi"] > 100:
        add("cok_fazla_kaynak", "dusuk", str(yv["dis_kaynak_sayisi"]) + " kaynak")
    if "noindex" in (yv["robots_meta"] or "").lower():
        add("noindex", "yuksek", "meta robots: " + str(yv["robots_meta"]))
    seviyeler = yv.get("baslik_seviyeleri") or []
    atlamalar = [f"H{a}->H{b}" for a, b in zip(seviyeler, seviyeler[1:]) if b > a + 1]
    if atlamalar:
        add("baslik_atlamasi", "dusuk", ", ".join(sorted(set(atlamalar))[:3]))
    hreflang = [h for h in (yv.get("hreflang") or []) if h is not None]
    if hreflang:
        gecersiz = [h for h in hreflang if not HREFLANG_DESENI.match(h.strip())]
        if gecersiz:
            add("hreflang_gecersiz", "dusuk", ", ".join(gecersiz[:3]))
        if not any(h.strip().lower() == "x-default" for h in hreflang):
            add("hreflang_x_default_yok", "dusuk")
    if yv["jsonld_sayisi"] and not (set(yv.get("schema_turleri") or []) & KURUM_SCHEMA_TURLERI):
        add("schema_kurum_turu_yok", "dusuk", ", ".join(yv.get("schema_turleri") or []) or "tur yok")
    if sayfa_url and sayfa_url.lower().startswith("https://") and yv.get("http_kaynak_sayisi"):
        add("karisik_icerik", "orta", str(yv["http_kaynak_sayisi"]) + " kaynak")
    return issues


def odak_terim_denetimi(d: dict) -> list:
    """Title, H1 ve icerik arasinda ortak anahtar terim olup olmadigini denetler.
    Kokler 5 harfe kisaltildigi icin Turkce ek farklari tolere edilir; kurumlarin her sayfada
    gecen genel sozcukleri (GENEL_KOKLER) sayilmaz."""
    issues = []
    def add(kod, ayrinti=""):
        issues.append({"sorun": kod, "ciddiyet": "dusuk", "ayrinti": ayrinti,
                       "katman": "sayfa", "cozum_yolu": cozum_yolu(kod)})
    title_k = kokler(d.get("title") or "") - GENEL_KOKLER
    h1_k = kokler(" ".join(d.get("h1") or [])) - GENEL_KOKLER
    if title_k and h1_k and not (title_k & h1_k):
        add("title_h1_uyumsuz", "title: " + (d.get("title") or "")[:40] + " | h1: " + " / ".join(d["h1"])[:40])
    if title_k and d.get("icerik_kokleri") and not (title_k & d["icerik_kokleri"]):
        add("title_icerikle_uyumsuz", (d.get("title") or "")[:60])
    return issues


def _normal(metin):
    return " ".join((metin or "").lower().split())


def site_geneli(rapor: list) -> list:
    """Taramadaki sayfalar arasinda tekrar eden title / meta / H1 degerlerini bulur.
    Her kayit icin tek tek bakilarak gorulemeyen, tarama geneline ait bir denetimdir.
    Grup listesi dondurur: [{"sorun", "deger", "sayfalar"}]."""
    gruplar = {"title_tekrar": defaultdict(list), "meta_tekrar": defaultdict(list), "h1_tekrar": defaultdict(list)}
    for k in rapor:
        if k.get("hata") or k.get("atlandi") or k.get("hata_sayfasi"):
            continue
        if _normal(k.get("title")):
            gruplar["title_tekrar"][_normal(k["title"])].append(k["ad"])
        if _normal(k.get("meta_description")):
            gruplar["meta_tekrar"][_normal(k["meta_description"])].append(k["ad"])
        for h in set(_normal(h) for h in (k.get("h1") or []) if _normal(h)):
            gruplar["h1_tekrar"][h].append(k["ad"])
    return [{"sorun": kod, "cozum_yolu": cozum_yolu(kod), "deger": deger, "sayfalar": sayfalar}
            for kod, g in gruplar.items() for deger, sayfalar in g.items() if len(sayfalar) > 1]


def puan(issues) -> int:
    """Sorunlarin ciddiyetine gore 0-100 arasi saydam bir SEO puani.
    Lighthouse gibi bagimsiz bir olcum degildir; bu uygulamanin kendi olcegidir."""
    ceza = sum(CIDDIYET_AGIRLIK.get(i.get("ciddiyet"), 5) for i in issues)
    return max(0, 100 - ceza)


# ------------------------------------------------------------ kategori bazli puan
# kod: (kategori, grup, en yuksek ciddiyet, gorulebildigi katmanlar)
# Ayni gruptaki kodlar birbirini dislar (ornegin title_yok / title_kisa / title_uzun);
# bir grubun en fazla cezasi o gruptaki en yuksek ciddiyetin agirligidir.
SORUN_TANIMI = {
    "title_yok": ("icerik", "title", "yuksek", "sayfa"), "title_kisa": ("icerik", "title", "orta", "sayfa"),
    "title_uzun": ("icerik", "title", "orta", "sayfa"),
    "meta_description_yok": ("icerik", "meta", "yuksek", "sayfa"),
    "meta_description_kisa": ("icerik", "meta", "orta", "sayfa"),
    "meta_description_uzun": ("icerik", "meta", "orta", "sayfa"),
    "h1_yok": ("icerik", "h1", "yuksek", "sayfa"), "h1_birden_fazla": ("icerik", "h1", "orta", "sayfa"),
    "h1_bos": ("icerik", "h1_bos", "dusuk", "sayfa"),
    "img_alt_eksik": ("icerik", "img_alt", "orta", "sayfa"),
    "icerik_az": ("icerik", "icerik_az", "dusuk", "sayfa"),
    "title_h1_uyumsuz": ("icerik", "title_h1", "dusuk", "sayfa"),
    "title_icerikle_uyumsuz": ("icerik", "title_icerik", "dusuk", "sayfa"),
    "baslik_atlamasi": ("icerik", "baslik", "dusuk", "sayfa"),
    "canonical_yok": ("teknik", "canonical", "dusuk", "sayfa"),
    "html_lang_yok": ("teknik", "lang", "dusuk", "sayfa"),
    "viewport_yok": ("teknik", "viewport", "orta", "sayfa"),
    "yapisal_veri_yok": ("teknik", "yapisal", "dusuk", "sayfa"),
    "yapisal_veri_gecersiz": ("teknik", "yapisal", "dusuk", "sayfa"),
    "schema_kurum_turu_yok": ("teknik", "schema_tur", "dusuk", "sayfa"),
    "og_etiketleri_yok": ("teknik", "og", "dusuk", "sayfa"),
    "twitter_card_yok": ("teknik", "twitter", "dusuk", "sayfa"),
    "favicon_yok": ("teknik", "favicon", "dusuk", "sayfa"),
    "hreflang_gecersiz": ("teknik", "hreflang_gecersiz", "dusuk", "sayfa"),
    "hreflang_x_default_yok": ("teknik", "hreflang_x", "dusuk", "sayfa"),
    "noindex": ("teknik", "noindex", "yuksek", "sayfa site"),
    "cok_fazla_kaynak": ("performans", "kaynak", "dusuk", "sayfa"),
    "karisik_icerik": ("guvenlik", "karisik", "orta", "sayfa"),
    "erisilemedi": ("teknik", "erisim", "yuksek", "site"),
    "hata_durum_kodu": ("teknik", "erisim", "yuksek", "site"),
    "uzun_yonlendirme_zinciri": ("teknik", "yonlendirme", "dusuk", "site"),
    "robots_yok": ("teknik", "robots", "orta", "site"), "robots_okunamadi": ("teknik", "robots", "orta", "site"),
    "robots_tum_siteyi_engelliyor": ("teknik", "robots", "yuksek", "site"),
    "robots_sayfayi_engelliyor": ("teknik", "robots", "yuksek", "site"),
    "robots_sitemap_bildirilmemis": ("teknik", "robots_sitemap", "dusuk", "site"),
    "sitemap_yok": ("teknik", "sitemap", "orta", "site"), "sitemap_gecersiz": ("teknik", "sitemap", "orta", "site"),
    "sitemap_bos": ("teknik", "sitemap", "orta", "site"),
    "sayfa_sitemapte_yok": ("teknik", "sitemap", "dusuk", "site"),
    "https_yok": ("guvenlik", "https", "yuksek", "site"),
    "https_yonlendirme_yok": ("guvenlik", "https_yon", "orta", "site"),
    "sertifika_suresi_dolmus": ("guvenlik", "sertifika_sure", "yuksek", "site"),
    "sertifika_yakinda_bitiyor": ("guvenlik", "sertifika_sure", "orta", "site"),
    "sertifika_zinciri_eksik": ("guvenlik", "sertifika_zincir", "yuksek", "site"),
    "sertifika_dogrulanamadi": ("guvenlik", "sertifika_zincir", "yuksek", "site"),
    "hsts_yok": ("guvenlik", "hsts", "dusuk", "site"),
    "yavas_yanit": ("performans", "hiz", "dusuk", "site"), "cok_yavas_yanit": ("performans", "hiz", "orta", "site"),
    "sikistirma_yok": ("performans", "sikistirma", "dusuk", "site"),
    "html_cok_buyuk": ("performans", "boyut", "dusuk", "site"),
}
KATEGORILER = ("icerik", "teknik", "guvenlik", "performans")
# tarama geneline ait bulgular (site_geneli); sayfa kaydinin sorunlarina girmez, puanlanmaz
TARAMA_GENELI_KODLARI = ("title_tekrar", "meta_tekrar", "h1_tekrar")


def _azami_ceza(katmanlar, kategori=None):
    """Verilen katmanlarda gorulebilen tum gruplarin en yuksek cezalarinin toplami."""
    gruplar = {}
    for kat, grup, ciddiyet, kod_katmanlari in SORUN_TANIMI.values():
        if (kategori is None or kat == kategori) and set(kod_katmanlari.split()) & set(katmanlar):
            gruplar[grup] = max(gruplar.get(grup, 0), CIDDIYET_AGIRLIK[ciddiyet])
    return sum(gruplar.values())


def _normal_puan(issues, katmanlar, kategori=None):
    secili = [i for i in issues if i.get("katman") in katmanlar and
              (kategori is None or SORUN_TANIMI.get(i["sorun"], ("",))[0] == kategori)]
    azami = _azami_ceza(katmanlar, kategori)
    if not azami:
        return None
    ceza = sum(CIDDIYET_AGIRLIK.get(i.get("ciddiyet"), 5) for i in secili)
    return max(0, round(100 * (1 - ceza / azami)))


def puanlar(issues, sayfa_olculdu=True) -> dict:
    """Katman ve kategori bazli, 0-100 arasina normallestirilmis puanlar.
    Her puan, o kapsamda gorulebilecek en kotu durumun cezasina bolunur; boylece birkac
    sorun olcegi 0'a indirmez ve siteler birbirinden ayirt edilebilir. Sayfa katmani
    olculmediyse (hata sayfasi) sayfa puani None olur, kategoriler site katmanindan hesaplanir."""
    # hata sayfasinda (4xx/5xx) sayfa katmani denetlenmez; bulgu olmamasi "kusursuz" demek degildir
    katmanlar = ("sayfa", "site") if sayfa_olculdu else ("site",)
    sonuc = {"sayfa": _normal_puan(issues, ("sayfa",)) if sayfa_olculdu else None,
             "site": _normal_puan(issues, ("site",))}
    for kat in KATEGORILER:
        sonuc[kat] = _normal_puan(issues, katmanlar, kat)
    return sonuc


def acikla(kod: str) -> str:
    return ACIKLAMA.get(kod, kod)
