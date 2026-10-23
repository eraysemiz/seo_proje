"""Masaustu baslaticinin arayuz disi mantigi: onay argumanlari, diff ayristirma, sonuc listesi,
ayarlar, hata iletileri ve alt surec iptali."""
import json
import sys
import time

import pytest

from masaustu import ayarlar as ay
from masaustu import durum
from masaustu import plan as pl
from masaustu import sonuclar as sn
from masaustu.surecler import Surec, betik_komutu


def degisiklik(i, kategori="yz", risk="dusuk", durum_="oneriliyor", duzenleme=None, yeni="x"):
    return {"id": i, "kategori": kategori, "risk": risk, "durum": durum_, "duzenleme": duzenleme, "yeni": yeni}


PLAN = {"degisiklikler": [
    degisiklik("D001", "kural"), degisiklik("D002", "kural"),
    degisiklik("D003"), degisiklik("D004", risk="yuksek"),
    degisiklik("D005", duzenleme={"alan": "title"}, yeni="Eski başlık"),
    degisiklik("D006", durum_="gecersiz"),
]}
BOS = {"kural_hepsi": False, "kararlar": {}}


def secim(**kararlar):
    s = pl.baslangic_secimleri(PLAN, BOS)
    for i, k in kararlar.items():
        s[i].update(k)
    return s


def test_onay_argumanlari_temel():
    arg, uyari = pl.onay_argumanlari(PLAN, BOS, secim(D003={"karar": "onay"}, D004={"karar": "onay", "risk": True},
                                                      D002={"karar": "ret"}), kural_hepsi=True)
    assert arg == ["--kural-hepsi", "--onay", "D003", "D004", "--ret", "D002", "--riski-kabul", "D004"]
    assert uyari == []


def test_duzenlenen_deger_turkce_karakterle_gonderilir():
    arg, _ = pl.onay_argumanlari(PLAN, BOS, secim(D005={"karar": "onay", "deger": "Çay ve ıhlamur | Şube"}), False)
    assert arg == ["--onay", "D005", "--duzenle", "D005=Çay ve ıhlamur | Şube"]


def test_degismeyen_deger_ve_gecersiz_oneri_gonderilmez():
    arg, _ = pl.onay_argumanlari(PLAN, BOS, secim(D005={"karar": "onay", "deger": "Eski başlık"},
                                                  D006={"karar": "onay"}), False)
    assert arg == ["--onay", "D005"]


def test_geri_cekilen_onay_ve_kapatilan_tumunu_onayla_ret_olur():
    onceki = {"kural_hepsi": True, "kararlar": {"D003": {"karar": "onay"}, "D004": {"karar": "onay", "risk_onay": True}}}
    s = pl.baslangic_secimleri(PLAN, onceki)
    s["D003"]["karar"] = None
    s["D004"]["risk"] = False
    arg, uyari = pl.onay_argumanlari(PLAN, onceki, s, kural_hepsi=False)
    assert arg == ["--onay", "D004", "--ret", "D001", "D002", "D003"]
    assert len(uyari) == 1 and "D004" in uyari[0]


def test_onaylanan_sayisi_kararlari_coz_kosullarini_izler():
    kararlar = {"kural_hepsi": True, "kararlar": {"D002": {"karar": "ret"}, "D003": {"karar": "onay"},
                                                  "D004": {"karar": "onay"}, "D006": {"karar": "onay"}}}
    assert pl.onaylanan_sayisi(PLAN, kararlar) == 2      # D001 (tumu) + D003; D004 risk onaysiz, D006 gecersiz


def test_diff_bloklari(tmp_path):
    (tmp_path / "onizleme.diff").write_text(
        "#####\n# Kural çözer — 1 değişiklik\n#####\n\n# D002 [Kural çözer] h1 — /\n--- a/index.html\n+++ b/index.html\n"
        "-<h1>Çay</h1>\n+<h2>Çay</h2>\n\n#####\n# YZ önerir\n#####\n# D010 [YZ önerir] title — /\n-a\n+b\n",
        encoding="utf-8")
    b = pl.diff_bloklari(tmp_path)
    assert set(b) == {"D002", "D010"}
    assert b["D002"].splitlines()[-1] == "+<h2>Çay</h2>" and "YZ önerir\n" not in b["D002"]


