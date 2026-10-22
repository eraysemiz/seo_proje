"""Denetim gelistirmeleri: indekslenebilirlik, canonical, yonlendirme, sitemap, baglanti, gorsel,
yapisal veri, icerik tekrari, site taramasi, yalnizca denetim, Core Web Vitals ve raporlama.
Ag kullanilmaz; canli yanitlar taklit edilir."""
from datetime import timedelta
from urllib.robotparser import RobotFileParser

import pytest
from conftest import html_yap, sahte_canli, sahte_model

from seo_app import bagimsiz, boru, canli, rapor, render, tarama, web
from seo_app.cikarma import baslik_piksel, extract, icerik_imzasi, imza_benzerligi, yapisal_veri
from seo_app.kurallar import (ACIKLAMA, DUZELTME, ek_html_denetimi, rule_checks, site_geneli, site_ozeti,
                              tekillestir)
from seo_app.uygula import izleme_parametresiz, kural_duzelt

URL = "https://ornek.com/bolum/sayfa"


def ek(html, url=URL, link_basligi=None):
    return {i["sorun"]: i for i in ek_html_denetimi(yapisal_veri(html, url, link_basligi), url)}


# ------------------------------------------------------------------ indekslenebilirlik
@pytest.mark.parametrize("etiket,noindex,nofollow", [
    ('<meta name="robots" content="none">', True, True),
    ('<meta name="googlebot" content="noindex, nofollow">', True, True),
    ('<meta name="ROBOTS" content="NOFOLLOW">', False, True),
    ('<meta name="robots" content="index"><meta name="googlebot" content="noindex">', True, False),
    ('<meta name="robots" content="noarchive">', False, False),
])
def test_meta_robots_turleri(etiket, noindex, nofollow):
    k = ek(html_yap(head_ek=etiket))
    assert ("noindex" in k) is noindex and ("sayfa_nofollow" in k) is nofollow


@pytest.mark.parametrize("deger,beklenen", [
    ("noindex", {"noindex"}), ("none", {"none"}), ("googlebot: noindex, nofollow", {"noindex", "nofollow"}),
    ("bingbot: noindex", set()), ("noarchive, unavailable_after: 25 Jun 2030 15:00:00 PST", {"noarchive"}),
])
def test_x_robots_tag_cozumleme(deger, beklenen):
    assert canli.x_robots_yonergeleri(deger) == beklenen


def test_ayni_sorun_iki_kaynaktan_bir_kez_sayilir():
    s = tekillestir([{"sorun": "noindex", "ayrinti": "meta"}, {"sorun": "noindex", "ayrinti": "X-Robots-Tag"},
                     {"sorun": "hsts_yok", "ayrinti": ""}])
    assert [i["sorun"] for i in s] == ["noindex", "hsts_yok"] and "X-Robots-Tag" in s[0]["ayrinti"]


# ------------------------------------------------------------------ canonical
def test_canonical_capraz_ve_noindex_catismasi():
    k = ek(html_yap(head_ek='<link rel="canonical" href="https://ornek.com/"><meta name="robots" content="noindex">'))
    assert "canonical_capraz" in k and "noindex_canonical_catismasi" in k


def test_kendine_isaret_eden_canonical_sorunsuz():
    k = ek(html_yap(head_ek='<link rel="canonical" href="https://www.ornek.com/bolum/sayfa/">'))
    assert not {"canonical_capraz", "canonical_goreli", "canonical_coklu"} & set(k)


def test_canonical_yapi_sorunlari():
    k = ek(html_yap(head_ek='<link rel="Canonical" href="/bolum/sayfa"><link rel="canonical" href="/baska">',
                    govde='<link rel="canonical" href="">'))
    assert {"canonical_coklu", "canonical_bos", "canonical_head_disi", "canonical_goreli"} <= set(k)


