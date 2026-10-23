"""Yonetici modu (Mod 1): admin erisimi olan siteyi tara -> oneri plani -> onizleme -> onay ->
yedekle + uygula + gunluk -> tekrar tara -> once/sonra raporu; tek komutla son uygulamayi geri al.

Standart mod (Mod 2) bu modulu kullanmaz; analiz akisi (boru.topluca_analiz) iki modda aynidir.
Yazma yalnizca hedef_dogrula'dan gecen, acikca yapilandirilmis site kokune ve yalnizca onaylanan
degisiklikler icin yapilir.

Bir yonetici calismasinin klasoru (sonuclar/<site>/sonuc_<tarih_saat>/):
  rapor.json, site_geneli.json, ...   once taramasi (standart modla ayni ciktilar)
  degisiklikler.json                  plan: yapilandirilmis degisiklikler, elle yapilacaklar, atlananlar
  onizleme.diff                       kategoriye gore gruplu onizleme
  onaylar.json                        kullanicinin kararlari
  yedek/                              uygulama oncesi sitenin tam yedegi (+ manifest.json)
  uygulama_gunlugu.jsonl              her degisikligin sonucu
  uygulanan.diff, uygulama.json       uygulanan degisikliklerin dosya diff'leri ve ozeti
  sonra/                              uygulama sonrasi otomatik tekrar taramasi
  yonetici_raporu.json / .html        once/sonra raporu
"""
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import duzeltme
from . import kategoriler as kat
from .boru import site_adi, topluca_analiz, zaman_damgasi
from .kurallar import CIDDIYET_AGIRLIK
from .yazma import YerelDosyaAdaptoru, YolGuvenligiHatasi
from .yz_oneri import YZIstemcisi

PROJE_KOK = Path(__file__).resolve().parent.parent
PUAN_ANAHTARLARI = ("sayfa", "site", "icerik", "teknik", "guvenlik", "performans")
_ortam = Environment(loader=FileSystemLoader(str(Path(__file__).resolve().parent / "sablonlar")),
                     autoescape=select_autoescape(["html"]))


class YoneticiHatasi(ValueError):
    """Kullaniciya oldugu gibi gosterilen yapilandirma/akis hatasi."""


def _json_oku(yol):
    return json.loads(Path(yol).read_text(encoding="utf-8"))


