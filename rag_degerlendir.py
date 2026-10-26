#!/usr/bin/env python3
"""Bilgi getirme (RAG) kalitesini dil modeli calistirmadan olcer.

Kullanim:
    py rag_degerlendir.py --veri-olustur
        sonuclar/ ve snapshots/ altindaki kayitli HTML'lerden tests/veri/rag_degerlendirme.json uretir
        (daha once --veri-ekle ile eklenen canli kayitlar korunur)
    py rag_degerlendir.py --veri-ekle test_setleri/rag_ek_siteler.txt
        listedeki sitelerin anasayfasini ve bir ic sayfasini canli indirip sete ekler (robots.txt'ye uyar)
    py rag_degerlendir.py --embed-model text-embedding-qwen3-embedding-0.6b
        her sayfa icin bilgi parcalarini getirir; kapsama, isabet, MRR ve sureyi raporlar
    py rag_degerlendir.py --embed-model a,b,c
        birden fazla gomme modelini ayni sette karsilastirir

Olcum yalnizca gomme modelini kullanir (LM Studio'da yuklu olmali); dil modeli calismaz.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seo_app import canli, ogretme
from seo_app.boru import VARSAYILAN_AYARLAR, zaman_damgasi
from seo_app.cikarma import extract
from seo_app.kurallar import rule_checks
from seo_app.rag_olcum import ALTIN_SURUM, beklenen_alanlar, olc, ortalama, sorun_isabeti

KOK = Path(__file__).resolve().parent
VERI = KOK / "tests" / "veri" / "rag_degerlendirme.json"


def _kayit(ad, grup, kaynak_turu, html):
    """HTML'den olcum kaydi; modele gidecek sorunu yoksa None (getirme hic calismaz)."""
    d = extract(html)
    sorunlar = [{"sorun": i["sorun"]} for i in rule_checks(d) if i["cozum_yolu"] == "model"]
    if not sorunlar:
        return None
    return {"ad": ad, "grup": grup, "kaynak_turu": kaynak_turu,
            "title": d["title"], "h1": d["h1"], "site_adi": d["site_adi"],
            "text_sample": d["text_sample"], "icerik_ozeti": d["icerik_ozeti"], "sorunlar": sorunlar}


def _mevcut():
    return json.loads(VERI.read_text(encoding="utf-8")) if VERI.exists() else []


def _yaz(kayitlar):
    VERI.parent.mkdir(parents=True, exist_ok=True)
    VERI.write_text(json.dumps(kayitlar, ensure_ascii=False, indent=1), encoding="utf-8")


def veri_olustur():
    """Dil modeli calismamis taramalarin duzeltilmis HTML'leri ve kayitli sayfalardan olcum seti.
    Duzeltilmis HTML'de yalnizca kural duzeltmeleri vardir; title, meta, h1 ve gorseller ozgundur.
    Daha once canli indirilmis kayitlar korunur."""
    kaynaklar = [(y, "duzce_birim") for y in sorted(KOK.glob("sonuclar/sonuc_taban_canli_v2/duzeltilmis_*.html"))] + \
        [(y, "universite") for y in sorted(KOK.glob("snapshots/*.htm"))]
    kayitlar = []
    for yol, grup in kaynaklar:
        k = _kayit(yol.stem.replace("duzeltilmis_", ""), grup, "kayitli_html",
                   yol.read_text(encoding="utf-8", errors="ignore"))
        if k:
            kayitlar.append(k)
    canlilar = [k for k in _mevcut() if k.get("kaynak_turu") == "canli"]
    _yaz(kayitlar + canlilar)
    print(len(kayitlar), "kayitli sayfa +", len(canlilar), "canli sayfa yazildi:", VERI.relative_to(KOK))


# ic sayfa secerken atlanacak adresler: oturum, sepet, dosya, dil secimi ve iletisim baglantilari
ATLANACAK_YOL = re.compile(r"(login|giris|uye|sepet|cart|hesap|account|arama|search|javascript:|mailto:|tel:|"
                           r"\.(pdf|jpe?g|png|gif|zip|docx?|xlsx?)$|/(en|de|ar|ru)/?$)", re.I)