def test_http_baslik_canonical_celiskisi():
    baslik = [{"url": "https://ornek.com/a", "rel": "canonical"}]
    k = ek(html_yap(head_ek='<link rel="canonical" href="https://ornek.com/bolum/sayfa">'), link_basligi=baslik)
    assert k["canonical_baslik_catismasi"]["katman"] == "site"


def test_baslik_canonical_varsa_canonical_yok_bulgusu_cikmaz(monkeypatch, tmp_path):
    sahte_canli(monkeypatch, {"https://ornek.com": html_yap()})
    getir = canli.sayfa_getir
    monkeypatch.setattr(canli, "sayfa_getir", lambda *a, **k: {
        **getir(*a, **k), "link_basligi": [{"url": "https://ornek.com/", "rel": "canonical"}]})
    k = boru.analiz_et({"url": "ornek.com"}, {"yalnizca_denetim": True}, str(tmp_path))
    assert "canonical_yok" not in [s["sorun"] for s in k["sorunlar"]]


def test_self_canonical_izleme_parametrelerini_atar():
    assert izleme_parametresiz("https://a.com/x?id=5&utm_source=g&gclid=1#y") == "https://a.com/x?id=5"
    yeni, uygulanan = kural_duzelt(html_yap(), ["canonical_yok"], "https://a.com/x?utm_medium=e", "tr")
    assert 'href="https://a.com/x"' in yeni and uygulanan


# ------------------------------------------------------------------ yonlendirmeler
def test_meta_refresh_ve_js_yonlendirme():
    k = ek(html_yap(head_ek='<meta http-equiv="refresh" content="0;url=/yeni">'
                            '<script>window.location.href = "/baska";</script>'))
    assert "https://ornek.com/yeni" in k["meta_refresh"]["ayrinti"] and "js_yonlendirme" in k


def test_uzun_betikteki_location_yonlendirme_sayilmaz():
    betik = "<script>" + "var x = 1;" * 80 + "function git(){ window.location.href = '/a'; }</script>"
    assert "js_yonlendirme" not in ek(html_yap(head_ek=betik))


class _Yanit:
    def __init__(self, durum=200, konum=None, govde=b"<html><title>x</title></html>", basliklar=None):
        self.status_code = durum
        self.headers = {"Content-Type": "text/html; charset=utf-8", **(basliklar or {})}
        if konum:
            self.headers["Location"] = konum
        self.content = govde
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"
        self.elapsed = timedelta(milliseconds=20)

    def close(self):
        pass


def _yonlendirmeler(monkeypatch, harita):
    istenen = []

    def sahte_get(adres, **k):
        istenen.append(adres)
        return harita[adres]
    monkeypatch.setattr(canli._oturum, "get", sahte_get)
    return istenen


def test_yonlendirme_dongusu_ayri_hata_turu(monkeypatch):
    _yonlendirmeler(monkeypatch, {"https://a.com/1": _Yanit(301, "/2"), "https://a.com/2": _Yanit(302, "/1")})
    g = canli.sayfa_getir("https://a.com/1")
    assert not g["basarili"] and g["hata_turu"] == "yonlendirme_dongusu"
    sorunlar, _ = canli.canli_denetim(g)
    assert [s["sorun"] for s in sorunlar] == ["yonlendirme_dongusu"]


def test_robotsun_yasakladigi_ara_adres_istenmez(monkeypatch):
    istenen = _yonlendirmeler(monkeypatch, {"https://a.com/izinli": _Yanit(301, "/yasak"),
                                            "https://a.com/yasak": _Yanit(301, "/hedef"),
                                            "https://a.com/hedef": _Yanit(200)})
    g = canli.sayfa_getir("https://a.com/izinli", izin=lambda adres: "yasak" not in adres)
    assert g["robots_engeli"] == "https://a.com/yasak" and istenen == ["https://a.com/izinli"]


