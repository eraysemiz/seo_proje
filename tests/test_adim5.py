"""Adim 5: TTFB olcumu (A7), ayar dogrulama (C5), otomatik ozet.csv (E1)."""
import time
from datetime import timedelta

import pytest
import requests

from conftest import KOK, sahte_canli, sahte_model

from seo_app import canli, web


class _SahteYanit:
    def __init__(self, elapsed_sn):
        self.url = "https://ornek.edu.tr/"
        self.status_code = 200
        self.history = []
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.content = b"<html><title>x</title></html>"
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"
        self.elapsed = timedelta(seconds=elapsed_sn)


def test_basarisiz_ssl_denemesi_ttfbye_karismaz(monkeypatch):
    """Ilk (dogrulamali) deneme 0,4 sn bekleyip SSL hatasi verir; olcum yalnizca ikinci istegi yansitmali."""
    cagrilar = []

    def sahte_get(adres, verify=True, **k):
        cagrilar.append(verify)
        if verify:
            time.sleep(0.4)
            raise requests.exceptions.SSLError("zincir eksik")
        return _SahteYanit(0.05)

    monkeypatch.setattr(canli._oturum, "get", sahte_get)
    g = canli.sayfa_getir("https://ornek.edu.tr/")
    assert cagrilar == [True, False]
    assert g["ssl_hatasi"]
    assert g["ttfb_ms"] == 50
    assert g["toplam_ms"] < 400            # basarisiz denemenin 400 ms'si toplam sureye de girmiyor
    assert g["yonlendirme_ms"] == 0


@pytest.mark.parametrize("alan,deger", [("retry", "iki"), ("max_tokens", -5),
                                        ("bekleme_sn", "hizli"), ("zaman_asimi", 0)])
def test_hatali_ayarlar_reddedilir(alan, deger):
    ayarlar, hata = web.ayarlari_dogrula({alan: deger})
    assert ayarlar is None and hata


def test_gecerli_ayarlar_donusturulur():
    ayarlar, hata = web.ayarlari_dogrula({"retry": "1", "bekleme_sn": "0.5"})
    assert hata is None
    assert ayarlar["retry"] == 1 and ayarlar["bekleme_sn"] == 0.5


def test_deney_kosulu_her_zaman_ornek_bilgi():
    """Kosul kullaniciya sorulmaz; istekte gonderilse bile yok sayilir."""
    for gonderilen in (None, "sifir", "xyz"):
        ayarlar, hata = web.ayarlari_dogrula({} if gonderilen is None else {"kosul": gonderilen})
        assert hata is None and ayarlar["kosul"] == "ornek+bilgi"


def test_analiz_ogretme_metnini_ornek_bilgi_ile_cagirir(monkeypatch, tmp_path):
    from seo_app import boru
    sahte_canli(monkeypatch, {"https://ornek.edu.tr": "<html><title>Kisa</title></html>"})
    sahte_model(monkeypatch)
    cagri = {}

    def sahte_ogretme(kosul, *a, **k):
        cagri["kosul"] = kosul
        return "", {"ornek": 3, "kural": 4, "yontem": "anahtar_kelime"}

    monkeypatch.setattr(boru, "ogretme_metni", sahte_ogretme)
    ayarlar, _ = web.ayarlari_dogrula({"model": "sahte", "kosul": "sifir"})   # istekteki kosul yok sayilir
    k = boru.analiz_et({"url": "ornek.edu.tr"}, ayarlar, str(tmp_path))
    assert cagri["kosul"] == "ornek+bilgi" and k["kosul"] == "ornek+bilgi"


def test_arayuzde_kosul_secenegi_yok():
    html = (KOK / "seo_app/sablonlar/index.html").read_text(encoding="utf-8")
    js = (KOK / "seo_app/statik/uygulama.js").read_text(encoding="utf-8")
    assert 'id="kosul"' not in html and "#kosul" not in js and "kosul:" not in js


def test_tarama_sonunda_ozet_csv_kendiliginden_yazilir(monkeypatch, tmp_path):
    sahte_canli(monkeypatch, {"https://ornek.edu.tr":
                              "<html><head><title>Bolum</title></head><body><h1>Bolum</h1></body></html>"})
    sahte_model(monkeypatch)
    ayarlar, _ = web.ayarlari_dogrula({"model": "sahte"})
    web._tarama_isi([{"url": "ornek.edu.tr"}], ayarlar, str(tmp_path), tmp_path / "s", "sonuc_t")
    csv = (tmp_path / "s" / "ornek.edu.tr" / "sonuc_t" / "ozet.csv").read_text(encoding="utf-8-sig")
    assert csv.splitlines()[0].startswith("ad;") and "https://ornek.edu.tr" in csv
    assert "yok_sayilan_oneri" in csv.splitlines()[0]
