"""SEO kural listesine gore eklenen denetimler ve duzelticiler (1.1, 1.2, 1.5, 3.8, 4.4, 4.7, 5.5, 6.2,
6.3, 6.5, 7.4, 7.5). Ag ve dil modeli kullanilmaz."""
import json
from datetime import date
from urllib.robotparser import RobotFileParser

from seo_app import boru, canli, tarama
from seo_app import duzeltme as dz
from seo_app import html_konum as hk
from seo_app.cikarma import extract, yapisal_veri
from seo_app.kurallar import anahtar_yogunlugu, ek_html_denetimi, puanlar
from seo_app.yazma import YerelDosyaAdaptoru

TEMEL = "http://site.test/"


def _kodlar(html, url=TEMEL):
    return {i["sorun"]: i for i in ek_html_denetimi(yapisal_veri(html, url), url)}


def _sayfa(govde="", head=""):
    return f'<!DOCTYPE html>\n<html lang="tr">\n<head>\n<meta charset="utf-8">\n<title>Çay</title>\n{head}</head>\n<body>\n<main>\n<h1>Çay</h1>\n{govde}\n</main>\n</body>\n</html>\n'


# ------------------------------------------------------------------ tespit
def test_blank_noopener_yalnizca_dis_baglantida():
    html = _sayfa('<a href="https://dis.example/x" target="_blank">dış</a><a href="/ic" target="_blank">iç</a>'
                  '<a href="https://dis.example/y" target="_blank" rel="noreferrer">tamam</a>')
    k = _kodlar(html)
    assert "1 bağlantı" in k["blank_noopener_yok"]["ayrinti"]


def test_guvenlik_basliklari_ve_onbellek_yorumu():
    assert canli.guvenlik_basligi_eksikleri(None) == []
    eksik = canli.guvenlik_basligi_eksikleri({"X-Content-Type-Options": None, "X-Frame-Options": None,
                                              "Content-Security-Policy": "frame-ancestors 'self'"})
    assert eksik == ["X-Content-Type-Options: nosniff"]
    assert len(canli.guvenlik_basligi_eksikleri({k: None for k in canli.GUVENLIK_BASLIKLARI})) == 3
    assert canli.onbellekleniyor_mu({"cache_control": "public, max-age=31536000"}) is True
    assert canli.onbellekleniyor_mu({"cache_control": "no-store"}) is False
    assert canli.onbellekleniyor_mu({"cache_control": None, "expires": "Wed, 21 Oct 2026 07:28:00 GMT"}) is True
    assert canli.onbellekleniyor_mu({"cache_control": None, "expires": None}) is False
    assert canli.onbellekleniyor_mu(None) is None


def test_robots_yonerge_hatalari():
    h = canli.robots_yonerge_hatalari("User-agent: *\n# yorum\nDissallow: /x\nAllow: /\nSitemap: /s.xml\nbozuk satir\n")
    assert [(x["satir"], x["alan"]) for x in h] == [(3, "dissallow"), (6, None)]


def test_kurum_logo_ve_sameas_yalnizca_ana_sayfada():
    jl = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Ç"}</script>'
    k = _kodlar(_sayfa(head=jl))
    assert "schema_kurum_logo_yok" in k and "schema_sosyal_profil_yok" in k
    assert "schema_kurum_logo_yok" not in _kodlar(_sayfa(head=jl), TEMEL + "hakkimizda.html")
    tam = jl.replace('"name":"Ç"', '"name":"Ç","logo":"http://site.test/l.png","sameAs":["https://x.com/c"]')
    k = _kodlar(_sayfa(head=tam))
    assert "schema_kurum_logo_yok" not in k and "schema_sosyal_profil_yok" not in k


def test_breadcrumb_iki_duzey_derinlikte_istenir():
    assert "breadcrumb_yok" in _kodlar(_sayfa(), TEMEL + "urunler/ada-cayi.html")
    assert "breadcrumb_yok" not in _kodlar(_sayfa(), TEMEL + "hakkimizda.html")
    bc = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"A","item":"http://site.test/"}]}</script>'
    assert "breadcrumb_yok" not in _kodlar(_sayfa(head=bc), TEMEL + "urunler/ada-cayi.html")


