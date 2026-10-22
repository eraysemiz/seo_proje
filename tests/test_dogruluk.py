"""Adim 7: A4 (alt metni / gorsel kimligi), A5 (bos H1), A6 (sitemap karsilastirmasi),
A9 (hata sayfalari ve robots uyumu) regresyon testleri. Ag kullanilmaz."""
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
from conftest import html_yap, sahte_model

from seo_app import boru, canli
from seo_app.cikarma import extract
from seo_app.kurallar import rule_checks
from seo_app.uygula import apply_fixes, kural_duzelt


def kodlar(html):
    return {i["sorun"] for i in rule_checks(extract(html))}


# ------------------------------------------------------------------ A4
def test_bos_alt_dekoratif_sayilir_eksik_sayilmaz():
    d = extract(html_yap(govde='<img src="cizgi.png" alt=""><img src="logo.png" alt="Logo">'))
    assert d["img_no_alt"] == [] and d["img_bos_alt"] == 1
    assert "img_alt_eksik" not in kodlar(html_yap(govde='<img src="cizgi.png" alt="">'))


def test_ortak_yer_tutucu_src_alt_metnini_cogaltmaz():
    """Tembel yuklemede uc gorsel ayni yer tutucuyu paylasir; oneri yalnizca hedef gorsele yazilmali."""
    govde = "".join(f'<img src="bos.gif" data-src="foto{i}.jpg">' for i in range(3))
    html = html_yap(govde=govde)
    d = extract(html)
    assert [g["src"] for g in d["img_no_alt"]] == ["foto0.jpg", "foto1.jpg", "foto2.jpg"]
    hedef = d["img_no_alt"][1]
    yeni = apply_fixes(html, [{"alan": "img_alt", "yeni_deger": "Ikinci fotograf",
                               "hedef_src": hedef["src"], "hedef_sira": hedef["sira"]}])
    altlar = [i.get("alt") for i in BeautifulSoup(yeni, "lxml").find_all("img")]
    assert altlar == [None, "Ikinci fotograf", None]


def test_noscript_yedegi_sira_numarasini_kaydirmaz():
    govde = '<noscript><img src="yedek.png"></noscript><img src="a.png"><img src="b.png">'
    html = html_yap(govde=govde)
    d = extract(html)
    hedef = d["img_no_alt"][1]                      # b.png
    yeni = apply_fixes(html, [{"alan": "img_alt", "yeni_deger": "B gorseli",
                               "hedef_src": hedef["src"], "hedef_sira": hedef["sira"]}])
    s = BeautifulSoup(yeni, "lxml")
    assert s.find("img", src="b.png")["alt"] == "B gorseli"
    assert s.find("img", src="a.png").get("alt") is None


# ------------------------------------------------------------------ A5
def test_yalnizca_logo_iceren_h1_var_sayilmaz():
    k = kodlar(html_yap(h1='<h1><img src="logo.png" alt=""></h1>'))
    assert "h1_yok" in k and "h1_bos" in k


def test_model_h1_onerisi_bos_h1_varken_de_uygulanir():
    html = html_yap(h1='<h1><img src="logo.png" alt=""></h1>')
    yeni = apply_fixes(html, [{"alan": "h1", "yeni_deger": "Bilgisayar Muhendisligi"}])
    assert "h1_yok" not in kodlar(yeni)


def test_birden_fazla_h1_duzeltmesi_bos_h1_yuzunden_asil_basligi_dusurmez():
    html = html_yap(h1='<h1><img src="logo.png" alt=""></h1><h1>Asil Baslik</h1><h1>Ikinci</h1>')
    yeni, _ = kural_duzelt(html, ["h1_birden_fazla"], None, "tr")
    metinli = [h.get_text(strip=True) for h in BeautifulSoup(yeni, "lxml").find_all("h1") if h.get_text(strip=True)]
    assert metinli == ["Asil Baslik"]


# ------------------------------------------------------------------ A6
class _Yanit:
    def __init__(self, govde, durum=200):
        self.status_code = durum
        self.content = govde.encode()


def _sitemap_kur(monkeypatch, dosyalar):
    canli.onbellek_temizle()
    monkeypatch.setattr(canli, "_al", lambda adres, *a, **k: (dosyalar.get(adres, _Yanit("", 404)), None))


