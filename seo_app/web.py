"""Yerel web arayuzu (Flask).

Tarama arka planda bir is parcaciginda calisir; arayuz ilerlemeyi duzenli araliklarla
sorarak gunlugu ve sonuc tablosunu gunceller. Sunucu yalnizca bu bilgisayardan
erisilebilir sekilde baslatilir.
"""
import io
import json
import threading
import time
from pathlib import Path

import requests
from flask import Flask, abort, jsonify, render_template, request, send_file

from . import canli
from . import kategoriler as kat
from . import yonetici
from .boru import (VARSAYILAN_AYARLAR, alt_siteleri_kesfet, hedefleri_hazirla, site_adi, topluca_analiz,
                   zaman_damgasi, csv_uret as _csv_uret)
from .kurallar import ACIKLAMA, DUZELTME, site_geneli, site_ozeti
from .rapor import html_rapor
from .tarama import baglanti_bulgulari
from .llm import ModelHatasi, model_durumlari, modelleri_dogrula

KOK = Path(__file__).resolve().parent.parent
SONUC_KOK = KOK / "sonuclar"     # tum tarama ciktilari bu klasorun altina yazilir
uygulama = Flask(__name__, template_folder="sablonlar", static_folder="statik")
uygulama.json.ensure_ascii = False     # JSON yanitlari Turkce harfleri ş gibi kacislamadan UTF-8 yazar

# ---------------------------------------------------------------- tarama durumu
_kilit = threading.Lock()
DURUM = {
    "calisiyor": False,
    "iptal": False,
    "toplam": 0,
    "biten": 0,
    "gunluk": [],
    "sonuclar": [],
    "cikti_klasoru": None,
    "baslangic": None,
    "bitis": None,
    "hata": None,
    "bulgular": None,      # tarama sonunda hesaplanan tarama geneli bulgular (yetim sayfa vb.)
    "mod": "standart",     # standart: salt okunur analiz; yonetici: onayli duzeltmeleri siteye yazar
    "yonetici": None,      # yonetici modu: {"asama", "klasor", "hata", "rapor"}
}
MODLAR = ("standart", "yonetici")


def _istek_dogrula():
    """Durum degistiren isteklerin yalnizca bu arayuzden gelmesini saglar.
    Baska bir sitenin, kullanici sayfayi acikken yerel sunucuya istek gondermesini
    (siteler arasi istek sahteciligi) engeller; JSON olmayan govdeyi reddeder."""
    kaynak = request.headers.get("Origin")
    if kaynak and kaynak != request.host_url.rstrip("/"):
        abort(403)
    veri = request.get_json(silent=True)
    if not isinstance(veri, dict):
        abort(400)
    return veri


def _proje_ici(yol, taban):
    """Verilen yolu taban klasore gore cozer; taban disina cikiyorsa None dondurur."""
    taban = Path(taban).resolve()
    hedef = (taban / str(yol)).resolve()
    return hedef if hedef == taban or hedef.is_relative_to(taban) else None


def _gunluk_yaz(mesaj):
    with _kilit:
        DURUM["gunluk"].append(time.strftime("%H:%M:%S") + "  " + str(mesaj))
        del DURUM["gunluk"][:-400]      # gunluk sinirsiz buyumesin


def _sifirla(toplam, cikti, mod="standart"):
    with _kilit:
        DURUM.update({"calisiyor": True, "iptal": False, "toplam": toplam, "biten": 0,
                      "gunluk": [], "sonuclar": [], "cikti_klasoru": str(cikti),
                      "baslangic": time.time(), "bitis": None, "hata": None, "bulgular": None,
                      "mod": mod, "yonetici": {"asama": "taraniyor"} if mod == "yonetici" else None})


def _cikti_ozeti(hedefler, zaman):
    """Arayuzde gosterilecek cikti yeri: tek site icin tam yol, birden fazla site icin desen."""
    siteler = sorted({site_adi(h["url"]) for h in hedefler})
    if len(siteler) == 1:
        return str(Path("sonuclar") / siteler[0] / zaman)
    return str(Path("sonuclar") / ("<" + str(len(siteler)) + " site>") / zaman)


