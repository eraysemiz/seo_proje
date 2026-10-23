"""Kategori ve katman bazli puan: carpimsal agirlik, kritik tavan, sayfaya atama (puanlama.py)."""
import json

import pytest
from conftest import KOK, html_yap, sahte_canli, sahte_model

from seo_app import boru, puanlama
from seo_app.kurallar import (ACIKLAMA, CIDDIYET_AGIRLIK, KATEGORILER, SORUN_TANIMI, TARAMA_GENELI_KODLARI,
                              puan, puanlar)

TABAN = KOK / "sonuclar" / "sonuc_taban_canli_v2" / "rapor.json"


def sorun(kod, ciddiyet, katman):
    return {"sorun": kod, "ciddiyet": ciddiyet, "katman": katman}


def test_her_sorun_kodunun_puan_tanimi_var():
    assert set(ACIKLAMA) == set(SORUN_TANIMI)
    for kod, (kat, _, ciddiyet, katmanlar) in SORUN_TANIMI.items():
        assert kat in KATEGORILER and ciddiyet in CIDDIYET_AGIRLIK
        assert set(katmanlar.split()) <= {"sayfa", "site", "tarama"}
        assert ("tarama" in katmanlar) == (kod in TARAMA_GENELI_KODLARI)
    assert set(puanlama.TARAMA_CIDDIYETI) == set(TARAMA_GENELI_KODLARI)
    assert set(puanlama.TAVAN) | set(puanlama.SAYFAYA_OZGU) | set(puanlama.KOD_CIDDIYETI) <= set(SORUN_TANIMI)


def test_sorunsuz_sayfa_100_tum_sayfa_sorunlari_sifira_yakin():
    assert puanlar([])["sayfa"] == 100
    en_kotu = [sorun(kod, ciddiyet, "sayfa") for kod, (_, _, ciddiyet, k) in SORUN_TANIMI.items() if "sayfa" in k]
    assert puanlar(en_kotu)["sayfa"] <= 5


def test_tek_yuksek_sorun_belirgin_dusurur_ve_sorunlar_birikir():
    """Eski hesapta tek yuksek sorun sayfa puanini 6,6 puan dusuruyordu; artik agirligi kadar (%20)."""
    tek = puanlar([sorun("meta_description_yok", "yuksek", "sayfa")])["sayfa"]
    assert tek == 80
    bes = puanlar([sorun("meta_description_yok", "yuksek", "sayfa"), sorun("img_alt_eksik", "orta", "sayfa"),
                   sorun("viewport_yok", "orta", "sayfa"), sorun("canonical_yok", "dusuk", "sayfa"),
                   sorun("html_lang_yok", "dusuk", "sayfa")])["sayfa"]
    assert bes < 65 < tek


def test_sorun_eklemek_puani_hic_artirmaz():
    kodlar = [(k, c) for k, (_, _, c, katman) in SORUN_TANIMI.items() if "sayfa" in katman][:25]
    onceki, liste = 100, []
    for kod, c in kodlar:
        liste.append(sorun(kod, c, "sayfa"))
        p = puanlar(liste)["sayfa"]
        assert p <= onceki
        onceki = p


def test_ayni_grup_bir_kez_cezalanir():
    assert puanlar([sorun("title_kisa", "orta", "sayfa"), sorun("title_uzun", "orta", "sayfa")])["sayfa"] == 91


def test_kritik_sorun_tavani():
    assert puanlar([sorun("noindex", "yuksek", "sayfa")])["sayfa"] == 60
    assert puanlar([sorun("yumusak_404", "yuksek", "site")])["sayfa"] == 40


def test_sayfaya_ozgu_site_bulgusu_ve_tarama_geneli_bulgu_sayfa_puanina_girer():
    temel = puanlar([])["sayfa"]
    assert puanlar([sorun("kirik_ic_link", "orta", "site")])["sayfa"] < temel
    assert puanlar([sorun("https_yok", "yuksek", "site")])["sayfa"] == temel        # site geneli: site puaninda
    assert puanlar([sorun("https_yok", "yuksek", "site")])["site"] == 80
    p = puanlar([], tarama_kodlari=["title_tekrar", "icerik_tekrar"])
    assert p["sayfa"] == 70 and p["icerik"] == 70                                   # kopya icerik tavani 70


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
