#!/usr/bin/env python3
"""Analiz aracinin tarama ciktisini sorunlar.json ile karsilastirir.

Kullanim (sunucu calisirken):
    py test_sitesi_degerlendirme/degerlendir.py --sonuc sonuclar/127.0.0.1/sonuc_<tarih_saat>
    py test_sitesi_degerlendirme/degerlendir.py --once <klasor> [--sonra <klasor>]

--sonuc yonetici modu klasorunu bekler: once taramasi klasorun kendisinde, sonra taramasi sonra/
(onayli asama) ya da yoksa sonra_otomatik/ (otomatik asama) alt klasorunde, uygulanan degisiklikler
degisiklikler.json'dadir. Klasorde bulgu_durumlari.json varsa aracin "Çözüldü" durumlari canli sitedeki
kontrollerle karsilastirilir (tutarlilik).

Her sorun icin:
  tespit edildi mi  -> once taramasinda sorunun 'tespit' kodlarindan biri ilgili adreste var mi
  duzeltildi mi     -> sorunun kontrolleri canli sitede (su anki halinde) artik dogru degil mi
  arac sonrasi      -> sonra taramasinda tespit kodu kalmis mi
Ayrica: sonra taramasinda yeni cikan bulgular ve sorunlar.json disinda kalan (plansiz) bulgular.
Sonuc degerlendirme.json ve degerlendirme.md olarak --sonuc klasorune (ya da --cikti) yazilir.
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

from kontroller import onbellegi_temizle, sorun_var_mi
from ortak import sorunlari_oku

ZORLUKLAR = ("kolay", "orta", "zor")


def yol(adres):
    p = urlsplit(adres or "")
    return (p.path or "/") + ("?" + p.query if p.query else "")


def bulgular(klasor, degisiklikler=None):
    """{(kod, yol)} — sayfa kayitlarinin sorunlari, robots nedeniyle atlanan sayfalar,
    tarama geneli bulgular ve (varsa) yonetici modunun dosya duzeyindeki ek bulgulari."""
    klasor = Path(klasor)
    kume = set()
    for k in json.loads((klasor / "rapor.json").read_text(encoding="utf-8")):
        y = yol(k.get("ad"))
        if k.get("atlandi") and "robots" in k["atlandi"]:
            kume.add(("ATLANDI_ROBOTS", y))
        for s in k.get("sorunlar") or []:
            kume.add((s["sorun"], y))
    geneli = klasor / "site_geneli.json"
    if geneli.exists():
        for g in json.loads(geneli.read_text(encoding="utf-8")):
            for a in g.get("sayfalar") or []:
                kume.add((g["sorun"], yol(a)))
    for b in (degisiklikler or {}).get("ek_bulgular") or []:
        kume.add((b["sorun"], yol(b["url"])))
    return kume


def eslesir(cift, desenler):
    kod, y = cift
    return any((dk in ("*", kod)) and (dy in ("*", y)) for dk, dy in desenler)


def oran(pay, payda):
    return f"{pay}/{payda} (%{round(100 * pay / payda)})" if payda else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sonuc", help="yönetici modu sonuç klasörü")
    ap.add_argument("--once")
    ap.add_argument("--sonra")
    ap.add_argument("--cikti", help="raporların yazılacağı klasör")
    args = ap.parse_args()
    if args.sonuc:
        once_k = Path(args.sonuc)
        sonra_k = Path(args.sonra) if args.sonra else next(
            (once_k / alt for alt in ("sonra", "sonra_otomatik") if (once_k / alt / "rapor.json").exists()), None)
    elif args.once:
        once_k, sonra_k = Path(args.once), Path(args.sonra) if args.sonra else None
    else:
        ap.error("--sonuc ya da --once gerekli")
    cikti = Path(args.cikti) if args.cikti else once_k
    deg_yolu = once_k / "degisiklikler.json"
    degisiklikler = json.loads(deg_yolu.read_text(encoding="utf-8")) if deg_yolu.exists() else None

    veri = sorunlari_oku()
    ortam = set(veri.get("ortam_bulgulari") or [])
    once = bulgular(once_k, degisiklikler)
    sonra = bulgular(sonra_k) if sonra_k else None

    durum_yolu = once_k / "bulgu_durumlari.json"
    arac_durumlari = json.loads(durum_yolu.read_text(encoding="utf-8")) if durum_yolu.exists() else None

    onbellegi_temizle()
    satirlar = []
    for s in veri["sorunlar"]:
        tespit = any(eslesir(c, s["tespit"]) for c in once) if s["tespit"] else False
        hala_var, _ = sorun_var_mi(s)
        arac_sonra = (any(eslesir(c, s["tespit"]) for c in sonra) if s["tespit"] else None) if sonra is not None else None
        ilgili = []
        for d in (degisiklikler or {}).get("degisiklikler") or []:
            if eslesir((d.get("bulgu"), yol(d.get("url"))), s["tespit"]):
                ilgili.append({"id": d["id"], "kategori": d["kategori"], "durum": d.get("durum", "önerildi"),
                               "neden": d.get("durum_nedeni", "")})
        # aracin bu sorunla eslesen bulgularina verdigi durumlar (yeniden taramaya dayali)
        arac = [b["durum"] for b in (arac_durumlari or {}).get("bulgular") or []
                if eslesir((b["sorun"], yol(b["url"])), s["tespit"])] if s["tespit"] else []
        satirlar.append({"id": s["id"], "baslik": s["baslik"], "zorluk": s["zorluk"], "kategori": s["kategori"],
                         "beklenen_cozum": s["beklenen_cozum"], "tespit_edildi": tespit,
                         "tespit_edilebilir": bool(s["tespit"]), "duzeltildi": not hala_var,
                         "arac_sonra_buluyor": arac_sonra, "degisiklikler": ilgili, "arac_durumlari": arac,
                         "arac_cozuldu": bool(arac) and all(d.startswith("cozuldu") for d in arac)})

    # tablolar
    def ozet(anahtar, degerler):
        tablo = []
        for d in degerler:
            grup = [r for r in satirlar if r[anahtar] == d]
            if grup:
                tablo.append({"grup": d, "toplam": len(grup), "tespit": sum(r["tespit_edildi"] for r in grup),
                              "duzeltildi": sum(r["duzeltildi"] for r in grup)})
        return tablo
    tablolar = {
        "zorluk": ozet("zorluk", ZORLUKLAR),
        "beklenen_cozum": ozet("beklenen_cozum", ("kural", "yz", "elle")),
        "kategori": ozet("kategori", sorted({r["kategori"] for r in satirlar})),
    }
    beklenen = [desen for s in veri["sorunlar"] for desen in s["tespit"] + s["yan"]]
    plansiz = sorted(c for c in once if c[0] not in ortam and not eslesir(c, beklenen))
    yeni = sorted(c for c in (sonra or set()) - once if c[0] not in ortam) if sonra is not None else []

    # tutarlilik: arac "Çözüldü" dedi ama canli kontrol sorunu hala buluyor (yanlis cozuldu) ya da
    # canli kontrolde duzelmis ama arac cozuldu demiyor (eksik cozuldu)
    tutarlilik = None
    if arac_durumlari is not None:
        yanlis = [r["id"] for r in satirlar if r["arac_cozuldu"] and not r["duzeltildi"]]
        eksik = [{"id": r["id"], "durumlar": sorted(set(r["arac_durumlari"]))} for r in satirlar
                 if r["duzeltildi"] and r["arac_durumlari"] and not r["arac_cozuldu"]]
        tutarlilik = {"arac_cozuldu": sum(r["arac_cozuldu"] for r in satirlar),
                      "arac_cozuldu_ve_duzeldi": sum(r["arac_cozuldu"] and r["duzeltildi"] for r in satirlar),
                      "yanlis_cozuldu": yanlis, "eksik_cozuldu": eksik, "geri_alindi": arac_durumlari.get("geri_alindi")}
    sonuc = {"once": str(once_k), "sonra": str(sonra_k) if sonra_k else None, "sorunlar": satirlar,
             "tablolar": tablolar, "plansiz_bulgular": plansiz, "yeni_bulgular": yeni, "tutarlilik": tutarlilik,
             "toplam": {"sorun": len(satirlar), "tespit": sum(r["tespit_edildi"] for r in satirlar),
                        "duzeltildi": sum(r["duzeltildi"] for r in satirlar)}}
    cikti.mkdir(parents=True, exist_ok=True)
    (cikti / "degerlendirme.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# Test sitesi değerlendirmesi", "",
          f"- Önce taraması: `{once_k}`", f"- Sonra taraması: `{sonra_k or '—'}`", "",
          f"**Toplam:** {len(satirlar)} sorun · tespit {oran(sonuc['toplam']['tespit'], len(satirlar))} · "
          f"düzeltildi {oran(sonuc['toplam']['duzeltildi'], len(satirlar))}", ""]
    for baslik, anahtar in (("Zorluğa göre", "zorluk"), ("Beklenen çözüm kategorisine göre", "beklenen_cozum"),
                            ("SEO alanına göre", "kategori")):
        md += [f"## {baslik}", "", "| Grup | Sorun | Tespit | Düzeltildi |", "|---|---|---|---|"]
        md += [f"| {t['grup']} | {t['toplam']} | {oran(t['tespit'], t['toplam'])} | {oran(t['duzeltildi'], t['toplam'])} |"
               for t in tablolar[anahtar]]
        md.append("")
    md += ["## Sorun bazında", "", "| ID | Zorluk | Beklenen | Sorun | Tespit | Düzeldi | Araç sonra | İlgili değişiklikler |",
           "|---|---|---|---|---|---|---|---|"]
    for r in satirlar:
        tespit = "✓" if r["tespit_edildi"] else ("✗" if r["tespit_edilebilir"] else "— (araçta denetim yok)")
        sonra_m = {True: "hâlâ buluyor", False: "bulmuyor", None: "—"}[r["arac_sonra_buluyor"]]
        degs = ", ".join(f"{d['id']}:{d['durum']}" for d in r["degisiklikler"]) or "—"
        md.append(f"| {r['id']} | {r['zorluk']} | {r['beklenen_cozum']} | {r['baslik']} | {tespit} | "
                  f"{'✓' if r['duzeltildi'] else '✗'} | {sonra_m} | {degs} |")
    md += ["", f"## Düzeltme sonrası yeni çıkan bulgular ({len(yeni)})", ""]
    md += [f"- `{k}` — {y}" for k, y in yeni] or ["- yok"]
    if tutarlilik is not None:
        md += ["", "## Aracın \"Çözüldü\" durumlarıyla tutarlılık", "",
               f"Araç {tutarlilik['arac_cozuldu']} sorunu (eşleşen tüm bulguları) çözüldü olarak işaretledi; "
               f"bunların {tutarlilik['arac_cozuldu_ve_duzeldi']} tanesi canlı kontrolde de düzelmiş.", ""]
        md += [f"- **Yanlış \"Çözüldü\"** (araç çözüldü diyor, canlı kontrol hâlâ buluyor): "
               + (", ".join(tutarlilik["yanlis_cozuldu"]) or "yok")]
        md += ["- Eksik \"Çözüldü\" (canlı kontrolde düzelmiş, araç çözüldü demiyor): "
               + (", ".join(f"{e['id']} ({'/'.join(e['durumlar'])})" for e in tutarlilik["eksik_cozuldu"]) or "yok")]
        if tutarlilik["geri_alindi"]:
            md.append("- Not: uygulama geri alındı; durumlar başlangıç halindedir.")
    md += ["", f"## sorunlar.json dışında kalan bulgular (önce taraması, {len(plansiz)})", ""]
    md += [f"- `{k}` — {y}" for k, y in plansiz] or ["- yok"]
    (cikti / "degerlendirme.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("\n".join(md[:6 + sum(len(t) + 5 for t in tablolar.values())]))
    print(f"Yeni çıkan bulgu: {len(yeni)} · Plansız bulgu: {len(plansiz)}")
    if tutarlilik is not None:
        print(f"Tutarlılık: araç çözüldü {tutarlilik['arac_cozuldu']} · yanlış çözüldü "
              f"{', '.join(tutarlilik['yanlis_cozuldu']) or 'yok'} · eksik çözüldü "
              f"{', '.join(e['id'] for e in tutarlilik['eksik_cozuldu']) or 'yok'}")
    print("Rapor:", cikti / "degerlendirme.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
