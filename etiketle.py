#!/usr/bin/env python3
"""Model onerilerinin insan etiketlemesi: kor sablon, etiketci uyumu, kosul ozeti ve guven kalibrasyonu.

Etiketci: modelin urettigi her oneriyi okuyup "dogru / kismen / yanlis" diye isaretleyen kisi. Iki kisi ayni
dosyayi birbirinden habersiz etiketlerse uyumlari (Cohen kappa) olculur; uyum dusukse etiket kurali belirsizdir.

Adimlar:
    py etiketle.py hazirla sonuclar/<site>/<deney klasoru>       (deney.py ciktisi: kosul karsilastirmasi)
    py etiketle.py hazirla sonuc_<tarih_saat>                     (cok siteli deney: tum siteler tek sablonda)
    py etiketle.py hazirla sonuclar/<site>/<sonuc>/degisiklikler.json   (yonetici modu plani: kalibrasyon)
        -> etiket_sablonu.csv (kor: model/kosul yazmaz) + etiket_anahtari.json (oneri no -> kosul, model)
    Sablon iki kopya halinde (etiket_A.csv, etiket_B.csv) iki kisiye verilir; her satira:
        etiket   : dogru (oldugu gibi yayimlanabilir) | kismen (kucuk duzeltmeyle) | yanlis
        uydurma  : evet (sayfada olmayan bilgi var) | hayir
        turkce   : 1 (bozuk) | 2 (anlasilir) | 3 (dogal)
    py etiketle.py uyum etiket_A.csv etiket_B.csv
    py etiketle.py ozet etiket_A.csv [etiket_B.csv]       (kosul basina dogruluk, uydurma, kaynak; %95 aralik)
    py etiketle.py retler                                   (yonetici modunda en sik ret nedenleri)
    py etiketle.py kalibre etiket_A.csv [etiket_B.csv] [--geri-bildirim]
        -> ogretme/kalibrasyon.json: alan basina olculmus dogruluk; guven tabani bundan gelir (seo_app/kalibrasyon.py)

Iki etiketci varsa bir oneri ancak ikisi de "dogru" dediyse dogru sayilir (anlasmazlikta kotu olan alinir).
"""
import argparse
import csv
import json
import random
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from seo_app import geri_bildirim, kalibrasyon  # noqa: E402
from seo_app.guven import ESIK  # noqa: E402
from seo_app.istatistik import bootstrap_fark, cohen_kappa, wilson_alt  # noqa: E402

SUTUNLAR = ["oneri_no", "sayfa", "alan", "sayfa_basligi", "sayfa_h1", "mevcut", "onerilen", "etiket", "uydurma",
            "turkce", "not"]
ETIKET_SIRASI = {"yanlis": 0, "kismen": 1, "dogru": 2}
ALAN_ADI = {"meta": "meta_description"}


def _ilk(x):
    return (x[0] if x else "") if isinstance(x, list) else (x or "")


def _deney_raporlari(kaynak):
    """deney.py klasoru (tek site) ya da zaman damgasi (sonuc_...; tum sitelerdeki ayni deney)."""
    yol = Path(kaynak)
    if yol.is_dir():
        return sorted(yol.glob("*/rapor.json"))
    return sorted((KOK / "sonuclar").glob(f"*/{yol.name}/*__*__r*/rapor.json"))


def _deney_onerileri(klasor):
    """deney.py ciktisi: her kombinasyonun rapor.json'undaki kabul edilen oneriler."""
    for rapor_yolu in _deney_raporlari(klasor):
        ad = rapor_yolu.parent.name
        model, kosul, retry = (ad.split("__") + ["", "", ""])[:3]
        for k in json.loads(rapor_yolu.read_text(encoding="utf-8")):
            for f in k.get("fixes", []):
                mevcut = {"title": k.get("title"), "meta_description": k.get("meta_description"),
                          "h1": _ilk(k.get("h1")), "img_alt": "(yok) " + str(f.get("hedef_src") or "")}.get(f["alan"], "")
                yield ({"sayfa": k.get("url") or k["ad"], "alan": f["alan"], "sayfa_basligi": k.get("title") or "",
                        "sayfa_h1": _ilk(k.get("h1")), "mevcut": mevcut or "(yok)", "onerilen": f["yeni_deger"]},
                       {"model": k.get("model") or model, "kosul": k.get("kosul") or kosul, "retry": retry,
                        "kaynaklar": f.get("kaynaklar") or [], "kombinasyon": ad})


def _plan_onerileri(plan_yolu):
    """Yonetici modu plani: model onerileri (alan basina; JSON-LD ve paragraf dahil)."""
    plan = json.loads(Path(plan_yolu).read_text(encoding="utf-8"))
    for d in plan["degisiklikler"]:
        if d.get("uretici") != "model" or not (d.get("duzenleme") or {}).get("alan"):
            continue
        yield ({"sayfa": d.get("url"), "alan": d["duzenleme"]["alan"], "sayfa_basligi": "", "sayfa_h1": "",
                "mevcut": d.get("eski") or "(yok)", "onerilen": d["duzenleme"].get("deger", d.get("yeni"))},
               {"model": (plan.get("tarama") or {}).get("ayarlar", {}).get("model"), "kosul": "yonetici",
                "retry": "", "kaynaklar": [x.get("id") for x in d.get("kaynaklar") or [] if isinstance(x, dict)],
                "degisiklik": d["id"], "guven": d.get("guven"), "plan": str(plan_yolu)})


