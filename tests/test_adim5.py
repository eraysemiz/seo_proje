"""Adim 5: TTFB olcumu (A7), ayar dogrulama (C5), otomatik ozet.csv (E1)."""
import time
from datetime import timedelta

import pytest
import requests

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


@pytest.mark.parametrize("alan,deger", [("kosul", "xyz"), ("retry", "iki"), ("max_tokens", -5),
                                        ("bekleme_sn", "hizli"), ("zaman_asimi", 0)])
def test_hatali_ayarlar_reddedilir(alan, deger):
    ayarlar, hata = web.ayarlari_dogrula({alan: deger})
    assert ayarlar is None and hata


def test_gecerli_ayarlar_donusturulur():
    ayarlar, hata = web.ayarlari_dogrula({"kosul": "ornek+bilgi", "retry": "1", "bekleme_sn": "0.5"})
    assert hata is None
    assert ayarlar["kosul"] == "ornek+bilgi" and ayarlar["retry"] == 1 and ayarlar["bekleme_sn"] == 0.5


def test_bilinmeyen_kosul_apide_400(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "SONUC_KOK", tmp_path)
    web.DURUM["calisiyor"] = False
    r = web.uygulama.test_client().post("/api/tara", json={"mod": "dosya", "klasor": "snapshots",
                                                           "llm_kullan": False, "kosul": "xyz"})
    assert r.status_code == 400 and "kosul" in r.get_json()["hata"]


def test_tarama_sonunda_ozet_csv_kendiliginden_yazilir(tmp_path):
    sayfa = tmp_path / "sayfa.html"
    sayfa.write_text("<html><head><title>Bolum</title></head><body><h1>Bolum</h1></body></html>",
                     encoding="utf-8")
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    ayarlar, _ = web.ayarlari_dogrula({"llm_kullan": False})
    web._tarama_isi([{"tur": "dosya", "yol": str(sayfa)}], ayarlar, str(tmp_path), cikti)
    csv = (cikti / "ozet.csv").read_text(encoding="utf-8-sig")
    assert csv.splitlines()[0].startswith("ad;") and "sayfa.html" in csv
    assert "yok_sayilan_oneri" in csv.splitlines()[0]