def _kancalar():
    """topluca_analiz'in ilerleme kancalari: her sayfa bittiginde DURUM guncellenir."""
    def iptal():
        return DURUM["iptal"]

    def her_kayitta(sira, kayit, rapor):
        # her sayfa bittiginde arayuzun gorebilmesi icin durum adim adim guncellenir
        with _kilit:
            DURUM["biten"] = sira
            DURUM["sonuclar"] = list(rapor)

    def bulgular_hazir(bulgular):
        with _kilit:
            DURUM["bulgular"] = bulgular

    def toplam_degisti(n):
        # site taramasinda toplam sayfa sayisi kesfedildikce degisir
        with _kilit:
            DURUM["toplam"] = max(n, DURUM["biten"])
    return {"iptal": iptal, "her_kayitta": her_kayitta, "toplam_degisti": toplam_degisti,
            "bulgular_hazir": bulgular_hazir}


def _yonetici_ozeti(klasor):
    """Arayuz icin asama metrikleri ve bulgu durumlari (yonetici_raporu.json); yoksa None."""
    yol = Path(klasor) / "yonetici_raporu.json"
    if not yol.exists():
        return None
    r = json.loads(yol.read_text(encoding="utf-8"))
    guncel = {}
    son = next((a for a in reversed(r.get("asamalar") or []) if a["olculdu"] and a["ad"] != "baslangic"), None)
    if son and (Path(klasor) / son["tarama"] / "rapor.json").exists():
        for k in json.loads((Path(klasor) / son["tarama"] / "rapor.json").read_text(encoding="utf-8")):
            guncel[k.get("ad")] = {"puan": (k.get("once_puanlar") or {}).get("sayfa"), "sorun": k.get("once_sorun_sayisi")}
    return {"asamalar": r.get("asamalar") or [], "sayilar": r.get("bulgu_sayilari") or {},
            "toplam": r.get("bulgu_toplam", 0), "tanim": r.get("cozum_orani_tanimi"),
            "geri_alindi": r.get("geri_alindi"), "guncel": guncel,
            "durumlar": {b["sorun"] + "|" + b["url"]: {k: b[k] for k in ("durum", "durum_adi", "neden")}
                         for b in r.get("bulgu_durumlari") or []}}


def _tarama_isi(hedefler, ayarlar, ogretme_klasoru, sonuc_koku, zaman, yonetici_hedefi=None):
    """Arka planda calisan tarama. Yonetici modunda tarama bitince degisiklik plani uretilir ve guven
    esigini gecen degisiklikler onay beklemeden uygulanir (otomatik asama); digerleri onay ister."""
    cikti = _cikti_ozeti(hedefler, zaman)
    gunluk = _gunluk_yaz
    try:
        if yonetici_hedefi:
            klasor, _ = yonetici.tara_ve_planla(hedefler, yonetici_hedefi["kok"], yonetici_hedefi["temel_url"], ayarlar,
                                                ogretme_klasoru, sonuc_koku, gunluk=gunluk, zaman=zaman,
                                                tarama_kancalari=_kancalar())
            with _kilit:
                DURUM["yonetici"] = {"asama": "plan_hazir", "klasor": str(klasor), "ozet": _yonetici_ozeti(klasor)}
        else:
            topluca_analiz(hedefler, ayarlar, ogretme_klasoru, sonuc_koku, zaman, gunluk=gunluk, **_kancalar())
        gunluk("Tarama tamamlandı. Çıktı klasörü: " + cikti)
    except Exception as e:
        with _kilit:
            DURUM["hata"] = type(e).__name__ + ": " + str(e)
            if DURUM.get("yonetici"):
                DURUM["yonetici"] = {"asama": "hata", "hata": str(e)}
        _gunluk_yaz("BEKLENMEYEN HATA: " + str(e))
    finally:
        with _kilit:
            DURUM["calisiyor"] = False
            DURUM["bitis"] = time.time()


