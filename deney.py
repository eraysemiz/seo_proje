#!/usr/bin/env python3
"""Deney matrisi kosucusu: model x kosul x retry kombinasyonlarini tek komutla calistirir.
Arayuzde kosul sabittir (ornek+bilgi); burada --kosullar ile bilgi tabaninin ve orneklerin
katkisini olcmek icin sifir/ornek/bilgi/ornek+bilgi karsilastirilabilir (varsayilan: ornek+bilgi).

Her kombinasyon sonuclar/<site>/sonuc_<tarih_saat>/<model>__<kosul>__r<retry>/ klasorune
yazilir (rapor.json, ozet.csv, duzeltilmis sayfalar). Her sitenin kombinasyon karsilastirmasi
sonuclar/<site>/sonuc_<tarih_saat>/karsilastirma.csv dosyasinda toplanir.

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
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from seo_app.boru import (VARSAYILAN_AYARLAR, _guvenli_ad, hedefleri_hazirla, site_adi,  # noqa: E402
                          topluca_analiz, zaman_damgasi)
from seo_app.llm import ModelHatasi, modelleri_dogrula  # noqa: E402
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


def deney_calistir(hedefler, modeller, kosullar, retryler, temel_ayarlar, sonuc_koku, zaman,
                   ogretme_klasoru, gunluk=print):
    """Tum kombinasyonlari sirayla calistirir. Her kombinasyon
    <sonuc_koku>/<site>/<zaman>/<kombinasyon>/ altina, her sitenin karsilastirmasi
    <sonuc_koku>/<site>/<zaman>/karsilastirma.csv dosyasina yazilir.
    {site deney klasoru: karsilastirma satirlari} dondurur."""
    satirlar = {}
    kombinasyonlar = list(itertools.product(modeller, kosullar, retryler))
    for n, (model, kosul, retry) in enumerate(kombinasyonlar, 1):
        ad = _guvenli_ad(model) + "__" + _guvenli_ad(kosul) + "__r" + str(retry)
        gunluk("=== [" + str(n) + "/" + str(len(kombinasyonlar)) + "] " + ad)
        ayarlar = {**temel_ayarlar, "model": model, "kosul": kosul, "retry": retry}
        rapor = topluca_analiz(hedefler, ayarlar, ogretme_klasoru, sonuc_koku, str(Path(zaman) / ad),
                               gunluk=lambda m: gunluk("   " + m))
        site_kayitlari = {}
        for k in rapor:
            site_kayitlari.setdefault(Path(sonuc_koku) / site_adi(k["ad"]) / zaman, []).append(k)
        for deney_klasoru, kayitlar in site_kayitlari.items():
            satirlar.setdefault(deney_klasoru, []).append(
                kombinasyon_ozeti(model, kosul, retry, kayitlar, deney_klasoru / ad))
            # her kombinasyondan sonra yazilir; deney yarida kesilse bile o ana kadarki sonuclar kalir
            (deney_klasoru / "karsilastirma.csv").write_text(karsilastirma_csv(satirlar[deney_klasoru]),
                                                             encoding="utf-8-sig")
    return satirlar


def _liste(metin):
    return [x.strip() for x in metin.split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deney matrisi: model x koşul x retry")
    ap.add_argument("--adresler", required=True, help="her satırında bir adres bulunan metin dosyası")
    ap.add_argument("--modeller", required=True, help="virgülle ayrılmış sohbet modeli kimlikleri")
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

    zaman = zaman_damgasi()
    temel = {"url": args.url, "embed_model": args.embed_model, "max_tokens": args.max_tokens,
             "bekleme_sn": args.bekleme, "bilgi_sayisi": args.bilgi_sayisi,
             "rerank_url": args.rerank_url, "rerank_model": args.rerank_model}
    toplam = len(_liste(args.modeller)) * len(kosullar) * len(retryler)
    print(str(len(hedefler)) + " sayfa x " + str(toplam) + " kombinasyon -> sonuclar/<site>/" + zaman)
    satirlar = deney_calistir(hedefler, _liste(args.modeller), kosullar, retryler, temel, KOK / "sonuclar",
                              zaman, KOK / "ogretme")
    for deney_klasoru in satirlar:
        print("Karşılaştırma:", deney_klasoru / "karsilastirma.csv")


if __name__ == "__main__":
    main()
