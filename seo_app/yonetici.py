"""Yonetici modu (Mod 1): admin erisimi olan siteyi tara -> oneri plani -> otomatik asama (guven esigini
gecenler onaysiz yazilir) -> onay -> onayli asama -> her asamadan sonra tekrar tarama -> uc asamali rapor;
tek komutla tum asamalari geri al.

Standart mod (Mod 2) bu modulu kullanmaz; analiz akisi (boru.topluca_analiz) iki modda aynidir.
Yazma yalnizca hedef_dogrula'dan gecen, acikca yapilandirilmis site kokune ve yalnizca onaylanan
(otomatik ya da kullanici) degisiklikler icin yapilir.

Bir yonetici calismasinin klasoru (sonuclar/<site>/sonuc_<tarih_saat>/):
  rapor.json, site_geneli.json, ...   baslangic taramasi (standart modla ayni ciktilar)
  degisiklikler.json                  plan: degisiklikler, elle yapilacaklar, atlananlar, asamalar
  onizleme.diff                       kategoriye gore gruplu onizleme
  onaylar.json                        kullanicinin kararlari
  yedek/                              ilk yazmadan once sitenin tam yedegi (+ manifest.json)
  uygulama_gunlugu.jsonl              her degisikligin her asamadaki sonucu
  uygulanan.diff, uygulama.json       asama asama dosya diff'leri ve ozet
  sonra_otomatik/, sonra/             otomatik ve onayli asamalardan sonraki tekrar taramalari
  geri_alma/                          (istege bagli) geri alma sonrasi tekrar taramasi
  bulgu_durumlari.json                her bulgunun durumu ve asama metrikleri
  yonetici_raporu.json / .html        uc asamali rapor
"""
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import canli, duzeltme, puanlama
from . import kategoriler as kat
from . import rapor as rapor_modulu
from .boru import site_adi, topluca_analiz, zaman_damgasi
from .cikarma import url_anahtari
from .kurallar import ACIKLAMA, CIDDIYET_AGIRLIK
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
    """Baslangic taramasi + degisiklik plani + otomatik asama: guven esigini gecen ve zorunlu onay
    kuralina girmeyen degisiklikler yedek alinarak hemen yazilir ve site yeniden taranir
    (ayarlar["oto_uygula"] False ise yazilmaz). (klasor, plan) dondurur."""
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
    if ayarlar.get("oto_uygula", True) and o["sayilar"]["otomatik"]:
        yaz(f"Otomatik aşama: güven eşiğini geçen {o['sayilar']['otomatik']} değişiklik onay beklemeden uygulanıyor "
            "(önce tam yedek alınır)")
        # yeniden tarama arayuzun ilerleme kancalarini almaz: baslangic sonuclarinin uzerine yazmasin
        iptal = {k: v for k, v in (tarama_kancalari or {}).items() if k == "iptal"}
        asama_uygula(klasor, plan, {}, "otomatik", sonuc_kok, yaz, tekrar_tara=True, tarama_kancalari=iptal)
    else:
        rapor_uret(klasor, plan)
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
                                            if d.get("onay_turu") != "otomatik" and d["durum"] != "gecersiz"),
                        "uygulandi": sum(1 for d in plan["degisiklikler"] if d["durum"] == "uygulandi"),
                        "otomatik_uygulandi": sum(1 for d in plan["degisiklikler"]
                                                  if d["durum"] == "uygulandi" and d.get("asama") == "otomatik")},
            "hedef": plan["hedef"], "model": plan.get("model"), "esik": plan.get("esik"),
            "asamalar": [a["ad"] for a in plan.get("asamalar") or []], "geri_alindi": bool(plan.get("geri_alindi"))}


def kararlari_kaydet(klasor, kararlar):
    _json_yaz(Path(klasor) / "onaylar.json", kararlar)


def _son_uygulama_yolu(site_klasoru):
    return Path(site_klasoru) / "son_uygulama.json"


ASAMA_ADI = {"baslangic": "Başlangıç", "otomatik": "Otomatik düzeltmeler sonrası",
             "onayli": "Onaylı düzeltmeler sonrası", "geri_alma": "Geri alma sonrası"}
TARAMA_KLASORU = {"otomatik": "sonra_otomatik", "onayli": "sonra", "geri_alma": "geri_alma"}


def _asamalar(plan):
    return plan.get("asamalar") or []


def asama_yapildi_mi(plan, ad):
    return any(a["ad"] == ad for a in _asamalar(plan))


def _son_tarama(plan):
    """Son olculen asamanin tarama klasoru (sonuc klasorune gore goreli; '' baslangic taramasi)."""
    for a in reversed(_asamalar(plan)):
        if a.get("tarama") is not None:
            return a["tarama"]
    return ""


def _tekrar_tara(plan, alt, sonuc_kok, yaz, tarama_kancalari):
    # ayni surecteki onceki taramanin robots.txt / sitemap / yoklama onbellegi yazilan dosyalari gizler
    canli.onbellek_temizle()
    tarama = plan["tarama"]
    topluca_analiz(tarama["hedefler"], tarama["ayarlar"], tarama["ogretme_klasoru"], sonuc_kok,
                   alt_yol=tarama["zaman"] + "/" + alt, gunluk=yaz, **(tarama_kancalari or {}))


