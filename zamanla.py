#!/usr/bin/env python3
"""Zamanlanmis salt okunur tarama (Windows Gorev Zamanlayicisi) ve ardindan trend raporu.

    py zamanla.py olustur --adres https://ornek.edu.tr --site-modu --gun MON --saat 09:00 [--model M] [--kuru]
    py zamanla.py listele
    py zamanla.py sil --adres https://ornek.edu.tr
    py zamanla.py calistir --adres https://ornek.edu.tr --site-modu      (gorevin calistirdigi komut)

Gorev siteye HICBIR SEY yazmaz: masaustu/salt_okunur.py ile tarar, sonra trend.py ile son iki taramayi
karsilastirir. Gerileme varsa sonuclar/<site>/zamanli_gunluk.txt dosyasina GERILEME satiri yazilir.
--model verilmezse dil modeli kullanilmaz (yalnizca denetim); LM Studio'nun acik olmasi gerekmez.
--kuru ile gorev olusturulmaz, yalnizca calistirilacak schtasks komutu yazdirilir.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from seo_app.boru import site_adi  # noqa: E402

ONEK = "SEO_Denetim_"
GUNLER = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def gorev_adi(adres):
    return ONEK + site_adi(adres)


def tarama_argumanlari(a):
    arg = ["--adres", *a.adres]
    if a.site_modu:
        arg.append("--site-modu")
    if getattr(a, "model", None):
        arg += ["--model", a.model] + (["--embed-model", a.embed_model] if a.embed_model else [])
    else:
        arg.append("--yalnizca-denetim")
    return arg


def schtasks_komutu(a):
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")           # konsol penceresi acilmasin
    calistirici = pythonw if pythonw.exists() else python
    tr = subprocess.list2cmdline([str(calistirici), str(KOK / "zamanla.py"), "calistir", *tarama_argumanlari(a)])
    komut = ["schtasks", "/Create", "/F", "/TN", gorev_adi(a.adres[0]), "/TR", tr, "/ST", a.saat]
    komut += ["/SC", "DAILY"] if a.gun == "HER" else ["/SC", "WEEKLY", "/D", a.gun]
    return komut


def calistir(a):
    from masaustu import salt_okunur
    import trend as trend_cli
    klasor = KOK / "sonuclar" / site_adi(a.adres[0])
    klasor.mkdir(parents=True, exist_ok=True)
    gunluk = klasor / "zamanli_gunluk.txt"

    def yaz(m):
        print(m)
        with gunluk.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + m + "\n")

    yaz("Zamanlanmış tarama başladı: " + " ".join(a.adres))
    kod = salt_okunur.main(tarama_argumanlari(a))
    if kod:
        yaz(f"HATA: tarama başarısız (çıkış kodu {kod})")
        return kod
    t = trend_cli.calistir(str(klasor), yaz=yaz)
    return 2 if t["uyarilar"] else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Zamanlanmış salt okunur tarama + trend")
    alt = ap.add_subparsers(dest="komut", required=True)
    for ad in ("olustur", "calistir"):
        p = alt.add_parser(ad)
        p.add_argument("--adres", nargs="+", required=True)
        p.add_argument("--site-modu", action="store_true")
        p.add_argument("--model")
        p.add_argument("--embed-model")
        if ad == "olustur":
            p.add_argument("--gun", default="MON", choices=GUNLER + ("HER",), help="haftanın günü ya da HER (her gün)")
            p.add_argument("--saat", default="09:00", help="SS:DD")
            p.add_argument("--kuru", action="store_true", help="görevi oluşturma, komutu yazdır")
    s = alt.add_parser("sil")
    s.add_argument("--adres", required=True)
    alt.add_parser("listele")
    a = ap.parse_args(argv)
    if a.komut == "calistir":
        return calistir(a)
    if a.komut == "olustur":
        komut = schtasks_komutu(a)
        if a.kuru:
            print(subprocess.list2cmdline(komut))
            return 0
        return subprocess.call(komut)
    if a.komut == "sil":
        return subprocess.call(["schtasks", "/Delete", "/F", "/TN", gorev_adi(a.adres)])
    cikti = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                           encoding="mbcs", errors="replace").stdout
    satirlar = [x for x in cikti.splitlines() if ONEK in x]
    print("\n".join(satirlar) if satirlar else "Zamanlanmış SEO görevi yok.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
