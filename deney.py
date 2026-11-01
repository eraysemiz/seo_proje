#!/usr/bin/env python3
"""Deney matrisi kosucusu: model x kosul x retry kombinasyonlarini tek komutla calistirir.
Arayuzde kosul sabittir (ornek+bilgi); burada --kosullar ile bilgi tabaninin ve orneklerin
katkisini olcmek icin sifir/ornek/bilgi/ornek+bilgi karsilastirilabilir (varsayilan: ornek+bilgi).

Her kombinasyon sonuclar/<site>/sonuc_<tarih_saat>/<model>__<kosul>__r<retry>/ klasorune
yazilir (rapor.json, ozet.csv, duzeltilmis sayfalar). Her sitenin kombinasyon karsilastirmasi
sonuclar/<site>/sonuc_<tarih_saat>/karsilastirma.csv dosyasinda toplanir. Birden fazla kosul calistirilirsa
her kosulun ornek+bilgi'ye gore sayfa basina eslestirilmis farki ve %95 bootstrap araligi
kosul_farklari.csv dosyasina yazilir. Oneri kalitesi (dogruluk, uydurma) insan etiketiyle olculur: etiketle.py.

Ornekler:
    py deney.py --adresler test_setleri/duzce_birimleri.txt --modeller qwen/qwen3.5-9b,qwen3.8-4b-distill
    py deney.py --adresler test_setleri/duzce_birimleri.txt --modeller qwen/qwen3.5-9b ^
                --retry 0,1 --embed-model text-embedding-qwen3-embedding-0.6b
    py deney.py --adresler test_setleri/duzce_birimleri.txt --modeller qwen/qwen3.5-9b --retry 1 ^
                --kosullar sifir,ornek,bilgi,ornek+bilgi --embed-model text-embedding-qwen3-embedding-0.6b

Not: LM Studio farkli bir modeli ilk istekte bellege yukler. Model karsilastirmasinda
hiz olcumlerinin adil olmasi icin modelleri tek tek yuklu tutmak onerilir.
"""
import argparse
import csv
import io
import itertools
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from seo_app import canli  # noqa: E402
from seo_app.boru import (VARSAYILAN_AYARLAR, _guvenli_ad, hedefleri_hazirla, site_adi,  # noqa: E402
                          topluca_analiz, zaman_damgasi)
from seo_app.llm import ModelHatasi, modelleri_dogrula  # noqa: E402
from seo_app.istatistik import bootstrap_fark  # noqa: E402
from seo_app.kurallar import ALAN_SORUN  # noqa: E402
from seo_app.ogretme import KOSULLAR  # noqa: E402
from seo_app.rag_olcum import ALTIN_PARCALAR  # noqa: E402

KARSILASTIRMA_SUTUNLARI = [
    "model", "kosul", "retry", "sayfa", "hatali_sayfa", "json_gecerli_orani",
    "ort_once_sorun", "ort_sonra_sorun", "ort_once_puan", "ort_sonra_puan",
    "ort_model_cozum_orani", "ort_toplam_cozum_orani",
    "toplam_kabul", "toplam_reddedilen", "toplam_yok_sayilan", "kaynak_gosterme_orani", "kaynak_isabeti",
    "uydurma_reddi_orani", "kalip_reddi_orani", "ort_model_suresi_sn", "klasor"]
FARK_SUTUNLARI = ["model", "retry", "metrik", "kosul", "referans", "fark", "alt", "ust", "n", "anlamli"]
UYDURMA_NEDENLERI = ("dogrulanamayan_niteleme", "sayfada_olmayan_ifade", "kaynakta_olmayan_sayi", "sayfada_olmayan_ad")
KALIP_NEDENLERI = ("marka_tekrari", "bos_kalip")
REFERANS_KOSUL = "ornek+bilgi"


def _ortalama(degerler):
    degerler = [x for x in degerler if isinstance(x, (int, float))]
    return round(sum(degerler) / len(degerler), 3) if degerler else ""


