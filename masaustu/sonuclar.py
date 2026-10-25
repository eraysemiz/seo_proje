"""sonuclar/<site>/sonuc_<tarih_saat>/ klasorlerinin listelenmesi."""
import json
from pathlib import Path

RAPORLAR = (("Yönetici raporu", "yonetici_raporu.html"), ("Analiz raporu", "rapor.html"),
            ("Değerlendirme", "degerlendirme.md"), ("Önizleme diff", "onizleme.diff"),
            ("Uygulanan diff", "uygulanan.diff"))


def _zaman(ad):
    # sonuc_2026-10-23_16-08-28 -> 2026-10-23 16:08:28
    parca = ad.removeprefix("sonuc_").split("_")
    return parca[0] + " " + parca[1].replace("-", ":") if len(parca) >= 2 else ad


def son_uygulama(site_klasoru):
    try:
        return json.loads((Path(site_klasoru) / "son_uygulama.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def geri_alinabilir(site_klasoru):
    bilgi = son_uygulama(site_klasoru)
    return bool(bilgi) and bilgi.get("durum") != "geri_alindi"


def _uygulama_kaydi(k):
    try:
        return json.loads((k / "uygulama.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def klasor_bilgisi(k):
    yonetici = (k / "degisiklikler.json").exists()
    u = _uygulama_kaydi(k) if (k / "uygulama.json").exists() else None
    adlar = [a["ad"] for a in (u or {}).get("asamalar") or []]
    var = u is not None
    if var and u.get("geri_alindi"):
        durum = "geri alındı"
    elif var and ("onayli" in adlar or not adlar):
        durum = "uygulandı"                   # asamasiz kayit: eski tek seferlik uygulama
    elif var and "otomatik" in adlar:
        durum = "otomatik uygulandı"
    elif (k / "onaylar.json").exists():
        durum = "onaylandı"
    elif yonetici:
        durum = "plan hazır"
    else:
        durum = "analiz"
    return {"site": k.parent.name, "klasor": k, "zaman": _zaman(k.name),
            "tur": "Yönetici" if yonetici else "Salt okunur", "durum": durum,
            "raporlar": [(ad, k / dosya) for ad, dosya in RAPORLAR if (k / dosya).exists()]}


def listele(proje_koku):
    kok = Path(proje_koku) / "sonuclar"
    if not kok.is_dir():
        return []
    kayitlar = [klasor_bilgisi(k) for site in kok.iterdir() if site.is_dir()
                for k in site.glob("sonuc_*") if k.is_dir()]
    return sorted(kayitlar, key=lambda x: x["klasor"].name, reverse=True)


def son_yonetici_klasoru(proje_koku, site="127.0.0.1", uygulanmis=False):
    for x in listele(proje_koku):
        if x["site"] == site and x["tur"] == "Yönetici" and (not uygulanmis or x["durum"] in ("uygulandı", "otomatik uygulandı")):
            return x["klasor"]
    return None
