#!/usr/bin/env python3
"""Salt okunur (standart mod) tarama: web arayuzundeki 'Standart mod' taramasinin komut satiri
karsiligi. Masaustu uygulamasi bu betigi alt surec olarak calistirir. Ayarlar web arayuzuyle ayni
denetimden (web.ayarlari_dogrula) gecer, tarama ayni donguyle (boru.topluca_analiz) yapilir;
siteye hicbir sey yazilmaz.

    py masaustu/salt_okunur.py --adres https://ornek.edu.tr [--site-modu] [--model M --embed-model E]
    py masaustu/salt_okunur.py --adres https://ornek.edu.tr --yalnizca-denetim
"""
import argparse
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from seo_app import canli                                                   # noqa: E402
from seo_app.boru import hedefleri_hazirla, site_adi, topluca_analiz, zaman_damgasi  # noqa: E402
from seo_app.llm import ModelHatasi, modelleri_dogrula                     # noqa: E402
from seo_app.web import ayarlari_dogrula                                    # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="SEO Denetim Aracı — salt okunur tarama (siteye yazmaz)")
    ap.add_argument("--adres", nargs="+", required=True, help="taranacak adresler")
    ap.add_argument("--site-modu", action="store_true", help="site içi bağlantıları izle")
    ap.add_argument("--sayfa", type=int, default=50, help="site modunda en fazla sayfa")
    ap.add_argument("--derinlik", type=int, default=3, help="site modunda en fazla derinlik")
    ap.add_argument("--model", help="LM Studio sohbet modeli")
    ap.add_argument("--embed-model", help="bilgi tabanı için gömme modeli")
    ap.add_argument("--lm-url", help="LM Studio adresi")
    ap.add_argument("--yalnizca-denetim", action="store_true", help="dil modeli kullanma")
    a = ap.parse_args(argv)

    hedefler = hedefleri_hazirla("\n".join(a.adres))
    if not hedefler:
        print("HATA: Analiz edilecek adres bulunamadı.")
        return 2
    veri = {"model": a.model, "embed_model": a.embed_model, "url": a.lm_url,
            "tarama_modu": "site" if a.site_modu else "liste", "en_fazla_sayfa": a.sayfa,
            "en_fazla_derinlik": a.derinlik, "yalnizca_denetim": a.yalnizca_denetim}
    ayarlar, hata = ayarlari_dogrula(veri)
    if hata:
        print("HATA:", hata)
        return 2
    if not ayarlar["yalnizca_denetim"]:
        try:
            modelleri_dogrula(ayarlar["url"], [ayarlar.get("model"), ayarlar.get("embed_model")])
        except ModelHatasi as e:
            print("HATA:", e)
            return 2
    zaman = zaman_damgasi()
    canli.onbellek_temizle()
    print("Tarama başladı:", len(hedefler), "hedef" +
          (" · yalnızca denetim (dil modeli yok)" if ayarlar["yalnizca_denetim"] else " · model=" + str(ayarlar["model"])))
    topluca_analiz(hedefler, ayarlar, KOK / "ogretme", KOK / "sonuclar", zaman, gunluk=lambda m: print("  ·", m))
    for site in sorted({site_adi(h["url"]) for h in hedefler}):
        print("Sonuç klasörü:", KOK / "sonuclar" / site / zaman)
    return 0


if __name__ == "__main__":
    sys.exit(main())