def test_onerilen_alanlar_ve_guncellik():
    from seo_app.kurallar import yapisal_ek_denetim
    jl = ('<script type="application/ld+json">{"@context":"https://schema.org","@type":"BlogPosting",'
          '"headline":"Çay","datePublished":"2022-01-10"}</script>')
    yv = yapisal_veri(_sayfa(head=jl), TEMEL + "blog/cay.html")
    assert set(yv["schema_onerilen_eksikleri"]) == {"BlogPosting: image", "BlogPosting: author"}
    bulgular = []
    yapisal_ek_denetim(yv, TEMEL + "blog/cay.html", lambda kod, c, a="": bulgular.append((kod, a)),
                       bugun=date(2026, 10, 25))
    kodlar = dict(bulgular)
    assert "yapisal_veri_onerilen_alan" in kodlar and kodlar["icerik_eski"].startswith("son tarih 2022-01-10")
    yv = yapisal_veri(_sayfa(head=jl.replace(',"datePublished":"2022-01-10"', "")), TEMEL + "blog/cay.html")
    bulgular = []
    yapisal_ek_denetim(yv, TEMEL + "blog/cay.html", lambda kod, c, a="": bulgular.append(kod), bugun=date(2026, 10, 25))
    assert "tarih_bilgisi_yok" in bulgular and "icerik_eski" not in bulgular


def test_anahtar_kelime_doldurma_esigi():
    dolu = extract(_sayfa("<p>" + " ".join(["demlik"] * 8 + ["kelime"] * 150) + "</p>").replace("<title>Çay", "<title>Demlik seti"))
    assert anahtar_yogunlugu(dolu)[0] == "demli"
    dogal = extract(_sayfa("<p>" + " ".join(["demlik"] * 2 + ["kelime"] * 150) + "</p>").replace("<title>Çay", "<title>Demlik seti"))
    assert anahtar_yogunlugu(dogal) is None
    sinirda = extract(_sayfa("<p>" + " ".join(["demlik"] * 4 + ["kelime"] * 150) + "</p>").replace("<title>Çay", "<title>Demlik seti"))
    assert anahtar_yogunlugu(sinirda) is None                   # %2,6: esigin (%3) altinda
    kisa = extract(_sayfa("<p>" + " ".join(["demlik"] * 20 + ["kelime"] * 40) + "</p>").replace("<title>Çay", "<title>Demlik seti"))
    assert anahtar_yogunlugu(kisa) is None                      # 150 kelimenin altinda olculmez


def test_erisilebilirlik_denetimi():
    html = _sayfa('<form><input name="ad"><label for="e">E-posta</label><input id="e" name="e">'
                  '<label>Not <textarea name="n"></textarea></label><input type="submit">'
                  '<button></button><button aria-label="Kapat"></button>'
                  '<div aria-labelledby="yok"></div></form>')
    k = _kodlar(html)
    assert k["form_etiketi_yok"]["ayrinti"] == "1 alan, ör. ad"
    assert k["buton_adi_yok"]["ayrinti"] == "1 düğme"
    assert k["aria_gecersiz_referans"]["ayrinti"] == "yok"


def test_sitemap_olu_adres_tarama_geneli_ve_yetim_sayilmaz():
    rapor = [{"ad": TEMEL, "derinlik": 0, "durum_kodu": 200, "ic_baglantilar": []},
             {"ad": TEMEL + "eski.html", "durum_kodu": 404, "hata_sayfasi": True, "ic_baglantilar": []}]
    bulgular = {g["sorun"]: g for g in tarama.baglanti_bulgulari(rapor, [TEMEL, TEMEL + "eski.html"])}
    assert bulgular["sitemap_olu_adres"]["sayfalar"] == [TEMEL + "eski.html"]
    assert "yetim_sayfa" not in bulgular
    # liste modunda da uretilir
    assert any(g["sorun"] == "sitemap_olu_adres" for g in tarama.baglanti_bulgulari(rapor, [TEMEL + "eski.html"], False))


