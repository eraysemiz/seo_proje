#!/usr/bin/env python3
"""Masaustu uygulamasini (.exe) tek komutla derler.

    py build_exe.py             # onedir (varsayilan): dist/SEO_Denetim/SEO_Denetim.exe
    py build_exe.py --onefile   # tek dosya: dist/SEO_Denetim.exe
    build_exe.bat               # ayni komut, cift tiklanabilir

Derleme uv ile kurulan ayri bir Python 3.13 ortaminda (build/venv313) yapilir; projenin kendi
ortamina PyInstaller eklenmez. Ikon masaustu/ikon.ico'dur (yoksa masaustu/ikon_uret.py ile
uretilir; kendi ikonunuzu ayni adla koyabilirsiniz).

onedir: hizli acilir, antivirus yazilimlari daha az takilir; klasor butun olarak tasinir.
onefile: tek dosyadir ama her acilista kendini gecici klasore acar (birkac saniye gecikme) ve
Windows Defender gibi yazilimlarin yanlis alarmina daha sik takilir.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
ORTAM = KOK / "build" / "venv313"
PYTHON = ORTAM / "Scripts" / "python.exe"
SPEC = KOK / "masaustu" / "seo_masaustu.spec"


def uv_komutu():
    try:
        import uv  # noqa: F401
        return [sys.executable, "-m", "uv"]
    except ImportError:
        if shutil.which("uv"):
            return ["uv"]
    sys.exit("HATA: uv bulunamadı. Kurmak için: py -m pip install uv")


def calistir(komut, **kw):
    print("›", " ".join(map(str, komut)), flush=True)
    subprocess.run(list(map(str, komut)), check=True, **kw)


def main():
    ap = argparse.ArgumentParser(description="SEO Denetim Aracı masaüstü uygulamasını derler")
    ap.add_argument("--onefile", action="store_true", help="tek dosya .exe üret (yavaş açılır)")
    a = ap.parse_args()
    uv = uv_komutu()
    if not PYTHON.exists():
        calistir([*uv, "venv", "--python", "3.13", "--managed-python", ORTAM])
    calistir([*uv, "pip", "install", "--python", PYTHON, "-r", KOK / "requirements.txt", "pyinstaller"])
    if not (KOK / "masaustu" / "ikon.ico").exists():
        calistir([sys.executable, KOK / "masaustu" / "ikon_uret.py"])
    ortam = {**os.environ, "SEO_ONEFILE": "1" if a.onefile else "0", "PYTHONUTF8": "1"}
    calistir([PYTHON, "-m", "PyInstaller", SPEC, "--noconfirm", "--clean", "--distpath", KOK / "dist",
              "--workpath", KOK / "build" / "pyinstaller"], env=ortam)
    hedef = KOK / "dist" / ("SEO_Denetim.exe" if a.onefile else "SEO_Denetim/SEO_Denetim.exe")
    print("\nHazır:", hedef)
    print("Proje klasörü ayarlardan okunur; .exe başka bir yere taşınırsa ilk açılışta Ayarlar sekmesinden seçin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