def ic_sayfa_sec(html, taban):
    """Anasayfadan ayni host'taki anlamli bir ic sayfa: en az bir yol parcasi olan, baglanti metni
    8+ karakter olan adaylarin ortasindaki (menunun ilk ve son ogelerinden kacinmak icin)."""
    host = urlparse(taban).hostname
    adaylar, gorulen = [], set()
    for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
        adres = urljoin(taban, a["href"]).split("#")[0]
        u = urlparse(adres)
        if u.hostname != host or u.path.strip("/") == "" or ATLANACAK_YOL.search(adres):
            continue
        if len(a.get_text(" ", strip=True)) < 8 or adres in gorulen:
            continue
        gorulen.add(adres)
        adaylar.append(adres)
    return adaylar[len(adaylar) // 2] if adaylar else None


def veri_ekle(liste_yolu, bekleme=1.0):
    """Listedeki sitelerin anasayfasini ve bir ic sayfasini indirip sete ekler. robots.txt'nin
    izin vermedigi adres atlanir; ayni adres iki kez eklenmez."""
    kayitlar = _mevcut()
    var = {k["ad"] for k in kayitlar}
    eklenen = atlanan = sorunsuz = 0
    for satir in (KOK / liste_yolu).read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#"):
            continue
        grup, adres = satir.split(None, 1)
        hedefler = [canli.normalize(adres)]
        while hedefler:
            url = hedefler.pop(0)
            robots = canli.robots_bilgisi(canli.kok(url))
            if canli.sayfa_engelli_mi(robots, url, canli.AJAN_BELIRTECI):
                print("robots.txt izin vermiyor:", url)
                atlanan += 1
                continue
            g = canli.sayfa_getir(url)
            time.sleep(bekleme)
            if not g.get("basarili") or (g.get("durum_kodu") or 0) >= 400:
                print("alinamadi:", url, g.get("hata") or g.get("durum_kodu"))
                atlanan += 1
                continue
            son = g.get("son_url") or url
            if url == canli.normalize(adres):                 # anasayfadan bir ic sayfa da alinir
                ic = ic_sayfa_sec(g["html"], son)
                if ic:
                    hedefler.append(ic)
            k = _kayit(son, grup, "canli", g["html"])
            if k is None:
                sorunsuz += 1
                print("modele gidecek sorun yok:", son)
            elif son not in var:
                k["tarih"] = time.strftime("%Y-%m-%d")
                kayitlar.append(k)
                var.add(son)
                eklenen += 1
                print("eklendi:", grup, son, [s["sorun"] for s in k["sorunlar"]])
    _yaz(kayitlar)
    print(eklenen, "sayfa eklendi;", sorunsuz, "sayfanin modele gidecek sorunu yok;", atlanan, "atlandi. Toplam:",
          len(kayitlar))


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
        satirlar.append({"ad": kayit["ad"], "grup": kayit.get("grup", ""), "beklenen": beklenen,
                         "getirilen": [p.get("id") for p in secili],
                         **{x: (round(y, 3) if y is not None else None) for x, y in o.items()}})
    return ortalama(olcumler), satirlar


def grup_ortalamalari(satirlar):
    gruplar = {}
    for s in satirlar:
        gruplar.setdefault(s.get("grup") or "-", []).append(s)
    return {g: {"sayfa": len(x), **ortalama([{k: s[k] for k in ("kapsama", "isabet", "mrr", "sorun_isabeti")}
                                              for s in x])} for g, x in sorted(gruplar.items())}


def main():
    ap = argparse.ArgumentParser(description="RAG getirme kalitesini olcer.")
    ap.add_argument("--veri-olustur", action="store_true", help="olcum setini kayitli HTML'lerden yeniden uret")
    ap.add_argument("--veri-ekle", metavar="LISTE", help="'grup adres' satirlari olan dosyadaki siteleri canli ekle")
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
    if args.veri_ekle:
        veri_ekle(args.veri_ekle)
        return
    if not args.embed_model:
        ap.error("--embed-model gerekli (ya da --veri-olustur)")
    hedef = KOK / "sonuclar" / "rag_degerlendirme" / (zaman_damgasi() + ("_" + args.etiket if args.etiket else ""))
    hedef.mkdir(parents=True, exist_ok=True)
    ozet = {}
    for model in [m.strip() for m in args.embed_model.split(",") if m.strip()]:
        ort, satirlar = degerlendir(args.url, model, args.k, tuple(_s.strip() for _s in args.siralama.split(",")))
        gruplar = grup_ortalamalari(satirlar)
        ozet[model] = {**ort, "gruplar": gruplar}
        (hedef / (model.replace("/", "_") + ".json")).write_text(
            json.dumps({"ortalama": ort, "gruplar": gruplar, "sayfalar": satirlar}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        si = ort.get("sorun_isabeti")
        print(f"{model:40s} [{args.siralama}] kapsama={ort['kapsama']:.3f} isabet={ort['isabet']:.3f} "
              f"mrr={ort['mrr']:.3f} sorun_isabeti={'-' if si is None else format(si, '.3f')} "
              f"parca={ort['parca_sayisi']:.2f} sure={ort['sure_ms']:.0f} ms")
        for g, o in gruplar.items():
            gsi = o.get("sorun_isabeti")
            print(f"    {g:14s} sayfa={o['sayfa']:3d} sorun_isabeti={'-' if gsi is None else format(gsi, '.3f')} "
                  f"kapsama={o['kapsama']:.3f}")
    (hedef / "ozet.json").write_text(json.dumps({"k": args.k, "siralama": args.siralama, "altin_surum": ALTIN_SURUM, "modeller": ozet},
                                                ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    print("Sonuç:", hedef.relative_to(KOK))


if __name__ == "__main__":
    main()