def test_kirik_canonical_ve_robots_kaynak_engeli(monkeypatch):
    rp = RobotFileParser()
    rp.parse(["User-agent: *", "Disallow: /js/"])
    monkeypatch.setattr(canli, "robots_bilgisi", lambda *a, **k: {"_parser": rp})
    monkeypatch.setattr(canli, "baglanti_durumu", lambda adres, **k: {"durum": 404 if "yok" in adres else 200})
    html = _sayfa(head='<link rel="canonical" href="/yok.html">\n<script src="/js/a.js"></script>\n'
                       '<link rel="stylesheet" href="/css/s.css">\n')
    yv = yapisal_veri(html, TEMEL + "sayfa.html")
    k = {i["sorun"]: i for i in boru.kaynak_ve_canonical_denetimi(yv, TEMEL + "sayfa.html",
                                                                  {**boru.VARSAYILAN_AYARLAR})}
    assert "404" in k["canonical_kirik"]["ayrinti"] and k["robots_kaynak_engelliyor"]["ayrinti"] == "1 dosya: /js/a.js"
    assert k["canonical_kirik"]["katman"] == "site"


def test_yeni_bulgular_puana_girer():
    temel = puanlar([])
    for kod in ("canonical_kirik", "robots_kaynak_engelliyor", "onbellek_basligi_yok"):
        assert puanlar([{"sorun": kod, "ciddiyet": "orta", "katman": "site"}])["sayfa"] < temel["sayfa"]
    assert puanlar([], tarama_kodlari=["sitemap_olu_adres"])["sayfa"] < temel["sayfa"]
    assert puanlar([{"sorun": "anahtar_kelime_doldurma", "ciddiyet": "orta", "katman": "sayfa"}])["icerik"] < 100


# ------------------------------------------------------------------ duzelticiler
def _site(tmp_path, dosyalar):
    kok = tmp_path / "site"
    for ad, metin in dosyalar.items():
        (kok / ad).parent.mkdir(parents=True, exist_ok=True)
        (kok / ad).write_text(metin, encoding="utf-8")
    return YerelDosyaAdaptoru(kok)


def _uygula_hepsi(plan, a, tmp_path):
    kararlar = {"kural_hepsi": True, "kararlar": {d["id"]: {"karar": "onay", "risk_onay": True}
                                                  for d in plan["degisiklikler"]}}
    dz.uygula(plan, kararlar, a, tmp_path / "yedek", tmp_path / "g.jsonl")


def _kayit(url, *kodlar, katman="sayfa"):
    return {"ad": url, "site_url": url, "durum_kodu": 200,
            "sorunlar": [{"sorun": k, "katman": katman} for k in kodlar]}


def test_noopener_kurum_alanlari_ve_breadcrumb_uygulanir(tmp_path):
    jl = '<script type="application/ld+json">\n{"@context": "https://schema.org", "@type": "Organization", "name": "Ç"}\n</script>\n'
    ana = _sayfa('<img src="/img/logo.png" alt="Ç"><a href="https://www.instagram.com/caylibahce" target="_blank">ig</a>', jl)
    a = _site(tmp_path, {"index.html": ana, "urunler/index.html": _sayfa().replace("<h1>Çay</h1>", "<h1>Ürünler</h1>"),
                         "urunler/ada.html": _sayfa().replace("<h1>Çay</h1>", "<h1>Ada Çayı</h1>")})
    plan = dz.plan_uret([_kayit(TEMEL, "blank_noopener_yok", "schema_kurum_logo_yok", "schema_sosyal_profil_yok"),
                         _kayit(TEMEL + "urunler/ada.html", "breadcrumb_yok")], [], a, TEMEL, esik=1.01)
    assert {d["bulgu"] for d in plan["degisiklikler"]} >= {"blank_noopener_yok", "schema_kurum_logo_yok",
                                                           "schema_sosyal_profil_yok", "breadcrumb_yok"}
    _uygula_hepsi(plan, a, tmp_path)
    assert all(d["durum"] == "uygulandi" for d in plan["degisiklikler"] if d["bulgu"] != "charset_yok")
    metin = a.oku("index.html").decode("utf-8")
    assert 'target="_blank" rel="noopener"' in metin
    veri = json.loads(metin.split('ld+json">', 1)[1].split("</script>", 1)[0])
    assert veri["logo"] == "http://site.test/img/logo.png" and veri["sameAs"] == ["https://www.instagram.com/caylibahce"]
    alt = a.oku("urunler/ada.html").decode("utf-8")
    bc = json.loads(alt.split('ld+json">', 1)[1].split("</script>", 1)[0])
    assert [x["name"] for x in bc["itemListElement"]] == ["Ana sayfa", "Ürünler", "Ada Çayı"]
    assert bc["itemListElement"][1]["item"] == "http://site.test/urunler/"


