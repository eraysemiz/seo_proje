#!/usr/bin/env python3
"""Bilgi tabani parcalarinin gomme onbellegini gunceller (Bilgi tabani ekranindaki dugme).
Yalnizca seo_app.ogretme'nin mevcut fonksiyonlarini cagirir; bilgi tabaninin icerigini degistirmez.

    py masaustu/gomme_yenile.py <gomme modeli> [LM Studio adresi]
"""
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from seo_app.ogretme import bilgi_tabani, parca_vektorleri  # noqa: E402


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("HATA: Gömme modeli verilmedi.")
        return 2
    url = argv[1] if len(argv) > 1 else "http://127.0.0.1:1234/v1"
    klasor = KOK / "ogretme"
    parcalar, surum, _ = bilgi_tabani(klasor)
    print(f"Bilgi tabanı: {len(parcalar)} parça, sürüm {surum}. Gömme modeli: {argv[0]}")
    try:
        vektorler = parca_vektorleri(klasor, parcalar, surum, url, argv[0])
    except Exception as e:                       # noqa: BLE001 - kullaniciya anlasilir ileti
        print("HATA: Gömme modeline ulaşılamadı (" + url + "). LM Studio açık ve model yüklü olmalı. "
              "Ayrıntı: " + type(e).__name__)
        return 1
    print(f"Önbellek güncel: {len(vektorler)} parça ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