SAYI_ALANLARI = {"retry": (0, 5), "max_tokens": (100, 64000), "timeout": (10, 3600),
                 "ornek_sayisi": (0, 10), "bilgi_sayisi": (1, 10), "zaman_asimi": (1, 120),
                 "en_fazla_sayfa": (1, 500), "en_fazla_derinlik": (0, 10), "link_siniri": (0, 300)}
MANTIKSAL_ALANLAR = ("bagimsiz_olcum", "yalnizca_denetim", "link_denetimi", "js_render", "sitemap_tohum",
                     "ssl_zorunlu", "uy_robots", "json_schema")
TARAMA_MODLARI = ("liste", "site")


def ayarlari_dogrula(veri):
    """Arayuzden gelen ayarlari tur ve aralik bakimindan denetler. (ayarlar, hata) dondurur.
    Deney kosulu arayuzden alinmaz; her zaman varsayilan (ornek+bilgi) kullanilir."""
    ayarlar = {**VARSAYILAN_AYARLAR}
    for k in ("url", "model", "embed_model", "embed_url", "retry",
              "max_tokens", "timeout", "ornek_sayisi", "bilgi_sayisi", "rerank_url", "rerank_model",
              "json_schema", "dil", "uy_robots",
              "bekleme_sn", "zaman_asimi", "bagimsiz_olcum", "yalnizca_denetim", "tarama_modu",
              "en_fazla_sayfa", "en_fazla_derinlik", "link_denetimi", "link_siniri", "js_render",
              "sitemap_tohum", "ssl_zorunlu", "oto_esik"):
        if k in veri and veri[k] not in ("", None):
            ayarlar[k] = veri[k]
    try:
        ayarlar["oto_esik"] = float(ayarlar["oto_esik"])
    except (TypeError, ValueError):
        return None, "oto_esik bir sayı olmalı."
    if not 0 <= ayarlar["oto_esik"] <= 1.01:
        return None, "oto_esik 0-1 aralığında olmalı (1'in üstü otomatik onayı kapatır)."
    for alan, (en_az, en_cok) in SAYI_ALANLARI.items():
        try:
            ayarlar[alan] = int(ayarlar[alan])
        except (TypeError, ValueError):
            return None, alan + " bir tam sayı olmalı."
        if not en_az <= ayarlar[alan] <= en_cok:
            return None, alan + " " + str(en_az) + "-" + str(en_cok) + " aralığında olmalı."
    try:
        ayarlar["bekleme_sn"] = float(ayarlar["bekleme_sn"])
    except (TypeError, ValueError):
        return None, "bekleme_sn bir sayı olmalı."
    if ayarlar["bekleme_sn"] < 0:
        return None, "bekleme_sn negatif olamaz."
    for alan in MANTIKSAL_ALANLAR:
        ayarlar[alan] = bool(ayarlar[alan])
    if ayarlar["tarama_modu"] not in TARAMA_MODLARI:
        return None, "tarama_modu 'liste' ya da 'site' olmalı."
    if ayarlar["yalnizca_denetim"]:
        ayarlar["model"] = None              # acik secim: dil modeli bu taramada hic cagrilmaz
    return ayarlar, None


# ------------------------------------------------------------------- sayfalar
@uygulama.route("/")
def anasayfa():
    return render_template("index.html",
                           varsayilan=VARSAYILAN_AYARLAR, kok=str(KOK))


@uygulama.route("/api/modeller")
def api_modeller():
    url = request.args.get("url") or VARSAYILAN_AYARLAR["url"]
    try:
        return jsonify({"modeller": model_durumlari(url), "hata": None})
    except requests.RequestException as e:
        return jsonify({"modeller": [], "hata": "LM Studio'ya ulaşılamadı: " + type(e).__name__})


@uygulama.route("/api/kesif", methods=["POST"])
def api_kesif():
    veri = _istek_dogrula()
    sonuc = alt_siteleri_kesfet(veri.get("adres", ""))
    return jsonify(sonuc)


