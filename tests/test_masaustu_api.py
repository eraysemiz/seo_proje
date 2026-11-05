"""Masaustu arayuzunun yerel sunucusu: jeton ve Host denetimi, yol kisitlari, cakisma engeli, yerel varliklar.
Ag, dil modeli ve pencere kullanilmaz; analiz betikleri calistirilmaz."""
import json
import re
from pathlib import Path

import pytest

from masaustu import api
from masaustu.cekirdek import Cekirdek, KullaniciHatasi, hata_iletisi, satir_turu, sonuc_klasoru

ARAYUZ = Path(api.__file__).parent / "arayuz"
JETON = "deneme-jetonu"
ADRES = "http://127.0.0.1:5999"


@pytest.fixture
def ortam(tmp_path):
    proje = tmp_path / "Düzce Üniversitesi" / "proje"
    (proje / "seo_app").mkdir(parents=True)
    (proje / "yonet.py").write_text("", encoding="utf-8")
    (proje / "ogretme").mkdir()
    sonuc = proje / "sonuclar" / "127.0.0.1" / "sonuc_2026-11-01_10-00-00"
    sonuc.mkdir(parents=True)
    (sonuc / "rapor.html").write_text("<h1>Rapor ğüşıöç</h1>", encoding="utf-8")
    (sonuc / "gizli.txt").write_text("gizli", encoding="utf-8")
    ayar = tmp_path / "ayar.json"
    ayar.write_text(json.dumps({"proje_koku": str(proje), "lm_url": "http://127.0.0.1:9/v1"}), encoding="utf-8")
    c = Cekirdek(ayar)
    yield c, proje, sonuc
    c.kapat()


def istemci(c, oturum=True):
    k = api.uygulama_olustur(c, JETON).test_client()
    if oturum:
        assert k.get("/?jeton=" + JETON, base_url=ADRES).status_code == 200
    return k


def _post(k, yol, veri=None, jeton=JETON):
    return k.post(yol, json=veri or {}, base_url=ADRES, headers={"X-Jeton": jeton})


def test_jeton_ve_host_denetimi(ortam):
    c, _, _ = ortam
    yabanci = istemci(c, oturum=False)
    assert yabanci.get("/?jeton=yanlis", base_url=ADRES).status_code == 403
    assert yabanci.get("/api/durum", base_url=ADRES).status_code == 403
    k = istemci(c)
    assert k.get("/api/durum", base_url=ADRES).status_code == 200
    assert k.get("/api/durum", base_url="http://kotu.example:5999").status_code == 403
    assert _post(k, "/api/iptal", jeton="yanlis").status_code == 403
    assert _post(k, "/api/iptal").status_code == 200


def test_yalnizca_sonuclar_altindaki_izinli_raporlar_okunur(ortam, tmp_path):
    c, proje, sonuc = ortam
    k = istemci(c)
    r = k.get("/rapor", query_string={"klasor": str(sonuc), "dosya": "rapor.html"}, base_url=ADRES)
    assert r.status_code == 200 and "ğüşıöç" in r.get_data(as_text=True)
    assert k.get("/rapor", query_string={"klasor": str(sonuc), "dosya": "gizli.txt"}, base_url=ADRES).status_code == 404
    assert k.get("/rapor", query_string={"klasor": str(sonuc), "dosya": "../../yonet.py"}, base_url=ADRES).status_code == 404
    assert k.get("/rapor", query_string={"klasor": str(proje), "dosya": "rapor.html"}, base_url=ADRES).status_code == 400
    assert k.get("/rapor", query_string={"klasor": str(sonuc / ".." / ".." / ".."), "dosya": "rapor.html"},
                 base_url=ADRES).status_code == 400


def test_lm_kapaliyken_tarama_baslamaz_ve_anlasilir_ileti_doner(ortam):
    c, _, _ = ortam
    r = _post(istemci(c), "/api/tara", {"mod": "yonetici", "adres": "http://127.0.0.1:8080/", "kok": "site", "model": True,
                                        "sohbet": "m", "gomme": ""})
    assert r.status_code == 400 and "LM Studio sunucusuna ulaşılamadı" in r.get_json()["hata"] and c.is_ is None


def test_cakisma_ve_iptal_edilemez_is(ortam):
    c, proje, _ = ortam
    (proje / "masaustu").mkdir()
    (proje / "masaustu" / "gomme_yenile.py").write_text("import time\nprint('başladı', flush=True)\ntime.sleep(30)\n", encoding="utf-8")
    s = c.calistir("Uzun iş", "gomme", [])
    with pytest.raises(KullaniciHatasi, match="çalışıyor"):
        c.calistir("İkinci iş", "gomme", [])
    assert c.kapanabilir_mi() == (True, "'Uzun iş' çalışıyor. İptal edilip uygulama kapatılsın mı?")
    s.iptal_edilebilir = False
    with pytest.raises(KullaniciHatasi, match="yazıyor"):
        c.iptal()
    assert c.kapanabilir_mi()[0] is False
    s.iptal()
    s.bekle(10)
    assert c.is_ is None and c.son_is["iptal"] is True and c.biten_is_sayisi == 1


def test_yardimcilar():
    assert hata_iletisi(["HATA: Plan yok"], 2) == "Plan yok"
    assert satir_turu("HATA: x") == "hata" and satir_turu("hash eşleşiyor ✓") == "tamam"
    assert sonuc_klasoru(["a", "Sonuç klasörü: sonuclar\\s\\k"], "C:\\Düzce Ü") == Path("C:\\Düzce Ü") / "sonuclar\\s\\k"


def test_arayuz_varliklari_yerel_ve_cdn_yok():
    metinler = {p.name: p.read_text(encoding="utf-8") for p in ARAYUZ.iterdir() if p.suffix in (".html", ".css", ".js")}
    assert set(metinler) == {"index.html", "stil.css", "uygulama.js"}
    for ad, m in metinler.items():
        assert not re.findall(r"https?://(?!127\.0\.0\.1)[\w.-]+", m), ad
    for yazi in re.findall(r"url\((fontlar/[^)]+)\)", metinler["stil.css"]):
        assert (ARAYUZ / yazi).exists(), yazi
    ikonlar = re.search(r"const IKONLAR = \[(.*?)\];", metinler["uygulama.js"], re.S).group(1)
    for ad in re.findall(r'"([a-z0-9-]+)"', ikonlar):
        assert (ARAYUZ / "ikonlar" / (ad + ".svg")).exists(), ad
    # tek dogruluk kaynagi: ekran sayilari rapordan gelir, puan arayuzde hesaplanmaz
    assert "once_puan" not in metinler["uygulama.js"]