def hazirla(kaynak, cikti, tohum=0):
    kaynak = Path(kaynak)
    oneriler = list(_plan_onerileri(kaynak) if kaynak.suffix == ".json" else _deney_onerileri(kaynak))
    if not oneriler:
        raise SystemExit("Etiketlenecek model önerisi bulunamadı: " + str(kaynak))
    random.Random(tohum).shuffle(oneriler)            # kor: kosullar karisik sirada
    cikti = Path(cikti)
    cikti.parent.mkdir(parents=True, exist_ok=True)
    with cikti.open("w", encoding="utf-8-sig", newline="") as f:
        yazici = csv.DictWriter(f, fieldnames=SUTUNLAR, delimiter=";")
        yazici.writeheader()
        for i, (satir, _) in enumerate(oneriler, 1):
            yazici.writerow({**satir, "oneri_no": i, "etiket": "", "uydurma": "", "turkce": "", "not": ""})
    anahtar = cikti.with_name("etiket_anahtari.json")
    anahtar.write_text(json.dumps({str(i): {**gizli, "alan": satir["alan"], "sayfa": satir["sayfa"]}
                                   for i, (satir, gizli) in enumerate(oneriler, 1)}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    print(f"{len(oneriler)} öneri: {cikti}\nAnahtar (etiketçiye vermeyin): {anahtar}")
    return cikti, anahtar


def oku(yol):
    with Path(yol).open(encoding="utf-8-sig", newline="") as f:
        return {r["oneri_no"]: r for r in csv.DictReader(f, delimiter=";")}


def birlestir(dosyalar):
    """Birden fazla etiketcinin etiketleri: her oneri icin en kotu etiket, herhangi biri 'evet' dediyse uydurma."""
    tablolar = [oku(y) for y in dosyalar]
    sonuc = {}
    for no in tablolar[0]:
        satirlar = [t[no] for t in tablolar if no in t and t[no].get("etiket") in ETIKET_SIRASI]
        if not satirlar:
            continue
        r = dict(satirlar[0])
        r["etiket"] = min((s["etiket"] for s in satirlar), key=ETIKET_SIRASI.get)
        r["uydurma"] = "evet" if any(s.get("uydurma") == "evet" for s in satirlar) else \
            ("hayir" if any(s.get("uydurma") == "hayir" for s in satirlar) else "")
        puanlar = [int(s["turkce"]) for s in satirlar if str(s.get("turkce", "")).strip() in ("1", "2", "3")]
        r["turkce"] = sum(puanlar) / len(puanlar) if puanlar else None
        sonuc[no] = r
    return sonuc


def uyum(a_yolu, b_yolu):
    a, b = oku(a_yolu), oku(b_yolu)
    ortak = sorted(set(a) & set(b), key=int)
    sonuc = {}
    for sutun in ("etiket", "uydurma", "turkce"):
        k = cohen_kappa([a[n].get(sutun) for n in ortak], [b[n].get(sutun) for n in ortak])
        sonuc[sutun] = None if k is None else round(k, 3)
    print(f"{len(ortak)} ortak öneri. Cohen kappa: " + ", ".join(f"{s}={v}" for s, v in sonuc.items()))
    print("Yorum: 0,6 ve üstü önemli uyum; 0,4'ün altında etiket kuralları netleştirilmeli.")
    return sonuc


def _anahtar(dosya):
    yol = Path(dosya).with_name("etiket_anahtari.json")
    return json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}


def _oran(satirlar, kosul):
    n = len(satirlar)
    d = sum(kosul(r) for r in satirlar)
    return {"n": n, "oran": round(d / n, 3) if n else None, "alt": round(wilson_alt(d, n), 3) if n else None}


def ozet(dosyalar, referans="ornek+bilgi"):
    etiketler = birlestir(dosyalar)
    anahtar = _anahtar(dosyalar[0])
    gruplar = {}
    for no, r in etiketler.items():
        gruplar.setdefault((anahtar.get(no) or {}).get("kosul") or "?", []).append((no, r))
    satirlar = []
    for kosul, liste in sorted(gruplar.items()):
        rs = [r for _, r in liste]
        dogru, uydurma = _oran(rs, lambda r: r["etiket"] == "dogru"), _oran(rs, lambda r: r["uydurma"] == "evet")
        tr = [r["turkce"] for r in rs if r["turkce"] is not None]
        satirlar.append({"kosul": kosul, "oneri": len(rs), "dogru_orani": dogru["oran"], "dogru_alt_sinir": dogru["alt"],
                         "kabul_edilebilir_orani": _oran(rs, lambda r: r["etiket"] != "yanlis")["oran"],
                         "uydurma_orani": uydurma["oran"],
                         "turkce_ort": round(sum(tr) / len(tr), 2) if tr else None})
    # sayfa basina dogruluk, referans kosulla eslestirilmis fark
    sayfa_dogru = {}
    for no, r in etiketler.items():
        g = anahtar.get(no) or {}
        sayfa_dogru.setdefault(g.get("kosul"), {}).setdefault(g.get("sayfa"), []).append(r["etiket"] == "dogru")
    ort = {k: {s: sum(v) / len(v) for s, v in d.items()} for k, d in sayfa_dogru.items()}
    for s in satirlar:
        if s["kosul"] != referans and referans in ort and s["kosul"] in ort:
            ortak = sorted(set(ort[s["kosul"]]) & set(ort[referans]))
            b = bootstrap_fark([ort[s["kosul"]][x] for x in ortak], [ort[referans][x] for x in ortak])
            if b:
                s["fark_" + referans] = f"{b['fark']:+.3f} [{b['alt']:+.3f}, {b['ust']:+.3f}] n={b['n']}"
    for s in satirlar:
        print(" · ".join(f"{k}={v}" for k, v in s.items()))
    return satirlar


def kalibre(dosyalar, geri_bildirim_de=False, yol=None):
    etiketler = []
    if dosyalar:
        anahtar = _anahtar(dosyalar[0])
        for no, r in birlestir(dosyalar).items():
            alan = (anahtar.get(no) or {}).get("alan") or r.get("alan")
            etiketler.append({"alan": ALAN_ADI.get(alan, alan), "etiket": r["etiket"]})
    gb = geri_bildirim.oku(KOK / "ogretme") if geri_bildirim_de else []
    alanlar = kalibrasyon.hesapla(etiketler, gb)
    hedef = kalibrasyon.yaz(alanlar, yol, aciklama="etiketle.py kalibre: " + ", ".join(map(str, dosyalar)) +
                            (" + geri_bildirim.jsonl" if geri_bildirim_de else ""))
    for alan, o in alanlar.items():
        durum = ("ölçüm yetersiz" if o["n"] < kalibrasyon.EN_AZ_ORNEK else
                 "otomatik uygulanabilir" if o["alt_sinir"] >= ESIK else "onay gerekir")
        print(f"{alan:18s} n={o['n']:3d} doğru={o['dogru']:3d} oran={o['oran']:.2f} alt sınır={o['alt_sinir']:.2f} -> {durum}")
    print("Yazıldı:", hedef)
    return alanlar


def main(argv=None):
    ap = argparse.ArgumentParser(description="Model önerilerinin insan etiketlemesi ve kalibrasyon")
    alt = ap.add_subparsers(dest="komut", required=True)
    h = alt.add_parser("hazirla", help="kör etiket şablonu üret")
    h.add_argument("kaynak", help="deney.py klasörü, çok siteli deneyin zaman damgası (sonuc_...) "
                                  "ya da yönetici modu degisiklikler.json")
    h.add_argument("--cikti", help="şablon dosyası (varsayılan: kaynağın yanında etiketleme/etiket_sablonu.csv)")
    h.add_argument("--tohum", type=int, default=0)
    u = alt.add_parser("uyum", help="iki etiketçinin Cohen kappa uyumu")
    u.add_argument("a")
    u.add_argument("b")
    o = alt.add_parser("ozet", help="koşul başına doğruluk / uydurma / Türkçe")
    o.add_argument("dosyalar", nargs="+")
    k = alt.add_parser("kalibre", help="alan başına ölçülmüş doğruluk -> ogretme/kalibrasyon.json")
    k.add_argument("dosyalar", nargs="*")
    k.add_argument("--geri-bildirim", action="store_true", help="yönetici modundaki kullanıcı kararlarını da kat")
    alt.add_parser("retler", help="yönetici modunda en sık ret nedenleri (geri_bildirim.jsonl)")
    a = ap.parse_args(argv)
    if a.komut == "hazirla":
        kaynak = Path(a.kaynak)
        taban = kaynak.parent if kaynak.suffix == ".json" else kaynak if kaynak.is_dir() else             KOK / "sonuclar" / "_deneyler" / kaynak.name
        varsayilan = taban / "etiketleme" / "etiket_sablonu.csv"
        hazirla(kaynak, a.cikti or varsayilan, a.tohum)
    elif a.komut == "uyum":
        uyum(a.a, a.b)
    elif a.komut == "ozet":
        ozet(a.dosyalar)
    elif a.komut == "kalibre":
        if not a.dosyalar and not a.geri_bildirim:
            ap.error("etiket dosyası ya da --geri-bildirim gerekli")
        kalibre(a.dosyalar, a.geri_bildirim)
    elif a.komut == "retler":
        kayitlar = geri_bildirim.oku(KOK / "ogretme")
        print(f"{len(kayitlar)} karar; ret nedenleri (en sık önce):")
        for r in geri_bildirim.ret_ozeti(kayitlar):
            print(f"  {r['sayi']:3d}  {r['alan']:18s} {r['neden']}")


if __name__ == "__main__":
    main()
