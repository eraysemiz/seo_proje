#!/usr/bin/env python3
"""Bir sitenin taramalari arasindaki egilim ve gerileme uyarisi; istege bagli Search Console onceligi.

    py trend.py 127.0.0.1                       (sonuclar/<site> klasoru ya da alan adi)
    py trend.py ornek.edu.tr --gsc Sayfalar.csv  (Search Console > Performans > Sayfalar > Disa aktar > CSV)

sonuclar/<site>/trend.html ve trend.csv yazilir; --gsc verilirse son taramanin sayfalari gosterim x sorun
agirligina gore siralanip oncelik.csv'ye de yazilir. Gerileme varsa cikis kodu 2'dir (zamanlanmis gorevde
uyari icin).
"""
import argparse
import csv
import io
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from seo_app import gsc, trend  # noqa: E402


def site_klasoru(ad):
    yol = Path(ad)
    return yol if yol.is_dir() else KOK / "sonuclar" / ad


def calistir(ad, gsc_yolu=None, yaz=print):
    klasor = site_klasoru(ad)
    t = trend.trend(klasor)
    if not t["taramalar"]:
        raise SystemExit("Bu site için tarama bulunamadı: " + str(klasor))
    oncelik = None
    if gsc_yolu:
        son = klasor / t["taramalar"][-1]["tarama"] / "rapor.json"
        oncelik = gsc.oncelik(json.loads(son.read_text(encoding="utf-8")), gsc.oku(gsc_yolu))
        tampon = io.StringIO()
        sutunlar = ["url", "gosterim", "tiklama", "ctr", "konum", "sorun_sayisi", "sorun_agirligi", "oncelik_puani",
                    "gsc_eslesti", "en_ciddi_sorunlar"]
        w = csv.DictWriter(tampon, fieldnames=sutunlar, delimiter=";")
        w.writeheader()
        w.writerows({**o, "en_ciddi_sorunlar": ", ".join(o["en_ciddi_sorunlar"])} for o in oncelik)
        (klasor / "oncelik.csv").write_text(tampon.getvalue(), encoding="utf-8-sig")
        eslesen = sum(o["gsc_eslesti"] for o in oncelik)
        yaz(f"Search Console: {eslesen}/{len(oncelik)} sayfa eşleşti -> {klasor / 'oncelik.csv'}")
    (klasor / "trend.csv").write_text(trend.csv_metni(t), encoding="utf-8-sig")
    (klasor / "trend.html").write_text(trend.html_metni(t, oncelik), encoding="utf-8")
    for x in t["taramalar"][-5:]:
        yaz(f"  {x['tarama']}: {x['sayfa']} sayfa · sayfa puanı {x['ort_sayfa_puani']} · sorun {x['toplam_sorun']}"
            f" (yüksek {x['yuksek_sorun']})")
    for u in t["uyarilar"]:
        yaz("  GERİLEME: " + u)
    yaz("Trend raporu: " + str(klasor / "trend.html"))
    return t


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tarama eğilimi ve gerileme uyarısı")
    ap.add_argument("site", help="sonuclar/<site> klasörü ya da alan adı (ör. 127.0.0.1)")
    ap.add_argument("--gsc", help="Search Console 'Sayfalar' CSV dışa aktarımı")
    a = ap.parse_args(argv)
    t = calistir(a.site, a.gsc)
    return 2 if t["uyarilar"] else 0


if __name__ == "__main__":
    sys.exit(main())
