"""Yerel web arayuzu (Flask).

Tarama arka planda bir is parcaciginda calisir; arayuz ilerlemeyi duzenli araliklarla
sorarak gunlugu ve sonuc tablosunu gunceller. Sunucu yalnizca bu bilgisayardan
erisilebilir sekilde baslatilir.
"""
import csv
import io
import json
import threading
import time
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request, send_file

from . import canli
from .boru import VARSAYILAN_AYARLAR, alt_siteleri_kesfet, analiz_et, hedefleri_hazirla
from .kurallar import ACIKLAMA, acikla
from .llm import model_durumlari
from .ogretme import KOSULLAR

KOK = Path(__file__).resolve().parent.parent
SONUC_KOK = KOK / "sonuclar"     # tum tarama ciktilari bu klasorun altina yazilir
uygulama = Flask(__name__, template_folder="sablonlar", static_folder="statik")

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
}


def _gunluk_yaz(mesaj):
    with _kilit:
        DURUM["gunluk"].append(time.strftime("%H:%M:%S") + "  " + str(mesaj))
        del DURUM["gunluk"][:-400]      # gunluk sinirsiz buyumesin


def _sifirla(toplam, cikti):
    with _kilit:
        DURUM.update({"calisiyor": True, "iptal": False, "toplam": toplam, "biten": 0,
                      "gunluk": [], "sonuclar": [], "cikti_klasoru": str(cikti),
                      "baslangic": time.time(), "bitis": None, "hata": None})