def kaynak_olcumu(kayitlar):
    """Kabul edilen onerilerin kaynak gosterme orani ve kaynak isabeti: gosterilen parcalardan en az biri
    o alandaki sorunun altin parcalarindan mi (rag_olcum.ALTIN_PARCALAR). (gosterme, isabet) dondurur."""
    toplam = gosteren = altinli = isabetli = 0
    for k in kayitlar:
        kodlar = set(k.get("modelle_cozulebilir") or [])
        for f in k.get("fixes", []):
            toplam += 1
            kaynaklar = set(f.get("kaynaklar") or [])
            gosteren += bool(kaynaklar)
            altin = set().union(*[ALTIN_PARCALAR[c] for c in ALAN_SORUN.get(f.get("alan"), ())
                                  if c in kodlar and c in ALTIN_PARCALAR] or [set()])
            if kaynaklar and altin:
                altinli += 1
                isabetli += bool(kaynaklar & altin)
    return (round(gosteren / toplam, 3) if toplam else ""), (round(isabetli / altinli, 3) if altinli else "")


def ret_orani(kayitlar, nedenler):
    """Modelin urettigi oneriler icinde verilen nedenlerle reddedilenlerin orani (yok sayilanlar haric)."""
    kabul = sum(len(k.get("fixes", [])) for k in kayitlar)
    red = [r for k in kayitlar for r in k.get("reddedilen", [])]
    toplam = kabul + len(red)
    return round(sum(1 for r in red if str(r.get("neden", "")).startswith(nedenler)) / toplam, 3) if toplam else ""


def kombinasyon_ozeti(model, kosul, retry, rapor, klasor):
    """Bir kombinasyonun tum sayfalarini tek satirlik karsilastirma ozetine indirger."""
    gecerli = [k for k in rapor if not k.get("hata") and not k.get("atlandi")]
    modelli = [k for k in gecerli if k.get("model")]
    gosterme, isabet = kaynak_olcumu(modelli)
    return {
        "model": model, "kosul": kosul, "retry": retry,
        "sayfa": len(rapor), "hatali_sayfa": len(rapor) - len(gecerli),
        "json_gecerli_orani": _ortalama([1 if k.get("json_gecerli") else 0 for k in modelli]),
        "ort_once_sorun": _ortalama([k.get("once_sorun_sayisi") for k in gecerli]),
        "ort_sonra_sorun": _ortalama([k.get("sonra_sorun_sayisi") for k in gecerli]),
        "ort_once_puan": _ortalama([k.get("once_puan") for k in gecerli]),
        "ort_sonra_puan": _ortalama([k.get("sonra_puan") for k in gecerli]),
        "ort_model_cozum_orani": _ortalama([k.get("cozum_orani") for k in gecerli]),
        "ort_toplam_cozum_orani": _ortalama([k.get("toplam_cozum_orani") for k in gecerli]),
        "toplam_kabul": sum(len(k.get("fixes", [])) for k in gecerli),
        "toplam_reddedilen": sum(len(k.get("reddedilen", [])) for k in gecerli),
        "toplam_yok_sayilan": sum(len(k.get("yok_sayilan", [])) for k in gecerli),
        "kaynak_gosterme_orani": gosterme, "kaynak_isabeti": isabet,
        "uydurma_reddi_orani": ret_orani(modelli, UYDURMA_NEDENLERI),
        "kalip_reddi_orani": ret_orani(modelli, KALIP_NEDENLERI),
        "ort_model_suresi_sn": _ortalama([k.get("sure_sn") for k in modelli]),
        "klasor": str(klasor),
    }