def test_zincir_gecici_yonlendirme_ve_basliklar(monkeypatch):
    _yonlendirmeler(monkeypatch, {"https://a.com/x": _Yanit(302, "https://a.com/y"),
                                  "https://a.com/y": _Yanit(200, basliklar={"Link": '<https://a.com/y>; rel="canonical"',
                                                                            "Refresh": "5; url=/z"})})
    g = canli.sayfa_getir("https://a.com/x")
    assert g["son_url"] == "https://a.com/y" and g["yonlendirme_zinciri"] == ["302 https://a.com/x"]
    assert g["link_basligi"][0]["rel"] == "canonical" and g["refresh"]


def test_analizde_ara_adres_engeli_atlanir(monkeypatch, tmp_path):
    p = RobotFileParser()
    p.parse("User-agent: *\nDisallow: /yasak\n".splitlines())
    monkeypatch.setattr(canli, "robots_bilgisi", lambda *a, **k: {"_parser": p})
    _yonlendirmeler(monkeypatch, {"https://a.com/x": _Yanit(301, "/yasak")})
    k = boru.analiz_et({"url": "https://a.com/x"}, {"yalnizca_denetim": True}, str(tmp_path))
    assert k["atlandi"] and "/yasak" in k["atlandi"]


# ------------------------------------------------------------------ sitemap
class _Akis(_Yanit):
    def __init__(self, govde, durum=200):
        super().__init__(durum, govde=govde)

    def iter_content(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]


def test_sitemap_goreli_adres_hatali_aday_ve_boyut_siniri(monkeypatch):
    urlset = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://a.com/s</loc></url></urlset>'
    dosyalar = {"https://a.com/goreli.xml": _Akis(urlset), "https://a.com/buyuk.xml": _Akis(b"x" * 2000)}
    canli.onbellek_temizle()
    monkeypatch.setattr(canli, "SITEMAP_BOYUT_SINIRI", 1000)
    monkeypatch.setattr(canli, "_al", lambda adres, *a, **k: (dosyalar.get(adres, _Akis(b"", 404)), None))
    s = canli.sitemap_bilgisi("https://a.com", {"sitemapler": ["/goreli.xml", "https://a.com/yok.xml",
                                                               "https://a.com/buyuk.xml"]})
    assert s["acilan"] == ["https://a.com/goreli.xml"] and s["tohumlar"] == ["https://a.com/s"]
    assert any("yok.xml" in h for h in s["hatali_adresler"]) and s["cok_buyuk"]


# ------------------------------------------------------------------ on-page
def test_svg_basligi_sayfa_basligi_sayilmaz_ve_meta_buyuk_harf():
    d = extract('<html><head><meta name="Description" content="aciklama"></head>'
                '<body><svg><title>Simge</title></svg><p>metin</p></body></html>')
    assert d["title"] is None and d["meta_description"] == "aciklama"


def test_title_piksel_genisligi():
    genis = "WWWW MMMM WWWW MMMM WWWW MMMM WWWW MMMM WWWW MMMM"      # 49 karakter ama cok genis
    assert baslik_piksel(genis) > 580 and "title_genis" in {i["sorun"] for i in rule_checks(extract(html_yap(title=genis)))}
    assert "title_genis" not in {i["sorun"] for i in rule_checks(extract(html_yap()))}


def test_ince_icerik_menu_disindaki_metinle_olculur():
    menu = "<nav>" + " ".join(["menu ogesi baglantisi"] * 200) + "</nav>"
    d = extract('<html><body>' + menu + '<main><p>kisa icerik metni</p></main></body></html>')
    assert d["word_count"] > 300 and "icerik_az" in {i["sorun"] for i in rule_checks(d)}


def test_bos_baslik_viewport_og_gorsel():
    k = ek(html_yap(head_ek='<meta name="viewport" content="width=device-width, user-scalable=no">'
                            '<meta property="og:title" content="x">', govde="<h2> </h2>"))
    assert {"bos_baslik", "viewport_sorunlu", "og_gorsel_yok"} <= set(k)


