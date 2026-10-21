"""Adim 8: baslik hiyerarsisi, hreflang/schema, karisik icerik, odak terim ve sayfalar arasi tekrar."""
import json

import pytest
from conftest import html_yap, sahte_canli, sahte_model

from seo_app import boru
from seo_app.cikarma import extract, yapisal_veri
from seo_app.kurallar import ACIKLAMA, cozum_yolu, ek_html_denetimi, odak_terim_denetimi, site_geneli

YENI_KODLAR = ["baslik_atlamasi", "hreflang_gecersiz", "hreflang_x_default_yok", "schema_kurum_turu_yok",
               "karisik_icerik", "title_h1_uyumsuz", "title_icerikle_uyumsuz",
               "title_tekrar", "meta_tekrar", "h1_tekrar", "h1_bos"]


def ek(html, url=None):
    return {i["sorun"]: i for i in ek_html_denetimi(yapisal_veri(html), url)}


@pytest.mark.parametrize("kod", YENI_KODLAR)
def test_yeni_kodlar_aciklamali_ve_elle_sinifinda(kod):
    assert kod in ACIKLAMA
    assert cozum_yolu(kod) == "elle"        # modele gitmez, deney kosullarini degistirmez


def test_baslik_atlamasi():
    assert "baslik_atlamasi" in ek(html_yap(govde="<h3>Alt</h3>"))           # H1 -> H3
    assert "baslik_atlamasi" not in ek(html_yap(govde="<h2>Bolum</h2><h3>Alt</h3>"))


def test_hreflang_denetimi():
    gecerli = '<link rel="alternate" hreflang="tr" href="/"><link rel="alternate" hreflang="en-GB" href="/en">'
    k = ek(html_yap(head_ek=gecerli))
    assert "hreflang_gecersiz" not in k and "hreflang_x_default_yok" in k
    k = ek(html_yap(head_ek='<link rel="alternate" hreflang="turkce" href="/">'
                           '<link rel="alternate" hreflang="x-default" href="/">'))
    assert "hreflang_gecersiz" in k and "hreflang_x_default_yok" not in k
    assert not {"hreflang_gecersiz", "hreflang_x_default_yok"} & set(ek(html_yap()))   # hreflang yoksa sessiz


def test_schema_kurum_turu():
    kisi = '<script type="application/ld+json">{"@type": "WebPage"}</script>'
    kurum = '<script type="application/ld+json">{"@type": "CollegeOrUniversity", "name": "X"}</script>'
    assert "schema_kurum_turu_yok" in ek(html_yap(head_ek=kisi))
    assert "schema_kurum_turu_yok" not in ek(html_yap(head_ek=kurum))


def test_karisik_icerik_yalnizca_https_sayfada_ve_kaynaklarda():
    govde = '<img src="http://eski.edu.tr/a.png" alt="a"><a href="http://baska.org">baglanti</a>'
    assert ek(html_yap(govde=govde), "https://x.edu.tr/")["karisik_icerik"]["ayrinti"] == "1 kaynak"
    assert "karisik_icerik" not in ek(html_yap(govde=govde), "http://x.edu.tr/")
    assert "karisik_icerik" not in ek(html_yap(govde=govde))                   # adres bilinmiyorsa denetlenmez


def test_odak_terim_uyumu():
    d = extract(html_yap(title="Kimya Laboratuvari Duyurulari Sayfasi", h1="<h1>Kimya Laboratuvari</h1>"))
    assert "title_h1_uyumsuz" not in {i["sorun"] for i in odak_terim_denetimi(d)}
    d = extract(html_yap(title="Kariyer Merkezi Etkinlik Takvimi Sayfasi", h1="<h1>Kimya Laboratuvari</h1>"))
    kodlar = {i["sorun"] for i in odak_terim_denetimi(d)}
    assert "title_h1_uyumsuz" in kodlar and "title_icerikle_uyumsuz" in kodlar


def test_site_geneli_tekrarlari_bulur():
    rapor = [{"ad": "a", "title": "Düzce Üniversitesi", "meta_description": "Ortak aciklama", "h1": ["Anasayfa"]},
             {"ad": "b", "title": "düzce  üniversitesi", "meta_description": "Baska aciklama", "h1": ["Anasayfa"]},
             {"ad": "c", "title": "Kutuphane", "meta_description": "Ortak aciklama", "h1": []},
             {"ad": "d", "title": "Düzce Üniversitesi", "hata": "baglanti yok"}]
    g = {(x["sorun"], tuple(x["sayfalar"])) for x in site_geneli(rapor)}
    assert ("title_tekrar", ("a", "b")) in g          # buyuk/kucuk harf ve bosluk farki yok sayilir
    assert ("meta_tekrar", ("a", "c")) in g
    assert ("h1_tekrar", ("a", "b")) in g
    assert all("d" not in s for _, s in g)            # hatali sayfa gruba katilmaz


def test_topluca_analiz_site_geneli_dosyasi_ve_kayit_notlari(monkeypatch, tmp_path):
    ortak = html_yap(title="Ortak Baslik Metni Burada Yer Aliyor Sayfa")
    sahte_canli(monkeypatch, {"https://a.edu.tr": ortak, "https://b.edu.tr": ortak})
    sahte_model(monkeypatch)
    hedefler = boru.hedefleri_hazirla("a.edu.tr\nb.edu.tr")
    rapor = boru.topluca_analiz(hedefler, {"model": "sahte", "bekleme_sn": 0}, str(tmp_path), tmp_path / "cikti")
    from pathlib import Path
    gruplar = json.loads((Path(rapor[0]["cikti_klasoru"]) / "site_geneli.json").read_text(encoding="utf-8"))
    assert any(g["sorun"] == "title_tekrar" for g in gruplar)
    assert all("title_tekrar" in k["tekrar_bulgulari"] for k in rapor)
    assert all(k["once_puan"] == rapor[0]["once_puan"] for k in rapor)   # puana katilmaz
