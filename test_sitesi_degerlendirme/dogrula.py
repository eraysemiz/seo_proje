#!/usr/bin/env python3
"""sorunlar.json'daki her sorunun canli test sitesinde gercekten var oldugunu denetler.

Kullanim (sunucu calisirken):
    py test_sitesi_degerlendirme/dogrula.py
Cikis kodu: tum sorunlar varsa 0, eksik varsa 1.
"""
import sys
from collections import Counter

from kontroller import sorun_var_mi
from ortak import sorunlari_oku


def main():
    veri = sorunlari_oku()
    sorunlar = veri["sorunlar"]
    eksik = []
    for s in sorunlar:
        var, ayrinti = sorun_var_mi(s)
        print(f"{'✓' if var else '✗'} {s['id']} [{s['zorluk']:5}] {s['baslik']}" + ("" if var else f"  {ayrinti}"))
        if not var:
            eksik.append(s["id"])
    sayac = Counter(s["zorluk"] for s in sorunlar)
    print(f"\n{len(sorunlar) - len(eksik)}/{len(sorunlar)} sorun sitede doğrulandı "
          f"(kolay {sayac['kolay']}, orta {sayac['orta']}, zor {sayac['zor']}).")
    if eksik:
        print("Doğrulanamayan:", ", ".join(eksik))
    return 1 if eksik else 0


if __name__ == "__main__":
    sys.exit(main())