@uygulama.route("/api/tara", methods=["POST"])
def api_tara():
    veri = _istek_dogrula()
    if DURUM["calisiyor"]:
        return jsonify({"hata": "Zaten çalışan bir tarama var."}), 409
    hedefler = hedefleri_hazirla(veri.get("adresler"))
    if not hedefler:
        return jsonify({"hata": "Analiz edilecek adres bulunamadı."}), 400

    ayarlar, hata = ayarlari_dogrula(veri)
    if hata:
        return jsonify({"hata": hata}), 400
    mod = veri.get("mod") or "standart"
    if mod not in MODLAR:
        return jsonify({"hata": "mod 'standart' ya da 'yonetici' olmalı."}), 400
    yonetici_hedefi = None
    if mod == "yonetici":
        # yazma yalnizca acikca yapilandirilan hedefe yapilir; hedef ve adresler tarama baslamadan denetlenir
        try:
            _, temel = yonetici.hedef_dogrula(veri.get("kok"), veri.get("temel_url"), SONUC_KOK)
            yonetici.adresleri_denetle(hedefler, temel)
        except yonetici.YoneticiHatasi as e:
            return jsonify({"hata": str(e)}), 400
        yonetici_hedefi = {"kok": veri.get("kok"), "temel_url": temel}
    # tarama baslamadan once LM Studio ve secilen modeller denetlenir; sorun varsa tarama baslamaz.
    # "yalnizca denetim" acikca secildiyse dil modeli kullanilmaz ve LM Studio gerekmez.
    if not ayarlar["yalnizca_denetim"]:
        try:
            modelleri_dogrula(ayarlar["url"], [ayarlar.get("model"), ayarlar.get("embed_model")])
        except ModelHatasi as e:
            return jsonify({"hata": str(e)}), 503

    ogretme_klasoru = _proje_ici(veri.get("ogretme_klasoru") or "ogretme", KOK)
    if ogretme_klasoru is None:
        return jsonify({"hata": "Öğretme klasörü proje klasörünün içinde olmalı."}), 400

    # ciktilar sonuclar/<site_adi>/sonuc_<tarih_saat>/ altina yazilir; klasor adi kullanicidan alinmaz
    zaman = zaman_damgasi()
    cikti = _cikti_ozeti(hedefler, zaman)
    canli.onbellek_temizle()
    _sifirla(ayarlar["en_fazla_sayfa"] if ayarlar["tarama_modu"] == "site" else len(hedefler), cikti, mod)
    _gunluk_yaz("Tarama başladı: " + str(len(hedefler)) + " hedef" +
                (" · YÖNETİCİ MODU (hedef: " + str(veri.get("kok")) + ")" if mod == "yonetici" else "") +
                (", site modu (en fazla " + str(ayarlar["en_fazla_sayfa"]) + " sayfa)" if ayarlar["tarama_modu"] == "site" else "") +
                (", yalnızca denetim (dil modeli yok)" if ayarlar["yalnizca_denetim"] else
                 ", model=" + str(ayarlar["model"]) + ", koşul=" + ayarlar["kosul"]))
    is_parcacigi = threading.Thread(target=_tarama_isi,
                                    args=(hedefler, ayarlar, ogretme_klasoru, SONUC_KOK, zaman),
                                    kwargs={"yonetici_hedefi": yonetici_hedefi}, daemon=True)
    is_parcacigi.start()
    return jsonify({"tamam": True, "toplam": len(hedefler), "cikti": cikti})


@uygulama.route("/api/durum")
def api_durum():
    with _kilit:
        return jsonify({k: DURUM[k] for k in
                        ("calisiyor", "toplam", "biten", "gunluk", "sonuclar",
                         "cikti_klasoru", "baslangic", "bitis", "hata", "mod", "yonetici")})


@uygulama.route("/api/durdur", methods=["POST"])
def api_durdur():
    if request.headers.get("Origin") not in (None, request.host_url.rstrip("/")):
        abort(403)
    with _kilit:
        DURUM["iptal"] = True
    return jsonify({"tamam": True})


@uygulama.route("/api/aciklamalar")
def api_aciklamalar():
    return jsonify(ACIKLAMA)