def asama_uygula(klasor, plan, kararlar, asama, sonuc_kok, gunluk=None, tekrar_tara=True, tarama_kancalari=None):
    """Bir uygulama asamasini yurutur: ilk yazmadan once tam yedek, uygulama + gunluk + diff, dosya
    yazildiysa sitenin yeniden taranmasi, bulgu durumlari ve raporlar. (asama kaydi, rapor) dondurur.

    Site geneli bulgular (tekrar eden baslik, yetim sayfa, sitemap, robots.txt) tum sayfalara baglidir;
    bu yuzden yeniden kontrol yalnizca degisen sayfalarla sinirlanmaz, site bastan taranir."""
    yaz = gunluk or (lambda m: None)
    klasor = Path(klasor)
    hedef = plan["hedef"]
    adaptor, temel_url = hedef_dogrula(hedef["adaptor"]["kok"], hedef["temel_url"], sonuc_kok)
    yedek = klasor / "yedek"
    ilk_yedek = not (yedek / "manifest.json").exists()
    ozet = duzeltme.uygula(plan, kararlar, adaptor, yedek, klasor / "uygulama_gunlugu.jsonl", asama=asama)
    if ilk_yedek and ozet["yedek"]:
        yaz("Uygulama öncesi sitenin tam yedeği alındı: " + ozet["yedek"])
    zaman = time.strftime("%Y-%m-%d %H:%M:%S")
    kayit = {"ad": asama, "zaman": zaman, "yeni_uygulanan": ozet["yeni_uygulanan"],
             "geri_cekilen": ozet["geri_cekilen"],
             "dosyalar": {d: {k: v[k] for k in ("once", "sonra")} for d, v in ozet["dosyalar"].items()}}
    if ozet["dosyalar"]:
        with (klasor / "uygulanan.diff").open("a", encoding="utf-8") as f:
            f.write(f"# ===== Aşama: {ASAMA_ADI[asama]} ({zaman}) =====\n" +
                    "".join(v["diff"] for v in ozet["dosyalar"].values()))
        _json_yaz(_son_uygulama_yolu(klasor.parent), {
            "sonuc": str(klasor), "yedek": str(yedek), "adaptor": adaptor.tanim(), "temel_url": temel_url,
            "zaman": zaman, "durum": "uygulandi", "asamalar": [a["ad"] for a in _asamalar(plan)] + [asama]})
    yaz(f"{ASAMA_ADI[asama]}: {ozet['yeni_uygulanan']} değişiklik uygulandı"
        + (f", {ozet['geri_cekilen']} değişiklik geri çekildi" if ozet["geri_cekilen"] else "")
        + f" ({len(ozet['dosyalar'])} dosya yazıldı).")
    if ozet["dosyalar"] and tekrar_tara:
        yaz("Düzeltmelerin etkisini ölçmek için site yeniden taranıyor")
        _tekrar_tara(plan, TARAMA_KLASORU[asama], sonuc_kok, yaz, tarama_kancalari)
        kayit["tarama"] = TARAMA_KLASORU[asama]
    else:
        # dosya yazilmadiysa site degismedi ve onceki olcum gecerlidir; yazildi ama taranmadiysa olcum yoktur
        kayit["tarama"] = None if ozet["dosyalar"] else _son_tarama(plan)
    plan.setdefault("asamalar", []).append(kayit)
    _json_yaz(klasor / "degisiklikler.json", plan)
    _uygulama_ozeti_yaz(klasor, plan, kararlar)
    return kayit, rapor_uret(klasor, plan)


def _uygulama_ozeti_yaz(klasor, plan, kararlar):
    ds = plan["degisiklikler"]
    dosyalar = {}
    for a in _asamalar(plan):
        for dosya, h in (a.get("dosyalar") or {}).items():
            dosyalar.setdefault(dosya, {"once": h["once"]})["sonra"] = h["sonra"]
    yedek = Path(klasor) / "yedek"
    _json_yaz(Path(klasor) / "uygulama.json", {
        "zaman": time.strftime("%Y-%m-%d %H:%M:%S"),
        "yedek": str(yedek) if (yedek / "manifest.json").exists() else None,
        "uygulanan": sum(1 for d in ds if d["durum"] == "uygulandi"), "dosyalar": dosyalar,
        "durumlar": _durum_sayilari(plan), "esik": duzeltme.onay_esigi(plan, kararlar),
        "onay_kaynaklari": {kaynak: sum(1 for d in ds if d["durum"] == "uygulandi" and d.get("onay_kaynagi") == kaynak)
                            for kaynak in ("otomatik", "kullanıcı", "toplu")},
        "asamalar": [{k: a.get(k) for k in ("ad", "zaman", "yeni_uygulanan", "geri_cekilen", "tarama")}
                     for a in _asamalar(plan)],
        "geri_alindi": plan.get("geri_alindi")})


def uygula_ve_dogrula(klasor, kararlar, sonuc_kok, gunluk=None, tekrar_tara=True, tarama_kancalari=None):
    """Onayli asama: kullanicinin kararlari (onay / ret / duzenleme) uygulanir; otomatik asamada yazilmis
    bir degisiklik reddedildiyse geri cekilir. Ardindan site yeniden taranir ve raporlar guncellenir."""
    yaz = gunluk or (lambda m: None)
    klasor = Path(klasor)
    plan = _json_oku(klasor / "degisiklikler.json")
    if plan.get("geri_alindi"):
        raise YoneticiHatasi("Bu planın uygulaması geri alındı. Yeni değişiklikler için siteyi yeniden tarayın.")
    if asama_yapildi_mi(plan, "onayli") or ((klasor / "uygulama.json").exists() and not _asamalar(plan)):
        raise YoneticiHatasi("Bu plan zaten uygulandı. Yeni değişiklikler için siteyi yeniden tarayın.")
    kararlari_kaydet(klasor, kararlar)
    _, rapor = asama_uygula(klasor, plan, kararlar, "onayli", sonuc_kok, yaz, tekrar_tara, tarama_kancalari)
    yaz("Yönetici raporu: " + str(klasor / "yonetici_raporu.html"))
    return rapor


