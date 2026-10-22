"""Adim 6: deney matrisi kosucusu ve ortak tarama dongusu (C2).
Model cagrisi sahte bir fonksiyonla degistirilir; kombinasyon ve klasor mantigi sinanir."""
import csv
import io
import shutil

import pytest
from conftest import KOK, sahte_canli

import deney
from seo_app import boru, web


def _sahte_llm_fixes(d, issues, model, *a, retry=1, **k):
    return {"fixes": [], "reddedilen": [{"neden": "x"}] * retry, "yok_sayilan": [],
            "json_gecerli": True, "sure_sn": 1.5, "bitis_nedeni": "stop", "dusunme_karakter": 0,
            "cevap_karakter": 10, "denemeler": [], "ham": "", "dusunme_basi": ""}


@pytest.fixture
def sayfalar(tmp_path, monkeypatch):
    """Iki canli sayfa (ag olmadan taklit edilir) ve bunlari listeleyen adres dosyasi."""
    html = "<html><head><title>Kisa</title></head><body><p>az</p></body></html>"
    sahte_canli(monkeypatch, {"https://s0.edu.tr": html, "https://s1.edu.tr": html})
    (tmp_path / "adresler.txt").write_text("s0.edu.tr\ns1.edu.tr\n", encoding="utf-8")
    return "adresler.txt"


def test_iki_model_iki_retry_tek_komutla_kosul_sabit(monkeypatch, tmp_path, sayfalar):
    monkeypatch.setattr(boru, "llm_fixes", _sahte_llm_fixes)
    monkeypatch.setattr(deney, "KOK", tmp_path)
    monkeypatch.setattr(deney, "modelleri_dogrula", lambda *a, **k: None)
    shutil.copytree(KOK / "ogretme", tmp_path / "ogretme",
                    ignore=shutil.ignore_patterns("bilgi_tabani_gomme_cache.json"))
    deney.main(["--adresler", sayfalar, "--modeller", "qwen/qwen3.5-9b,qwen3.8-4b-distill",
                "--bekleme", "0", "--retry", "0,1"])
    for site in ("s0.edu.tr", "s1.edu.tr"):           # her site kendi klasorunde
        zamanlar = list((tmp_path / "sonuclar" / site).iterdir())
        assert len(zamanlar) == 1 and zamanlar[0].name.startswith("sonuc_")
        deney_kl = zamanlar[0]
        alt = sorted(p.name for p in deney_kl.iterdir() if p.is_dir())
        assert len(alt) == 4                          # 2 model x 2 retry; kosul sabit
        assert "qwen_qwen3.5-9b__ornek_bilgi__r1" in alt
        for a in alt:
            assert (deney_kl / a / "rapor.json").exists() and (deney_kl / a / "ozet.csv").exists()
        satirlar = list(csv.DictReader(io.StringIO((deney_kl / "karsilastirma.csv").read_text(encoding="utf-8-sig")),
                                       delimiter=";"))
        assert len(satirlar) == 4 and {r["kosul"] for r in satirlar} == {"ornek+bilgi"}
        assert all(s["hatali_sayfa"] == "0" and s["sayfa"] == "1" for s in satirlar)
        assert all(s["toplam_reddedilen"] == "1" for s in satirlar if s["retry"] == "1")
    assert (tmp_path / "sonuclar" / "s0.edu.tr").iterdir().__next__().name ==         (tmp_path / "sonuclar" / "s1.edu.tr").iterdir().__next__().name     # ayni deney zamani


def test_gecersiz_kosul_reddedilir(tmp_path, monkeypatch, sayfalar, capsys):
    monkeypatch.setattr(deney, "KOK", tmp_path)
    monkeypatch.setattr(deney, "modelleri_dogrula", lambda *a, **k: None)
    with pytest.raises(SystemExit) as h:
        deney.main(["--adresler", sayfalar, "--modeller", "m", "--kosullar", "sifir,uydurma"])
    assert h.value.code == 2 and "geçersiz koşul: uydurma" in capsys.readouterr().err


def test_kosullar_yalnizca_deneyde_karsilastirilir(monkeypatch, tmp_path, sayfalar):
    """Arayuzde kosul sabit; deney.py'de bilgi tabaninin katkisini olcmek icin kosullar secilebilir."""
    monkeypatch.setattr(boru, "llm_fixes", _sahte_llm_fixes)
    monkeypatch.setattr(deney, "KOK", tmp_path)
    monkeypatch.setattr(deney, "modelleri_dogrula", lambda *a, **k: None)
    shutil.copytree(KOK / "ogretme", tmp_path / "ogretme",
                    ignore=shutil.ignore_patterns("bilgi_tabani_gomme_cache.json"))
    deney.main(["--adresler", sayfalar, "--modeller", "m", "--bekleme", "0", "--retry", "0",
                "--kosullar", "sifir,ornek+bilgi"])
    deney_kl = next((tmp_path / "sonuclar" / "s0.edu.tr").iterdir())
    assert sorted(p.name for p in deney_kl.iterdir() if p.is_dir()) == ["m__ornek_bilgi__r0", "m__sifir__r0"]
    satirlar = list(csv.DictReader(io.StringIO((deney_kl / "karsilastirma.csv").read_text(encoding="utf-8-sig")),
                                   delimiter=";"))
    assert {r["kosul"] for r in satirlar} == {"sifir", "ornek+bilgi"}


def test_web_ve_cli_ayni_donguyu_kullanir(monkeypatch, tmp_path, sayfalar):
    """C2: web arayuzunun tarama isi topluca_analiz uzerinden calisir."""
    cagrildi = {}
    asil = boru.topluca_analiz

    def izle(*a, **k):
        cagrildi["evet"] = True
        return asil(*a, **k)

    monkeypatch.setattr(web, "topluca_analiz", izle)
    monkeypatch.setattr(boru, "llm_fixes", _sahte_llm_fixes)
    ayarlar, _ = web.ayarlari_dogrula({"model": "sahte", "bekleme_sn": 0})
    hedefler = boru.hedefleri_hazirla((tmp_path / sayfalar).read_text(encoding="utf-8"))
    web._tarama_isi(hedefler, ayarlar, str(KOK / "ogretme"), tmp_path / "c", "sonuc_t")
    assert cagrildi.get("evet")
    assert web.DURUM["biten"] == 2 and len(web.DURUM["sonuclar"]) == 2
    assert (tmp_path / "c" / "s0.edu.tr" / "sonuc_t" / "ozet.csv").exists()
