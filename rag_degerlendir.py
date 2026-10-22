#!/usr/bin/env python3
"""Bilgi getirme (RAG) kalitesini dil modeli calistirmadan olcer.

Kullanim:
    py rag_degerlendir.py --veri-olustur
        sonuclar/ ve snapshots/ altindaki kayitli HTML'lerden tests/veri/rag_degerlendirme.json uretir
    py rag_degerlendir.py --embed-model text-embedding-qwen3-embedding-0.6b
        her sayfa icin bilgi parcalarini getirir; kapsama, isabet, MRR ve sureyi raporlar
    py rag_degerlendir.py --embed-model a,b,c
        birden fazla gomme modelini ayni sette karsilastirir

Olcum yalnizca gomme modelini kullanir (LM Studio'da yuklu olmali); dil modeli calismaz.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seo_app import ogretme
from seo_app.boru import VARSAYILAN_AYARLAR, zaman_damgasi
from seo_app.cikarma import extract
from seo_app.kurallar import rule_checks
from seo_app.rag_olcum import beklenen_alanlar, olc, ortalama, sorun_isabeti

KOK = Path(__file__).resolve().parent
VERI = KOK / "tests" / "veri" / "rag_degerlendirme.json"


def veri_olustur():
    """Dil modeli calismamis taramalarin duzeltilmis HTML'leri ve kayitli sayfalardan olcum seti.
    Duzeltilmis HTML'de yalnizca kural duzeltmeleri vardir; title, meta, h1 ve gorseller ozgundur."""
    kaynaklar = sorted(KOK.glob("sonuclar/sonuc_taban_canli_v2/duzeltilmis_*.html")) + \
        sorted(KOK.glob("snapshots/*.htm"))
    kayitlar = []
    for yol in kaynaklar:
        d = extract(yol.read_text(encoding="utf-8", errors="ignore"))
        sorunlar = [{"sorun": i["sorun"]} for i in rule_checks(d) if i["cozum_yolu"] == "model"]
        if not sorunlar:
            continue
        kayitlar.append({"ad": yol.stem.replace("duzeltilmis_", ""),
                         "title": d["title"], "h1": d["h1"], "site_adi": d["site_adi"],
                         "text_sample": d["text_sample"], "icerik_ozeti": d["icerik_ozeti"],
                         "sorunlar": sorunlar})
    VERI.parent.mkdir(parents=True, exist_ok=True)
    VERI.write_text(json.dumps(kayitlar, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(kayitlar), "sayfa yazildi:", VERI.relative_to(KOK))


def getir(kayit, embed_url, embed_model, k, siralama=("bm25", "vektor")):
    """Yeni hattin getirme fonksiyonu varsa onu, yoksa eski anlamsal_getir'i kullanir."""
    if hasattr(ogretme, "bilgi_getir"):
        secili, bilgi = ogretme.bilgi_getir(kayit, kayit["sorunlar"], KOK / "ogretme", embed_url, embed_model, k,
                                            siralama=siralama)
        return secili
    return ogretme.anlamsal_getir(kayit, kayit["sorunlar"], KOK / "ogretme", embed_url, embed_model, k)


def degerlendir(embed_url, embed_model, k, siralama=("bm25", "vektor")):
    kayitlar = json.loads(VERI.read_text(encoding="utf-8"))
    getir(kayitlar[0], embed_url, embed_model, k, siralama)   # ilk cagri: indeks/onbellek isinmasi olcume girmez
    olcumler, satirlar = [], []
    for kayit in kayitlar:
        t0 = time.perf_counter()
        secili = getir(kayit, embed_url, embed_model, k, siralama)
        sure_ms = (time.perf_counter() - t0) * 1000
        kodlar = [s["sorun"] for s in kayit["sorunlar"]]
        beklenen = beklenen_alanlar(kodlar)
        o = olc(secili, beklenen)
        o["sorun_isabeti"] = sorun_isabeti(secili, kodlar)
        o["sure_ms"] = sure_ms
        olcumler.append(o)
        satirlar.append({"ad": kayit["ad"], "beklenen": beklenen,
                         "getirilen": [p.get("id") for p in secili],
                         **{x: (round(y, 3) if y is not None else None) for x, y in o.items()}})
    return ortalama(olcumler), satirlar


def main():
    ap = argparse.ArgumentParser(description="RAG getirme kalitesini olcer.")
    ap.add_argument("--veri-olustur", action="store_true", help="olcum setini kayitli HTML'lerden yeniden uret")
    ap.add_argument("--embed-model", help="virgulle ayrilmis gomme modeli listesi")
    ap.add_argument("--url", default=VARSAYILAN_AYARLAR["url"], help="LM Studio adresi")
    ap.add_argument("--k", type=int, default=VARSAYILAN_AYARLAR.get("bilgi_sayisi", VARSAYILAN_AYARLAR["ornek_sayisi"]))
    ap.add_argument("--etiket", default="", help="sonuc dosyasinin adina eklenecek kisa ad (ornek: onceki)")
    ap.add_argument("--siralama", default="bm25,vektor",
                    help="birlestirilecek siralamalar: bm25, vektor ya da ikisi (hibrit)")
    args = ap.parse_args()
    if args.veri_olustur:
        veri_olustur()
        return
    if not args.embed_model:
        ap.error("--embed-model gerekli (ya da --veri-olustur)")
    hedef = KOK / "sonuclar" / "rag_degerlendirme" / (zaman_damgasi() + ("_" + args.etiket if args.etiket else ""))
    hedef.mkdir(parents=True, exist_ok=True)
    ozet = {}
    for model in [m.strip() for m in args.embed_model.split(",") if m.strip()]:
        ort, satirlar = degerlendir(args.url, model, args.k, tuple(_s.strip() for _s in args.siralama.split(",")))
        ozet[model] = ort
        (hedef / (model.replace("/", "_") + ".json")).write_text(
            json.dumps({"ortalama": ort, "sayfalar": satirlar}, ensure_ascii=False, indent=1), encoding="utf-8")
        si = ort.get("sorun_isabeti")
        print(f"{model:40s} [{args.siralama}] kapsama={ort['kapsama']:.3f} isabet={ort['isabet']:.3f} "
              f"mrr={ort['mrr']:.3f} sorun_isabeti={'-' if si is None else format(si, '.3f')} "
              f"parca={ort['parca_sayisi']:.2f} sure={ort['sure_ms']:.0f} ms")
    (hedef / "ozet.json").write_text(json.dumps({"k": args.k, "siralama": args.siralama, "modeller": ozet},
                                                ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    print("Sonuç:", hedef.relative_to(KOK))


if __name__ == "__main__":
    main()
