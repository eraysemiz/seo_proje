"""Kural tabanli duzeltmeler, oneri uygulama ve kucuk yardimci fonksiyon testleri."""
from bs4 import BeautifulSoup
from conftest import html_yap

from seo_app.boru import _guvenli_ad
from seo_app.canli import normalize
from seo_app.uygula import apply_fixes, kural_duzelt


def test_kural_duzelt_canonical_lang_h1_viewport():
    html = html_yap(h1="<h1>Bir</h1><h1>Iki</h1>", lang="")
    yeni, uygulanan = kural_duzelt(html, ["canonical_yok", "html_lang_yok", "h1_birden_fazla", "viewport_yok"],
                                   "https://x.edu.tr/", "tr")
    s = BeautifulSoup(yeni, "lxml")
    assert s.find("link", rel="canonical")["href"] == "https://x.edu.tr/"
    assert s.html["lang"] == "tr"
    assert len(s.find_all("h1")) == 1
    assert s.find("meta", attrs={"name": "viewport"}) is not None
    assert len(uygulanan) == 4


def test_kural_duzelt_og_etiketleri_mevcut_degerlerden_turetilir():
    yeni, _ = kural_duzelt(html_yap(), ["og_etiketleri_yok"], "https://x.edu.tr/", "tr")
    s = BeautifulSoup(yeni, "lxml")
    assert s.find("meta", property="og:title")["content"] == s.title.get_text()
    assert s.find("meta", property="og:url")["content"] == "https://x.edu.tr/"


def test_kural_duzelt_canonical_adres_yoksa_eklemez():
    _, uygulanan = kural_duzelt(html_yap(), ["canonical_yok"], None, "tr")
    assert uygulanan == []


def test_apply_fixes_title_ve_alt():
    html = html_yap(govde='<img src="logo.png">')
    fixes = [{"alan": "title", "yeni_deger": "Yeni Baslik Metni Burada Yer Aliyor"},
             {"alan": "img_alt", "yeni_deger": "Universite logosu", "hedef": "g1", "hedef_src": "logo.png"}]
    s = BeautifulSoup(apply_fixes(html, fixes), "lxml")
    assert s.title.get_text() == "Yeni Baslik Metni Burada Yer Aliyor"
    assert s.find("img")["alt"] == "Universite logosu"


def test_normalize():
    assert normalize("duzce.edu.tr") == "https://duzce.edu.tr"
    assert normalize("http://a.com/x#bolum") == "http://a.com/x"
    assert normalize("  ") == ""


def test_guvenli_ad_turkce_harfleri_korur():
    assert _guvenli_ad("Düzce Üniversitesi _ Anasayfa.htm") == "Düzce_Üniversitesi___Anasayfa"
    assert _guvenli_ad("https://bap.duzce.edu.tr") == "https_bap.duzce.edu.tr"
