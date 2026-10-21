"""A3: sadakat denetimi. Gercek kaydedilmis Duzce anasayfasi ve 20 Ekim 2026 testinde
modelin urettigi, sadakat denetimini haksiz yere gecen meta aciklama kullanilir."""
import pytest
from conftest import KOK, html_yap

from seo_app.cikarma import extract, kokler
from seo_app.llm import dogrula

SAYFA = KOK / "snapshots" / "Düzce Üniversitesi _ Anasayfa.htm"
KODLAR = ["title_kisa", "meta_description_kisa", "h1_yok", "img_alt_eksik"]
UYDURMA_META = ("Düzce Üniversitesi, Çevre ve Sağlık alanında uzmanlaşmış bir üniversitedir. "
                "Kuruluşu, başarıları, akademik birimler, yönetim kadrosu ve iletişim bilgileri.")


def oneri(alan, deger):
    return {"alan": alan, "hedef": "", "yeni_deger": deger, "gerekce": ""}


@pytest.fixture(scope="module")
def duzce():
    if not SAYFA.exists():
        pytest.skip("kaydedilmis Duzce sayfasi yok")
    return extract(SAYFA.read_text(encoding="utf-8", errors="ignore"))


def test_uydurma_niteleme_iceren_meta_reddedilir(duzce):
    ok, neden = dogrula(oneri("meta_description", UYDURMA_META), duzce, KODLAR, set(), {})
    assert not ok
    assert neden.startswith("dogrulanamayan_niteleme")
    assert "uzmanlaşmış" in neden and "başarıları" in neden


def test_daha_once_kabul_edilen_mesru_oneriler_hala_gecer(duzce):
    assert dogrula(oneri("h1", "Düzce Üniversitesi Anasayfa"), duzce, KODLAR, set(), {})[0]
    meta = ("Düzce Üniversitesi resmi web sitesi: akademik birimler, duyurular, "
            "etkinlikler ve iletişim bilgileri.")
    assert dogrula(oneri("meta_description", meta), duzce, KODLAR, set(), {}) == (True, "")


def test_menudeki_kelimeler_sadakat_kanitı_sayilmaz():
    html = html_yap(govde="<nav><a>Başarı Sıralamaları</a><a>Uzay Madenciliği Merkezi</a></nav>")
    d = extract(html)
    assert "madenciliği"[:5] not in d["kelime_kokleri"]
    ok, neden = dogrula(oneri("title", "Bilgisayar Mühendisliği Uzay Madenciliği Merkezi"),
                        d, ["title_kisa"], set(), {})
    assert not ok and neden.startswith("sayfada_olmayan_ifade")


def test_main_varsa_yalnizca_main_kullanilir():
    html = ("<html><head><title>Bolum Sayfasi</title></head><body>"
            "<div class='menu'>Kuantum Laboratuvari</div><main><h1>Ders Programi</h1></main></body></html>")
    d = extract(html)
    assert "kuant" not in d["kelime_kokleri"] and "progr" in d["kelime_kokleri"]


def test_sayfanin_kendi_basliginda_gecen_niteleme_serbest():
    d = extract(html_yap(title="Mükemmel Mühendislik Laboratuvarı Tanıtım Sayfası"))
    ok, _ = dogrula(oneri("title", "Mükemmel Mühendislik Laboratuvarı Tanıtım Sayfası"),
                    d, ["title_kisa"], set(), {})
    assert ok


def test_sapkali_harfler_kelimeyi_bolmez():
    # duzeltmeden once "zekâsı" kelimesi "zek" + "sı" diye bolunup hic kok uretmiyordu
    assert "zekâs" in kokler("Yapay Zekâsı")
