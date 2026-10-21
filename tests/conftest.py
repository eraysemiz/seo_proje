"""Testlerin seo_app paketini proje kokunden bulabilmesi icin yol ayari ve ortak yardimcilar."""
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from seo_app.cikarma import extract  # noqa: E402


def html_yap(title="Duzce Universitesi Bilgisayar Muhendisligi Bolumu Sayfasi",
             meta="Duzce Universitesi Bilgisayar Muhendisligi bolumu ders programi, akademik kadro ve duyurular sayfasi.",
             h1="<h1>Bilgisayar Muhendisligi</h1>", govde="", head_ek="", lang=' lang="tr"'):
    """Testlerde kullanilan kucuk ama gercekci bir HTML belgesi uretir."""
    meta_etiketi = f'<meta name="description" content="{meta}">' if meta is not None else ""
    title_etiketi = f"<title>{title}</title>" if title is not None else ""
    metin = " ".join(["ders programi akademik kadro duyurular laboratuvar"] * 70)
    return (f"<html{lang}><head>{title_etiketi}{meta_etiketi}{head_ek}</head>"
            f"<body>{h1}<p>{metin}</p>{govde}</body></html>")


@pytest.fixture
def ornek_sayfa():
    return extract(html_yap())


def sahte_canli(monkeypatch, html_haritasi, site_sorunlari=()):
    """Canli taramayi ag olmadan taklit eder: {url: html} haritasindaki sayfalar 200 ile doner,
    robots.txt engellemez, site katmani denetimi verilen sorunlari dondurur."""
    from seo_app import canli

    def sayfa_getir(url, *a, **k):
        return {"basarili": True, "url": url, "son_url": url, "durum_kodu": 200,
                "html": html_haritasi[canli.normalize(url)]}

    canli.onbellek_temizle()
    monkeypatch.setattr(canli, "robots_bilgisi", lambda *a, **k: {"_parser": None})
    monkeypatch.setattr(canli, "sayfa_getir", sayfa_getir)
    monkeypatch.setattr(canli, "canli_denetim", lambda *a, **k: (list(site_sorunlari), {}))


def sahte_model(monkeypatch, fixes=()):
    """Dil modeli ve ogretme metnini taklit eder; modele giden sorunlari kaydeder."""
    from seo_app import boru
    kayit = {}

    def llm_fixes(d, issues, *a, **k):
        kayit["kodlar"] = [i["sorun"] for i in issues]
        return {"fixes": [dict(f) for f in fixes], "reddedilen": [], "yok_sayilan": [], "json_gecerli": True,
                "sure_sn": 1.0, "bitis_nedeni": "stop", "dusunme_karakter": 0, "cevap_karakter": 10,
                "denemeler": [], "ham": "", "dusunme_basi": ""}

    monkeypatch.setattr(boru, "llm_fixes", llm_fixes)
    monkeypatch.setattr(boru, "ogretme_metni", lambda *a, **k: ("", {"ornek": 3, "kural": 4, "yontem": "anlamsal"}))
    return kayit