def test_js_iskelet_tahmini():
    k = ek('<html><head><title>Uygulama</title></head><body><div id="root"></div>'
           '<script src="/a.js"></script></body></html>')
    assert "js_bagimli_icerik" in k


# ------------------------------------------------------------------ yapisal veri ve hreflang
def test_graph_icindeki_turler_okunur_ve_zorunlu_alanlar():
    graf = ('<script type="application/ld+json">{"@context": "https://schema.org", "@graph": ['
            '{"@type": "Organization", "name": "X"}, {"@type": "Product", "name": "Y"}]}</script>')
    yv = yapisal_veri(html_yap(head_ek=graf), "https://ornek.com/")
    assert yv["schema_turleri"] == ["Organization", "Product"]
    k = ek(html_yap(head_ek=graf), "https://ornek.com/")
    assert "schema_kurum_turu_yok" not in k
    assert "Product: offers/review/aggregateRating" in k["yapisal_veri_eksik_alan"]["ayrinti"]


def test_kurulus_turu_yalnizca_ana_sayfada_beklenir():
    makale = '<script type="application/ld+json">{"@context": "https://schema.org", "@type": "Article", "headline": "h"}</script>'
    assert "schema_kurum_turu_yok" not in ek(html_yap(head_ek=makale), "https://ornek.com/haber/1")
    assert "schema_kurum_turu_yok" in ek(html_yap(head_ek=makale), "https://ornek.com/")


def test_hreflang_bolge_kodu_ve_kendine_referans():
    h = ('<link rel="alternate" hreflang="en-UK" href="https://ornek.com/en">'
         '<link rel="alternate" hreflang="x-default" href="https://ornek.com/">')
    k = ek(html_yap(head_ek=h))
    assert "en-UK" in k["hreflang_gecersiz"]["ayrinti"] and "hreflang_kendine_referans_yok" in k


# ------------------------------------------------------------------ baglanti ve gorsel
def test_baglanti_metni_nofollow_ve_cikmaz_sayfa():
    govde = ('<a href="/a" rel="nofollow">Başvuru koşulları</a><a href="/b">Tıklayın</a>'
             '<a href="https://dis.org/"><img src="x.png"></a>')
    k = ek(html_yap(govde=govde))
    assert {"ic_nofollow", "genel_baglanti_metni", "bos_baglanti_metni"} <= set(k) and "ic_baglanti_yok" not in k
    assert "ic_baglanti_yok" in ek(html_yap(govde='<a href="https://dis.org/">Dış kaynak</a>'))


def test_gorsel_boyut_format_ve_tembel_yukleme():
    gorseller = '<img src="ilk.jpg" alt="a" loading="lazy">' + "".join(
        f'<img src="g{i}.webp" alt="g" width="10" height="10">' for i in range(4))
    k = ek(html_yap(govde=gorseller))
    assert {"ilk_gorsel_lazy", "gorsel_lazy_yok", "gorsel_eski_format", "gorsel_boyut_yok"} <= set(k)
    assert k["gorsel_eski_format"]["ayrinti"] == "1/5 görsel"


def test_kirik_baglanti_ve_buyuk_gorsel_bulgulari(monkeypatch):
    durum = {"https://ornek.com/kirik": {"durum": 404, "yonlendirme": 0, "boyut": None, "hata": None},
             "https://ornek.com/eski": {"durum": 200, "yonlendirme": 1, "boyut": None, "hata": None},
             "https://olu-alan.example/": {"durum": None, "yonlendirme": 0, "boyut": None, "hata": "ConnectionError"},
             "https://ornek.com/b.jpg": {"durum": 200, "yonlendirme": 0, "boyut": 900 * 1024, "hata": None}}
    istenen = []
    monkeypatch.setattr(canli, "baglantilari_denetle", lambda adresler, **k: istenen.extend(adresler) or durum)
    yv = yapisal_veri(html_yap(govde='<a href="/kirik">Kırık</a><a href="/eski">Eski</a>'
                                     '<a href="https://olu-alan.example/">Ölü</a><img src="/b.jpg" alt="b">'), URL)
    a = {**boru.VARSAYILAN_AYARLAR}
    sorunlar, ozet = boru.baglanti_ve_gorsel_denetimi(yv, a, lambda adres: False)
    kodlar = {s["sorun"] for s in sorunlar}
    assert kodlar == {"kirik_ic_link", "kirik_dis_link", "ic_link_yonlendirme", "gorsel_buyuk"}
    assert all(s["katman"] == "site" for s in sorunlar) and ozet["buyuk_gorsel"][0]["kb"] == 900