URLSET = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          '<url><loc>{}</loc></url></urlset>')


def test_www_ve_sema_farki_yanlis_pozitif_uretmez(monkeypatch):
    _sitemap_kur(monkeypatch, {"https://ornek.edu.tr/sitemap.xml": _Yanit(URLSET.format("http://www.ornek.edu.tr/bolum/"))})
    s = canli.sitemap_bilgisi("https://ornek.edu.tr", {"sitemapler": []})
    assert s["tam_okundu"]
    assert canli.url_anahtari("https://ornek.edu.tr/bolum") in s["adresler"]


def test_tam_okunmayan_sitemap_dizini_sayfa_yok_bulgusu_uretmez(monkeypatch):
    n = canli.EN_FAZLA_SITEMAP + 2           # acma sinirindan fazla alt dosya
    dizin = ('<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
             "".join(f"<sitemap><loc>https://ornek.edu.tr/s{i}.xml</loc></sitemap>" for i in range(n)) +
             "</sitemapindex>")
    dosyalar = {"https://ornek.edu.tr/sitemap.xml": _Yanit(dizin)}
    dosyalar.update({f"https://ornek.edu.tr/s{i}.xml": _Yanit(URLSET.format(f"https://ornek.edu.tr/s{i}")) for i in range(n)})
    _sitemap_kur(monkeypatch, dosyalar)
    s = canli.sitemap_bilgisi("https://ornek.edu.tr", {"sitemapler": []})
    assert s["tam_okundu"] is False          # dizin + sinir kadar alt dosya acildi, kalanlar okunmadi


# ------------------------------------------------------------------ A9
def _robots(metin):
    p = RobotFileParser()
    p.parse(metin.splitlines())
    return {"_parser": p, "var": True, "sitemapler": [], "hata": None}


def test_araca_ozel_robots_kurali_uygulanir():
    r = _robots("User-agent: DU-SEO-Denetim\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    assert canli.sayfa_engelli_mi(r, "https://ornek.edu.tr/x", canli.AJAN_BELIRTECI)
    assert not canli.sayfa_engelli_mi(r, "https://ornek.edu.tr/x")          # genel SEO durumu acik


def _sahte_getirme(durum, son_url="https://ornek.edu.tr/"):
    return {"basarili": True, "url": "https://ornek.edu.tr/", "son_url": son_url, "durum_kodu": durum,
            "html": "<html><head><title>Sayfa bulunamadi</title></head><body>404</body></html>"}


def test_hata_sayfasinin_html_i_denetlenmez(monkeypatch, tmp_path):
    canli.onbellek_temizle()
    monkeypatch.setattr(canli, "robots_bilgisi", lambda *a, **k: {"_parser": None})
    monkeypatch.setattr(canli, "sayfa_getir", lambda *a, **k: _sahte_getirme(404))
    monkeypatch.setattr(canli, "canli_denetim",
                        lambda *a, **k: ([{"sorun": "hata_durum_kodu", "ciddiyet": "yuksek", "ayrinti": "404",
                                           "katman": "site", "cozum_yolu": "elle"}], {}))
    sahte_model(monkeypatch)
    k = boru.analiz_et({"url": "ornek.edu.tr"}, {"model": "sahte"}, str(tmp_path))
    assert k["hata_sayfasi"] is True
    assert [i["sorun"] for i in k["sorunlar"]] == ["hata_durum_kodu"]
    assert k["sonra_sorun_sayisi"] == 1


def test_yonlendirilen_hostun_robots_kurali_da_uygulanir(monkeypatch, tmp_path):
    engelli = _robots("User-agent: *\nDisallow: /\n")
    acik = {"_parser": None}
    monkeypatch.setattr(canli, "robots_bilgisi",
                        lambda kok_adres, *a, **k: engelli if "baska" in kok_adres else acik)
    monkeypatch.setattr(canli, "sayfa_getir", lambda *a, **k: _sahte_getirme(200, "https://baska.edu.tr/"))
    k = boru.analiz_et({"url": "ornek.edu.tr"}, {"model": "sahte"}, str(tmp_path))
    assert k.get("atlandi") and "baska.edu.tr" in k["atlandi"]