def kosul_farklari(sayfa_olcumleri, referans=REFERANS_KOSUL, metrikler=("cozum_orani", "toplam_cozum_orani")):
    """Her kosulun referans kosula gore sayfa basina eslestirilmis farki ve %95 bootstrap araligi.
    sayfa_olcumleri: {(model, kosul, retry): {sayfa adi: kayit}}. Aralik 0'i icermiyorsa fark anlamli."""
    satirlar = []
    for (model, kosul, retry), sayfalar in sorted(sayfa_olcumleri.items()):
        ref = sayfa_olcumleri.get((model, referans, retry))
        if kosul == referans or not ref:
            continue
        ortak = sorted(set(sayfalar) & set(ref))
        for metrik in metrikler:
            b = bootstrap_fark([sayfalar[a].get(metrik) for a in ortak], [ref[a].get(metrik) for a in ortak])
            if b:
                satirlar.append({"model": model, "retry": retry, "metrik": metrik, "kosul": kosul, "referans": referans,
                                 **b, "anlamli": "evet" if b["alt"] > 0 or b["ust"] < 0 else "hayir"})
    return satirlar


def karsilastirma_csv(satirlar, sutunlar=None):
    tampon = io.StringIO()
    yazici = csv.DictWriter(tampon, fieldnames=sutunlar or KARSILASTIRMA_SUTUNLARI, delimiter=";")
    yazici.writeheader()
    yazici.writerows(satirlar)
    return tampon.getvalue()


def _kayitli(sonuc_koku, zaman, ad, hedefler):
    """Bir kombinasyonun diske yazilmis sayfa kayitlari: {normallestirilmis adres: kayit}."""
    sonuc = {}
    for site in sorted({site_adi(h["url"]) for h in hedefler}):
        yol = Path(sonuc_koku) / site / zaman / ad / "rapor.json"
        if yol.exists():
            for k in json.loads(yol.read_text(encoding="utf-8")):
                sonuc[canli.normalize(k["ad"])] = k
    return sonuc


def deney_calistir(hedefler, modeller, kosullar, retryler, temel_ayarlar, sonuc_koku, zaman,
                   ogretme_klasoru, gunluk=print, devam=False):
    """Tum kombinasyonlari sirayla calistirir. Her kombinasyon
    <sonuc_koku>/<site>/<zaman>/<kombinasyon>/ altina, her sitenin karsilastirmasi
    <sonuc_koku>/<site>/<zaman>/karsilastirma.csv dosyasina yazilir.
    devam: ayni zaman damgasiyla yarida kalmis deneyi surdurur; kombinasyonda sonucu diske yazilmis
    sayfalar yeniden calistirilmaz (her sayfanin rapor.json'u sayfa bitince yazilir).
    {site deney klasoru: karsilastirma satirlari} dondurur."""
    satirlar, olcumler = {}, {}
    kombinasyonlar = list(itertools.product(modeller, kosullar, retryler))
    for n, (model, kosul, retry) in enumerate(kombinasyonlar, 1):
        ad = _guvenli_ad(model) + "__" + _guvenli_ad(kosul) + "__r" + str(retry)
        gunluk("=== [" + str(n) + "/" + str(len(kombinasyonlar)) + "] " + ad)
        ayarlar = {**temel_ayarlar, "model": model, "kosul": kosul, "retry": retry}
        kalan = hedefler
        if devam:
            biten = _kayitli(sonuc_koku, zaman, ad, hedefler)
            kalan = [h for h in hedefler if canli.normalize(h["url"]) not in biten]
            gunluk(f"   devam: {len(hedefler) - len(kalan)} sayfa önceden bitmiş, {len(kalan)} sayfa kaldı")
        if kalan:
            topluca_analiz(kalan, ayarlar, ogretme_klasoru, sonuc_koku, str(Path(zaman) / ad),
                           gunluk=lambda m: gunluk("   " + m))
        rapor = list(_kayitli(sonuc_koku, zaman, ad, hedefler).values())
        site_kayitlari = {}
        for k in rapor:
            site_kayitlari.setdefault(Path(sonuc_koku) / site_adi(k["ad"]) / zaman, []).append(k)
        for deney_klasoru, kayitlar in site_kayitlari.items():
            olcumler.setdefault(deney_klasoru, {})[(model, kosul, retry)] = {
                k["ad"]: k for k in kayitlar if not k.get("hata") and not k.get("atlandi")}
            farklar = kosul_farklari(olcumler[deney_klasoru])
            if farklar:
                (deney_klasoru / "kosul_farklari.csv").write_text(karsilastirma_csv(farklar, FARK_SUTUNLARI),
                                                                  encoding="utf-8-sig")
            satirlar.setdefault(deney_klasoru, []).append(
                kombinasyon_ozeti(model, kosul, retry, kayitlar, deney_klasoru / ad))
            # her kombinasyondan sonra yazilir; deney yarida kesilse bile o ana kadarki sonuclar kalir
            (deney_klasoru / "karsilastirma.csv").write_text(karsilastirma_csv(satirlar[deney_klasoru]),
                                                             encoding="utf-8-sig")
    return satirlar