def test_breadcrumb_ust_sayfa_yoksa_atlanir(tmp_path):
    a = _site(tmp_path, {"index.html": _sayfa(), "urunler/ada.html": _sayfa()})
    plan = dz.plan_uret([_kayit(TEMEL + "urunler/ada.html", "breadcrumb_yok")], [], a, TEMEL, esik=1.01)
    assert not any(d["bulgu"] == "breadcrumb_yok" for d in plan["degisiklikler"])
    assert any(x["bulgu"] == "breadcrumb_yok" and "üst dizin" in x["neden"] for x in plan["atlanan"])


def test_robots_yonerge_ve_kaynak_duzeltmesi_onay_ister(tmp_path):
    robots = "User-agent: *\nDissallow: /gizli/\nDisallow: /js/\n"
    a = _site(tmp_path, {"robots.txt": robots, "index.html": _sayfa(head='<script src="/js/a.js"></script>\n')})
    plan = dz.plan_uret([_kayit(TEMEL, "robots_bilinmeyen_yonerge", "robots_kaynak_engelliyor", katman="site")],
                        [], a, TEMEL)
    yon = next(d for d in plan["degisiklikler"] if d["bulgu"] == "robots_bilinmeyen_yonerge")
    kay = next(d for d in plan["degisiklikler"] if d["bulgu"] == "robots_kaynak_engelliyor")
    assert yon["kategori"] == "yz" and yon["risk"] == "yuksek" and yon["onay_turu"] != "otomatik"
    assert yon["zorunlu_onay"]                                   # duzeltme bir Disallow'u etkinlestirir
    _uygula_hepsi(plan, a, tmp_path)
    yeni = a.oku("robots.txt").decode("utf-8").replace("\r\n", "\n")
    assert yeni == "User-agent: *\nAllow: /js/a.js\nDisallow: /gizli/\nDisallow: /js/\n"
    rp = RobotFileParser()
    rp.parse(yeni.splitlines())
    assert rp.can_fetch("*", TEMEL + "js/a.js") and not rp.can_fetch("*", TEMEL + "gizli/x")
    assert kay["durum"] == "uygulandi"


def test_sitemap_olu_adres_ve_kirik_canonical_plani(tmp_path, monkeypatch):
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               f'  <url><loc>{TEMEL}</loc></url>\n  <url><loc>{TEMEL}eski.html</loc></url>\n</urlset>\n')
    a = _site(tmp_path, {"sitemap.xml": sitemap, "index.html": _sayfa(head='<link rel="canonical" href="/yok.html">\n')})
    monkeypatch.setattr(dz.Plan, "durum_kodu", lambda self, url: (404, url))
    kayitlar = [_kayit(TEMEL, "canonical_capraz") | {"sorunlar": [{"sorun": "canonical_capraz", "katman": "sayfa"},
                                                                 {"sorun": "canonical_kirik", "katman": "site"}]},
                {"ad": TEMEL + "eski.html", "durum_kodu": 404, "hata_sayfasi": True, "sorunlar": []}]
    bulgular = [{"sorun": "sitemap_olu_adres", "sayfalar": [TEMEL + "eski.html"]}]
    plan = dz.plan_uret(kayitlar, bulgular, a, TEMEL)
    kodlar = [d["bulgu"] for d in plan["degisiklikler"]]
    assert "sitemap_olu_adres" in kodlar and kodlar.count("canonical_kirik") == 1 and "canonical_capraz" not in kodlar
    kirik = next(d for d in plan["degisiklikler"] if d["bulgu"] == "canonical_kirik")
    assert kirik["guven"] >= 0.9 and kirik["yeni"] == TEMEL
    assert any(x["bulgu"] == "canonical_capraz" and "canonical_kirik" in x["neden"] for x in plan["atlanan"])
    assert not any(b["sorun"] == "sitemap_olu_adres" for b in plan["ek_bulgular"])
