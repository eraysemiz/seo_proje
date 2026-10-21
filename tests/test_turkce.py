"""Turkce karakterlerin (ç, ğ, ı, İ, ö, ş, ü) arayuz metinlerinde ve tarama ciktilarinda
korundugunu dogrular. Sorun kodlari ve dosya/klasor adlari bilincli olarak ASCII'dir."""
import csv
import io
import json
import re

from conftest import KOK, sahte_canli, sahte_model

from seo_app import boru, web
from seo_app.kurallar import ACIKLAMA

TURKCE = "çğıİöşü"
# kaynak kodda Turkce karaktersiz yazilmis eski metinlerden ornekler
ESKI_ASCII = re.compile(r"\b(basligi|aciklama yok|Taramayi|Sonuclar|Islem gunlugu|Henuz|kurallarina|"
                        r"Canli adresler|gorsellerde|bulunamadi|yonlendirilmiyor|Secenekler)\b")

SAYFA = """<html lang="tr"><head><meta charset="utf-8"><title>Çağrı Merkezi</title></head>
<body><h1>Öğrenci İşleri Şubesi</h1><p>Güncel duyurular, ölçüm sonuçları ve ılık geçişler.</p>
<img src="logo.png"></body></html>"""
ONERI = [{"alan": "title", "hedef": "", "yeni_deger": "Çağrı Merkezi | Öğrenci İşleri Şubesi Güncel Duyurular",
          "gerekce": "Başlık kısa"}]


def test_kural_aciklamalari_turkce_karakterli():
    assert not [m for m in ACIKLAMA.values() if ESKI_ASCII.search(m)]
    assert ACIKLAMA["title_kisa"] == "Sayfa başlığı çok kısa (30 karakterden az)"
    assert ACIKLAMA["img_alt_eksik"] == "Bazı görsellerde alt metni yok"


def test_arayuz_metinleri_turkce_karakterli():
    for yol in ("seo_app/sablonlar/index.html", "seo_app/statik/uygulama.js"):
        metin = (KOK / yol).read_text(encoding="utf-8")
        assert not ESKI_ASCII.search(metin), (yol, ESKI_ASCII.search(metin).group(0))
        assert set(TURKCE) <= set(metin), yol


def test_aciklama_ucu_utf8_ve_kacissiz_doner():
    r = web.uygulama.test_client().get("/api/aciklamalar")
    # JSON standardi (RFC 8259) UTF-8'i zorunlu tutar; govde dogrudan UTF-8 bayt olmali
    assert "Sayfa başlığı (title) yok".encode("utf-8") in r.get_data()   # ş gibi kacis yok


def test_tarama_ciktilarinda_turkce_karakterler_korunur(monkeypatch, tmp_path):
    sahte_canli(monkeypatch, {"https://ornek.edu.tr": SAYFA})
    sahte_model(monkeypatch, ONERI)
    rapor = boru.topluca_analiz([{"tur": "canli", "url": "ornek.edu.tr"}],
                                {"model": "sahte"}, str(KOK / "ogretme"), tmp_path / "c")
    k = rapor[0]
    assert k["title"] == "Çağrı Merkezi" and k["h1"] == ["Öğrenci İşleri Şubesi"]
    klasor = tmp_path / "c" / "ornek.edu.tr"
    klasor = next(klasor.iterdir())                                   # sonuc_<tarih_saat>
    ham = (klasor / "rapor.json").read_text(encoding="utf-8")
    assert "Öğrenci İşleri Şubesi" in ham and "\\u" not in ham           # ensure_ascii kapali
    assert json.loads(ham)[0]["fixes"][0]["yeni_deger"] == ONERI[0]["yeni_deger"]
    duzeltilmis = (klasor / k["duzeltilmis_dosya"]).read_text(encoding="utf-8")
    assert "<title>Çağrı Merkezi | Öğrenci İşleri Şubesi Güncel Duyurular</title>" in duzeltilmis
    assert "ılık geçişler" in duzeltilmis
    satir = next(csv.DictReader(io.StringIO((klasor / "ozet.csv").read_text(encoding="utf-8-sig")),
                                delimiter=";"))
    assert satir["ad"] == "https://ornek.edu.tr"
    sorun_metni = " ".join(s["ayrinti"] for s in k["sorunlar"])
    assert "görsel" in sorun_metni
