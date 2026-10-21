#!/usr/bin/env python3
"""Deney matrisi kosucusu: model x kosul x retry kombinasyonlarini tek komutla calistirir.

Her kombinasyon sonuclar/<deney_adi>/<model>__<kosul>__r<retry>/ klasorune yazilir
(rapor.json, ozet.csv, duzeltilmis sayfalar). Tum kombinasyonlarin karsilastirmasi
sonuclar/<deney_adi>/karsilastirma.csv dosyasinda toplanir.

Ornekler:
    py deney.py --klasor snapshots --modeller qwen/qwen3.5-9b,qwen3.8-4b-distill
    py deney.py --adresler test_setleri/duzce_birimleri.txt --modeller qwen/qwen3.5-9b ^
                --kosullar sifir,bilgi --retry 0,1 --embed-model text-embedding-qwen3-embedding-0.6b

Not: LM Studio farkli bir modeli ilk istekte bellege yukler. Model karsilastirmasinda
hiz olcumlerinin adil olmasi icin modelleri tek tek yuklu tutmak onerilir.
"""
import argparse
import csv
import io
import itertools
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from seo_app.boru import VARSAYILAN_AYARLAR, _guvenli_ad, hedefleri_hazirla, topluca_analiz  # noqa: E402
from seo_app.ogretme import KOSULLAR  # noqa: E402

KARSILASTIRMA_SUTUNLARI = [
    "model", "kosul", "retry", "sayfa", "hatali_sayfa", "json_gecerli_orani",
    "ort_once_sorun", "ort_sonra_sorun", "ort_once_puan", "ort_sonra_puan",
    "ort_model_cozum_orani", "ort_toplam_cozum_orani",
    "toplam_kabul", "toplam_reddedilen", "toplam_yok_sayilan", "ort_model_suresi_sn", "klasor"]


def _ortalama(degerler):
    degerler = [x for x in degerler if isinstance(x, (int, float))]
    return round(sum(degerler) / len(degerler), 3) if degerler else ""


def kombinasyon_ozeti(model, kosul, retry, rapor, klasor):
    """Bir kombinasyonun tum sayfalarini tek satirlik karsilastirma ozetine indirger."""
    gecerli = [k for k in rapor if not k.get("hata") and not k.get("atlandi")]
    modelli = [k for k in gecerli if k.get("model")]
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
        "ort_model_suresi_sn": _ortalama([k.get("sure_sn") for k in modelli]),
        "klasor": str(klasor),
    }


def karsilastirma_csv(satirlar):
    tampon = io.StringIO()
    yazici = csv.DictWriter(tampon, fieldnames=KARSILASTIRMA_SUTUNLARI, delimiter=";")
    yazici.writeheader()
    yazici.writerows(satirlar)
    return tampon.getvalue()


def deney_calistir(hedefler, modeller, kosullar, retryler, temel_ayarlar, deney_klasoru,
                   ogretme_klasoru, gunluk=print):
    """Tum kombinasyonlari sirayla calistirir; karsilastirma satirlarini dondurur."""
    deney_klasoru = Path(deney_klasoru)
    deney_klasoru.mkdir(parents=True, exist_ok=True)
    satirlar = []
    kombinasyonlar = list(itertools.product(modeller, kosullar, retryler))
    for n, (model, kosul, retry) in enumerate(kombinasyonlar, 1):
        ad = _guvenli_ad(model) + "__" + _guvenli_ad(kosul) + "__r" + str(retry)
        klasor = deney_klasoru / ad
        gunluk("=== [" + str(n) + "/" + str(len(kombinasyonlar)) + "] " + ad)
        ayarlar = {**temel_ayarlar, "llm_kullan": True, "model": model, "kosul": kosul, "retry": retry}
        rapor = topluca_analiz(hedefler, ayarlar, ogretme_klasoru, klasor,
                               gunluk=lambda m: gunluk("   " + m))
        satirlar.append(kombinasyon_ozeti(model, kosul, retry, rapor, klasor))
        # her kombinasyondan sonra yazilir; deney yarida kesilse bile o ana kadarki sonuclar kalir
        (deney_klasoru / "karsilastirma.csv").write_text(karsilastirma_csv(satirlar), encoding="utf-8-sig")
    return satirlar


def _liste(metin):
    return [x.strip() for x in metin.split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deney matrisi: model x kosul x retry")
    kaynak = ap.add_mutually_exclusive_group(required=True)
    kaynak.add_argument("--klasor", help="kaydedilmis HTML klasoru (proje kokune gore)")
    kaynak.add_argument("--adresler", help="her satirda bir adres bulunan metin dosyasi")
    ap.add_argument("--modeller", required=True, help="virgulle ayrilmis sohbet modeli kimlikleri")
    ap.add_argument("--kosullar", default=",".join(KOSULLAR), help="varsayilan: dort kosulun tamami")
    ap.add_argument("--retry", default="0,1", help="virgulle ayrilmis retry degerleri")
    ap.add_argument("--ad", default=None, help="deney klasorunun adi (varsayilan: deney_<tarih>)")
    ap.add_argument("--url", default=VARSAYILAN_AYARLAR["url"], help="LM Studio adresi")
    ap.add_argument("--embed-model", default=None, help="bilgi kosulu icin gomme modeli")
    ap.add_argument("--max-tokens", type=int, default=VARSAYILAN_AYARLAR["max_tokens"])
    ap.add_argument("--bekleme", type=float, default=VARSAYILAN_AYARLAR["bekleme_sn"],
                    help="canli modda istekler arasi bekleme (sn)")
    args = ap.parse_args(argv)

    kosullar = _liste(args.kosullar)
    bilinmeyen = [k for k in kosullar if k not in KOSULLAR]
    if bilinmeyen:
        ap.error("bilinmeyen kosul: " + ", ".join(bilinmeyen) + " (gecerli: " + ", ".join(KOSULLAR) + ")")
    try:
        retryler = [int(x) for x in _liste(args.retry)]
    except ValueError:
        ap.error("--retry virgulle ayrilmis tam sayilar olmali")

    if args.klasor:
        hedefler = hedefleri_hazirla("dosya", None, KOK / args.klasor)
    else:
        hedefler = hedefleri_hazirla("canli", (KOK / args.adresler).read_text(encoding="utf-8"), None)
    if not hedefler:
        ap.error("analiz edilecek sayfa bulunamadi")

    deney_klasoru = KOK / "sonuclar" / (args.ad or ("deney_" + time.strftime("%Y%m%d_%H%M%S")))
    temel = {"url": args.url, "embed_model": args.embed_model, "max_tokens": args.max_tokens,
             "bekleme_sn": args.bekleme}
    toplam = len(_liste(args.modeller)) * len(kosullar) * len(retryler)
    print(str(len(hedefler)) + " sayfa x " + str(toplam) + " kombinasyon -> " + str(deney_klasoru))
    deney_calistir(hedefler, _liste(args.modeller), kosullar, retryler, temel, deney_klasoru,
                   KOK / "ogretme")
    print("Karsilastirma:", deney_klasoru / "karsilastirma.csv")


if __name__ == "__main__":
    main()
