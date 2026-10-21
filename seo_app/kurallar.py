"""Kural tabanli (modelsiz) SEO denetimi ve puanlama.

Sorunlar iki katmanda toplanir:
  katman="sayfa" -> yalnizca HTML'den gorulebilir, cevrimdisi anlik goruntulerde de calisir
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
    "title_yok": "Sayfa basligi (title) yok",
    "title_kisa": "Sayfa basligi cok kisa (30 karakterden az)",
    "title_uzun": "Sayfa basligi cok uzun (60 karakterden fazla)",
    "meta_description_yok": "Meta aciklama yok",
    "meta_description_kisa": "Meta aciklama cok kisa (70 karakterden az)",
    "meta_description_uzun": "Meta aciklama cok uzun (160 karakterden fazla)",
    "h1_yok": "Sayfada H1 basligi yok",
    "h1_birden_fazla": "Sayfada birden fazla H1 var",
    "h1_bos": "Metni olmayan H1 var (bos ya da yalnizca gorsel iceriyor)",
    "img_alt_eksik": "Bazi gorsellerde alt metni yok",
    "canonical_yok": "Canonical (asil adres) etiketi yok",
    "html_lang_yok": "html etiketinde dil (lang) bilgisi yok",
    "icerik_az": "Metin icerigi az (300 kelimeden az)",
    # --- site katmani ---
    "robots_yok": "robots.txt dosyasi bulunamadi",
    "robots_okunamadi": "robots.txt okunamadi veya hatali",
    "robots_tum_siteyi_engelliyor": "robots.txt tum siteyi aramaya kapatiyor",
    "robots_sayfayi_engelliyor": "robots.txt bu sayfanin taranmasini engelliyor",
    "robots_sitemap_bildirilmemis": "robots.txt icinde Sitemap satiri yok",
    "sitemap_yok": "sitemap.xml bulunamadi",
    "sitemap_gecersiz": "sitemap.xml okunamiyor veya gecerli XML degil",
    "sitemap_bos": "sitemap.xml icinde adres yok",
    "sayfa_sitemapte_yok": "Bu sayfa sitemap icinde listelenmemis",
    "https_yok": "Site HTTPS kullanmiyor",
    "https_yonlendirme_yok": "http adresi https adresine yonlendirilmiyor",
    "sertifika_suresi_dolmus": "SSL sertifikasinin suresi dolmus",
    "sertifika_zinciri_eksik": "Sunucu eksik/yanlis ara sertifika gonderiyor (kati istemciler baglanamaz)",
    "sertifika_dogrulanamadi": "SSL sertifikasi dogrulanamadi",
    "erisilemedi": "Sayfaya canli olarak erisilemedi",
    "sertifika_yakinda_bitiyor": "SSL sertifikasinin suresi 30 gunden az kaldi",
    "uzun_yonlendirme_zinciri": "Adres birden fazla yonlendirmeden geciyor",
    "hata_durum_kodu": "Sunucu basarili olmayan bir durum kodu dondurdu",
    "hsts_yok": "HSTS (Strict-Transport-Security) basligi yok",
    "yavas_yanit": "Sunucu yanit suresi yuksek (TTFB 1 saniyeden fazla)",
    "cok_yavas_yanit": "Sunucu yanit suresi cok yuksek (TTFB 2.5 saniyeden fazla)",
    # arac yalnizca gzip/deflate ister (brotli icin ek paket gerekir); yalnizca br sunan
    # bir sunucu da bu bulguyu alir
    "sikistirma_yok": "Yanit sikistirilmamis (gzip/deflate ile istendi, sikistirilmadi)",
    "html_cok_buyuk": "HTML belgesi cok buyuk (500 KB ustu)",
    "cok_fazla_kaynak": "Sayfa cok sayida dis kaynak yukluyor (100 ustu)",
    "viewport_yok": "Mobil uyum icin viewport meta etiketi yok",
    "yapisal_veri_yok": "Yapisal veri (schema.org/JSON-LD) yok",
    "yapisal_veri_gecersiz": "JSON-LD yapisal verisi okunamiyor",
    "og_etiketleri_yok": "Open Graph (og:) paylasim etiketleri yok",
    "twitter_card_yok": "Twitter Card etiketi yok",
    "favicon_yok": "Favicon (site simgesi) tanimlanmamis",
    "noindex": "Sayfa noindex ile aramaya kapatilmis",
    # --- baslik yapisi, uluslararasilastirma, yapisal veri turu, guvenlik ---
    "baslik_atlamasi": "Baslik hiyerarsisinde seviye atlaniyor (ornegin H1'den H3'e)",
    "hreflang_gecersiz": "hreflang degeri gecerli bir dil/bolge kodu degil",
    "hreflang_x_default_yok": "hreflang kullaniliyor ama x-default tanimli degil",
    "schema_kurum_turu_yok": "Yapisal veri var ama kurum turu (Organization/CollegeOrUniversity) yok",
    "karisik_icerik": "HTTPS sayfa http:// uzerinden kaynak yukluyor (karisik icerik)",
    # --- odak terim tutarliligi ---
    "title_h1_uyumsuz": "Sayfa basligi (title) ile H1 ortak hicbir anahtar terim icermiyor",
    "title_icerikle_uyumsuz": "Sayfa basligindaki terimler sayfa iceriginde gecmiyor",
    # --- sayfalar arasi (tarama geneli) ---
    "title_tekrar": "Ayni sayfa basligi (title) baska sayfalarda da kullaniliyor",
    "meta_tekrar": "Ayni meta aciklama baska sayfalarda da kullaniliyor",
    "h1_tekrar": "Ayni H1 basligi baska sayfalarda da kullaniliyor",
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
    if d["img_no_alt"]: add("img_alt_eksik", "orta", f"{len(d['img_no_alt'])}/{d['img_total']} gorsel")
    if not d["canonical"]: add("canonical_yok", "dusuk")
    if not d["lang"]: add("html_lang_yok", "dusuk")
    if d["word_count"] < 300: add("icerik_az", "dusuk", f"{d['word_count']} kelime")
    return issues


def ek_html_denetimi(yv: dict, sayfa_url=None) -> list:
    """Yapisal veri, mobil uyum, paylasim etiketleri, baslik yapisi ve karisik icerik denetimi.
    Tamami HTML'den gorulebildigi icin cevrimdisi modda da calisir; modele gonderilmez.
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


def acikla(kod: str) -> str:
    return ACIKLAMA.get(kod, kod)