@uygulama.route("/api/duzeltmeler")
def api_duzeltmeler():
    """Sorun kodu -> somut duzeltme onerisi (raporda "Nasil duzeltilir")."""
    return jsonify({**kat.EK_DUZELTME, **DUZELTME})


@uygulama.route("/api/kategoriler")
def api_kategoriler():
    """Sorun kodu -> duzeltme kategorisi (Kural çözer / YZ önerir / Elle düzeltilir) ve risk."""
    return jsonify({"adlar": kat.KATEGORI_ADI, "kodlar": kat.kategori_tablosu()})


# ------------------------------------------------------------- yonetici modu
def _yonetici_klasoru(asama):
    """Yonetici uclarinin on kosulu: son tarama yonetici modunda yapilmis ve beklenen asamada olmali.
    Standart modda bu uclar hicbir kosulda siteye yazmaz."""
    with _kilit:
        y, mod, calisiyor = DURUM.get("yonetici"), DURUM.get("mod"), DURUM["calisiyor"]
    if mod != "yonetici" or not y:
        abort(409, "Yönetici modu etkin değil: son tarama standart modda yapıldı.")
    if calisiyor:
        abort(409, "Çalışan bir işlem var.")
    if asama and y.get("asama") not in asama:
        abort(409, "Bu işlem şu aşamada yapılamaz: " + str(y.get("asama")))
    return Path(y["klasor"]) if y.get("klasor") else None


@uygulama.errorhandler(409)
def _cakisma(e):
    return jsonify({"hata": e.description}), 409


@uygulama.route("/api/yonetici/plan")
def api_yonetici_plan():
    klasor = _yonetici_klasoru(("plan_hazir", "tamam", "geri_alindi"))
    plan = json.loads((klasor / "degisiklikler.json").read_text(encoding="utf-8"))
    oku_onbellek = {}
    oz = (klasor / "yedek" / "dosyalar")

    def oku(dosya):
        # uygulamadan sonra da onizleme ozgun (plan anindaki) icerige gore gosterilir
        if dosya not in oku_onbellek:
            yedekteki = oz / dosya
            kaynak = yedekteki if yedekteki.exists() else Path(plan["hedef"]["adaptor"]["kok"]) / dosya
            oku_onbellek[dosya] = kaynak.read_text(encoding="utf-8")
        return oku_onbellek[dosya]
    with _kilit:
        asama = DURUM["yonetici"].get("asama")
    return jsonify({"asama": asama, "klasor": str(klasor), **yonetici.plan_ozeti(plan, oku),
                    "ozet": _yonetici_ozeti(klasor)})


def _yonetici_uygula_isi(klasor, kararlar):
    try:
        rapor = yonetici.uygula_ve_dogrula(klasor, kararlar, SONUC_KOK, gunluk=_gunluk_yaz,
                                           tarama_kancalari={"iptal": lambda: DURUM["iptal"]})
        with _kilit:
            DURUM["yonetici"] = {"asama": "tamam", "klasor": str(klasor), "ozet": _yonetici_ozeti(klasor),
                                 "rapor": {k: rapor[k] for k in ("puanlar", "yeni_bulgular", "giderilen_bulgu_sayisi")} |
                                 {"durumlar": {kt: {d: len(v) for d, v in g.items()} for kt, g in rapor["durumlar"].items()}}}
    except Exception as e:
        with _kilit:
            DURUM["yonetici"] = {"asama": "hata", "klasor": str(klasor), "hata": str(e)}
        _gunluk_yaz("HATA: " + str(e))
    finally:
        with _kilit:
            DURUM["calisiyor"] = False
            DURUM["bitis"] = time.time()


