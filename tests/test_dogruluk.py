"""Dogruluk iyilestirmesi: guven puani ve otomatik onay, yeni denetimler, deterministik duzelticiler,
takma adlarin tekillestirilmesi. Ag ve dil modeli kullanilmaz."""
import json

from seo_app import duzeltme as dz
from seo_app import guven as gv
from seo_app import kurallar as kr
from seo_app import tarama
from seo_app.cikarma import extract, yapisal_veri
from seo_app.yazma import YerelDosyaAdaptoru
from seo_app.yz_oneri import dogrula_metin, json_onar, teklif_normallestir

TEMEL = "http://site.test/"
SAYFA = ('<!DOCTYPE html>\n<html>\n<head>\n<title>Çay Demleme Rehberi ve Öneriler | Örnek</title>\n'
         '<meta name="robots" content="noindex, follow">\n<script src="/js/a.js"></script>\n</head>\n<body>\n<main>\n'
         '<h1>Çay demleme</h1>\n<p>Demlik ısıtılır, çay 185 TL değerindeki pakettendir.</p>\n<h1>Servis</h1>\n'
         '</main>\n</body>\n</html>\n')


def _site(tmp_path, metin=SAYFA, ek=None):
    kok = tmp_path / "site"
    kok.mkdir()
    (kok / "index.html").write_text(metin, encoding="utf-8")
    for ad, icerik in (ek or {}).items():
        (kok / ad).parent.mkdir(parents=True, exist_ok=True)
        (kok / ad).write_text(icerik, encoding="utf-8")
    return YerelDosyaAdaptoru(kok)


def _plan(a, kodlar, yz=None, esik=None):
    kayit = [{"ad": TEMEL, "site_url": TEMEL, "durum_kodu": 200,
              "sorunlar": [{"sorun": k, "katman": "sayfa"} for k in kodlar]}]
    return dz.plan_uret(kayit, [], a, TEMEL, yz=yz, esik=esik)


def _bul(plan, bulgu):
    return next(d for d in plan["degisiklikler"] if d["bulgu"] == bulgu)


class SahteYZ:
    model = "sahte"

    def __init__(self, *cevaplar):
        self.cevaplar, self.gorevler = list(cevaplar), []

    def iste(self, gorev, d, kodlar, sayfa_verisi, dil="tr"):
        self.gorevler.append(gorev)
        deger = self.cevaplar.pop(0) if len(self.cevaplar) > 1 else self.cevaplar[0]
        return {"deger": deger, "gerekce": "g", "kaynaklar": [], "kaynak_metni": ""}