def test_baglanti_denetimi_robots_yasagina_uyar(monkeypatch):
    canli.onbellek_temizle()
    monkeypatch.setattr(canli, "baglanti_durumu", lambda adres, *a: pytest.fail("yasakli adres istendi"))
    s = canli.baglantilari_denetle(["https://a.com/yasak"], izin=lambda adres: False)
    assert s["https://a.com/yasak"]["hata"] == "robots.txt"


# ------------------------------------------------------------------ icerik tekrari
def _kayit(ad, metin):
    return {"ad": ad, "icerik_imzasi": icerik_imzasi(metin), "icerik_kelime_sayisi": len(metin.split())}


def test_birebir_ve_benzer_icerik_gruplari():
    taban = " ".join(f"kelime{i}" for i in range(400))
    benzer = taban.replace("kelime399", "farkli399")
    rapor = [_kayit("a", taban), _kayit("b", taban), _kayit("c", benzer), _kayit("d", " ".join(f"baska{i}" for i in range(400)))]
    gruplar = {g["sorun"]: g for g in site_geneli(rapor) if g["sorun"].startswith("icerik")}
    assert sorted(gruplar["icerik_tekrar"]["sayfalar"]) == ["a", "b"]
    assert sorted(gruplar["icerik_benzer"]["sayfalar"]) == ["a", "b", "c"]
    assert imza_benzerligi(icerik_imzasi(taban), icerik_imzasi(benzer)) >= 0.9


# ------------------------------------------------------------------ site taramasi
def test_kuyruk_bfs_ve_sitemap_ikincil():
    q = tarama.Kuyruk()
    q.ekle("https://a.com/", 0, "başlangıç")
    q.ekle("https://a.com/s", None, "sitemap", yedek=True)
    q.ekle("https://a.com/b", 1, "bağlantı")
    q.ekle("https://www.a.com/b/", 1, "bağlantı")                  # ayni adres sayilir
    assert [q.al()[0] for _ in range(3)] == ["https://a.com/", "https://a.com/b", "https://a.com/s"]
    assert q.al() is None and not tarama.taranabilir("https://a.com/dosya.pdf", "a.com")


def test_baglanti_grafigi_yetim_derin_ve_hreflang_donus():
    rapor = [
        {"ad": "https://a.com/", "derinlik": 0, "ic_baglantilar": ["https://a.com/b"],
         "hreflang_baglantilari": [{"kod": "en", "href": "https://a.com/en"}]},
        {"ad": "https://a.com/b", "derinlik": 4, "ic_baglantilar": ["https://a.com/"]},
        {"ad": "https://a.com/en", "derinlik": 1, "ic_baglantilar": []},
    ]
    bulgular = {g["sorun"]: g for g in tarama.baglanti_bulgulari(rapor, ["https://a.com/b", "https://a.com/yetim"])}
    assert bulgular["yetim_sayfa"]["sayfalar"] == ["https://a.com/yetim"]
    assert bulgular["derin_sayfa"]["sayfalar"] == ["https://a.com/b"]
    assert bulgular["hreflang_donus_yok"]["sayfalar"] == ["https://a.com/"]
    assert rapor[0]["gelen_baglanti"] == 1 and rapor[2]["gelen_baglanti"] == 0


