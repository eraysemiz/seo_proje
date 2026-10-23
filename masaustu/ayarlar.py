"""Masaustu uygulamasinin ayarlari ve proje klasorunun bulunmasi.

Ayarlar %APPDATA%/SEO Denetim Aracı/ayarlar.json dosyasinda tutulur; .exe hangi klasorden
calistirilirsa calistirilsin ayni dosya okunur (SEO_MASAUSTU_AYAR ortam degiskeni baska bir
dosya gosterebilir). Proje koku ayarda yoksa ya da gecersizse .exe'nin (kaynaktan calisirken bu
paketin) bulundugu klasorden ve calisma klasorunden yukari dogru yonet.py + seo_app/ aranir.
"""
import json
import os
import sys
from pathlib import Path

UYGULAMA_ADI = "SEO Denetim Aracı"
VARSAYILAN = {
    "proje_koku": "",
    "lm_url": "http://127.0.0.1:1234/v1",
    "sohbet_modeli": "qwen/qwen3.5-9b",
    "gomme_modeli": "text-embedding-qwen3-embedding-0.6b",
    "site_url": "http://127.0.0.1:8080/",
    "site_koku": "test_sitesi/site",
    "test_portu": 8080,
    "web_portu": 5000,
    "ses": True,
}
IMZA = ("yonet.py", "seo_app")       # proje kokunu taniyan dosyalar


def ayar_dosyasi():
    if os.environ.get("SEO_MASAUSTU_AYAR"):
        return Path(os.environ["SEO_MASAUSTU_AYAR"])
    taban = os.environ.get("APPDATA") or str(Path.home())
    return Path(taban) / UYGULAMA_ADI / "ayarlar.json"


def proje_koku_mu(yol):
    return bool(yol) and all((Path(yol) / ad).exists() for ad in IMZA)


def proje_kokunu_bul(baslangiclar):
    for b in baslangiclar:
        if not b:
            continue
        p = Path(b).resolve()
        for aday in (p, *p.parents):
            if proje_koku_mu(aday):
                return aday
    return None


def baslangic_klasorleri():
    ilk = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return [ilk, Path.cwd()]


def yukle(dosya=None):
    dosya = Path(dosya or ayar_dosyasi())
    ayar = dict(VARSAYILAN)
    try:
        kayitli = json.loads(dosya.read_text(encoding="utf-8"))
        ayar.update({k: v for k, v in kayitli.items() if k in VARSAYILAN})
    except (OSError, ValueError):
        pass
    if not proje_koku_mu(ayar["proje_koku"]):
        bulunan = proje_kokunu_bul(baslangic_klasorleri())
        ayar["proje_koku"] = str(bulunan) if bulunan else ""
    return ayar


def kaydet(ayar, dosya=None):
    dosya = Path(dosya or ayar_dosyasi())
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_text(json.dumps({k: ayar[k] for k in VARSAYILAN if k in ayar}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return dosya


def dogrula(ayar):
    """Ayarlardaki sorunlari kullaniciya gosterilecek Turkce iletiler olarak dondurur."""
    hatalar = []
    if not proje_koku_mu(ayar.get("proje_koku")):
        hatalar.append("Proje klasörü bulunamadı ya da geçersiz (içinde yonet.py ve seo_app/ olmalı): "
                       + (str(ayar.get("proje_koku")) or "(boş)"))
    if not str(ayar.get("lm_url", "")).startswith(("http://", "https://")):
        hatalar.append("LM Studio adresi http:// ya da https:// ile başlamalı.")
    for alan, ad in (("test_portu", "Test sitesi portu"), ("web_portu", "Web arayüzü portu")):
        try:
            if not 1 <= int(ayar.get(alan)) <= 65535:
                raise ValueError
        except (TypeError, ValueError):
            hatalar.append(ad + " 1-65535 arasında bir sayı olmalı.")
    return hatalar