def _json_yaz(yol, veri):
    Path(yol).write_text(json.dumps(veri, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def hedef_dogrula(kok, temel_url, sonuc_kok=None):
    """Yonetici modunun yazacagi hedefi denetler; (adaptor, temel_url) dondurur.
    Kok var olmali; aracin kendi klasorunu ya da sonuc klasorunu kapsayamaz; temel adres http(s) olmali."""
    if not kok or not str(kok).strip():
        raise YoneticiHatasi("Yönetici modu için site kök klasörü belirtilmeli.")
    p = urlsplit((temel_url or "").strip())
    if p.scheme not in ("http", "https") or not p.netloc:
        raise YoneticiHatasi("Temel adres http:// ya da https:// ile başlayan tam bir adres olmalı.")
    kok_yolu = Path(str(kok).strip())
    if not kok_yolu.is_absolute():
        kok_yolu = PROJE_KOK / kok_yolu
    if not kok_yolu.is_dir():
        raise YoneticiHatasi("Site kök klasörü bulunamadı: " + str(kok_yolu))
    cozulmus = kok_yolu.resolve()
    sonuc = Path(sonuc_kok or PROJE_KOK / "sonuclar").resolve()
    for k in (PROJE_KOK, sonuc):                     # kok bunlari kapsarsa aracin kodu ya da yedekler yazilabilir
        if cozulmus == k or cozulmus in k.parents:
            raise YoneticiHatasi("Site kökü aracın kendi klasörünü ya da sonuç klasörünü kapsayamaz: " + str(cozulmus))
    if sonuc in cozulmus.parents:
        raise YoneticiHatasi("Site kökü sonuç klasörünün içinde olamaz.")
    for korunan_alt in (PROJE_KOK / "seo_app", PROJE_KOK / "ogretme", PROJE_KOK / "tests"):
        if cozulmus == korunan_alt.resolve() or korunan_alt.resolve() in cozulmus.parents:
            raise YoneticiHatasi("Site kökü aracın kod ya da veri klasörlerinden biri olamaz.")
    try:
        adaptor = YerelDosyaAdaptoru(cozulmus)
    except (FileNotFoundError, YolGuvenligiHatasi) as e:
        raise YoneticiHatasi(str(e)) from e
    taban = p.scheme + "://" + p.netloc + (p.path if p.path.endswith("/") else (p.path or "") + "/")
    return adaptor, taban


def adresleri_denetle(hedefler, temel_url):
    """Yonetici modunda taranacak adresler temel adresin altinda olmali."""
    disarida = [h["url"] for h in hedefler if duzeltme._goreli(h["url"], temel_url) is None]
    if disarida:
        raise YoneticiHatasi("Yönetici modunda yalnızca temel adresin altındaki sayfalar taranabilir: " +
                             ", ".join(disarida[:3]))


def yz_istemcisi(ayarlar, ogretme_klasoru):
    if not ayarlar.get("model"):
        return None
    return YZIstemcisi(ayarlar["url"], ayarlar["model"], ogretme_klasoru, embed_model=ayarlar.get("embed_model"),
                       embed_url=ayarlar.get("embed_url") or ayarlar["url"], max_tokens=ayarlar.get("max_tokens", 4000),
                       timeout=ayarlar.get("timeout", 600), bilgi_k=ayarlar.get("bilgi_sayisi", 4))


def _site_klasoru(hedefler, sonuc_kok):
    return Path(sonuc_kok) / site_adi(hedefler[0]["url"])


def tara_ve_planla(hedefler, kok, temel_url, ayarlar, ogretme_klasoru, sonuc_kok, gunluk=None, zaman=None,
                   tarama_kancalari=None):
    """Once taramasi + degisiklik plani. Siteye yazmaz. (klasor, plan) dondurur."""
    yaz = gunluk or (lambda m: None)
    adaptor, temel_url = hedef_dogrula(kok, temel_url, sonuc_kok)
    adresleri_denetle(hedefler, temel_url)
    zaman = zaman or zaman_damgasi()
    # analiz standart modla aynidir; YZ onerileri plan asamasinda uretilir (taramada model cagrilmaz)
    tarama_ayarlari = {**ayarlar, "yalnizca_denetim": True, "model": None}
    rapor = topluca_analiz(hedefler, tarama_ayarlari, ogretme_klasoru, sonuc_kok, alt_yol=zaman, gunluk=yaz,
                           **(tarama_kancalari or {}))
    klasor = _site_klasoru(hedefler, sonuc_kok) / zaman
    bulgular = _json_oku(klasor / "site_geneli.json") if (klasor / "site_geneli.json").exists() else []
    yaz("Değişiklik planı hazırlanıyor (siteye henüz hiçbir şey yazılmıyor)")
    plan = duzeltme.plan_uret(rapor, bulgular, adaptor, temel_url, ayarlar.get("dil", "tr"),
                              yz_istemcisi(ayarlar, ogretme_klasoru), gunluk=yaz, esik=ayarlar.get("oto_esik"))
    plan["tarama"] = {"hedefler": hedefler, "ayarlar": {k: v for k, v in tarama_ayarlari.items() if k != "model"},
                      "ogretme_klasoru": str(ogretme_klasoru), "zaman": zaman}
    _json_yaz(klasor / "degisiklikler.json", plan)
    (klasor / "onizleme.diff").write_text(duzeltme.onizleme_diff(plan, lambda d: adaptor.oku(d).decode("utf-8")),
                                         encoding="utf-8")
    o = plan_ozeti(plan)
    yaz(f"Plan hazır: {o['sayilar']['kural']} kural, {o['sayilar']['yz']} YZ önerisi "
        f"({o['sayilar']['yuksek_risk']} yüksek risk), {len(plan['elle'])} elle yapılacak iş. "
        f"{o['sayilar']['otomatik']} değişiklik güven eşiğini ({plan['esik']:.2f}) geçti ve otomatik onaylı; "
        f"{o['sayilar']['onay_gerekli']} değişiklik onay bekliyor.")
    return klasor, plan


def plan_ozeti(plan, oku=None):
    """Arayuz/CLI icin gruplu ozet. oku verilirse her degisikligin diff'i de eklenir."""
    gruplar = {"kural": [], "yz": []}
    for d in plan["degisiklikler"]:
        oge = {k: d.get(k) for k in ("id", "kategori", "risk", "bulgu", "bulgu_aciklamasi", "url", "dosya", "konum",
                                     "eski", "yeni", "gerekce", "kaynaklar", "uretici", "etki", "yer_tutucu",
                                     "dogrulama", "durum", "durum_nedeni", "onay_turu", "guven", "guven_nedenleri",
                                     "zorunlu_onay", "deneme")}
        oge["duzenlenebilir"] = bool(d.get("duzenleme")) and d["kategori"] == "yz"
        if oku:
            oge["diff"] = duzeltme.degisiklik_diff(d, oku(d["dosya"]))
        gruplar[d["kategori"]].append(oge)
    yz = gruplar["yz"]
    return {"gruplar": gruplar, "elle": plan["elle"], "atlanan": plan["atlanan"],
            "sayilar": {"kural": len(gruplar["kural"]), "yz": len(yz),
                        "yuksek_risk": sum(1 for d in yz if d["risk"] == "yuksek"),
                        "gecersiz": sum(1 for d in plan["degisiklikler"] if d["durum"] == "gecersiz"),
                        "yer_tutucu": sum(1 for d in plan["degisiklikler"] if d["yer_tutucu"]),
                        "otomatik": sum(1 for d in plan["degisiklikler"] if d.get("onay_turu") == "otomatik"),
                        "onay_gerekli": sum(1 for d in plan["degisiklikler"]
                                            if d.get("onay_turu") != "otomatik" and d["durum"] != "gecersiz")},
            "hedef": plan["hedef"], "model": plan.get("model"), "esik": plan.get("esik")}


def kararlari_kaydet(klasor, kararlar):
    _json_yaz(Path(klasor) / "onaylar.json", kararlar)


def _son_uygulama_yolu(site_klasoru):
    return Path(site_klasoru) / "son_uygulama.json"


def uygula_ve_dogrula(klasor, kararlar, sonuc_kok, gunluk=None, tekrar_tara=True, tarama_kancalari=None):
    """Onaylanan degisiklikleri yedek alarak uygular, gunluge yazar, siteyi tekrar tarar ve rapor uretir."""
    yaz = gunluk or (lambda m: None)
    klasor = Path(klasor)
    plan = _json_oku(klasor / "degisiklikler.json")
    if (klasor / "uygulama.json").exists():
        raise YoneticiHatasi("Bu plan zaten uygulandı. Yeni değişiklikler için siteyi yeniden tarayın.")
    hedef = plan["hedef"]
    adaptor, temel_url = hedef_dogrula(hedef["adaptor"]["kok"], hedef["temel_url"], sonuc_kok)
    kararlari_kaydet(klasor, kararlar)
    yedek = klasor / "yedek"
    yaz("Sitenin tam yedeği alınıyor: " + str(yedek))
    ozet = duzeltme.uygula(plan, kararlar, adaptor, yedek, klasor / "uygulama_gunlugu.jsonl")
    _json_yaz(klasor / "degisiklikler.json", plan)
    (klasor / "uygulanan.diff").write_text("".join(v["diff"] for v in ozet["dosyalar"].values()), encoding="utf-8")
    ozet_kayit = {"zaman": time.strftime("%Y-%m-%d %H:%M:%S"), "yedek": ozet["yedek"], "uygulanan": ozet["uygulanan"],
                  "dosyalar": {d: {k: v[k] for k in ("once", "sonra")} for d, v in ozet["dosyalar"].items()},
                  "durumlar": _durum_sayilari(plan), "esik": duzeltme.onay_esigi(plan, kararlar),
                  "onay_kaynaklari": {kaynak: sum(1 for d in plan["degisiklikler"] if d["durum"] == "uygulandi"
                                                  and d.get("onay_kaynagi") == kaynak)
                                      for kaynak in ("otomatik", "kullanıcı", "toplu")}}
    _json_yaz(klasor / "uygulama.json", ozet_kayit)
    yaz(f"{ozet['uygulanan']} değişiklik uygulandı ({len(ozet['dosyalar'])} dosya).")
    if ozet["yedek"]:
        _json_yaz(_son_uygulama_yolu(klasor.parent), {
            "sonuc": str(klasor), "yedek": ozet["yedek"], "adaptor": adaptor.tanim(), "temel_url": temel_url,
            "zaman": ozet_kayit["zaman"], "durum": "uygulandi"})
    if tekrar_tara:
        tarama = plan["tarama"]
        yaz("Uygulama sonrası site yeniden taranıyor")
        topluca_analiz(tarama["hedefler"], tarama["ayarlar"], tarama["ogretme_klasoru"], sonuc_kok,
                       alt_yol=tarama["zaman"] + "/sonra", gunluk=yaz, **(tarama_kancalari or {}))
    rapor = yonetici_raporu(klasor)
    yaz("Yönetici raporu: " + str(klasor / "yonetici_raporu.html"))
    return rapor


def _durum_sayilari(plan):
    sayac = {}
    for d in plan["degisiklikler"]:
        anahtar = d["kategori"] + ":" + d["durum"]
        sayac[anahtar] = sayac.get(anahtar, 0) + 1
    return sayac


def geri_al(site_klasoru, gunluk=None):
    """Son uygulamayi yedekten geri alir ve dosya hash'leriyle dogrular."""
    yaz = gunluk or (lambda m: None)
    isaret = _son_uygulama_yolu(site_klasoru)
    if not isaret.exists():
        raise YoneticiHatasi("Geri alınacak bir uygulama bulunamadı: " + str(isaret))
    bilgi = _json_oku(isaret)
    if bilgi.get("durum") == "geri_alindi":
        raise YoneticiHatasi("Son uygulama zaten geri alındı (" + bilgi.get("geri_alma_zamani", "") + ").")
    adaptor, _ = hedef_dogrula(bilgi["adaptor"]["kok"], bilgi["temel_url"], Path(site_klasoru).parent)
    yaz("Son uygulama geri alınıyor: " + bilgi["sonuc"])
    sonuc = adaptor.geri_al(bilgi["yedek"])
    bilgi.update({"durum": "geri_alindi", "geri_alma_zamani": time.strftime("%Y-%m-%d %H:%M:%S"), "geri_alma": sonuc})
    _json_yaz(isaret, bilgi)
    with (Path(bilgi["sonuc"]) / "uygulama_gunlugu.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"zaman": bilgi["geri_alma_zamani"], "olay": "geri_alma", **sonuc}, ensure_ascii=False) + "\n")
    yaz("Geri alma " + ("tamam: tüm dosyaların hash'i yedekle eşleşiyor" if sonuc["eslesiyor"] else "UYUMSUZ") +
        f" ({sonuc['geri_yazilan']} dosya geri yazıldı, {len(sonuc['silinen'])} dosya silindi)")
    return sonuc


# ------------------------------------------------------------------ rapor
def _ortalama_puanlar(kayitlar):
    gecerli = [k for k in kayitlar if not (k.get("hata") or k.get("atlandi")) and k.get("once_puanlar")]
    sonuc = {}
    for a in PUAN_ANAHTARLARI:
        degerler = [k["once_puanlar"].get(a) for k in gecerli if k["once_puanlar"].get(a) is not None]
        sonuc[a] = round(sum(degerler) / len(degerler)) if degerler else None
    sonuc["sayfa_sayisi"] = len(gecerli)
    return sonuc


def _bulgu_kumesi(klasor):
    kume = set()
    for k in _json_oku(klasor / "rapor.json"):
        for s in k.get("sorunlar") or []:
            kume.add((s["sorun"], k.get("ad")))
    if (klasor / "site_geneli.json").exists():
        for g in _json_oku(klasor / "site_geneli.json"):
            for a in g.get("sayfalar") or []:
                kume.add((g["sorun"], a))
    return kume


def yonetici_raporu(klasor):
    klasor = Path(klasor)
    plan = _json_oku(klasor / "degisiklikler.json")
    once_k = _json_oku(klasor / "rapor.json")
    sonra_var = (klasor / "sonra" / "rapor.json").exists()
    sonra_k = _json_oku(klasor / "sonra" / "rapor.json") if sonra_var else []
    once_p, sonra_p = _ortalama_puanlar(once_k), (_ortalama_puanlar(sonra_k) if sonra_var else None)
    yeni = sorted(_bulgu_kumesi(klasor / "sonra") - _bulgu_kumesi(klasor)) if sonra_var else []
    giderilen = sorted(_bulgu_kumesi(klasor) - _bulgu_kumesi(klasor / "sonra")) if sonra_var else []
    durumlar = {}
    for d in plan["degisiklikler"]:
        durumlar.setdefault(d["kategori"], {}).setdefault(d["durum"], []).append(
            {k: d.get(k) for k in ("id", "bulgu", "bulgu_aciklamasi", "url", "dosya", "eski", "yeni", "gerekce", "risk",
                                   "etki", "durum_nedeni", "uretici", "kaynaklar", "yer_tutucu", "guven",
                                   "guven_nedenleri", "zorunlu_onay", "onay_kaynagi")})
    uygulama = _json_oku(klasor / "uygulama.json") if (klasor / "uygulama.json").exists() else None
    rapor = {"klasor": str(klasor), "hedef": plan["hedef"], "model": plan.get("model"), "zaman": time.strftime("%Y-%m-%d %H:%M:%S"),
             "puanlar": {"once": once_p, "sonra": sonra_p}, "durumlar": durumlar, "elle": plan["elle"],
             "atlanan": plan["atlanan"], "yeni_bulgular": [{"sorun": k, "aciklama": kat.aciklama(k), "url": u,
                                                             "kategori": kat.kategori(k)} for k, u in yeni],
             "giderilen_bulgu_sayisi": len(giderilen), "uygulama": uygulama}
    _json_yaz(klasor / "yonetici_raporu.json", rapor)
    (klasor / "yonetici_raporu.html").write_text(_ortam.get_template("yonetici_rapor.html").render(
        r=rapor, KATEGORI_ADI=kat.KATEGORI_ADI, PUAN_ANAHTARLARI=PUAN_ANAHTARLARI,
        DURUM_ADI=DURUM_ADI, CIDDIYET_AGIRLIK=CIDDIYET_AGIRLIK), encoding="utf-8")
    return rapor


DURUM_ADI = {"uygulandi": "Uygulandı", "reddedildi": "Reddedildi", "basarisiz": "Başarısız",
             "onay_bekliyor": "Onay verilmedi", "gecersiz": "Doğrulamadan geçmedi", "oneriliyor": "Önerildi"}
