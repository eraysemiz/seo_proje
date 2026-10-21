"""llm_fixes akisi: model cagrisi sahte bir fonksiyonla degistirilerek ag olmadan sinanir.
Senaryo, 20 Ekim'deki gercek testi yeniden uretir: ilk denemede title iki kez uzun gelir,
ikinci denemede model zaten kabul edilmis alanlari da tekrar gonderir."""
import json

from conftest import html_yap

from seo_app import boru, llm
from seo_app.cikarma import extract
from seo_app.kurallar import rule_checks

UZUN_TITLE = "Duzce Universitesi | Bilgisayar Muhendisligi Bolumu Ders Programi Sayfasi"   # >60


def _cevap(fixes):
    return {"icerik": json.dumps({"fixes": fixes}), "dusunme": "", "bitis": "stop", "sure": 1.0,
            "ilk_token_sn": 0.1, "parca": 10, "uretim_hizi": 30.0}


def _sayfa():
    govde = "<p>Duzce Universitesi Bilgisayar Muhendisligi Bolumu</p>"
    html = html_yap(title="Kisa", meta="Kisa aciklama", h1="",
                    govde=govde + "".join(f'<img src="g{i}.png">' for i in range(1, 10)))
    d = extract(html)
    return d, rule_checks(d)


def _ilk_cevap_fixleri():
    fx = [{"alan": "title", "hedef": "", "yeni_deger": UZUN_TITLE, "gerekce": ""},
          {"alan": "meta_description", "hedef": "",
           "yeni_deger": "Duzce Universitesi Bilgisayar Muhendisligi bolumu ders programi ve akademik kadro bilgileri.",
           "gerekce": ""},
          {"alan": "h1", "hedef": "", "yeni_deger": "Bilgisayar Muhendisligi", "gerekce": ""}]
    fx += [{"alan": "img_alt", "hedef": f"g{i}", "yeni_deger": "Bolum gorseli", "gerekce": ""} for i in range(1, 9)]
    return fx


def test_yeniden_denemedeki_tekrarlar_ret_sayilmaz(monkeypatch):
    d, sorunlar = _sayfa()
    ilk = _ilk_cevap_fixleri()                       # 11 oneri: title (uzun) + 10 gecerli
    ikinci = [dict(f) for f in ilk]                  # model ayni 11 oneriyi tekrar gonderir
    cevaplar = iter([_cevap(ilk), _cevap(ikinci)])
    monkeypatch.setattr(llm, "_cagri", lambda *a, **k: next(cevaplar))
    sonuc = llm.llm_fixes(d, sorunlar, "sahte-model", "test", "http://x", 3000, 60, False, retry=1)
    nedenler = [r["neden"] for r in sonuc["reddedilen"]]
    assert nedenler == ["title_uzunluk_" + str(len(UZUN_TITLE))] * 2   # gercek ret: 2
    assert len(sonuc["yok_sayilan"]) == 10                              # tekrar: ret sayilmaz
    assert len(sonuc["fixes"]) == 10
    assert sonuc["denemeler"][1]["yok_sayilan"] == 10


def test_ayni_cevaptaki_cift_oneri_hala_ret_sayilir(monkeypatch):
    d, sorunlar = _sayfa()
    h1 = {"alan": "h1", "hedef": "", "yeni_deger": "Bilgisayar Muhendisligi", "gerekce": ""}
    monkeypatch.setattr(llm, "_cagri", lambda *a, **k: _cevap([h1, dict(h1)]))
    sonuc = llm.llm_fixes(d, sorunlar, "sahte-model", "test", "http://x", 3000, 60, False, retry=0)
    assert [r["neden"] for r in sonuc["reddedilen"]] == ["ayni_alan_tekrar"]
    assert sonuc["yok_sayilan"] == []


def test_modele_yalnizca_model_sinifi_sorunlar_gider(monkeypatch, tmp_path):
    """A1: canonical, lang, icerik_az gibi sorunlar modelin istemine girmez."""
    gonderilen = {}

    def sahte_llm_fixes(d, issues, *a, **k):
        gonderilen["kodlar"] = [i["sorun"] for i in issues]
        return {"fixes": [], "reddedilen": [], "yok_sayilan": [], "json_gecerli": True, "sure_sn": 0,
                "bitis_nedeni": "stop", "dusunme_karakter": 0, "cevap_karakter": 0, "denemeler": [],
                "ham": "", "dusunme_basi": ""}

    monkeypatch.setattr(boru, "llm_fixes", sahte_llm_fixes)
    yol = tmp_path / "sayfa.html"
    yol.write_text("<html><head><title>Kisa</title></head><body><p>az metin</p></body></html>", encoding="utf-8")
    kayit = boru.analiz_et({"tur": "dosya", "yol": str(yol)}, {"model": "sahte", "kosul": "sifir"}, str(tmp_path))
    tum = {i["sorun"] for i in kayit["sorunlar"]}
    assert {"canonical_yok", "html_lang_yok", "icerik_az"} <= tum          # sorunlar tespit ediliyor
    assert set(gonderilen["kodlar"]) == {"title_kisa", "meta_description_yok", "h1_yok"}
