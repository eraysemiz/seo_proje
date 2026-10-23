#!/usr/bin/env python3
"""Masaustu uygulamasinin giris noktasi (PyInstaller da bu dosyadan derler).

    py masaustu/baslat.py                     # arayuzu ac
    py masaustu/baslat.py --ayar ayarlar.json # baska bir ayar dosyasiyla
    py masaustu/baslat.py --oto-test rapor.json  # tam test dongusunu arayuz uzerinden calistir

.exe icinde ayrica `--betik <yol> [arg...]` bicimi vardir: uygulama betikleri alt surec olarak
kendini bu bicimde yeniden calistirir; .exe'nin gomulu Python'u proje klasorundeki betigi
(ve seo_app'i) diskten calistirir. Analiz kodu .exe'ye gomulmez.
"""
import argparse
import os
import runpy
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def akislari_hazirla():
    """Pencereli .exe'de stdout/stderr ya yoktur ya da sistem kod sayfasindadir (cp1252);
    Turkce karakterler ve ✓ gibi isaretler her durumda UTF-8 yazilir."""
    for ad in ("stdout", "stderr"):
        akim = getattr(sys, ad)
        if akim is None:
            setattr(sys, ad, open(os.devnull, "w", encoding="utf-8"))
        else:
            akim.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def betik_calistir(yol, argumanlar):
    yol = Path(yol).resolve()
    sys.argv = [str(yol), *argumanlar]
    sys.path.insert(0, str(yol.parent))
    try:
        runpy.run_path(str(yol), run_name="__main__")
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return 0


def main():
    akislari_hazirla()
    if len(sys.argv) >= 3 and sys.argv[1] == "--betik":
        return betik_calistir(sys.argv[2], sys.argv[3:])
    ap = argparse.ArgumentParser(description="SEO Denetim Aracı — masaüstü uygulaması")
    ap.add_argument("--ayar", help="ayar dosyası (varsayılan: %%APPDATA%%/SEO Denetim Aracı/ayarlar.json)")
    ap.add_argument("--oto-test", metavar="RAPOR", help="test döngüsünü arayüz üzerinden çalıştır, raporu yaz")
    a = ap.parse_args()
    if a.oto_test:
        from masaustu.oto_test import calistir
        return calistir(a.oto_test, a.ayar)
    from masaustu.uygulama import calistir_arayuz
    calistir_arayuz(a.ayar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
