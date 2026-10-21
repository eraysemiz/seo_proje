"""Adim 9: PageSpeed (Lighthouse) entegrasyonu. Ag kullanilmaz; API yaniti taklit edilir."""
import csv
import io

from seo_app import bagimsiz, boru, canli

ORNEK_YANIT = {"lighthouseResult": {
    "lighthouseVersion": "12.0.0",
    "categories": {"seo": {"score": 0.83, "auditRefs": [{"id": "meta-description"}, {"id": "document-title"}]}},
    "audits": {"meta-description": {"score": 0}, "document-title": {"score": 1}, "baska": {"score": 0}}}}


class _Yanit:
    def __init__(self, veri, durum=200):
        self._veri, self.status_code = veri, durum

    def json(self):
        return self._veri


def test_puan_ve_basarisiz_denetimler_okunur(monkeypatch):
    istek = {}

    def sahte_get(adres, params=None, timeout=None):
        istek.update(params)
        return _Yanit(ORNEK_YANIT)

    monkeypatch.setattr(bagimsiz.requests, "get", sahte_get)
    monkeypatch.setenv("PSI_API_ANAHTARI", "gizli-anahtar")
    s = bagimsiz.pagespeed_seo("https://ornek.edu.tr/")
    assert s["seo_puani"] == 83 and s["hata"] is None
    assert s["basarisiz_denetimler"] == ["meta-description"]       # SEO disi denetim sayilmaz
    assert istek["category"] == "SEO" and istek["key"] == "gizli-anahtar"
    assert "gizli-anahtar" not in str(s)                             # anahtar sonuca/rapora sizmaz


def test_kota_hatasi_istisnasiz_raporlanir(monkeypatch):
    monkeypatch.setattr(bagimsiz.requests, "get",
                        lambda *a, **k: _Yanit({"error": {"code": 429, "message": "Quota exceeded"}}, 429))
    s = bagimsiz.pagespeed_seo("https://ornek.edu.tr/")
    assert s["seo_puani"] is None and s["hata"].startswith("HTTP 429")


def test_analiz_akisinda_rapora_ve_csvye_yazilir(monkeypatch, tmp_path):
    canli.onbellek_temizle()
    monkeypatch.setattr(canli, "robots_bilgisi", lambda *a, **k: {"_parser": None})
    monkeypatch.setattr(canli, "sayfa_getir", lambda *a, **k: {
        "basarili": True, "url": "https://ornek.edu.tr/", "son_url": "https://ornek.edu.tr/", "durum_kodu": 200,
        "html": "<html><head><title>Bolum</title></head><body><h1>Bolum</h1></body></html>"})
    monkeypatch.setattr(canli, "canli_denetim", lambda *a, **k: ([], {}))
    monkeypatch.setattr(boru, "pagespeed_seo", lambda url: {"seo_puani": 0, "hata": None})
    rapor = boru.topluca_analiz([{"tur": "canli", "url": "ornek.edu.tr"}],
                                {"llm_kullan": False, "bagimsiz_olcum": True}, str(tmp_path), tmp_path / "c")
    assert rapor[0]["lighthouse"]["once"]["seo_puani"] == 0
    assert rapor[0]["lighthouse"]["sonra"] is None
    satir = next(csv.DictReader(io.StringIO((tmp_path / "c" / "ozet.csv").read_text(encoding="utf-8-sig")),
                                delimiter=";"))
    assert satir["lighthouse_seo_once"] == "0" and satir["lighthouse_seo_sonra"] == ""


def test_varsayilan_olarak_kapali_ve_cevrimdisi_modda_calismaz(monkeypatch, tmp_path):
    cagrildi = []
    monkeypatch.setattr(boru, "pagespeed_seo", lambda url: cagrildi.append(url))
    (tmp_path / "s.html").write_text("<html><title>x</title></html>", encoding="utf-8")
    boru.analiz_et({"tur": "dosya", "yol": str(tmp_path / "s.html")}, {"llm_kullan": False, "bagimsiz_olcum": True},
                   str(tmp_path))
    assert cagrildi == [] and boru.VARSAYILAN_AYARLAR["bagimsiz_olcum"] is False