def birlesik_ozet(sonuc_koku, zaman, hedef=None):
    """Bir deneyin tum sitelerdeki kombinasyonlarini tek karsilastirmada toplar (cok siteli setlerde site
    basina karsilastirma tek sayfaya dayanir). Kayitli rapor.json'lardan hesaplanir; deney yeniden
    calistirilmaz. <sonuc_koku>/_deneyler/<zaman>/ altina karsilastirma.csv ve kosul_farklari.csv yazar."""
    kosul_adi = {_guvenli_ad(k): k for k in KOSULLAR}
    gruplar = {}
    for rapor_yolu in sorted(Path(sonuc_koku).glob(f"*/{zaman}/*__*__r*/rapor.json")):
        model_ad, kosul_ad, retry = rapor_yolu.parent.name.split("__")
        kayitlar = json.loads(rapor_yolu.read_text(encoding="utf-8"))
        model = next((k["model"] for k in kayitlar if k.get("model")), model_ad)
        anahtar = (model, kosul_adi.get(kosul_ad, kosul_ad), int(retry.lstrip("r")))
        gruplar.setdefault(anahtar, []).extend(kayitlar)
    if not gruplar:
        raise SystemExit("Bu zaman damgasıyla deney bulunamadı: " + str(zaman))
    hedef = Path(hedef or Path(sonuc_koku) / "_deneyler" / zaman)
    hedef.mkdir(parents=True, exist_ok=True)
    satirlar = [kombinasyon_ozeti(m, k, r, kayitlar, hedef) for (m, k, r), kayitlar in sorted(gruplar.items())]
    (hedef / "karsilastirma.csv").write_text(karsilastirma_csv(satirlar), encoding="utf-8-sig")
    olcumler = {a: {k["ad"]: k for k in kayitlar if not k.get("hata") and not k.get("atlandi")}
                for a, kayitlar in gruplar.items()}
    farklar = kosul_farklari(olcumler)
    (hedef / "kosul_farklari.csv").write_text(karsilastirma_csv(farklar, FARK_SUTUNLARI), encoding="utf-8-sig")
    return hedef, satirlar, farklar