def _site(n):
    sayfalar = {"https://ornek.com": html_yap(govde='<a href="/a">Bölüm A</a><a href="/dosya.pdf">PDF</a>')}
    sayfalar["https://ornek.com/a"] = html_yap(govde='<a href="/b">Bölüm B</a><a href="/">Ana sayfa</a>')
    sayfalar["https://ornek.com/b"] = html_yap(govde='<a href="/c">Bölüm C</a>')
    sayfalar["https://ornek.com/c"] = html_yap()
    sayfalar["https://ornek.com/s"] = html_yap()
    return sayfalar


def test_site_modu_baglantilari_derinlik_ve_sayfa_siniriyla_izler(monkeypatch, tmp_path):
    sahte_canli(monkeypatch, _site(4))
    monkeypatch.setattr(canli, "sitemap_bilgisi", lambda *a, **k: {"tohumlar": ["https://ornek.com/s"]})
    toplamlar = []
    rapor = boru.topluca_analiz([{"url": "ornek.com"}], {"yalnizca_denetim": True, "tarama_modu": "site",
                                                         "en_fazla_derinlik": 2, "bekleme_sn": 0},
                                str(tmp_path), tmp_path / "c", toplam_degisti=toplamlar.append)
    adlar = [k["ad"] for k in rapor]
    assert adlar == ["https://ornek.com", "https://ornek.com/a", "https://ornek.com/b", "https://ornek.com/s"]
    assert [k["derinlik"] for k in rapor] == [0, 1, 2, None] and rapor[3]["kesif_kaynagi"] == "sitemap"
    assert rapor[0]["gelen_baglanti"] == 1 and toplamlar[-1] == 4
    rapor = boru.topluca_analiz([{"url": "ornek.com"}], {"yalnizca_denetim": True, "tarama_modu": "site",
                                                         "en_fazla_sayfa": 2, "bekleme_sn": 0},
                                str(tmp_path), tmp_path / "d")
    assert len(rapor) == 2


def test_liste_modu_baglantilari_izlemez(monkeypatch, tmp_path):
    sahte_canli(monkeypatch, _site(4))
    rapor = boru.topluca_analiz([{"url": "ornek.com"}], {"yalnizca_denetim": True, "bekleme_sn": 0},
                                str(tmp_path), tmp_path / "c")
    assert len(rapor) == 1 and rapor[0]["derinlik"] == 0


# ------------------------------------------------------------------ yalnizca denetim
def test_yalnizca_denetim_modeli_cagirmaz(monkeypatch, tmp_path):
    sahte_canli(monkeypatch, {"https://ornek.com": html_yap(title=None, lang="")})
    kayit = sahte_model(monkeypatch)
    k = boru.analiz_et({"url": "ornek.com"}, {"yalnizca_denetim": True}, str(tmp_path))
    assert "kodlar" not in kayit and k["model"] is None and k["yalnizca_denetim"]
    assert "title_yok" in k["kalan_sorunlar"] and "html_lang_yok" in k["cozulen_sorunlar"]   # kural duzeltmesi calisir
    assert k["cozum_orani"] is None


def test_yalnizca_denetimde_lm_studio_denetlenmez(monkeypatch):
    monkeypatch.setattr(web, "modelleri_dogrula", lambda *a, **k: pytest.fail("LM Studio denetlendi"))
    monkeypatch.setattr(web, "_tarama_isi", lambda *a, **k: None)
    web.DURUM["calisiyor"] = False
    r = web.uygulama.test_client().post("/api/tara", json={"adresler": "ornek.com", "yalnizca_denetim": True,
                                                           "model": "x"})
    assert r.status_code == 200


def test_gecersiz_tarama_modu_reddedilir():
    ayarlar, hata = web.ayarlari_dogrula({"tarama_modu": "hepsi"})
    assert ayarlar is None and "tarama_modu" in hata
    ayarlar, hata = web.ayarlari_dogrula({"tarama_modu": "site", "en_fazla_sayfa": "20", "yalnizca_denetim": True,
                                          "model": "m"})
    assert hata is None and ayarlar["en_fazla_sayfa"] == 20 and ayarlar["model"] is None


