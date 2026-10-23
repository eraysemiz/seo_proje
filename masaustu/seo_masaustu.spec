# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller tanimi; build_exe.py tarafindan calistirilir (SEO_ONEFILE=1 tek dosya uretir).

.exe yalnizca Python calisma ortamini, arayuzu (masaustu/) ve ucuncu taraf kutuphaneleri icerir.
seo_app/, betikler, ogretme/, sonuclar/ ve test sitesi gomulmez; proje klasorunden okunur.
Betiklerin ihtiyac duydugu moduller, proje dosyalarindaki import satirlari taranarak eklenir;
seo_app'in kendisi pakete girmez (diskteki guncel kod kullanilsin diye).
"""
import ast
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

KOK = Path(SPECPATH).resolve().parent
AD = "SEO_Denetim"
IKON = KOK / "masaustu" / "ikon.ico"
YEREL = {"seo_app", "masaustu", "tests", "ortak", "kontroller", "site_uret", "yonet", "calistir", "deney",
         "rag_degerlendir", "sunucu", "dogrula", "sifirla", "degerlendir", "ikon_uret"}
GEREKSIZ = ["pytest", "_pytest", "pluggy", "iniconfig"]
TARANAN = [KOK / "yonet.py", KOK / "calistir.py", KOK / "deney.py", KOK / "rag_degerlendir.py",
           KOK / "masaustu" / "salt_okunur.py", *(KOK / "seo_app").rglob("*.py"),
           *(KOK / "test_sitesi").glob("*.py"), *(KOK / "test_sitesi_degerlendirme").glob("*.py")]


def ice_aktarimlar(dosya):
    for dugum in ast.walk(ast.parse(dosya.read_text(encoding="utf-8"))):
        if isinstance(dugum, ast.Import):
            yield from (a.name for a in dugum.names)
        elif isinstance(dugum, ast.ImportFrom) and dugum.level == 0 and dugum.module:
            yield dugum.module


gizli = sorted({m for f in TARANAN for m in ice_aktarimlar(f)
                if m.split(".")[0] not in YEREL and m.split(".")[0] not in GEREKSIZ})
veriler, ikililer = [(str(IKON), "masaustu")], []
for paket in ("brotlicffi",):
    v, b, g = collect_all(paket)
    veriler += v
    ikililer += b
    gizli += g

a = Analysis([str(KOK / "masaustu" / "baslat.py")], pathex=[str(KOK)], binaries=ikililer, datas=veriler,
             hiddenimports=gizli, excludes=GEREKSIZ, noarchive=False)
a.pure = [m for m in a.pure if m[0].split(".")[0] != "seo_app"]
pyz = PYZ(a.pure)

if os.environ.get("SEO_ONEFILE") == "1":
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=AD, console=False, icon=str(IKON), upx=False)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=AD, console=False, icon=str(IKON), upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name=AD, upx=False)