def test_sonuc_listesi_ve_geri_alinabilirlik(tmp_path):
    site = tmp_path / "sonuclar" / "127.0.0.1"
    eski, yeni = site / "sonuc_2026-10-23_10-00-00", site / "sonuc_2026-10-23_11-30-05"
    for k in (eski, yeni):
        k.mkdir(parents=True)
    (yeni / "degisiklikler.json").write_text("{}", encoding="utf-8")
    (yeni / "uygulama.json").write_text("{}", encoding="utf-8")
    (eski / "rapor.html").write_text("", encoding="utf-8")
    liste = sn.listele(tmp_path)
    assert [x["zaman"] for x in liste] == ["2026-10-23 11:30:05", "2026-10-23 10:00:00"]
    assert (liste[0]["tur"], liste[0]["durum"]) == ("Yönetici", "uygulandı")
    assert (liste[1]["tur"], [a for a, _ in liste[1]["raporlar"]]) == ("Salt okunur", ["Analiz raporu"])
    assert sn.son_yonetici_klasoru(tmp_path, uygulanmis=True) == yeni
    assert not sn.geri_alinabilir(site)
    (site / "son_uygulama.json").write_text(json.dumps({"sonuc": str(yeni), "durum": "uygulandi"}), encoding="utf-8")
    assert sn.geri_alinabilir(site)
    (site / "son_uygulama.json").write_text(json.dumps({"sonuc": str(yeni), "durum": "geri_alindi"}), encoding="utf-8")
    assert not sn.geri_alinabilir(site)


def test_ayarlar_turkce_yolla_kaydedilir_ve_proje_koku_bulunur(tmp_path, monkeypatch):
    proje = tmp_path / "Düzce Üniversitesi" / "proje"
    (proje / "seo_app").mkdir(parents=True)
    (proje / "yonet.py").write_text("", encoding="utf-8")
    alt = proje / "dist" / "SEO_Denetim"
    alt.mkdir(parents=True)
    assert ay.proje_kokunu_bul([alt]) == proje.resolve()
    dosya = tmp_path / "ayarlar" / "ayarlar.json"
    ay.kaydet({**ay.VARSAYILAN, "proje_koku": str(proje), "sohbet_modeli": "model-ğüşiöç"}, dosya)
    okunan = ay.yukle(dosya)
    assert okunan["proje_koku"] == str(proje) and okunan["sohbet_modeli"] == "model-ğüşiöç"
    assert ay.dogrula(okunan) == []
    assert len(ay.dogrula({**okunan, "proje_koku": str(tmp_path), "test_portu": "abc"})) == 2


def test_lm_kapaliyken_anlasilir_ileti():
    d = durum.lm_durumu("http://127.0.0.1:9/v1", ["m"], sure=0.5)
    assert d["erisim"] is False
    assert "LM Studio sunucusuna ulaşılamadı" in durum.lm_iletisi(d, "http://127.0.0.1:9/v1")
    assert "bulunamadı: m" in durum.lm_iletisi({"erisim": True, "eksik": ["m"], "yuklu_degil": []}, "u")


def test_hata_iletisi():
    tk = pytest.importorskip("tkinter")       # noqa: F841 - uygulama modulu tkinter ice aktarir
    from masaustu.uygulama import hata_iletisi
    assert hata_iletisi(["  · bir şey", "HATA: Plan bulunamadı: x"], 2) == "Plan bulunamadı: x"
    assert hata_iletisi(["Traceback (most recent call last):", "OSError: [WinError 10048] ..."], 1).startswith("Port kullanımda")
    assert hata_iletisi(["Traceback (most recent call last):", "KeyError: 'a'"], 1) == "Beklenmeyen hata: KeyError: 'a'"
    assert "3 çıkış koduyla" in hata_iletisi([], 3)


def test_surec_turkce_cikti_ve_iptal(tmp_path):
    betik = tmp_path / "uzun_ş.py"
    betik.write_text("import time\nprint('başladı ğüşıöç', flush=True)\ntime.sleep(30)\n", encoding="utf-8")
    satirlar, bitis = [], {}
    s = Surec("deneme", betik_komutu(betik), tmp_path, satir=satirlar.append,
              bitti=lambda kod, iptal: bitis.update(kod=kod, iptal=iptal)).baslat()
    son = time.time() + 15
    while not satirlar and time.time() < son:
        time.sleep(0.05)
    assert satirlar == ["başladı ğüşıöç"]
    s.iptal()
    s.bekle(10)
    assert bitis["iptal"] is True and not s.calisiyor


def test_betik_komutu_kaynaktan():
    assert betik_komutu("a.py", "--x", 3) == [sys.executable, "-u", "a.py", "--x", "3"]
