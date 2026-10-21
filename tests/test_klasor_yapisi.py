"""Sonuc klasor yapisi: sonuclar/<site_adi>/sonuc_<YYYY-MM-DD_HH-MM-SS>/."""
import json
import re

import pytest
from conftest import KOK, html_yap, sahte_canli, sahte_model

from seo_app import boru, web

DESEN = re.compile(r"^sonuc_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")


@pytest.mark.parametrize("url,beklenen", [
    ("https://www.ornek.com.tr/x", "ornek.com.tr"),
    ("ornek.com.tr", "ornek.com.tr"),
    ("http://WWW.Ornek.COM.tr:8080/a?b=1#c", "ornek.com.tr"),
    ("https://bap.duzce.edu.tr", "bap.duzce.edu.tr"),
    ("https://www.duzce.edu.tr/birimler", "duzce.edu.tr"),
    ("https://müzik.com.tr/", "xn--mzik-0ra.com.tr"),          # IDN -> punycode (ASCII klasor adi)
])
def test_site_adi_alan_adindan_guvenli_turetilir(url, beklenen):
    ad = boru.site_adi(url)
    assert ad == beklenen
    assert re.fullmatch(r"[a-z0-9.-]+", ad)


def test_zaman_damgasi_bicimi():
    assert DESEN.match(boru.zaman_damgasi())


def test_tarama_site_klasorune_yazilir_ve_klasor_yoksa_olusturulur(monkeypatch, tmp_path):
    sahte_canli(monkeypatch, {"https://www.ornek.com.tr/x": html_yap()})
    sahte_model(monkeypatch)
    kok = tmp_path / "yok" / "sonuclar"                       # ust klasorler de yok
    rapor = boru.topluca_analiz([{"url": "https://www.ornek.com.tr/x"}], {"model": "sahte"},
                                str(KOK / "ogretme"), kok)
    klasorler = list((kok / "ornek.com.tr").iterdir())
    assert len(klasorler) == 1 and DESEN.match(klasorler[0].name)
    hedef = klasorler[0]
    assert rapor[0]["cikti_klasoru"] == str(hedef)
    assert {p.name for p in hedef.iterdir()} == {"rapor.json", "ozet.csv", "site_geneli.json",
                                                 "duzeltilmis_https_www.ornek.com.tr_x.html"}


def test_cok_siteli_taramada_her_site_ayri_klasorde_ayni_zamanla(monkeypatch, tmp_path):
    ortak = html_yap(title="Ortak Baslik Metni Burada Yer Aliyor Sayfa")
    sahte_canli(monkeypatch, {"https://a.edu.tr": ortak, "https://b.edu.tr": ortak, "https://a.edu.tr/iki": ortak})
    sahte_model(monkeypatch)
    rapor = boru.topluca_analiz(boru.hedefleri_hazirla("a.edu.tr\nb.edu.tr\na.edu.tr/iki"),
                                {"model": "sahte", "bekleme_sn": 0}, str(KOK / "ogretme"), tmp_path,
                                "sonuc_2026-10-21_10-00-00")
    a = json.loads((tmp_path / "a.edu.tr" / "sonuc_2026-10-21_10-00-00" / "rapor.json").read_text(encoding="utf-8"))
    b = json.loads((tmp_path / "b.edu.tr" / "sonuc_2026-10-21_10-00-00" / "rapor.json").read_text(encoding="utf-8"))
    assert [k["ad"] for k in a] == ["https://a.edu.tr", "https://a.edu.tr/iki"] and len(b) == 1
    # farkli sitelerdeki ayni title tarama genelinde yakalanir ve iki sitenin klasorune de yazilir
    gb = json.loads((tmp_path / "b.edu.tr" / "sonuc_2026-10-21_10-00-00" / "site_geneli.json").read_text(encoding="utf-8"))
    assert any(g["sorun"] == "title_tekrar" and len(g["sayfalar"]) == 3 for g in gb)
    assert all("title_tekrar" in k["tekrar_bulgulari"] for k in rapor)


def test_arayuz_istegi_klasor_adini_kullanicidan_almaz(monkeypatch, tmp_path):
    cagri = {}
    monkeypatch.setattr(web, "SONUC_KOK", tmp_path / "sonuclar")
    monkeypatch.setattr(web, "modelleri_dogrula", lambda *a, **k: None)
    monkeypatch.setattr(web, "_tarama_isi", lambda *a, **k: cagri.update(arg=a))
    web.DURUM["calisiyor"] = False
    r = web.uygulama.test_client().post("/api/tara", json={"adresler": "https://www.ornek.com.tr/x",
                                                           "model": "sahte", "cikti": "C:/baska_yer"})
    assert r.status_code == 200
    cikti = r.get_json()["cikti"].replace("\\", "/")
    assert re.fullmatch(r"sonuclar/ornek\.com\.tr/sonuc_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", cikti)
    _, _, _, sonuc_koku, zaman = cagri["arg"]
    assert sonuc_koku == tmp_path / "sonuclar" and DESEN.match(zaman)