def _durum_sayilari(plan):
    sayac = {}
    for d in plan["degisiklikler"]:
        anahtar = d["kategori"] + ":" + d["durum"]
        sayac[anahtar] = sayac.get(anahtar, 0) + 1
    return sayac


def geri_al(site_klasoru, gunluk=None, tekrar_tara=False, tarama_kancalari=None):
    """Son uygulamayi (otomatik ve onayli tum asamalari) yedekten geri alir ve dosya hash'leriyle dogrular.
    Plandaki durumlar ve raporlar baslangic haline dondurulur; tekrar_tara ile site yeniden de olculur."""
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
    klasor = Path(bilgi["sonuc"])
    with (klasor / "uygulama_gunlugu.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"zaman": bilgi["geri_alma_zamani"], "olay": "geri_alma", **sonuc}, ensure_ascii=False) + "\n")
    yaz("Geri alma " + ("tamam: tüm dosyaların hash'i yedekle eşleşiyor" if sonuc["eslesiyor"] else "UYUMSUZ") +
        f" ({sonuc['geri_yazilan']} dosya geri yazıldı, {len(sonuc['silinen'])} dosya silindi)")
    if (klasor / "degisiklikler.json").exists():
        plan = _json_oku(klasor / "degisiklikler.json")
        for d in plan["degisiklikler"]:
            if d["durum"] == "uygulandi":
                d["geri_alinan_asama"] = d.pop("asama", None)
                d["durum"], d["durum_nedeni"] = "geri_alindi", "geri alındı: site yedekten uygulama öncesi haline döndü"
        plan["geri_alindi"] = {"zaman": bilgi["geri_alma_zamani"], "eslesiyor": sonuc["eslesiyor"]}
        plan["dosya_guncel"] = {}
        # hash'ler eslesiyorsa site baslangic taramasindaki haliyle aynidir: baslangic olcumu gecerli
        kayit = {"ad": "geri_alma", "zaman": bilgi["geri_alma_zamani"], "yeni_uygulanan": 0, "geri_cekilen": 0,
                 "dosyalar": {}, "tarama": "" if sonuc["eslesiyor"] else None}
        if tekrar_tara and plan.get("tarama"):
            yaz("Geri alma sonrası site yeniden taranıyor")
            _tekrar_tara(plan, TARAMA_KLASORU["geri_alma"], Path(site_klasoru).parent, yaz, tarama_kancalari)
            kayit["tarama"] = TARAMA_KLASORU["geri_alma"]
        plan.setdefault("asamalar", []).append(kayit)
        _json_yaz(klasor / "degisiklikler.json", plan)
        kararlar = _json_oku(klasor / "onaylar.json") if (klasor / "onaylar.json").exists() else {}
        _uygulama_ozeti_yaz(klasor, plan, kararlar)
        rapor_uret(klasor, plan)
    return sonuc


# ------------------------------------------------------------------ bulgu durumlari ve metrikler
BULGU_DURUM_ADI = {"cozuldu_otomatik": "Çözüldü (otomatik)", "cozuldu_onayli": "Çözüldü (onaylı)",
                   "onay_bekliyor": "Onay bekliyor", "reddedildi": "Reddedildi", "basarisiz": "Başarısız",
                   "dogrulanmadi": "Uygulandı, yeniden kontrol yapılmadı", "elle": "Elle düzeltilir"}
TEKRAR_KODLARI = ("title_tekrar", "meta_tekrar", "h1_tekrar", "icerik_tekrar", "icerik_benzer")
# puanlamada sayfaya ozgu sayilan ama sunucu yapilandirmasiyla tek seferde duzelen bulgular (sayac birimi)
SUNUCU_AYARI_KODLARI = ("onbellek_basligi_yok",)
# bir site ayari bazi sayfalarda acik kaldiysa gosterilen durum (en bilgilendirici once)
SITE_DURUM_ONCELIGI = ("basarisiz", "onay_bekliyor", "reddedildi", "dogrulanmadi", "elle")
COZUM_ORANI_TANIMI = (
    "Bulgu: başlangıç taramasındaki her (sorun, sayfa) çifti. Çözülen: düzeltmeler uygulandıktan sonra "
    "yeniden taramada artık tespit edilmeyen bulgu (yalnızca yeniden tarama sonucuna dayanır). "
    "Çözüm oranı = çözülen çözülebilir bulgu / çözülebilir bulgu; çözülebilir = araçta bir düzeltme önerisi "
    "olan bulgu (onaylanmış, bekleyen, reddedilen ya da doğrulamadan geçemeyen). Önerisi olmayan "
    "'Elle düzeltilir' bulgular orana girmez, ayrı sayılır.")


def _tarama_bulgulari(klasor):
    """Bir taramanin (sorun, sayfa) bulgulari ve taranan sayfalar; tarama yoksa None."""
    klasor = Path(klasor)
    if not (klasor / "rapor.json").exists():
        return None
    kayitlar = _json_oku(klasor / "rapor.json")
    kume = {(s["sorun"], k.get("ad")) for k in kayitlar for s in k.get("sorunlar") or []}
    if (klasor / "site_geneli.json").exists():
        kume |= {(g["sorun"], a) for g in _json_oku(klasor / "site_geneli.json") for a in g.get("sayfalar") or []}
    return {"kume": kume, "sayfalar": {k.get("ad") for k in kayitlar}, "kayitlar": kayitlar}


def bulgu_durumlari(klasor, plan):
    """Baslangic taramasindaki her bulgunun durumu ve asama metrikleri.

    "Çözüldü" yalnizca yeniden tarama sonucuna dayanir: bulgu bir uygulama asamasindan sonraki taramada
    artik tespit edilmiyorsa o asamada cozulmus sayilir. Sayfa o taramada hic yoksa bulgu dogrulanamaz;
    yalnizca dogrudan uygulanmis bir duzeltmesi varsa cozulmus sayilir. Uygulandigi halde hala tespit
    edilen bulgu "Başarısız" (duzeltme etkisiz) olur. Geri alindiysa durumlar baslangic haline doner."""
    klasor = Path(klasor)
    once = _tarama_bulgulari(klasor)
    if once is None:
        return {"asamalar": [], "bulgular": [], "site_ayarlari": [], "sayilar": {}, "toplam": 0, "ozet": durum_sayaclari([]),
                "sayfalar": {}, "tanim": COZUM_ORANI_TANIMI, "geri_alindi": bool(plan.get("geri_alindi"))}
    b0 = once["kume"]
    geri = bool(plan.get("geri_alindi"))
    olcumler = [("baslangic", "", once)]
    for a in _asamalar(plan):
        t = a.get("tarama")
        olcumler.append((a["ad"], t, _tarama_bulgulari(klasor / t) if t is not None else None))
    tam, kod_ile = {}, {}
    for d in plan["degisiklikler"]:
        tam.setdefault((d["bulgu"], d["url"]), []).append(d)
        kod_ile.setdefault(d["bulgu"], []).append(d)
    elle = {(e["bulgu"], u): e.get("duzeltme", "") for e in plan.get("elle", []) for u in e.get("sayfalar", [])}
    atlanan = {(a["bulgu"], a["url"]): a.get("neden", "") for a in plan.get("atlanan", [])}

    site_kodlari = {s["sorun"] for k in once["kayitlar"] for s in k.get("sorunlar") or [] if s.get("katman") == "site"}

    def site_geneli_mi(kod):
        # tum siteyi ilgilendiren bulgu (robots.txt, sitemap adresi): tek bir duzeltmeyle her sayfada giderilir
        return kod in site_kodlari and kod not in puanlama.SAYFAYA_OZGU

    def site_ayari_mi(kod):
        # sayacta bir kez sayilan ayar: site geneli bulgular + sunucunun verdigi yanit basliklari
        return site_geneli_mi(kod) or kod in SUNUCU_AYARI_KODLARI

    def ilgili_degisiklikler(f):
        if f in tam:
            return tam[f], True
        if f in elle or f in atlanan:
            return [], False
        # site geneli bulgu ya da tekrar grubu (ayni title/icerik) baska adresteki tek bir duzeltmeyle
        # giderilir; sayfaya ozgu bulgu yalnizca kendi duzeltmesine baglanir
        if site_geneli_mi(f[0]) or f[0] in TEKRAR_KODLARI:
            return kod_ile.get(f[0], []), False
        return [], False

    def cozum_asamasi(v, son):
        # son olcume (son dahil) kadar: bulgu hangi uygulama asamasinda cozuldu (sonra yeniden cikarsa cozulmemis)
        c = None
        for (ad, _, _), var in zip(olcumler[:son + 1], v[:son + 1]):
            if ad in duzeltme.ASAMALAR and var is not None:
                c = None if var else (c or ad)
        return c

    bulgular, varlik = [], {}
    for f in sorted(b0):
        ilgili, dogrudan = ilgili_degisiklikler(f)
        uygulanan = [d for d in ilgili if d["durum"] == "uygulandi"]
        # gecmis asamalarin olcumu geri almadan sonra da ayni kalsin: geri alinan da o asamada uygulanmisti
        uygulanmisti = uygulanan or [d for d in ilgili if d.get("geri_alinan_asama")]
        # her olcumde bulgu: True hala var, False yok (cozulmus), None dogrulanamadi (sayfa taranmadi)
        v = []
        for _, _, o in olcumler:
            if o is None:
                v.append(None)
            elif f in o["kume"]:
                v.append(True)
            elif f[1] in o["sayfalar"] or (dogrudan and uygulanmisti) or \
                    (site_geneli_mi(f[0]) and f[0] not in {k for k, _ in o["kume"]}):
                v.append(False)
            else:
                v.append(None)
        varlik[f] = v
        cozuldu = None if geri else cozum_asamasi(v, len(olcumler) - 1)
        if geri:
            # site uygulama oncesi haline dondu: durumlar baslangictaki gibi (oneri bekliyor / gecersiz / elle)
            gecerli = [d for d in ilgili if d["durum"] != "gecersiz"]
            if gecerli:
                durum, neden = "onay_bekliyor", "uygulama geri alındı; öneri yeniden onay bekler"
            elif ilgili:
                durum, neden = "basarisiz", "doğrulamadan geçmedi: " + ilgili[0]["dogrulama"]["neden"]
            else:
                durum, neden = "elle", elle.get(f) or atlanan.get(f) or "otomatik düzeltme önerisi yok"
        elif cozuldu:
            durum = "cozuldu_" + cozuldu
            neden = "yeniden kontrolde artık tespit edilmiyor" + (
                " · düzeltme: " + ", ".join(d["id"] for d in uygulanan) if dogrudan and uygulanan else
                " · dolaylı: başka bir düzeltmeyle giderildi")
        elif uygulanan:
            sira = max(i for i, (ad, _, _) in enumerate(olcumler)
                       if ad in {d.get("asama") for d in uygulanan} or i == 0)
            sonraki = [var for (ad, _, _), var in list(zip(olcumler, v))[sira:] if ad in duzeltme.ASAMALAR]
            son_olcum = next((var for var in reversed(sonraki) if var is not None), None)
            if son_olcum:
                durum = "basarisiz"
                neden = ("düzeltme etkisiz: " + ", ".join(d["id"] for d in uygulanan) +
                         " uygulandı ama yeniden kontrolde hâlâ tespit ediliyor")
            else:
                durum = "dogrulanmadi"
                neden = ("düzeltme uygulandı; sayfa yeniden taramada yer almadığı için doğrulanamadı"
                         if any(o is not None for (ad, _, o) in olcumler[sira:] if ad in duzeltme.ASAMALAR)
                         else "düzeltme uygulandı; ardından yeniden tarama yapılmadı")
        else:
            bekleyen = [d for d in ilgili if d["durum"] in ("oneriliyor", "onay_bekliyor", "geri_alindi")]
            reddedilen = [d for d in ilgili if d["durum"] == "reddedildi"]
            basarisiz = [d for d in ilgili if d["durum"] in ("basarisiz", "gecersiz")]
            if bekleyen:
                durum, neden = "onay_bekliyor", bekleyen[0].get("durum_nedeni") or "öneri onay bekliyor"
            elif reddedilen:
                durum, neden = "reddedildi", reddedilen[0].get("durum_nedeni") or "kullanıcı reddetti"
            elif basarisiz:
                d = basarisiz[0]
                durum, neden = "basarisiz", d.get("durum_nedeni") or "doğrulamadan geçmedi: " + d["dogrulama"]["neden"]
            else:
                durum, neden = "elle", elle.get(f) or atlanan.get(f) or "otomatik düzeltme önerisi yok"
        # cozulen bulgu raporda nasil cozuldugunu (uygulanan degisiklik, guven, onay kaynagi) gosterir
        cozum = [{"id": d["id"], "ozet": _degisiklik_ozeti(d), "guven": d.get("guven"),
                  "onay_kaynagi": d.get("onay_kaynagi"), "asama": d.get("asama")}
                 for d in uygulanan] if durum.startswith("cozuldu") else []
        bulgular.append({"sorun": f[0], "url": f[1], "aciklama": ACIKLAMA.get(f[0], f[0]),
                         "kategori": kat.kategori(f[0]), "durum": durum, "durum_adi": BULGU_DURUM_ADI[durum],
                         "neden": neden, "degisiklikler": [d["id"] for d in ilgili], "dogrudan": dogrudan,
                         "elle_turu": not ilgili, "aktif": not durum.startswith("cozuldu"), "cozum": cozum,
                         "site_ayari": site_ayari_mi(f[0])})
    takma_adresleri_bagla(bulgular, once["kayitlar"])

    # sayac birimi: sayfa bulgusu ya da site geneli ayar (tum sayfalari etkileyen tek ayar bir kez sayilir;
    # yalnizca gosterim/sayac; tespit ve puanlama sayfa x sorun olarak kalir)
    birimler = []
    for f, b in zip(sorted(b0), bulgular):
        if not b["site_ayari"] and not b.get("takma"):
            birimler.append({"durum": b["durum"], "elle_turu": b["elle_turu"], "v": varlik[f],
                             "cozum_asamalari": [cozum_asamasi(varlik[f], i) for i in range(len(olcumler))]})
    site_gruplari = {}
    for f, b in zip(sorted(b0), bulgular):
        if b["site_ayari"]:
            site_gruplari.setdefault(f[0], []).append((f, b))
    site_ayarlari = []
    for kod, uyeler in sorted(site_gruplari.items()):
        v = [False if all(varlik[f][i] is False for f, _ in uyeler) else
             True if any(varlik[f][i] for f, _ in uyeler) else None for i in range(len(olcumler))]
        cs = []
        for i in range(len(olcumler)):
            c = [cozum_asamasi(varlik[f], i) for f, _ in uyeler]
            cs.append(None if None in c else "onayli" if "onayli" in c else "otomatik")
        bs = [b for _, b in uyeler]
        acik = [b for b in bs if b["aktif"]]
        # tum sayfalarda cozulduyse cozuldu; degilse en bilgilendirici acik durum
        temsil = min(acik, key=lambda b: SITE_DURUM_ONCELIGI.index(b["durum"])) if acik else \
            next((b for b in bs if b["durum"] == "cozuldu_onayli"), bs[0])
        birimler.append({"durum": temsil["durum"], "elle_turu": all(b["elle_turu"] for b in bs), "v": v,
                         "cozum_asamalari": cs})
        site_ayarlari.append({"sorun": kod, "aciklama": ACIKLAMA.get(kod, kod), "kategori": kat.kategori(kod),
                              "durum": temsil["durum"], "durum_adi": BULGU_DURUM_ADI[temsil["durum"]],
                              "neden": temsil["neden"], "aktif": bool(acik), "sayfa_sayisi": len(bs),
                              "aktif_sayfa": len(acik), "cozum": temsil["cozum"],
                              "degisiklikler": sorted({x for b in bs for x in b["degisiklikler"]})})

    cozulebilir = [u for u in birimler if not u["elle_turu"]]
    elle_birimleri = [u for u in birimler if u["elle_turu"]]
    asamalar = []
    for i, (ad, tarama, o) in enumerate(olcumler):
        m = {"ad": ad, "adi": ASAMA_ADI[ad], "tarama": tarama, "olculdu": o is not None}
        if o is not None:
            # geri alindiysa uygulama asamalarinin olcumleri gecmisi gosterir; durumlar baslangica doner
            cozulen = sum(1 for u in cozulebilir if u["v"][i] is False)
            elle_cozulen = sum(1 for u in elle_birimleri if u["v"][i] is False)
            # durum sayaclari: bu asamaya kadarki olcumlerle durum kurali (geri alma sonrasi hepsi aktif)
            cozum_asamalari = [None if ad == "geri_alma" else u["cozum_asamalari"][i] for u in birimler]
            oto = sum(1 for c in cozum_asamalari if c == "otomatik")
            onayli = sum(1 for c in cozum_asamalari if c == "onayli")
            m.update({"puanlar": _ortalama_puanlar(o["kayitlar"]), "bulgu_sayisi": len(o["kume"]),
                      "yeni_bulgu": len(o["kume"] - b0), "cozulen": cozulen, "cozulebilir": len(cozulebilir),
                      "elle": len(elle_birimleri) - elle_cozulen, "elle_dolayli_cozulen": elle_cozulen,
                      "cozum_orani": round(cozulen / len(cozulebilir), 3) if cozulebilir else None,
                      "aktif": len(birimler) - oto - onayli, "cozuldu_otomatik": oto, "cozuldu_onayli": onayli})
        asamalar.append(m)
    sayilar = {d: sum(1 for u in birimler if u["durum"] == d) for d in BULGU_DURUM_ADI}
    sayfa_bulgulari = [b for b in bulgular if not b["site_ayari"] and not b.get("takma")]
    ozet = durum_sayaclari(birimler)
    ozet.update({"sayfa": durum_sayaclari(sayfa_bulgulari), "site_ayari": durum_sayaclari(site_ayarlari),
                 "site_ayari_sayfa": sum(s["aktif_sayfa"] for s in site_ayarlari), "ham_toplam": len(b0),
                 "takma": sum(1 for b in bulgular if b.get("takma"))})
    son = next((o for (ad, _, o) in reversed(olcumler) if o is not None and ad != "baslangic"), None)
    return {"asamalar": asamalar, "bulgular": bulgular, "site_ayarlari": site_ayarlari, "sayilar": sayilar,
            "toplam": len(birimler), "ozet": ozet,
            "sayfalar": sayfa_sayaclari(bulgular, once["kayitlar"], (son or once)["kayitlar"]),
            "tanim": COZUM_ORANI_TANIMI, "geri_alindi": geri}


GECERSIZ_SAYFA_KODLARI = ("yumusak_404", "hata_durum_kodu")
TAKMA_TURU = {"yonlendirme": "yönlendirme", "parametre": "parametreli adres", "gecersiz": "geçersiz sayfa"}


def asil_adresler(kayitlar):
    """Takma adres → (asil adres, tur). Yonlendirme: son adresi baska bir kaydin adresi; parametre: sorgusuz
    yolu baska bir kaydin adresi (ayni dosyayi acar). Zincir izlenir; asil adresin kendisi takma degildir."""
    adlar = {url_anahtari(k.get("ad")): k.get("ad") for k in kayitlar if k.get("ad")}
    asil = {}
    for k in kayitlar:
        ad = k.get("ad")
        if not ad:
            continue
        son = k.get("site_url") or ad
        if url_anahtari(son) != url_anahtari(ad) and url_anahtari(son) in adlar:
            asil[ad] = (adlar[url_anahtari(son)], "yonlendirme")
        elif urlsplit(ad).query:
            yol = urlsplit(ad)._replace(query="").geturl()
            if url_anahtari(yol) in adlar and adlar[url_anahtari(yol)] != ad:
                asil[ad] = (adlar[url_anahtari(yol)], "parametre")
    for ad in list(asil):
        hedef, tur, gorulen = asil[ad][0], asil[ad][1], {ad}
        while hedef in asil and hedef not in gorulen:
            gorulen.add(hedef)
            hedef = asil[hedef][0]
        asil[ad] = (hedef, tur)
    return asil


def takma_adresleri_bagla(bulgular, kayitlar):
    """Ayni dosyanin baska adresindeki (yonlendirme, parametre) ya da gecersiz sayfadaki (yumusak 404, hata
    kodu) bulgular asil bulguya baglanir: durumunu asil bulgudan alir (o yeniden kontrole dayanir), sayaca
    ayrica girmez. Asil sayfada ayni kod yoksa bulgu kendi basina kalir. Yalnizca gosterim/sayac."""
    anahtar = {(b["sorun"], b["url"]): b for b in bulgular}
    asil = asil_adresler(kayitlar)
    gecersiz = {}
    for b in bulgular:
        if b["sorun"] in GECERSIZ_SAYFA_KODLARI:
            gecersiz.setdefault(b["url"], b)
    for b in bulgular:
        if b["site_ayari"] or b["sorun"] in GECERSIZ_SAYFA_KODLARI:
            continue
        hedef, tur = None, None
        if b["url"] in asil and (b["sorun"], asil[b["url"]][0]) in anahtar:
            hedef, tur = anahtar[(b["sorun"], asil[b["url"]][0])], asil[b["url"]][1]
        elif b["url"] in gecersiz and b["elle_turu"] and not b["sorun"].startswith("sitemap_"):
            # gecersiz sayfanin icerik bulgulari anlamsizdir; kendi duzeltmesi olan ya da sitemap dosyasina ait
            # bulgu (olu adresi sitemap'ten cikarmak) ayri is olarak kalir
            hedef, tur = gecersiz[b["url"]], "gecersiz"
        if hedef is None or hedef is b:
            continue
        b["takma"] = {"asil_url": hedef["url"], "asil_sorun": hedef["sorun"], "tur": tur}
        hedef.setdefault("takma_adresler", []).append({"url": b["url"], "sorun": b["sorun"], "tur": tur})
    for b in bulgular:
        t = b.get("takma")
        if t:
            h = anahtar[(t["asil_sorun"], t["asil_url"])]
            b.update(durum=h["durum"], durum_adi=h["durum_adi"], aktif=h["aktif"], cozum=h["cozum"],
                     neden=f"{TAKMA_TURU[t['tur']]}: {t['asil_url']} adresindeki "
                           f"'{h['aciklama']}' bulgusuna bağlı ({h['durum_adi']})")


def _kisalt(metin, n=70):
    metin = " ".join(str(metin or "").split())
    return metin if len(metin) <= n else metin[:n - 1] + "…"


def _degisiklik_ozeti(d):
    eski = d.get("eski")
    return (_kisalt(eski, 40) + " → " if eski and eski != "(yok)" else "eklendi: ") + _kisalt(d.get("yeni"))


def durum_sayaclari(bulgular):
    """Tek dogruluk kaynagi: aktif = Onay bekliyor + Reddedildi + Başarısız + Elle düzeltilir (+ uygulanmis
    ama yeniden kontrolle dogrulanmamis); cozulen = Çözüldü (otomatik) + Çözüldü (onaylı). Toplam her zaman
    baslangictaki birim sayisidir (aktif + cozulen). Birim: sayfa bulgusu ya da bir kez sayilan site ayari."""
    oto = sum(1 for b in bulgular if b["durum"] == "cozuldu_otomatik")
    onayli = sum(1 for b in bulgular if b["durum"] == "cozuldu_onayli")
    return {"toplam": len(bulgular), "aktif": len(bulgular) - oto - onayli, "cozulen": oto + onayli,
            "cozuldu_otomatik": oto, "cozuldu_onayli": onayli}


def sayfa_sayaclari(bulgular, once_kayitlar, guncel_kayitlar):
    """Sayfa basina durum sayaclari (site geneli ayarlar ve asil bulguya baglanan takma adres bulgulari haric;
    site_ayari sayfayi etkileyen acik ayar, takma baglanan bulgu sayisidir), baslangic ve guncel (son yeniden tarama) sayfa puani ve cozum
    orani (cozulen / cozulebilir; 'Elle düzeltilir' haric, COZUM_ORANI_TANIMI)."""
    def puan(kayitlar):
        return {k.get("ad"): (k.get("once_puanlar") or {}).get("sayfa") for k in kayitlar}
    once_p, guncel_p = puan(once_kayitlar), puan(guncel_kayitlar)
    gruplar = {}
    for b in bulgular:
        gruplar.setdefault(b["url"], []).append(b)
    sonuc = {}
    for url in [k.get("ad") for k in once_kayitlar] + sorted(set(gruplar) - {k.get("ad") for k in once_kayitlar}):
        hepsi = gruplar.get(url, [])
        bs = [b for b in hepsi if not b.get("site_ayari") and not b.get("takma")]
        cozulebilir = [b for b in bs if not b["elle_turu"]]
        s = durum_sayaclari(bs)
        s.update({"site_ayari": sum(1 for b in hepsi if b.get("site_ayari") and b["aktif"]),
                  "takma": sum(1 for b in hepsi if b.get("takma")),
                  "puan_once": once_p.get(url), "puan_guncel": guncel_p.get(url),
                  "cozum_orani": round(sum(1 for b in cozulebilir if not b["aktif"]) / len(cozulebilir), 3)
                  if cozulebilir else None})
        sonuc[url] = s
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
    t = _tarama_bulgulari(klasor)
    return t["kume"] if t else set()


def rapor_uret(klasor, plan=None):
    """bulgu_durumlari.json, yonetici_raporu.json/.html ve durumlu rapor.html'i yeniden yazar."""
    klasor = Path(klasor)
    plan = plan or _json_oku(klasor / "degisiklikler.json")
    durumlar = bulgu_durumlari(klasor, plan)
    _json_yaz(klasor / "bulgu_durumlari.json", durumlar)
    rapor = yonetici_raporu(klasor, plan, durumlar)
    _analiz_raporunu_guncelle(klasor, durumlar)
    return rapor


def _son_olcum(durumlar):
    """Son olculen uygulama/geri alma asamasi (baslangic haric); yoksa None."""
    return next((a for a in reversed(durumlar["asamalar"]) if a["olculdu"] and a["ad"] != "baslangic"), None)


def _analiz_raporunu_guncelle(klasor, durumlar):
    """Baslangic taramasinin rapor.html'i: her sorunun yaninda guncel durumu ve asama metrikleri.
    Yalnizca yonetici modu klasorlerinde cagrilir; standart mod raporu degismez."""
    gerekli = [klasor / a for a in ("rapor.json", "site_ozeti.json", "site_geneli.json")]
    if not all(p.exists() for p in gerekli):
        return
    kayitlar, ozet, bulgular = (_json_oku(p) for p in gerekli)
    son = _son_olcum(durumlar)
    sayfa_bulgulari = {}
    for b in durumlar["bulgular"]:
        sayfa_bulgulari.setdefault(b["url"], []).append(b)
    # tum sayaclar (genel, sayfa, sorun turu) bulgu durumlarindan: rapor.json/site_ozeti yalnizca aciklama icin
    tur = {}
    for b in durumlar["bulgular"]:
        t = tur.setdefault(b["sorun"], {"aktif": 0, "cozulen": 0})
        t["aktif" if b["aktif"] else "cozulen"] += 1
    bilgi = {"durumlar": {b["sorun"] + "|" + b["url"]: b for b in durumlar["bulgular"]},
             "asamalar": durumlar["asamalar"], "sayilar": durumlar["sayilar"], "toplam": durumlar["toplam"],
             "sayaclar": durumlar["ozet"], "sayfalar": durumlar["sayfalar"], "sayfa_bulgulari": sayfa_bulgulari,
             "site_ayarlari": durumlar["site_ayarlari"],
             "tur_sayaclari": tur, "DURUM_ADI": BULGU_DURUM_ADI, "tanim": durumlar["tanim"],
             "son_asama": son["adi"] if son else None}
    (klasor / "rapor.html").write_text(rapor_modulu.html_rapor(kayitlar, ozet, bulgular, baslik=klasor.parent.name,
                                                               yonetici=bilgi), encoding="utf-8")


def yonetici_raporu(klasor, plan=None, durumlar=None):
    klasor = Path(klasor)
    plan = plan or _json_oku(klasor / "degisiklikler.json")
    durumlar = durumlar or bulgu_durumlari(klasor, plan)
    once_k = _json_oku(klasor / "rapor.json")
    son = _son_olcum(durumlar)
    sonra_klasor = klasor / son["tarama"] if son else None
    once_p, sonra_p = _ortalama_puanlar(once_k), (son["puanlar"] if son else None)
    yeni = sorted(_bulgu_kumesi(sonra_klasor) - _bulgu_kumesi(klasor)) if son else []
    giderilen = sorted(_bulgu_kumesi(klasor) - _bulgu_kumesi(sonra_klasor)) if son else []
    gruplar = {}
    for d in plan["degisiklikler"]:
        gruplar.setdefault(d["kategori"], {}).setdefault(d["durum"], []).append(
            {k: d.get(k) for k in ("id", "bulgu", "bulgu_aciklamasi", "url", "dosya", "eski", "yeni", "gerekce", "risk",
                                   "etki", "durum_nedeni", "uretici", "kaynaklar", "yer_tutucu", "guven",
                                   "guven_nedenleri", "zorunlu_onay", "onay_kaynagi", "asama")})
    uygulama = _json_oku(klasor / "uygulama.json") if (klasor / "uygulama.json").exists() else None
    rapor = {"klasor": str(klasor), "hedef": plan["hedef"], "model": plan.get("model"), "zaman": time.strftime("%Y-%m-%d %H:%M:%S"),
             "puanlar": {"once": once_p, "sonra": sonra_p}, "durumlar": gruplar, "elle": plan["elle"],
             "atlanan": plan["atlanan"], "yeni_bulgular": [{"sorun": k, "aciklama": kat.aciklama(k), "url": u,
                                                             "kategori": kat.kategori(k)} for k, u in yeni],
             "giderilen_bulgu_sayisi": len(giderilen), "uygulama": uygulama,
             "asamalar": durumlar["asamalar"], "bulgu_durumlari": durumlar["bulgular"],
             "bulgu_sayilari": durumlar["sayilar"], "bulgu_toplam": durumlar["toplam"],
             "sayaclar": durumlar["ozet"], "sayfa_sayaclari": durumlar["sayfalar"],
             "site_ayarlari": durumlar["site_ayarlari"],
             "cozum_orani_tanimi": durumlar["tanim"], "geri_alindi": plan.get("geri_alindi")}
    _json_yaz(klasor / "yonetici_raporu.json", rapor)
    (klasor / "yonetici_raporu.html").write_text(_ortam.get_template("yonetici_rapor.html").render(
        r=rapor, KATEGORI_ADI=kat.KATEGORI_ADI, PUAN_ANAHTARLARI=PUAN_ANAHTARLARI, ASAMA_ADI=ASAMA_ADI,
        DURUM_ADI=DURUM_ADI, BULGU_DURUM_ADI=BULGU_DURUM_ADI, CIDDIYET_AGIRLIK=CIDDIYET_AGIRLIK), encoding="utf-8")
    return rapor


DURUM_ADI = {"uygulandi": "Uygulandı", "reddedildi": "Reddedildi", "basarisiz": "Başarısız",
             "onay_bekliyor": "Onay verilmedi", "gecersiz": "Doğrulamadan geçmedi", "oneriliyor": "Önerildi",
             "geri_alindi": "Geri alındı"}