def _tarama_isi(hedefler, ayarlar, ogretme_klasoru, cikti):
    """Arka planda calisan tarama. Her sayfa bittiginde DURUM guncellenir."""
    def gunluk(m):
        _gunluk_yaz(m)

    def iptal():
        return DURUM["iptal"]

    try:
        # her sayfa bittiginde arayuzun gorebilmesi icin sonuclari adim adim isliyoruz
        sonuclar = []
        for i, hedef in enumerate(hedefler, 1):
            if iptal():
                gunluk("Tarama durduruldu.")
                break
            ad = hedef.get("url") or Path(hedef.get("yol", "")).name
            gunluk("[" + str(i) + "/" + str(len(hedefler)) + "] " + ad)
            try:
                kayit = analiz_et(hedef, ayarlar, ogretme_klasoru, cikti, gunluk=gunluk)
            except Exception as e:          # tek sayfanin hatasi tum taramayi durdurmasin
                kayit = {"ad": ad, "kaynak_turu": hedef["tur"],
                         "hata": type(e).__name__ + ": " + str(e)}
                gunluk("HATA: " + kayit["hata"])
            sonuclar.append(kayit)
            with _kilit:
                DURUM["biten"] = i
                DURUM["sonuclar"] = sonuclar
            (Path(cikti) / "rapor.json").write_text(
                json.dumps(sonuclar, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            if hedef["tur"] == "canli" and i < len(hedefler) and ayarlar.get("bekleme_sn"):
                time.sleep(ayarlar["bekleme_sn"])    # sunucuyu yormamak icin nazik bekleme
        gunluk("Tarama tamamlandi. Cikti klasoru: " + str(cikti))
    except Exception as e:
        with _kilit:
            DURUM["hata"] = type(e).__name__ + ": " + str(e)
        _gunluk_yaz("BEKLENMEYEN HATA: " + str(e))
    finally:
        with _kilit:
            DURUM["calisiyor"] = False
            DURUM["bitis"] = time.time()


# ------------------------------------------------------------------- sayfalar
@uygulama.route("/")
def anasayfa():
    return render_template("index.html", kosullar=KOSULLAR,
                           varsayilan=VARSAYILAN_AYARLAR, kok=str(KOK))


@uygulama.route("/api/modeller")
def api_modeller():
    url = request.args.get("url") or VARSAYILAN_AYARLAR["url"]
    try:
        return jsonify({"modeller": model_durumlari(url), "hata": None})
    except requests.RequestException as e:
        return jsonify({"modeller": [], "hata": "LM Studio'ya ulasilamadi: " + type(e).__name__})


@uygulama.route("/api/kesif", methods=["POST"])
def api_kesif():
    veri = request.get_json(force=True)
    sonuc = alt_siteleri_kesfet(veri.get("adres", ""))
    return jsonify(sonuc)


@uygulama.route("/api/tara", methods=["POST"])
def api_tara():
    if DURUM["calisiyor"]:
        return jsonify({"hata": "Zaten calisan bir tarama var."}), 409
    veri = request.get_json(force=True)
    mod = veri.get("mod", "canli")
    hedefler = hedefleri_hazirla(mod, veri.get("adresler"), veri.get("klasor"))
    if not hedefler:
        return jsonify({"hata": "Analiz edilecek adres veya dosya bulunamadi."}), 400

    ayarlar = {**VARSAYILAN_AYARLAR}
    for k in ("llm_kullan", "url", "model", "kosul", "embed_model", "embed_url", "retry",
              "max_tokens", "timeout", "ornek_sayisi", "json_schema", "dil", "uy_robots",
              "bekleme_sn", "zaman_asimi"):
        if k in veri and veri[k] not in ("", None):
            ayarlar[k] = veri[k]
    for sayi in ("retry", "max_tokens", "timeout", "ornek_sayisi", "zaman_asimi"):
        ayarlar[sayi] = int(ayarlar[sayi])
    ayarlar["bekleme_sn"] = float(ayarlar["bekleme_sn"])
    ayarlar["llm_kullan"] = bool(ayarlar["llm_kullan"])
    if ayarlar["llm_kullan"] and not ayarlar.get("model"):
        return jsonify({"hata": "Dil modeli secilmedi. Model listesini yenileyin "
                                "veya 'Yalnizca kural denetimi' secenegini isaretleyin."}), 400

    # ad verilmezse tarihli bir klasor; goreli ad verilirse yine sonuclar/ altina yazilir
    cikti = Path(veri.get("cikti") or ("sonuc_" + time.strftime("%Y%m%d_%H%M%S")))
    if not cikti.is_absolute():
        cikti = SONUC_KOK / cikti
    cikti.mkdir(parents=True, exist_ok=True)
    ogretme_klasoru = veri.get("ogretme_klasoru") or str(KOK / "ogretme")

    canli.onbellek_temizle()
    _sifirla(len(hedefler), cikti)
    _gunluk_yaz("Tarama basladi: " + str(len(hedefler)) + " hedef, mod=" + mod +
                (", model=" + str(ayarlar["model"]) + ", kosul=" + ayarlar["kosul"]
                 if ayarlar["llm_kullan"] else ", yalnizca kural denetimi"))
    is_parcacigi = threading.Thread(target=_tarama_isi,
                                    args=(hedefler, ayarlar, ogretme_klasoru, cikti), daemon=True)
    is_parcacigi.start()
    return jsonify({"tamam": True, "toplam": len(hedefler), "cikti": str(cikti)})


@uygulama.route("/api/durum")
def api_durum():
    with _kilit:
        return jsonify({k: DURUM[k] for k in
                        ("calisiyor", "toplam", "biten", "gunluk", "sonuclar",
                         "cikti_klasoru", "baslangic", "bitis", "hata")})


@uygulama.route("/api/durdur", methods=["POST"])
def api_durdur():
    with _kilit:
        DURUM["iptal"] = True
    return jsonify({"tamam": True})


@uygulama.route("/api/aciklamalar")
def api_aciklamalar():
    return jsonify(ACIKLAMA)


def _csv_uret(sonuclar):
    sutunlar = ["ad", "kaynak_turu", "durum_kodu", "model", "kosul", "ogretme_yontemi",
                "once_sorun_sayisi", "sonra_sorun_sayisi", "once_puan", "sonra_puan",
                "sayfa_sorun_sayisi", "site_sorun_sayisi", "cozum_orani", "toplam_cozum_orani",
                "sure_sn", "sure_toplam_sn", "hata"]
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=";")
    yazici.writerow(sutunlar + ["kabul_edilen_oneri", "reddedilen_oneri", "cozulen", "kalan"])
    for k in sonuclar:
        yazici.writerow([k.get(s, "") for s in sutunlar] + [
            len(k.get("fixes", [])), len(k.get("reddedilen", [])),
            ", ".join(k.get("cozulen_sorunlar", [])), ", ".join(k.get("kalan_sorunlar", []))])
    return tampon.getvalue()


@uygulama.route("/api/csv")
def api_csv():
    with _kilit:
        sonuclar = list(DURUM["sonuclar"])
        cikti = DURUM["cikti_klasoru"]
    metin = _csv_uret(sonuclar)
    if cikti:
        (Path(cikti) / "ozet.csv").write_text(metin, encoding="utf-8-sig")
    return send_file(io.BytesIO(metin.encode("utf-8-sig")), mimetype="text/csv",
                     as_attachment=True, download_name="ozet.csv")


@uygulama.route("/api/rapor")
def api_rapor():
    with _kilit:
        sonuclar = list(DURUM["sonuclar"])
    ham = json.dumps(sonuclar, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    return send_file(io.BytesIO(ham), mimetype="application/json",
                     as_attachment=True, download_name="rapor.json")
