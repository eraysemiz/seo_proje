"""Yerel sunucunun siteler arasi istek ve yol disina yazma korumalari."""
import pytest

from seo_app import web


@pytest.fixture
def istemci(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "SONUC_KOK", tmp_path / "sonuclar")
    # gercek tarama baslatilmasin; yalnizca istek dogrulamasi sinaniyor
    monkeypatch.setattr(web, "_tarama_isi", lambda *a, **k: None)
    web.DURUM["calisiyor"] = False
    return web.uygulama.test_client()


DOSYA_ISTEGI = {"mod": "dosya", "klasor": "snapshots", "llm_kullan": False}


def test_baska_kaynaktan_duz_metin_istek_reddedilir(istemci):
    r = istemci.post("/api/tara", data='{"mod":"dosya","klasor":"snapshots"}',
                     headers={"Origin": "https://kotu-site.example", "Content-Type": "text/plain"})
    assert r.status_code == 403


def test_json_olmayan_govde_reddedilir(istemci):
    r = istemci.post("/api/tara", data='{"mod":"dosya"}', headers={"Content-Type": "text/plain"})
    assert r.status_code == 400


def test_mutlak_cikti_yolu_reddedilir(istemci):
    r = istemci.post("/api/tara", json={**DOSYA_ISTEGI, "cikti": "C:/x"})
    assert r.status_code == 400


def test_ust_klasore_cikan_cikti_reddedilir(istemci):
    r = istemci.post("/api/tara", json={**DOSYA_ISTEGI, "cikti": "../disari"})
    assert r.status_code == 400


def test_proje_disi_klasor_ve_ogretme_klasoru_reddedilir(istemci):
    assert istemci.post("/api/tara", json={**DOSYA_ISTEGI, "klasor": "C:/Windows"}).status_code == 400
    assert istemci.post("/api/tara", json={**DOSYA_ISTEGI, "ogretme_klasoru": "../../"}).status_code == 400


def test_ayni_kaynaktan_gecerli_istek_kabul_edilir(istemci, tmp_path):
    r = istemci.post("/api/tara", json={**DOSYA_ISTEGI, "cikti": "deneme"},
                     headers={"Origin": "http://localhost"})
    assert r.status_code == 200, r.get_json()
    assert (tmp_path / "sonuclar" / "deneme").is_dir()


def test_durdur_baska_kaynaktan_reddedilir(istemci):
    assert istemci.post("/api/durdur", headers={"Origin": "https://kotu-site.example"}).status_code == 403
