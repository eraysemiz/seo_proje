"""Puanlama yapilandirmasi: agirliklar, kritik sorun tavanlari ve bulgularin puanlara atanmasi (tek yer).

Hesap (kurallar.puanlar):
    puan = 100 x carpim(1 - agirlik_g)      g: sorun grubu (ayni gruptaki kodlardan en agiri bir kez)
    puan = min(puan, kritik sorunlarin TAVAN degerleri)

Neden boyle: onceki hesap toplam cezayi "o katmanda olabilecek tum sorunlarin cezasina" (43 grup,
227 puan) boluyordu. Yuksek onemli bir sorun (ornegin title yok) sayfa puanini yalnizca 6,6 puan
dusuruyor, 5 gercek sorunu olan sayfa 89 aliyordu. Carpimsal hesapta her sorun puani kendi agirligi
oraninda dusurur; sorun sayisi ve onemi puana dogrudan yansir, puan yine de 0'in altina inmez ve
ayni sorunun iki kaynaktan gelmesi (grup) iki kez cezalanmaz.

Atama:
    sayfa puani : sayfa katmani + sayfaya ozgu site bulgulari (SAYFAYA_OZGU) + o sayfayi iceren
                  tarama geneli bulgular (tekrar eden title, kopya icerik, yetim sayfa...)
    site puani  : site katmanindaki bulgular (HTTPS, robots.txt, sitemap...)
    kategoriler : kategoriye ait tum bulgular (sayfa + site + tarama geneli)
Arayuzdeki ve rapordaki bilgi balonlari bu yapilandirmayi anlatir (statik/uygulama.js -> puanlar).
"""

# Her sorunun puani dusurme orani. Yuksek: dizine alinmayi ya da arama sonucunu dogrudan bozar
# (title/meta/H1 yok, noindex, HTTPS yok); orta: siralamayi ve tiklamayi belirgin etkiler; dusuk: iyilestirme.
AGIRLIK = {"yuksek": 0.20, "orta": 0.09, "dusuk": 0.035}

# Bulgunun kendi ciddiyetinden farkli puanlanan kodlar (gerekceyle)
KOD_CIDDIYETI = {
    "yapisal_veri_gecersiz": "orta",   # okunamayan JSON-LD tamamen yok sayilir; zengin sonuc kaybedilir
    "hreflang_gecersiz": "orta",       # gecersiz kodlu hreflang kumesi arama motorunca yok sayilir
    "canonical_capraz": "orta",        # asil sayfa baska adrese canonical verirse dizinden duser
    "kirik_ic_link": "orta",           # kullanici ve tarayici cikmaza girer, baglanti degeri kaybolur
}

# Tarama geneli bulgularin (sayfalar arasi) ciddiyeti; bu bulgular ilgili her sayfanin puanina girer
TARAMA_CIDDIYETI = {
    "title_tekrar": "orta", "meta_tekrar": "dusuk", "h1_tekrar": "dusuk",
    "icerik_tekrar": "orta", "icerik_benzer": "orta",   # kopya icerik ceza degil (SEO Baslangic Rehberi)
    "yetim_sayfa": "orta", "derin_sayfa": "dusuk", "hreflang_donus_yok": "dusuk", "sitemap_yonlendirme": "dusuk",
    "sitemap_olu_adres": "orta",
}

# Kritik sorunlarda puanin ust siniri: bu sorun varken sayfa diger acilardan kusursuz olsa da bu degeri gecemez
TAVAN = {
    "erisilemedi": 0, "yonlendirme_dongusu": 0, "robots_tum_siteyi_engelliyor": 20, "hata_durum_kodu": 30,
    "yumusak_404": 40, "robots_sayfayi_engelliyor": 50, "noindex": 60, "title_yok": 75,
}

# Site katmaninda olculen ama tek bir sayfaya ait olan bulgular; o sayfanin puanina da girer
SAYFAYA_OZGU = {
    "kirik_ic_link", "kirik_dis_link", "ic_link_yonlendirme", "kirik_gorsel", "gorsel_buyuk",
    "sayfa_sitemapte_yok", "noindex_sitemapte", "robots_sayfayi_engelliyor", "gecici_yonlendirme",
    "uzun_yonlendirme_zinciri", "yumusak_404", "hata_durum_kodu", "canonical_baslik_catismasi", "noindex",
    "sayfa_nofollow", "meta_refresh", "yavas_yanit", "cok_yavas_yanit", "html_cok_buyuk",
    "cwv_lcp_yavas", "cwv_inp_yavas", "cwv_cls_yuksek", "sayfa_agir",
    "canonical_kirik", "robots_kaynak_engelliyor", "onbellek_basligi_yok",
}


def ciddiyet(bulgu):
    kod = bulgu["sorun"]
    if kod in KOD_CIDDIYETI:
        return KOD_CIDDIYETI[kod]
    if bulgu.get("katman") == "tarama":
        return TARAMA_CIDDIYETI.get(kod, "dusuk")
    return bulgu.get("ciddiyet") or "dusuk"


def agirlik(bulgu):
    return AGIRLIK.get(ciddiyet(bulgu), AGIRLIK["dusuk"])


def hesapla(bulgular, grup):
    """bulgular: [{"sorun", "ciddiyet", "katman"}]; grup(kod) -> grup adi. 0-100 tam sayi."""
    gruplar = {}
    for b in bulgular:
        g = grup(b["sorun"])
        gruplar[g] = max(gruplar.get(g, 0.0), agirlik(b))
    puan = 100.0
    for w in gruplar.values():
        puan *= 1 - w
    tavan = min((TAVAN[b["sorun"]] for b in bulgular if b["sorun"] in TAVAN), default=100)
    return round(min(puan, tavan))


def tarama_bulgulari(kodlar):
    """Kayda yazilan tarama geneli kodlarini (tekrar_bulgulari) puanlanacak bulgulara cevirir."""
    return [{"sorun": k, "katman": "tarama", "ciddiyet": TARAMA_CIDDIYETI.get(k, "dusuk")} for k in kodlar or ()]