def _liste(metin):
    return [x.strip() for x in metin.split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deney matrisi: model x koşul x retry")
    ap.add_argument("--adresler", help="her satırında bir adres bulunan metin dosyası")
    ap.add_argument("--modeller", help="virgülle ayrılmış sohbet modeli kimlikleri")
    ap.add_argument("--devam", metavar="ZAMAN",
                    help="yarıda kalan deneyi sürdür (ör. sonuc_2026-10-28_16-40-20); biten sayfalar atlanır")
    ap.add_argument("--birlestir", metavar="ZAMAN",
                    help="deney çalıştırma; sonuclar/*/ZAMAN altındaki tüm sitelerin sonuçlarını tek karşılaştırmada topla")
    ap.add_argument("--retry", default="0,1", help="virgülle ayrılmış yeniden deneme (retry) değerleri")
    ap.add_argument("--kosullar", default=VARSAYILAN_AYARLAR["kosul"],
                    help="virgülle ayrılmış deney koşulları: " + ", ".join(KOSULLAR) + " (varsayılan: ornek+bilgi)")
    ap.add_argument("--bilgi-sayisi", type=int, default=VARSAYILAN_AYARLAR["bilgi_sayisi"],
                    help="getirilecek bilgi tabanı parçası sayısı")
    ap.add_argument("--rerank-url", default=None, help="yeniden sıralama sunucusu (/rerank ucu olan)")
    ap.add_argument("--rerank-model", default=None, help="yeniden sıralama modeli")
    ap.add_argument("--url", default=VARSAYILAN_AYARLAR["url"], help="LM Studio adresi")
    ap.add_argument("--embed-model", default=None, help="bilgi tabanından anlamsal seçim için gömme modeli")
    ap.add_argument("--max-tokens", type=int, default=VARSAYILAN_AYARLAR["max_tokens"])
    ap.add_argument("--bekleme", type=float, default=VARSAYILAN_AYARLAR["bekleme_sn"],
                    help="istekler arası bekleme (sn)")
    args = ap.parse_args(argv)
    if args.birlestir:
        hedef, satirlar, farklar = birlesik_ozet(KOK / "sonuclar", args.birlestir)
        for x in satirlar:
            print(f"{x['kosul']:12s} sayfa={x['sayfa']} çözüm={x['ort_model_cozum_orani']} "
                  f"uydurma_reddi={x['uydurma_reddi_orani']} kaynak_isabeti={x['kaynak_isabeti']}")
        for f in farklar:
            print(f"{f['metrik']}: {f['kosul']} - {f['referans']} = {f['fark']:+.3f} [{f['alt']:+.3f}, {f['ust']:+.3f}]"
                  f" n={f['n']} anlamlı={f['anlamli']}")
        print("Birleşik karşılaştırma:", hedef)
        return
    if not args.adresler or not args.modeller:
        ap.error("--adresler ve --modeller gerekli (ya da --birlestir)")

    kosullar = _liste(args.kosullar)
    gecersiz = [k for k in kosullar if k not in KOSULLAR]
    if gecersiz or not kosullar:
        ap.error("geçersiz koşul: " + ", ".join(gecersiz) + " (seçenekler: " + ", ".join(KOSULLAR) + ")")
    try:
        retryler = [int(x) for x in _liste(args.retry)]
    except ValueError:
        ap.error("--retry virgülle ayrılmış tam sayılar olmalı")

    hedefler = hedefleri_hazirla((KOK / args.adresler).read_text(encoding="utf-8"))
    if not hedefler:
        ap.error("analiz edilecek sayfa bulunamadı")

    # deney baslamadan once LM Studio ve tum secilen modeller denetlenir; sorun varsa hic baslamaz
    try:
        modelleri_dogrula(args.url, _liste(args.modeller) + [args.embed_model])
    except ModelHatasi as e:
        raise SystemExit("HATA: " + str(e))

    zaman = args.devam or zaman_damgasi()
    temel = {"url": args.url, "embed_model": args.embed_model, "max_tokens": args.max_tokens,
             "bekleme_sn": args.bekleme, "bilgi_sayisi": args.bilgi_sayisi,
             "rerank_url": args.rerank_url, "rerank_model": args.rerank_model}
    toplam = len(_liste(args.modeller)) * len(kosullar) * len(retryler)
    print(str(len(hedefler)) + " sayfa x " + str(toplam) + " kombinasyon -> sonuclar/<site>/" + zaman)
    satirlar = deney_calistir(hedefler, _liste(args.modeller), kosullar, retryler, temel, KOK / "sonuclar",
                              zaman, KOK / "ogretme", devam=bool(args.devam))
    for deney_klasoru in satirlar:
        print("Karşılaştırma:", deney_klasoru / "karsilastirma.csv")
    if len(satirlar) > 1:
        print("Birleşik karşılaştırma:", birlesik_ozet(KOK / "sonuclar", zaman)[0])


if __name__ == "__main__":
    main()