# ------------------------------------------------------------------ Core Web Vitals
class _PsiYanit:
    status_code = 200

    def __init__(self, veri):
        self._veri = veri

    def json(self):
        return self._veri


def test_saha_verisi_oncelikli_ve_cwv_bulgulari(monkeypatch):
    veri = {"lighthouseResult": {"categories": {"seo": {"score": 0.9, "auditRefs": []}, "performance": {"score": 0.42}},
                                 "audits": {"largest-contentful-paint": {"numericValue": 1800.0},
                                            "cumulative-layout-shift": {"numericValue": 0.02},
                                            "total-blocking-time": {"numericValue": 700.0},
                                            "total-byte-weight": {"numericValue": 4 * 1048576}}},
            "loadingExperience": {"metrics": {"LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 4600},
                                              "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 15}}}}
    monkeypatch.setattr(bagimsiz.requests, "get", lambda *a, **k: _PsiYanit(veri))
    o = bagimsiz.pagespeed_seo("https://ornek.com/", anahtar="k")
    assert o["performans_puani"] == 42 and o["cwv"]["lcp_ms"] == 4600 and o["cwv"]["cls"] == 0.15
    kodlar = {s["sorun"]: s for s in bagimsiz.cwv_sorunlari(o)}
    assert kodlar["cwv_lcp_yavas"]["ciddiyet"] == "orta" and kodlar["cwv_cls_yuksek"]["ciddiyet"] == "dusuk"
    assert "TBT" in kodlar["cwv_inp_yavas"]["ayrinti"] and "sayfa_agir" in kodlar


# ------------------------------------------------------------------ raporlama
def test_her_sorunun_duzeltme_onerisi_var():
    assert set(ACIKLAMA) == set(DUZELTME) and all(DUZELTME.values())


def test_site_ozeti_ve_html_rapor_kacislar():
    kayitlar = [{"ad": "https://a.com/<b>", "title": "<script>alert(1)</script>", "once_puanlar": {"sayfa": 70, "site": 80},
                 "sonra_puanlar": {"sayfa": 90}, "once_sorun_sayisi": 2,
                 "sorunlar": [{"sorun": "title_kisa", "ciddiyet": "orta", "katman": "sayfa", "cozum_yolu": "model"},
                              {"sorun": "hsts_yok", "ciddiyet": "dusuk", "katman": "site", "cozum_yolu": "elle"}]},
                {"ad": "https://a.com/2", "sorunlar": [{"sorun": "hsts_yok", "ciddiyet": "dusuk", "katman": "site"}]}]
    ozet = site_ozeti(kayitlar)
    assert ozet[0]["sorun"] == "title_kisa" and next(s for s in ozet if s["sorun"] == "hsts_yok")["sayfa_sayisi"] == 2
    html = rapor.html_rapor(kayitlar, ozet, [{"sorun": "yetim_sayfa", "deger": "1", "sayfalar": ["https://a.com/y"]}])
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert DUZELTME["hsts_yok"].split("'")[0] in html and "https://a.com/y" in html


def test_render_tarayici_yoksa_aciklamali_hata(monkeypatch):
    monkeypatch.setattr(render, "tarayici_bul", lambda: None)
    html, hata = render.render_et("https://a.com/", "ajan")
    assert html is None and "bulunamadı" in hata


def test_og_duzeltmesi_sayfanin_gorselini_og_image_yapar():
    html = html_yap(govde='<img src="/ikon.svg" alt=""><img src="/foto.jpg" alt="Kampüs">')
    yeni, uygulanan = kural_duzelt(html, ["og_etiketleri_yok"], "https://a.com/x", "tr")
    assert 'content="https://a.com/foto.jpg"' in yeni and "og:image" in uygulanan[0]
