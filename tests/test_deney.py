"""Adim 6: deney matrisi kosucusu ve ortak tarama dongusu (C2).
Model cagrisi sahte bir fonksiyonla degistirilir; kombinasyon ve klasor mantigi sinanir."""
import csv
import io
import shutil

import pytest
from conftest import KOK

import deney
from seo_app import boru, web


def _sahte_llm_fixes(d, issues, model, *a, retry=1, **k):
    return {"fixes": [], "reddedilen": [{"neden": "x"}] * retry, "yok_sayilan": [],
            "json_gecerli": True, "sure_sn": 1.5, "bitis_nedeni": "stop", "dusunme_karakter": 0,
            "cevap_karakter": 10, "denemeler": [], "ham": "", "dusunme_basi": ""}


@pytest.fixture
def sayfalar(tmp_path):
    kl = tmp_path / "sayfalar"
    kl.mkdir()
    for i in range(2):
        (kl / f"s{i}.html").write_text("<html><head><title>Kisa</title></head><body><p>az</p></body></html>",
                                       encoding="utf-8")
    return kl


def test_iki_model_dort_kosul_iki_retry_tek_komutla(monkeypatch, tmp_path, sayfalar):
    monkeypatch.setattr(boru, "llm_fixes", _sahte_llm_fixes)
    monkeypatch.setattr(deney, "KOK", tmp_path)
    shutil.copytree(KOK / "ogretme", tmp_path / "ogretme",
                    ignore=shutil.ignore_patterns("bilgi_tabani_gomme_cache.json"))
    deney.main(["--klasor", "sayfalar", "--modeller", "qwen/qwen3.5-9b,qwen3.8-4b-distill",
                "--ad", "matris", "--kosullar", "sifir,ornek,bilgi,ornek+bilgi", "--retry", "0,1"])
    deney_kl = tmp_path / "sonuclar" / "matris"
    alt = sorted(p.name for p in deney_kl.iterdir() if p.is_dir())
    assert len(alt) == 16
    assert "qwen_qwen3.5-9b__ornek_bilgi__r1" in alt
    for a in alt:
        assert (deney_kl / a / "rapor.json").exists() and (deney_kl / a / "ozet.csv").exists()
    satirlar = list(csv.DictReader(io.StringIO((deney_kl / "karsilastirma.csv").read_text(encoding="utf-8-sig")),
                                   delimiter=";"))
    assert len(satirlar) == 16
    assert all(s["hatali_sayfa"] == "0" for s in satirlar)
    r1 = [s for s in satirlar if s["retry"] == "1"]
    assert all(s["toplam_reddedilen"] == "2" and s["sayfa"] == "2" for s in r1)


def test_bilinmeyen_kosul_cli_hatasi(tmp_path, monkeypatch, sayfalar):
    monkeypatch.setattr(deney, "KOK", tmp_path)
    with pytest.raises(SystemExit):
        deney.main(["--klasor", "sayfalar", "--modeller", "m", "--kosullar", "sifir,yanlis"])


def test_web_ve_cli_ayni_donguyu_kullanir(monkeypatch, tmp_path, sayfalar):
    """C2: web arayuzunun tarama isi topluca_analiz uzerinden calisir."""
    cagrildi = {}
    asil = boru.topluca_analiz

    def izle(*a, **k):
        cagrildi["evet"] = True
        return asil(*a, **k)

    monkeypatch.setattr(web, "topluca_analiz", izle)
    ayarlar, _ = web.ayarlari_dogrula({"llm_kullan": False})
    cikti = tmp_path / "c"
    web._tarama_isi(boru.hedefleri_hazirla("dosya", None, sayfalar), ayarlar, str(tmp_path), cikti)
    assert cagrildi.get("evet")
    assert web.DURUM["biten"] == 2 and len(web.DURUM["sonuclar"]) == 2
    assert (cikti / "ozet.csv").exists()
