#!/usr/bin/env python3
"""Yonetici modu (Mod 1) komut satiri: admin erisimi olan siteyi tara, onerileri onayla, uygula, geri al.

Akis (uc asama: baslangic -> otomatik duzeltmeler -> onayli duzeltmeler):
    py yonet.py tara --kok test_sitesi/site --url http://127.0.0.1:8080/ [--model qwen/qwen3.5-9b]
        # plan + otomatik asama: guven esigini gecenler yedek alinarak hemen yazilir, site yeniden taranir
    py yonet.py onizle sonuclar/127.0.0.1/sonuc_<tarih_saat> [--diff]
    py yonet.py onayla <klasor> --kural-hepsi --onay D012 D015 --riski-kabul D015 --ret D020 \
                                --duzenle "D013=Yeni başlık metni | Çaylıbahçe"
    py yonet.py uygula <klasor>            # onayli asama: onaylananlar yazilir, site yeniden taranir, rapor
    py yonet.py geri-al sonuclar/127.0.0.1 [--tekrar-tara]   # tum asamalari geri al (hash dogrulamali)

Onay kurallari: her degisikligin bir guven puani vardir (seo_app/guven.py). Esigi (--esik, varsayilan
0.8) gecenler tarama sonunda onay beklemeden uygulanir (--oto-uygulama-yok ile kapatilir); onay ekraninda
--ret ile reddedilirlerse onayli asamada geri cekilirler. Esigin altindakiler ve her zaman onay isteyenler
([doğrulanmalı] yer tutucusu, canonical ile birlestirme, indekslemeyi kapatan yonergeler) kimlikleriyle
--onay ister; yuksek riskli olanlar ayrica --riski-kabul ister. "Kural çözer" grubu --kural-hepsi ile
toplu onaylanabilir; her zaman onay isteyenler bu toplu onaya girmez. Onay verilmeyen (otomatik ya da elle) hicbir degisiklik siteye yazilmaz.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seo_app import kategoriler as kat
from seo_app import yonetici
from seo_app.boru import VARSAYILAN_AYARLAR
from seo_app.llm import ModelHatasi, modelleri_dogrula

KOK = Path(__file__).resolve().parent
SONUC_KOK = KOK / "sonuclar"


def _gunluk(mesaj):
    if not str(mesaj).startswith(("[", "İndiriliyor", "Bağlantılar ve", "Yalnızca denetim")):
        print("  ·", mesaj)


def komut_tara(a):
    ayarlar = {**VARSAYILAN_AYARLAR, "tarama_modu": "site", "en_fazla_sayfa": a.sayfa, "en_fazla_derinlik": a.derinlik,
               "bekleme_sn": a.bekleme, "dil": a.dil, "model": a.model, "embed_model": a.embed_model}
    if a.esik is not None:
        ayarlar["oto_esik"] = a.esik
    ayarlar["oto_uygula"] = not a.oto_uygulama_yok
    if a.lm_url:
        ayarlar["url"] = a.lm_url
    if a.model:
        try:
            modelleri_dogrula(ayarlar["url"], [a.model, a.embed_model])
        except ModelHatasi as e:
            print("HATA:", e)
            return 2
    else:
        print("Not: --model verilmedi; YZ önerilerinden yalnızca model gerektirmeyenler (sezgisel) üretilir.")
    hedefler = [{"url": u} for u in (a.adres or [a.url])]
    klasor, plan = yonetici.tara_ve_planla(hedefler, a.kok, a.url, ayarlar, KOK / "ogretme", SONUC_KOK, gunluk=_gunluk)
    print("\nSonuç klasörü:", klasor)
    _ozet_yaz(plan)
    print("\nÖnizleme:", klasor / "onizleme.diff")
    if (klasor / "yonetici_raporu.json").exists():
        _asama_ozeti_yaz(json.loads((klasor / "yonetici_raporu.json").read_text(encoding="utf-8")))
    print("\nSonraki adım: py yonet.py onayla", _goreli(klasor), "--onay <ID ...> [--riski-kabul <ID ...>] [--ret <ID ...>]")
    print("        sonra: py yonet.py uygula", _goreli(klasor), " (onaylı aşama)")
    return 0


def _goreli(p):
    try:
        return Path(p).resolve().relative_to(KOK)
    except ValueError:
        return p


def _ozet_yaz(plan, ayrinti=True):
    o = yonetici.plan_ozeti(plan)
    s = o["sayilar"]
    print(f"\nPlan: {s['kural']} Kural çözer · {s['yz']} YZ önerir ({s['yuksek_risk']} yüksek risk) · "
          f"{len(o['elle'])} Elle düzeltilir · {s['gecersiz']} doğrulamadan geçmeyen · {s['yer_tutucu']} yer tutuculu")
    if o.get("esik") is not None:
        print(f"Güven eşiği {o['esik']:.2f}: {s['otomatik']} değişiklik otomatik onaylı, {s['onay_gerekli']} onay bekliyor")
    if not ayrinti:
        return
    for kategori in ("kural", "yz"):
        print(f"\n== {kat.KATEGORI_ADI[kategori]} ==")
        for d in o["gruplar"][kategori]:
            isaret = []
            if d.get("guven") is not None:
                isaret.append(f"güven {d['guven']:.2f} " + ("OTOMATİK" if d.get("onay_turu") == "otomatik" else "ONAY"))
            if d.get("zorunlu_onay"):
                isaret.append("HER ZAMAN ONAY: " + d["zorunlu_onay"])
            elif d.get("onay_turu") != "otomatik" and d.get("guven_nedenleri"):
                isaret.append("; ".join(d["guven_nedenleri"]))
            if d["risk"] == "yuksek":
                isaret.append("YÜKSEK RİSK")
            if d["durum"] == "gecersiz":
                isaret.append("UYGULANAMAZ: " + d["dogrulama"]["neden"])
            if d["yer_tutucu"]:
                isaret.append("YER TUTUCU")
            if d.get("durum") not in ("oneriliyor", "gecersiz"):
                isaret.append(d["durum"] + (": " + d["durum_nedeni"] if d.get("durum_nedeni") else ""))
            yeni = " ".join(str(d["yeni"]).split())
            print(f"  {d['id']} {d['bulgu']:<28} {d['dosya']:<36} → {yeni[:70]}" +
                  (f"  [{'; '.join(isaret)}]" if isaret else ""))
            if d["risk"] == "yuksek" and d.get("etki"):
                print(f"       Olası etki: {d['etki']}")
    print(f"\n== {kat.KATEGORI_ADI['elle']} ==")
    for e in o["elle"]:
        print(f"  {e['bulgu_aciklamasi']} ({len(e['sayfalar'])} sayfa): {e['duzeltme']}")
    if o["atlanan"]:
        print(f"\n== Otomatik öneri üretilemeyenler ({len(o['atlanan'])}) ==")
        for x in o["atlanan"][:40]:
            print(f"  {x['bulgu']:<26} {x['url']}: {x['neden']}")


def _plan(klasor):
    yol = Path(klasor) / "degisiklikler.json"
    if not yol.exists():
        raise yonetici.YoneticiHatasi("Plan bulunamadı: " + str(yol))
    return json.loads(yol.read_text(encoding="utf-8"))


def komut_onizle(a):
    plan = _plan(a.klasor)
    _ozet_yaz(plan)
    if a.diff:
        print((Path(a.klasor) / "onizleme.diff").read_text(encoding="utf-8"))
    return 0


def komut_onayla(a):
    plan = _plan(a.klasor)
    if plan.get("geri_alindi") or yonetici.asama_yapildi_mi(plan, "onayli"):
        raise yonetici.YoneticiHatasi("Bu planın onaylı aşaması tamamlandı ya da uygulama geri alındı; "
                                      "kararlar artık değiştirilemez.")
    yol = Path(a.klasor) / "onaylar.json"
    kararlar = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {"kural_hepsi": False, "kararlar": {}}
    ids = {d["id"]: d for d in plan["degisiklikler"]}
    tek = kararlar.setdefault("kararlar", {})
    if a.kural_hepsi:
        kararlar["kural_hepsi"] = True
    if a.esik is not None:
        kararlar["esik"] = a.esik
    for i in a.onay or []:
        if i not in ids:
            raise yonetici.YoneticiHatasi("Bilinmeyen değişiklik kimliği: " + i)
        tek.setdefault(i, {})["karar"] = "onay"
    for i in a.ret or []:
        if i not in ids:
            raise yonetici.YoneticiHatasi("Bilinmeyen değişiklik kimliği: " + i)
        tek[i] = {"karar": "ret"}
    for i in a.riski_kabul or []:
        if i not in ids:
            raise yonetici.YoneticiHatasi("Bilinmeyen değişiklik kimliği: " + i)
        tek.setdefault(i, {})["risk_onay"] = True
    for ifade in a.duzenle or []:
        i, _, deger = ifade.partition("=")
        if i not in ids or not ids[i].get("duzenleme"):
            raise yonetici.YoneticiHatasi("Düzenlenemeyen ya da bilinmeyen değişiklik: " + i)
        tek.setdefault(i, {})["deger"] = deger
    yonetici.kararlari_kaydet(a.klasor, kararlar)
    yuksek = [i for i, k in tek.items() if k.get("karar") == "onay" and ids[i]["risk"] == "yuksek" and not k.get("risk_onay")]
    print("Kararlar kaydedildi:", yol)
    print(f"  Kural çözer: {'tümü onaylı' if kararlar.get('kural_hepsi') else 'tek tek'} · onay {sum(k.get('karar') == 'onay' for k in tek.values())}"
          f" · ret {sum(k.get('karar') == 'ret' for k in tek.values())} · düzenleme {sum('deger' in k for k in tek.values())}")
    if yuksek:
        print("  UYARI: Şu yüksek riskli önerilere risk onayı verilmedi, uygulanmayacak:", ", ".join(yuksek))
        for i in yuksek:
            print(f"    {i}: {ids[i]['etki']}")
    print("Sonraki adım: py yonet.py uygula", _goreli(a.klasor))
    return 0


def komut_uygula(a):
    yol = Path(a.klasor) / "onaylar.json"
    if yol.exists():
        kararlar = json.loads(yol.read_text(encoding="utf-8"))
    else:
        print("Onay kaydı yok: onaylı aşamada yalnızca (henüz yazılmamışsa) güven eşiğini geçenler uygulanır.")
        kararlar = {"kural_hepsi": False, "kararlar": {}}
    return _uygula(a.klasor, kararlar, tekrar_tara=not a.tekrar_tarama_yok)


def _uygula(klasor, kararlar, tekrar_tara=True):
    rapor = yonetici.uygula_ve_dogrula(klasor, kararlar, SONUC_KOK, gunluk=_gunluk, tekrar_tara=tekrar_tara)
    kaynaklar = json.loads((Path(klasor) / "uygulama.json").read_text(encoding="utf-8")).get("onay_kaynaklari") or {}
    if kaynaklar:
        print("Uygulananların onayı: " + ", ".join(f"{k} {v}" for k, v in kaynaklar.items() if v))
    for kategori, gruplar in rapor["durumlar"].items():
        print(f"{kat.KATEGORI_ADI[kategori]}: " + ", ".join(f"{yonetici.DURUM_ADI.get(d, d)} {len(v)}" for d, v in gruplar.items()))
    _asama_ozeti_yaz(rapor)
    print("Yeni çıkan bulgu:", len(rapor["yeni_bulgular"]))
    print("Rapor:", Path(klasor) / "yonetici_raporu.html")
    print("Geri almak için: py yonet.py geri-al", _goreli(Path(klasor).parent))
    return 0


def _asama_ozeti_yaz(rapor):
    """Uc asamali metrik tablosu ve sorun durumlari (yonetici_raporu.json)."""
    asamalar = rapor.get("asamalar") or []
    if not asamalar:
        return
    print("\nAşamalara göre metrikler:")
    print("  " + " " * 26 + "".join(a["adi"][:27].rjust(29) for a in asamalar))

    def satir(ad, deger):
        print("  " + ad.ljust(26) + "".join((deger(a) if a["olculdu"] else "—").rjust(29) for a in asamalar))
    satir("Ortalama sayfa puanı", lambda a: str(a["puanlar"]["sayfa"]))
    satir("Aktif sorun", lambda a: str(a.get("aktif", "—")))
    satir("Çözülen (otomatik)", lambda a: str(a.get("cozuldu_otomatik", "—")))
    satir("Çözülen (onaylı)", lambda a: str(a.get("cozuldu_onayli", "—")))
    satir("Çözüm oranı", lambda a: ("%" + str(round(100 * a["cozum_orani"])) + f" ({a['cozulen']}/{a['cozulebilir']})")
          if a["cozum_orani"] is not None else "—")
    satir("Elle düzeltilir (açık)", lambda a: str(a["elle"]))
    satir("Yeni çıkan sorun", lambda a: str(a["yeni_bulgu"]))
    satir("Elle, dolaylı giderilen", lambda a: str(a["elle_dolayli_cozulen"]))
    print("  Çözüm oranı = çözülen / çözülebilir (düzeltme önerisi olan bulgular); 'Elle düzeltilir' ayrı "
          "sayılır. Çözülen yalnızca yeniden taramaya dayanır.")
    print("Sorun durumları (" + str(rapor.get("bulgu_toplam", 0)) + "): " +
          ", ".join(f"{yonetici.BULGU_DURUM_ADI[d]} {n}" for d, n in (rapor.get("bulgu_sayilari") or {}).items() if n))
    s = rapor.get("sayaclar")
    if s:
        ayrim = f" ({s['sayfa']['aktif']} sayfa sorunu + {s['site_ayari']['aktif']} site geneli ayar)" if "sayfa" in s else ""
        print(f"Aktif {s['aktif']}{ayrim} · Çözülen {s['cozulen']} (otomatik {s['cozuldu_otomatik']}, onaylı "
              f"{s['cozuldu_onayli']}) · toplam {s['toplam']}")


def komut_geri_al(a):
    hedef = Path(a.klasor)
    site_klasoru = hedef if (hedef / "son_uygulama.json").exists() else hedef.parent
    sonuc = yonetici.geri_al(site_klasoru, gunluk=_gunluk, tekrar_tara=a.tekrar_tara)
    bilgi = json.loads((Path(site_klasoru) / "son_uygulama.json").read_text(encoding="utf-8"))
    rapor_yolu = Path(bilgi["sonuc"]) / "yonetici_raporu.json"
    if rapor_yolu.exists():
        _asama_ozeti_yaz(json.loads(rapor_yolu.read_text(encoding="utf-8")))
    return 0 if sonuc["eslesiyor"] else 1


def main():
    ap = argparse.ArgumentParser(description="SEO Denetim Aracı — yönetici modu (siteye yazar)")
    alt = ap.add_subparsers(dest="komut", required=True)
    t = alt.add_parser("tara", help="siteyi tara, plan üret, güven eşiğini geçenleri uygula")
    t.add_argument("--kok", required=True, help="sitenin kök klasörü (yazma yalnızca bu klasöre yapılır)")
    t.add_argument("--url", required=True, help="sitenin temel adresi, ör. http://127.0.0.1:8080/")
    t.add_argument("--adres", nargs="*", help="taramaya başlanacak adresler (varsayılan: temel adres)")
    t.add_argument("--model", help="YZ önerileri için LM Studio sohbet modeli")
    t.add_argument("--embed-model", help="bilgi tabanı için gömme modeli (isteğe bağlı)")
    t.add_argument("--lm-url", help="LM Studio adresi (varsayılan " + VARSAYILAN_AYARLAR["url"] + ")")
    t.add_argument("--sayfa", type=int, default=60)
    t.add_argument("--derinlik", type=int, default=6)
    t.add_argument("--bekleme", type=float, default=0.0)
    t.add_argument("--dil", default="tr")
    t.add_argument("--esik", type=float, help="otomatik onay güven eşiği 0-1 (varsayılan "
                                             + str(VARSAYILAN_AYARLAR["oto_esik"]) + ")")
    t.add_argument("--oto-uygulama-yok", action="store_true",
                   help="güven eşiğini geçenleri tarama sonunda uygulama (hepsi onay ekranına kalır)")
    t.add_argument("--oto-uygula", action="store_true", help=argparse.SUPPRESS)   # eski bayrak; artik varsayilan
    o = alt.add_parser("onizle", help="planı kategorilere göre göster")
    o.add_argument("klasor")
    o.add_argument("--diff", action="store_true", help="gruplu diff'i de yazdır")
    k = alt.add_parser("onayla", help="önerileri onayla / reddet / düzenle")
    k.add_argument("klasor")
    k.add_argument("--kural-hepsi", action="store_true", help="'Kural çözer' grubunun tamamını onayla")
    k.add_argument("--onay", nargs="*", help="onaylanan öneri kimlikleri (YZ önerileri yalnızca böyle onaylanır)")
    k.add_argument("--ret", nargs="*", help="reddedilen öneri kimlikleri")
    k.add_argument("--riski-kabul", nargs="*", help="yüksek riskli önerilerin risk onayı")
    k.add_argument("--duzenle", nargs="*", help="KIMLIK=yeni değer (düzenlenebilir YZ önerileri)")
    k.add_argument("--esik", type=float, help="bu plan için otomatik onay güven eşiğini değiştir (0-1)")
    u = alt.add_parser("uygula", help="onaylı aşama: onaylananları uygula, tekrar tara, rapor üret")
    u.add_argument("klasor")
    u.add_argument("--tekrar-tarama-yok", action="store_true")
    g = alt.add_parser("geri-al", help="son uygulamayı yedekten geri al")
    g.add_argument("klasor", help="sonuclar/<site> ya da uygulamanın sonuç klasörü")
    g.add_argument("--tekrar-tara", action="store_true", help="geri almadan sonra siteyi yeniden tarayıp ölç")
    a = ap.parse_args()
    try:
        return {"tara": komut_tara, "onizle": komut_onizle, "onayla": komut_onayla, "uygula": komut_uygula,
                "geri-al": komut_geri_al}[a.komut](a)
    except yonetici.YoneticiHatasi as e:
        print("HATA:", e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
