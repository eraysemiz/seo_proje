"""Kural denetimi, ek HTML denetimi, cozum yolu ve puanlama testleri."""
from conftest import html_yap

from seo_app.cikarma import extract, yapisal_veri
from seo_app.kurallar import cozum_yolu, ek_html_denetimi, puan, rule_checks


def kodlar(html):
    return {i["sorun"] for i in rule_checks(extract(html))}


def test_saglam_sayfada_temel_sorun_yok():
    assert kodlar(html_yap(head_ek='<link rel="canonical" href="https://x.edu.tr/">')) == set()


def test_title_yok_kisa_uzun():
    assert "title_yok" in kodlar(html_yap(title=None))
    assert "title_kisa" in kodlar(html_yap(title="Kisa baslik"))
    assert "title_uzun" in kodlar(html_yap(title="Uzun " * 20))


def test_meta_yok_kisa_uzun():
    assert "meta_description_yok" in kodlar(html_yap(meta=None))
    assert "meta_description_kisa" in kodlar(html_yap(meta="Cok kisa aciklama"))
    assert "meta_description_uzun" in kodlar(html_yap(meta="aciklama " * 30))


def test_h1_yok_ve_birden_fazla():
    assert "h1_yok" in kodlar(html_yap(h1=""))
    assert "h1_birden_fazla" in kodlar(html_yap(h1="<h1>Bir</h1><h1>Iki</h1>"))


def test_alt_metni_eksik_ve_lang_yok():
    k = kodlar(html_yap(govde='<img src="a.png"><img src="b.png" alt="Logo">', lang=""))
    assert "img_alt_eksik" in k and "html_lang_yok" in k


def test_cozum_yolu_siniflandirmasi():
    assert cozum_yolu("title_kisa") == "model"
    assert cozum_yolu("img_alt_eksik") == "model"
    assert cozum_yolu("canonical_yok") == "kural"
    assert cozum_yolu("viewport_yok") == "kural"
    assert cozum_yolu("icerik_az") == "elle"
    assert cozum_yolu("robots_yok") == "elle"


def test_ek_html_denetimi_eksikleri_bulur():
    k = {i["sorun"] for i in ek_html_denetimi(yapisal_veri(html_yap()))}
    assert {"viewport_yok", "yapisal_veri_yok", "og_etiketleri_yok", "twitter_card_yok", "favicon_yok"} <= k


def test_ek_html_denetimi_meta_noindex():
    yv = yapisal_veri(html_yap(head_ek='<meta name="robots" content="noindex, follow">'))
    assert "noindex" in {i["sorun"] for i in ek_html_denetimi(yv)}


def test_puan_agirliklari_ve_alt_sinir():
    assert puan([]) == 100
    assert puan([{"ciddiyet": "yuksek"}, {"ciddiyet": "orta"}, {"ciddiyet": "dusuk"}]) == 100 - 15 - 8 - 3
    assert puan([{"ciddiyet": "yuksek"}] * 20) == 0
