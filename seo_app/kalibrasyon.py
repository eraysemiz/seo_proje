"""Model onerilerinin guven tabani: olculmus dogruluktan (kalibrasyon).

Model metni (title, meta, H1, alt metni, JSON-LD) ancak o alan icin olculmus dogrulugu otomatik onay esigini
gecerse onaysiz uygulanabilir. Olcum iki kaynaktan gelir:
  - etiketleme (etiketle.py): insan etiketcinin "dogru / kismen / yanlis" karari; yalnizca "dogru" basari sayilir
  - geri bildirim (ogretme/geri_bildirim.jsonl): yonetici modunda kullanicinin karari; olduğu gibi onaylanan
    basari, duzenlenen ya da reddedilen basarisizdir. Kullanici gormeden otomatik uygulananlar sayilmaz
    (aracin kendi kararini kendine dogrulatmamak icin).
Taban, dogruluk oraninin %95 Wilson alt siniridir; boylece az ornekle olculen yuksek oran esigi gecmez.
Bir alan icin EN_AZ_ORNEK karardan az olcum varsa alan "kalibre edilmemis" sayilir ve taban esigin altindadir:
oneri onaya duser. Uzun serbest metin (paragraf) olcumden bagimsiz her zaman onay ister.
"""
import json
import time
from pathlib import Path

from .istatistik import wilson_alt

YOL = Path(__file__).resolve().parent.parent / "ogretme" / "kalibrasyon.json"
EN_AZ_ORNEK = 30
# olculmemis alanin tabani: varsayilan esigin (0.8) altinda, yani onay ister
OLCULMEMIS_TABAN = {"title": 0.75, "meta_description": 0.75, "h1": 0.75, "img_alt": 0.72, "baglanti_metni": 0.75,
                    "jsonld": 0.7, "paragraf": 0.6}
PARAGRAF_TAVANI = 0.7
_BELLEK = {}


def oku(yol=None):
    """Kalibrasyon dosyasinin 'alanlar' sozlugu; dosya yoksa {}."""
    yol = Path(yol or YOL)
    try:
        mt = yol.stat().st_mtime_ns
    except OSError:
        return {}
    if _BELLEK.get(str(yol), (None,))[0] != mt:
        try:
            veri = json.loads(yol.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            veri = {}
        _BELLEK[str(yol)] = (mt, veri.get("alanlar") or {})
    return _BELLEK[str(yol)][1]


def model_tabani(alan, yol=None):
    """(taban, kalibre_mi, neden). neden kullaniciya gosterilir."""
    olcum = oku(yol).get(alan)
    varsayilan = OLCULMEMIS_TABAN.get(alan, 0.7)
    if not olcum or olcum.get("n", 0) < EN_AZ_ORNEK:
        n = (olcum or {}).get("n", 0)
        return varsayilan, False, (f"bu alan için ölçülmüş doğruluk yok ({n}/{EN_AZ_ORNEK} etiketli karar); "
                                   "kalibrasyon tamamlanana kadar onay gerekir")
    taban = round(olcum["alt_sinir"], 3)
    neden = f"ölçülmüş doğruluk %{round(100 * olcum['oran'])} ({olcum['dogru']}/{olcum['n']}), alt sınır {taban:.2f}"
    if alan == "paragraf":
        taban = min(taban, PARAGRAF_TAVANI)
    return taban, True, neden


def _alan_ozeti(dogru, n, kaynaklar):
    return {"n": n, "dogru": dogru, "oran": round(dogru / n, 4) if n else 0.0,
            "alt_sinir": round(wilson_alt(dogru, n), 4), "kaynaklar": kaynaklar}


def hesapla(etiketler=(), geri_bildirimler=()):
    """etiketler: {"alan", "etiket"} (etiket: dogru/kismen/yanlis); geri_bildirimler: {"alan", "karar"}
    (karar: onay/duzenle/ret/otomatik). Alan basina ozet dondurur."""
    sayac = {}
    for e in etiketler:
        if e.get("etiket") in ("dogru", "kismen", "yanlis") and e.get("alan"):
            s = sayac.setdefault(e["alan"], {"dogru": 0, "n": 0, "etiket": 0, "geri_bildirim": 0})
            s["n"] += 1
            s["etiket"] += 1
            s["dogru"] += e["etiket"] == "dogru"
    for g in geri_bildirimler:
        if g.get("karar") in ("onay", "duzenle", "ret") and g.get("alan"):
            s = sayac.setdefault(g["alan"], {"dogru": 0, "n": 0, "etiket": 0, "geri_bildirim": 0})
            s["n"] += 1
            s["geri_bildirim"] += 1
            s["dogru"] += g["karar"] == "onay"
    return {a: _alan_ozeti(s["dogru"], s["n"], {"etiket": s["etiket"], "geri_bildirim": s["geri_bildirim"]})
            for a, s in sorted(sayac.items())}


def yaz(alanlar, yol=None, aciklama=""):
    yol = Path(yol or YOL)
    yol.write_text(json.dumps({"olusturma": time.strftime("%Y-%m-%d %H:%M:%S"), "en_az_ornek": EN_AZ_ORNEK,
                               "aciklama": aciklama, "alanlar": alanlar}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return yol
