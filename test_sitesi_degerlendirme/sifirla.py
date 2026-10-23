#!/usr/bin/env python3
"""Test sitesini sorunlu orijinal haline dondurur ve dosya hash'leriyle dogrular.

Kullanim:
    py test_sitesi_degerlendirme/sifirla.py            # geri yukle + dogrula
    py test_sitesi_degerlendirme/sifirla.py --kontrol  # yalnizca karsilastir, dosyalara dokunma

Yalnizca test_sitesi/site/ klasoru degisir. Orijinal kopya (orijinal_site/) once kayitli
hash manifestiyle karsilastirilir; kopya bozulmussa geri yukleme yapilmaz.
"""
import argparse
import shutil
import sys

from ortak import CANLI, ORIJINAL, klasor_hashleri, manifest_oku


def farklar(beklenen, gercek):
    eksik = sorted(set(beklenen) - set(gercek))
    fazla = sorted(set(gercek) - set(beklenen))
    degisen = sorted(k for k in set(beklenen) & set(gercek) if beklenen[k] != gercek[k])
    return eksik, fazla, degisen


def rapor(baslik, beklenen, gercek):
    eksik, fazla, degisen = farklar(beklenen, gercek)
    if not (eksik or fazla or degisen):
        print(f"{baslik}: {len(beklenen)} dosyanın hash'i eşleşiyor ✓")
        return True
    print(f"{baslik}: EŞLEŞMİYOR — {len(degisen)} değişen, {len(eksik)} eksik, {len(fazla)} fazla dosya")
    for ad, liste in (("değişen", degisen), ("eksik", eksik), ("fazla", fazla)):
        for yol in liste[:20]:
            print(f"   {ad}: {yol}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kontrol", action="store_true", help="yalnızca karşılaştır")
    args = ap.parse_args()
    manifest = manifest_oku()
    if not rapor("Orijinal kopya", manifest, klasor_hashleri(ORIJINAL)):
        print("Orijinal kopya bozulmuş; geri yükleme yapılmadı. site_uret.py ile yeniden üretin.")
        return 2
    if args.kontrol:
        return 0 if rapor("Canlı site", manifest, klasor_hashleri(CANLI) if CANLI.exists() else {}) else 1
    # yalnizca canli site klasorunun icerigi silinir ve yeniden kopyalanir
    if CANLI.exists():
        for oge in CANLI.iterdir():
            shutil.rmtree(oge) if oge.is_dir() and not oge.is_symlink() else oge.unlink()
    else:
        CANLI.mkdir(parents=True)
    shutil.copytree(ORIJINAL, CANLI, dirs_exist_ok=True)
    print("Test sitesi orijinal haline döndürüldü:", CANLI)
    return 0 if rapor("Canlı site", manifest, klasor_hashleri(CANLI)) else 1


if __name__ == "__main__":
    sys.exit(main())
