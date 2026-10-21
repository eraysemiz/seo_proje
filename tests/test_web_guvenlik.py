"""Yerel sunucunun siteler arasi istek ve yol disina yazma korumalari."""
import pytest

from seo_app import web


CAGRILAR = []


@pytest.fixture
def istemci(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "SONUC_KOK", tmp_path / "sonuclar")
    # gercek tarama baslatilmasin; yalnizca istek dogrulamasi sinaniyor
    monkeypatch.setattr(web, "_tarama_isi", lambda *a, **k: CAGRILAR.append(a))
    CAGRILAR.clear()
    monkeypatch.setattr(web, "modelleri_dogrula", lambda *a, **k: None)
    web.DURUM["calisiyor"] = False
    return web.uygulama.test_client()


TARAMA_ISTEGI = {"adresler": "ornek.edu.tr", "model": "sahte"}


def test_baska_kaynaktan_duz_metin_istek_reddedilir(istemci):
    r = istemci.post("/api/tara", data='{"adresler":"ornek.edu.tr"}',
                     headers={"Origin": "https://kotu-site.example", "Content-Type": "text/plain"})
    assert r.status_code == 403


def test_json_olmayan_govde_reddedilir(istemci):
    r = istemci.post("/api/tara", data='{"adresler":"ornek.edu.tr"}', headers={"Content-Type": "text/plain"})
    assert r.status_code == 400


@pytest.mark.parametrize("cikti", ["C:/x", "../disari"])
def test_istekteki_cikti_yolu_yok_sayilir(istemci, tmp_path, cikti):
    """Cikti klasoru kullanicidan alinmaz; mutlak ya da ust klasore cikan yol hicbir ise yaramaz."""
    r = istemci.post("/api/tara", json={**TARAMA_ISTEGI, "cikti": cikti})
    assert r.status_code == 200
    assert CAGRILAR[-1][3] == tmp_path / "sonuclar"          # tum ciktilar sonuclar/ altina


def test_proje_disi_ogretme_klasoru_reddedilir(istemci):
    assert istemci.post("/api/tara", json={**TARAMA_ISTEGI, "ogretme_klasoru": "../../"}).status_code == 400


def test_ayni_kaynaktan_gecerli_istek_kabul_edilir(istemci, tmp_path):
    r = istemci.post("/api/tara", json=TARAMA_ISTEGI, headers={"Origin": "http://localhost"})
    assert r.status_code == 200, r.get_json()
    assert len(CAGRILAR) == 1


def test_durdur_baska_kaynaktan_reddedilir(istemci):
    assert istemci.post("/api/durdur", headers={"Origin": "https://kotu-site.example"}).status_code == 403