# ------------------------------------------------------------------ guven ve otomatik onay
def test_kural_degisiklikleri_yuksek_guvenle_otomatik_uygulanir_yedek_ve_gunluk_tutulur(tmp_path):
    a = _site(tmp_path)
    plan = _plan(a, ("html_lang_yok", "h1_birden_fazla"))
    for kod in ("html_lang_yok", "charset_yok"):
        d = _bul(plan, kod)
        assert d["guven"] >= 0.9 and d["onay_turu"] == "otomatik"
    # Google icin baslik sayisi belirleyici degil (SEO Baslangic Rehberi): fazla H1 duzeltmesi onay ister
    h1 = _bul(plan, "h1_birden_fazla")
    assert h1["guven"] == 0.6 and h1["onay_turu"] != "otomatik"
    sonuc = dz.uygula(plan, {}, a, tmp_path / "yedek", tmp_path / "g.jsonl")          # hic onay verilmeden
    metin = a.oku("index.html").decode("utf-8")
    assert '<html lang="tr">' in metin and "<h2>Servis</h2>" not in metin and sonuc["uygulanan"] == 2
    assert (tmp_path / "yedek").exists()
    assert {d["onay_kaynagi"] for d in plan["degisiklikler"] if d["durum"] == "uygulandi"} == {"otomatik"}
    gunluk = [json.loads(s) for s in (tmp_path / "g.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {s["durum"] for s in gunluk if s.get("id") != h1["id"]} <= {"uygulandi"}


def test_otomatik_onayli_degisiklik_reddedilebilir_ve_esik_degistirilebilir(tmp_path):
    a = _site(tmp_path)
    plan = _plan(a, ("html_lang_yok",))
    d = _bul(plan, "html_lang_yok")
    p2 = json.loads(json.dumps(plan))
    dz.uygula(plan, {"kararlar": {d["id"]: {"karar": "ret"}}}, a, tmp_path / "y1", tmp_path / "g")
    assert _bul(plan, "html_lang_yok")["durum"] == "reddedildi" and "lang=" not in a.oku("index.html").decode()
    dz.uygula(p2, {"esik": 0.99}, a, tmp_path / "y2", tmp_path / "g")                  # esik yukseltildi
    assert _bul(p2, "html_lang_yok")["durum"] == "onay_bekliyor" and "eşiğin" in _bul(p2, "html_lang_yok")["durum_nedeni"]


def test_dusuk_guvenli_kural_onaya_duser_ve_nedeni_yazilir(tmp_path):
    plan = _plan(_site(tmp_path), ("render_engelleyen_kaynak",))
    d = _bul(plan, "render_engelleyen_kaynak")
    assert d["parcalar"][0]["yeni"] == " defer" and d["guven"] < gv.ESIK and d["onay_turu"] != "otomatik"
    assert any("defer" in n for n in d["guven_nedenleri"])


def test_yer_tutucu_ve_indekslemeyi_kapatan_degisiklik_her_zaman_onaya_duser():
    d = {"bulgu": "title_yok", "uretici": "kural", "dogrulama": {"gecti": True, "neden": ""}, "yer_tutucu": True,
         "parcalar": []}
    gv.degerlendir(d, guven=0.99)
    assert d["zorunlu_onay"] and not gv.otomatik_mi(d, 0.5)
    d = {"bulgu": "x", "uretici": "kural", "dogrulama": {"gecti": True, "neden": ""}, "yer_tutucu": False,
         "parcalar": [{"eski": "", "yeni": '<meta name="robots" content="noindex">'}]}
    gv.degerlendir(d)
    assert "kapatan" in d["zorunlu_onay"] and not gv.otomatik_mi(d)
    d = {"bulgu": "icerik_benzer", "uretici": "sezgisel", "dogrulama": {"gecti": True, "neden": ""},
         "yer_tutucu": False, "parcalar": []}
    gv.degerlendir(d)
    assert "dizinden düşer" in d["zorunlu_onay"]
    d = {"bulgu": "noindex", "uretici": "sezgisel", "dogrulama": {"gecti": True, "neden": ""}, "yer_tutucu": False,
         "parcalar": [{"eski": "noindex, follow", "yeni": "index, follow"}]}
    gv.degerlendir(d)
    assert not d["zorunlu_onay"] and gv.otomatik_mi(d)                  # indekslemeyi acan degisiklik kapatmaz


def test_dogrulamadan_gecmeyen_oneri_nedeniyle_yeniden_sorulur_ve_guveni_duser(tmp_path):
    a = _site(tmp_path, SAYFA.replace("<title>Çay Demleme Rehberi ve Öneriler | Örnek</title>\n", ""))
    yz = SahteYZ("Çay Demleme ve Servis: Demlik Isıtılır, Çay 185 TL Değerindeki Paketten Demlenir",
                 "Çay Demleme ve Servis: Demlik Isıtılır, Çay Paketten")
    plan = _plan(a, ("title_yok",), yz=yz)
    d = _bul(plan, "title_yok")
    assert len(yz.gorevler) == 2 and "REDDEDİLDİ" in yz.gorevler[1] and "title_uzunluk" in yz.gorevler[1]
    assert d["deneme"] == 2 and d["durum"] == "oneriliyor"
    assert d["guven"] < gv.MODEL_TABANI["title"] and any("ikinci denemede" in n for n in d["guven_nedenleri"])


def test_uzunluk_sinirini_asan_oneri_anlami_bozmadan_kirpilir(tmp_path):
    from seo_app.yz_oneri import uzunluk_kirp
    assert uzunluk_kirp("title", "İletişim: Çaylıbahçe Adres, Telefon ve Çalışma Saatleri | Çaylıbahçe") == \
        "İletişim: Çaylıbahçe Adres, Telefon ve Çalışma Saatleri"
    assert uzunluk_kirp("title", "Kış Çayı Harmanı Nasıl Hazırlanır: Tarçın ve Karanfil | Çaylıbahçe") == \
        "Kış Çayı Harmanı Nasıl Hazırlanır | Çaylıbahçe"
    assert uzunluk_kirp("title", "Kış Çayı Harmanı: Tarçın, Karanfil ve Portakal Kabuğuyla | Çaylıbahçe") is None  # 29 < 30
    meta = ("Demlik seti iki litrelik çaydanlık ve porselen demlikten oluşur. Altı ince belli bardak da sete dahildir. "
            "Sipariş aynı gün kargoya verilir, özenle paketlenir ve hediye notu eklenebilir.")
    assert len(meta) > 160
    assert uzunluk_kirp("meta_description", meta).endswith("dahildir.")
    assert uzunluk_kirp("meta_description", "Tek cümle " * 20) is None           # cumle ortasindan kesilmez
    a = _site(tmp_path, SAYFA.replace("<title>Çay Demleme Rehberi ve Öneriler | Örnek</title>\n", ""))
    uzun = "Çay Demleme ve Servis İçin Demlik: Çay 185 TL Değerindeki Paketten Demlenir | Örnek"
    d = _bul(_plan(a, ("title_yok",), yz=SahteYZ(uzun)), "title_yok")
    assert d["dogrulama"]["gecti"] and d["dogrulama"]["kirpildi"], d["dogrulama"]
    assert d["yeni"] == "Çay Demleme ve Servis İçin Demlik | Örnek"
    assert any("kısaltıldı" in n for n in d["guven_nedenleri"])


def test_kaynaga_dayanmayan_oneri_dusuk_guven_alir():
    d = {"bulgu": "meta_description_yok", "uretici": "model", "dogrulama": {"gecti": True, "neden": ""},
         "yer_tutucu": False, "parcalar": [], "yeni": "Kurumsal hizmetler danışmanlık eğitim çözümleri sunar",
         "duzenleme": {"alan": "meta_description"}}
    gv.degerlendir(d, kaynak_metin="Çay demleme rehberi demlik bardak")
    assert d["guven"] < gv.ESIK and any("kaynakta" in n for n in d["guven_nedenleri"])


# ------------------------------------------------------------------ deterministik duzelticiler
def test_bozuk_json_ld_modelsiz_onarilir_ve_otomatik_onaylanir(tmp_path):
    blok = '<script type="application/ld+json">\n{"@context": "https://schema.org", "@type": "Product", "name": "Çay",}\n</script>\n'
    a = _site(tmp_path, SAYFA.replace("</head>", blok + "</head>"))
    d = _bul(_plan(a, ("yapisal_veri_gecersiz",)), "yapisal_veri_gecersiz")
    assert d["kategori"] == "kural" and d["onay_turu"] == "otomatik" and json.loads(d["yeni"])["name"] == "Çay"
    assert json_onar('{"a": [1, 2,], /* yorum */ "b": 1,}') == {"a": [1, 2], "b": 1}


def test_fiyat_ve_para_birimi_yazimi_standartlasir_ve_istege_bagli_yer_tutucu_cikarilir(tmp_path):
    o = {"@type": "Offer", "price": "1.250,00", "priceCurrency": "TL"}
    assert teklif_normallestir(o) and o == {"@type": "Offer", "price": "1250.00", "priceCurrency": "TRY"}
    blok = ('<script type="application/ld+json">\n{"@context": "https://schema.org", "@type": "Product", '
            '"name": "Demlik Seti", "description": "Demlik seti 1.250 TL"}\n</script>\n')
    a = _site(tmp_path, SAYFA.replace("</head>", blok + "</head>").replace("185 TL", "1.250 TL"))
    oneri = {"@context": "https://schema.org", "@type": "Product", "name": "Demlik Seti",
             "description": "Demlik seti 1.250 TL",
             "offers": {"@type": "Offer", "price": "1.250", "priceCurrency": "TL", "availability": "[doğrulanmalı: stok]"}}
    d = _bul(_plan(a, ("yapisal_veri_eksik_alan",), yz=SahteYZ(oneri)), "yapisal_veri_eksik_alan")
    nesne = json.loads(d["yeni"])
    assert d["dogrulama"]["gecti"], d["dogrulama"]
    assert nesne["offers"] == {"@type": "Offer", "price": "1250", "priceCurrency": "TRY"} and not d["yer_tutucu"]
    assert "Standartlaştırma" in d["gerekce"]


def test_meta_aciklama_baglayici_kelimelerle_ozetleyebilir_ama_uydurma_ad_yazamaz():
    kaynak = "Çay demleme rehberi: suyun seçimi, demlik ısıtma, demleme süresi ve servis. Bardak ve saklama önerileri."
    d = {"kelime_kokleri": []}
    iyi = "Suyun seçiminden servise kadar çay demlemenin adımlarını ve saklama önerilerini anlatan kısa bir rehber."
    assert dogrula_metin("meta_description", iyi, kaynak, "tr", d)[0]
    kotu = "Ankara ve İzmir şubelerimizde suyun seçiminden servise kadar çay demleme ve saklama önerileri sunulur."
    gecti, neden, _ = dogrula_metin("meta_description", kotu, kaynak, "tr", d)
    assert not gecti and neden.startswith("sayfada_olmayan_ad")


def test_sitemapteki_yonlendirilen_adres_son_adresle_degistirilir(tmp_path):
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               f'  <url><loc>{TEMEL}eski</loc></url>\n</urlset>\n')
    a = _site(tmp_path, ek={"sitemap.xml": sitemap, "yeni.html": SAYFA})
    kayitlar = [{"ad": TEMEL + "eski", "site_url": TEMEL + "yeni.html", "durum_kodu": 200, "sorunlar": []}]
    plan = dz.plan_uret(kayitlar, [{"sorun": "sitemap_yonlendirme", "sayfalar": [TEMEL + "eski"]}], a, TEMEL)
    d = _bul(plan, "sitemap_yonlendirme")
    assert d["yeni"] == TEMEL + "yeni.html" and d["onay_turu"] == "otomatik"


# ------------------------------------------------------------------ yeni denetimler
def test_engelleyen_betik_charset_ve_buyuk_harfli_adres_tespit_edilir():
    html = ('<html><head><script src="/a.js"></script><script src="/b.js" defer></script>'
            '<script type="module" src="/c.js"></script></head><body></body></html>')
    yv = yapisal_veri(html, "http://site.test/Urunler/Kis-Cayi.html")
    assert yv["engelleyen_betikler"] == ["/a.js"] and yv["charset_meta"] is False
    kodlar = {i["sorun"] for i in kr.ek_html_denetimi(yv, "http://site.test/Urunler/Kis-Cayi.html")}
    assert {"render_engelleyen_kaynak", "charset_yok", "url_buyuk_harf"} <= kodlar
    yv2 = yapisal_veri('<html><head><meta charset="utf-8"></head></html>', "http://site.test/urunler/")
    kodlar2 = {i["sorun"] for i in kr.ek_html_denetimi(yv2, "http://site.test/urunler/")}
    assert not {"render_engelleyen_kaynak", "charset_yok", "url_buyuk_harf"} & kodlar2


def test_yumusak_404_supheli_hata_sayfasi_kalibini_tanir():
    assert kr.yumusak_404_supheli(extract("<title>Ürün bulunamadı | Mağaza</title><h1>Aradığınız ürün yok</h1>"))
    assert kr.yumusak_404_supheli(extract("<title>Page not found</title><p>Sorry.</p>"))
    uzun = "<title>Bulunamadı mı? Kayıp eşya rehberi</title><main><p>" + "kelime " * 400 + "</p></main>"
    assert kr.yumusak_404_supheli(extract(uzun)) is None                 # icerikli sayfa hata sayfasi degil
    assert kr.yumusak_404_supheli(extract("<title>Çay Demleme Rehberi</title>")) is None


# ------------------------------------------------------------------ takma adlar ve bilincli birlestirme
def test_parametreli_adresin_kendi_yoluna_canonicali_capraz_sayilmaz():
    assert kr.parametre_kanonigi_mi("http://s.test/urunler/?siralama=fiyat&ref=menu", "http://s.test/urunler/")
    assert not kr.parametre_kanonigi_mi("http://s.test/urunler/?siralama=fiyat", "http://s.test/blog/")
    assert not kr.parametre_kanonigi_mi("http://s.test/a.html", "http://s.test/b.html")


def _kayit(ad, title, imza, site_url=None, kanonik=None, kelime=300):
    return {"ad": ad, "site_url": site_url or ad, "title": title, "meta_description": None, "h1": [],
            "icerik_imzasi": imza, "icerik_kelime_sayisi": kelime, "kanonik": kanonik,
            "sorunlar": [{"sorun": "canonical_capraz", "katman": "sayfa"}] if kanonik and kanonik != ad else []}


def test_takma_adlar_ve_bilincli_canonical_tekrar_sayilmaz():
    imza = list(range(64))
    rapor = [_kayit("http://s.test/urunler/", "Ürünler", imza),
             _kayit("http://s.test/eski-urunler", "Ürünler", imza, site_url="http://s.test/urunler/"),
             _kayit("http://s.test/urunler/?s=fiyat", "Ürünler", imza, kanonik="http://s.test/urunler/"),
             _kayit("http://s.test/rehber.html", "Rehber", list(range(1000, 1060)) + [900, 901, 902, 903],
                    kanonik="http://s.test/demleme.html"),
             _kayit("http://s.test/demleme.html", "Demleme", list(range(1000, 1064)))]
    kr.kanonik_birlestirmeleri(rapor)
    assert rapor[3]["kanonik_birlestirme"] == "http://s.test/demleme.html" and rapor[3]["sorunlar"] == []
    gruplar = kr.site_geneli(rapor)
    assert not [g for g in gruplar if g["sorun"] in ("title_tekrar", "icerik_tekrar", "icerik_benzer")], gruplar


def test_farkli_icerige_verilen_canonical_bulgu_olarak_kalir():
    rapor = [_kayit("http://s.test/ada.html", "Bitki", list(range(64)), kanonik="http://s.test/ihlamur.html"),
             _kayit("http://s.test/ihlamur.html", "Bitki", list(range(500, 564)))]
    kr.kanonik_birlestirmeleri(rapor)
    assert rapor[0]["sorunlar"] and "kanonik_birlestirme" not in rapor[0]
    assert any(g["sorun"] == "title_tekrar" for g in kr.site_geneli(rapor))


def test_sitemapte_yonlenen_adres_yetim_degil_sitemap_yonlendirmesi():
    rapor = [{"ad": "http://s.test/", "site_url": "http://s.test/", "derinlik": 0, "ic_baglantilar": []},
             {"ad": "http://s.test/kampanya", "site_url": "http://s.test/blog/kis.html", "derinlik": None,
              "ic_baglantilar": []}]
    bulgular = {g["sorun"]: g["sayfalar"] for g in tarama.baglanti_bulgulari(rapor, ["http://s.test/kampanya"])}
    assert bulgular == {"sitemap_yonlendirme": ["http://s.test/kampanya"]}