@uygulama.route("/api/yonetici/uygula", methods=["POST"])
def api_yonetici_uygula():
    veri = _istek_dogrula()
    klasor = _yonetici_klasoru(("plan_hazir",))
    kararlar = veri.get("kararlar")
    if not isinstance(kararlar, dict):
        return jsonify({"hata": "Kararlar eksik."}), 400
    with _kilit:
        DURUM.update({"calisiyor": True, "iptal": False, "baslangic": time.time(), "bitis": None})
        DURUM["yonetici"]["asama"] = "uygulaniyor"
    _gunluk_yaz("Onaylı aşama: kararlar uygulanıyor (ilk yazmadan önce tam yedek alınır)")
    threading.Thread(target=_yonetici_uygula_isi, args=(klasor, kararlar), daemon=True).start()
    return jsonify({"tamam": True})


@uygulama.route("/api/yonetici/geri-al", methods=["POST"])
def api_yonetici_geri_al():
    _istek_dogrula()
    # otomatik asamadan sonra (plan_hazir) da yazilmis degisiklikler olabilir; geri alma tum asamalari kapsar
    klasor = _yonetici_klasoru(("plan_hazir", "tamam"))
    try:
        sonuc = yonetici.geri_al(klasor.parent, gunluk=_gunluk_yaz)
    except yonetici.YoneticiHatasi as e:
        return jsonify({"hata": str(e)}), 400
    with _kilit:
        DURUM["yonetici"]["asama"] = "geri_alindi"
        DURUM["yonetici"]["ozet"] = _yonetici_ozeti(klasor)
    return jsonify({"tamam": True, **sonuc})


@uygulama.route("/api/yonetici/rapor")
def api_yonetici_rapor():
    klasor = _yonetici_klasoru(("plan_hazir", "tamam", "geri_alindi"))
    yol = klasor / "yonetici_raporu.html"
    if not yol.exists():
        abort(404)
    return send_file(yol, mimetype="text/html")


def _tarama_bulgulari(sonuclar, hazir=None):
    """Arayuz icin site ozeti ve tarama geneli bulgular. Tarama bittiyse hesaplanmis bulgular
    (sitemap'e dayali yetim sayfalar dahil) kullanilir; surerken elde olan kayitlardan hesaplanir."""
    if hazir is None:
        site_modu = any(k.get("kesif_kaynagi") in ("bağlantı", "sitemap") for k in sonuclar)
        hazir = site_geneli(sonuclar) + baglanti_bulgulari([dict(k) for k in sonuclar], (), site_modu)
    return site_ozeti(sonuclar, hazir), hazir


@uygulama.route("/api/ozet")
def api_ozet():
    with _kilit:
        sonuclar, hazir = list(DURUM["sonuclar"]), DURUM["bulgular"]
    ozet, bulgular = _tarama_bulgulari(sonuclar, hazir)
    return jsonify({"ozet": ozet, "bulgular": bulgular})


@uygulama.route("/api/html")
def api_html():
    """Tum taramanin tek dosyalik HTML raporu."""
    with _kilit:
        sonuclar, hazir = list(DURUM["sonuclar"]), DURUM["bulgular"]
    ozet, bulgular = _tarama_bulgulari(sonuclar, hazir)
    baslik = ", ".join(sorted({site_adi(k["ad"]) for k in sonuclar if k.get("ad")})[:3]) or "SEO denetimi"
    metin = html_rapor(sonuclar, ozet, bulgular, baslik=baslik)
    return send_file(io.BytesIO(metin.encode("utf-8")), mimetype="text/html",
                     as_attachment=True, download_name="rapor.html")


@uygulama.route("/api/csv")
def api_csv():
    # site basina ozet.csv tarama sonunda zaten yazilir; bu uc yalnizca tum taramanin CSV'sini indirir
    with _kilit:
        sonuclar = list(DURUM["sonuclar"])
    metin = _csv_uret(sonuclar)
    return send_file(io.BytesIO(metin.encode("utf-8-sig")), mimetype="text/csv",
                     as_attachment=True, download_name="ozet.csv")


@uygulama.route("/api/rapor")
def api_rapor():
    with _kilit:
        sonuclar = list(DURUM["sonuclar"])
    ham = json.dumps(sonuclar, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    return send_file(io.BytesIO(ham), mimetype="application/json",
                     as_attachment=True, download_name="rapor.json")
