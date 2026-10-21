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
