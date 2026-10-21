"""Her tarama dil modeliyle yapilir; LM Studio kapaliysa veya secilen model yoksa / yuklu
degilse tarama baslamadan acik bir Turkce hatayla durulur. Sessiz geri donus yoktur."""
import pytest
import requests

import deney
from conftest import KOK, sahte_canli
from seo_app import boru, llm, ogretme, web

URL = "http://localhost:1234/v1"
DURUMLAR = [{"id": "qwen/qwen3.5-9b", "tur": "vlm", "yuklu": True},
            {"id": "qwen3.8-4b-distill", "tur": "llm", "yuklu": False},
            {"id": "text-embedding-qwen3-embedding-0.6b", "tur": "embeddings", "yuklu": True}]


def _kapali(*a, **k):
    raise requests.ConnectionError("baglanti reddedildi")


def test_lm_studio_kapaliyken_adresli_hata(monkeypatch):
    monkeypatch.setattr(llm.requests, "get", _kapali)
    with pytest.raises(llm.ModelHatasi) as h:
        llm.modelleri_dogrula(URL, ["qwen/qwen3.5-9b"])
    assert "LM Studio sunucusuna ulaşılamadı" in str(h.value) and URL in str(h.value)


def test_olmayan_model_adiyla_hata(monkeypatch):
    monkeypatch.setattr(llm, "model_durumlari", lambda *a, **k: DURUMLAR)
    with pytest.raises(llm.ModelHatasi) as h:
        llm.modelleri_dogrula(URL, ["olmayan-model-7b"])
    mesaj = str(h.value)
    assert "bulunamadı: olmayan-model-7b" in mesaj and URL in mesaj and "qwen/qwen3.5-9b" in mesaj


def test_yuklu_olmayan_model_ve_gomme_modeli_denetlenir(monkeypatch):
    monkeypatch.setattr(llm, "model_durumlari", lambda *a, **k: DURUMLAR)
    with pytest.raises(llm.ModelHatasi) as h:
        llm.modelleri_dogrula(URL, ["qwen3.8-4b-distill"])
    assert "yüklü değil: qwen3.8-4b-distill" in str(h.value)
    with pytest.raises(llm.ModelHatasi) as h:
        llm.modelleri_dogrula(URL, ["qwen/qwen3.5-9b", "olmayan-gomme"])
    assert "olmayan-gomme" in str(h.value)
    llm.modelleri_dogrula(URL, ["qwen/qwen3.5-9b", "text-embedding-qwen3-embedding-0.6b", None])   # hata yok


def test_model_secilmediyse_hata():
    with pytest.raises(llm.ModelHatasi, match="Sohbet modeli seçilmedi"):
        llm.modelleri_dogrula(URL, [None, ""])


def test_api_tarama_baslamadan_durur_ve_klasor_olusturmaz(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "SONUC_KOK", tmp_path / "sonuclar")
    monkeypatch.setattr(llm.requests, "get", _kapali)
    baslatildi = []
    monkeypatch.setattr(web, "_tarama_isi", lambda *a, **k: baslatildi.append(1))
    web.DURUM["calisiyor"] = False
    r = web.uygulama.test_client().post("/api/tara", json={"adresler": "ornek.edu.tr", "model": "qwen/qwen3.5-9b"})
    assert r.status_code == 503
    assert "LM Studio sunucusuna ulaşılamadı" in r.get_json()["hata"]
    assert baslatildi == [] and not (tmp_path / "sonuclar").exists()


def test_arayuzde_dil_modeli_secenegi_yok():
    html = (KOK / "seo_app/sablonlar/index.html").read_text(encoding="utf-8")
    js = (KOK / "seo_app/statik/uygulama.js").read_text(encoding="utf-8")
    assert "llm-kullan" not in html and "llm_kullan" not in js and "llm_kullan" not in boru.VARSAYILAN_AYARLAR


def test_modelsiz_analiz_sessizce_calismaz(monkeypatch, tmp_path):
    sahte_canli(monkeypatch, {"https://ornek.edu.tr": "<html><title>x</title></html>"})
    with pytest.raises(ValueError, match="Dil modeli belirtilmedi"):
        boru.analiz_et({"url": "ornek.edu.tr"}, {}, str(tmp_path))


def test_gomme_modeli_ulasilamazsa_anahtar_kelimeye_dusulmez(monkeypatch):
    monkeypatch.setattr(ogretme.requests, "post", _kapali)
    d = {"title": "x", "text_sample": "y"}
    sorunlar = [{"sorun": "title_kisa"}]
    with pytest.raises(RuntimeError, match="Gömme modeline ulaşılamadı"):
        ogretme.ogretme_metni("bilgi", d, sorunlar, KOK / "ogretme", 3, URL, "text-embedding-qwen3-embedding-0.6b")
    _, bilgi = ogretme.ogretme_metni("bilgi", d, sorunlar, KOK / "ogretme", 3, URL, None)
    assert bilgi["yontem"] == "anahtar_kelime"        # gomme modeli secilmediyse bilincli yontem


def test_deney_model_yoksa_hic_baslamaz(monkeypatch, tmp_path):
    monkeypatch.setattr(deney, "KOK", tmp_path)
    monkeypatch.setattr(llm, "model_durumlari", lambda *a, **k: DURUMLAR)
    (tmp_path / "a.txt").write_text("ornek.edu.tr\n", encoding="utf-8")
    with pytest.raises(SystemExit) as h:
        deney.main(["--adresler", "a.txt", "--modeller", "olmayan-model"])
    assert "bulunamadı: olmayan-model" in str(h.value.code)
    assert not (tmp_path / "sonuclar").exists()
