"""Adim 10: kategori ve katman bazli normallestirilmis puan (A10)."""
import json

import pytest
from conftest import KOK, html_yap, sahte_canli, sahte_model

from seo_app import boru
from seo_app.kurallar import (ACIKLAMA, CIDDIYET_AGIRLIK, KATEGORILER, SORUN_TANIMI, TARAMA_GENELI_KODLARI,
                              puan, puanlar)

TABAN = KOK / "sonuclar" / "sonuc_taban_canli_v2" / "rapor.json"


def sorun(kod, ciddiyet, katman):
    return {"sorun": kod, "ciddiyet": ciddiyet, "katman": katman}


def test_her_sorun_kodunun_puan_tanimi_var():
    assert set(ACIKLAMA) - set(TARAMA_GENELI_KODLARI) == set(SORUN_TANIMI)
    for kat, _, ciddiyet, katmanlar in SORUN_TANIMI.values():
        assert kat in KATEGORILER and ciddiyet in CIDDIYET_AGIRLIK
        assert set(katmanlar.split()) <= {"sayfa", "site"}


def test_sorunsuz_sayfa_100_tum_sayfa_sorunlari_0():
    assert puanlar([])["sayfa"] == 100
    # her sayfa grubundan en agir sorun bir arada -> en kotu durum
    en_kotu, gorulen = [], set()
    for kod, (kat, grup, ciddiyet, katmanlar) in SORUN_TANIMI.items():
        if "sayfa" in katmanlar.split():
            agirlik = CIDDIYET_AGIRLIK[ciddiyet]
            onceki = next((s for s in en_kotu if SORUN_TANIMI[s["sorun"]][1] == grup), None)
            if onceki is None or CIDDIYET_AGIRLIK[onceki["ciddiyet"]] < agirlik:
                if onceki:
                    en_kotu.remove(onceki)
                en_kotu.append(sorun(kod, ciddiyet, "sayfa"))
    assert puanlar(en_kotu)["sayfa"] == 0


def test_eski_olcegi_sifirlayan_sorunlar_yeni_olcekte_ayirt_edilir():
    """Eski olcekte 7 yuksek sorun puani 0'a indirir; yeni olcekte katman puanlari 0'dan buyuk kalir."""
    sorunlar = ([sorun("title_yok", "yuksek", "sayfa"), sorun("meta_description_yok", "yuksek", "sayfa"),
                 sorun("h1_yok", "yuksek", "sayfa")] +
                [sorun(k, "yuksek", "site") for k in ("https_yok", "hata_durum_kodu", "noindex",
                                                       "robots_tum_siteyi_engelliyor")])
    assert puan(sorunlar) == 0
    p = puanlar(sorunlar)
    assert 0 < p["sayfa"] < 100 and 0 < p["site"] < 100


def test_hata_sayfasinin_sayfa_puani_olculmedi_sayilir():
    p = puanlar([sorun("hata_durum_kodu", "yuksek", "site")], sayfa_olculdu=False)
    assert p["sayfa"] is None and p["site"] < 100
    assert p["icerik"] is None            # icerik kodlarinin tamami sayfa katmaninda
    assert p["guvenlik"] is not None      # guvenlik kodlari site katmaninda da var


def test_analiz_kaydinda_once_sonra_puanlari(monkeypatch, tmp_path):
    sahte_canli(monkeypatch, {"https://x.edu.tr": html_yap(lang="")},
                site_sorunlari=[{**sorun("robots_yok", "orta", "site"), "cozum_yolu": "elle", "ayrinti": ""}])
    sahte_model(monkeypatch)
    k = boru.analiz_et({"url": "x.edu.tr"}, {"model": "sahte"}, str(tmp_path))
    assert k["once_puanlar"]["site"] == k["sonra_puanlar"]["site"] < 100   # site katmani HTML'le degismez
    assert k["sonra_puanlar"]["sayfa"] > k["once_puanlar"]["sayfa"]      # kural duzeltmeleri puani artirir


@pytest.mark.skipif(not TABAN.exists(), reason="58 sitelik temel tarama yok")
def test_gercek_veride_tespit_edilen_ciddiyet_tablodaki_ust_siniri_asmaz():
    for k in json.loads(TABAN.read_text(encoding="utf-8")):
        for s in k.get("sorunlar", []):
            kat, grup, en_yuksek, katmanlar = SORUN_TANIMI[s["sorun"]]
            assert CIDDIYET_AGIRLIK[s["ciddiyet"]] <= CIDDIYET_AGIRLIK[en_yuksek], s
            assert s["katman"] in katmanlar.split(), s
