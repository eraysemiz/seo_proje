"""Masaustu arayuzunun yerel sunucusu: yalnizca 127.0.0.1, oturum jetonu ve Host denetimi.

Arayuz (masaustu/arayuz/) bu uclari cagirir; her sayi sonuc klasorlerindeki raporlardan okunur, burada
hesaplanmaz. Yazan her islem cekirdek uzerinden mevcut betikleri calistirir.
"""
import json
import logging
import secrets
import threading
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from werkzeug.serving import make_server

from . import ayarlar as ay
from . import durum as dr
from . import plan as pl
from . import sonuclar as sn
from .cekirdek import Cekirdek, KullaniciHatasi, dosya_ac

ARAYUZ = Path(__file__).resolve().parent / "arayuz"
RAPOR_DOSYALARI = {d for _, d in sn.RAPORLAR}
METIN_TURU = {".diff": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8"}


def _json_oku(yol):
    try:
        return json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sonuc_satiri(c, x):
    """Sonuclar listesi satiri: puan ve cozum orani yonetici_raporu.json'dan aynen okunur."""
    k = x["klasor"]
    oz = pl.rapor_ozeti(k)
    asamalar = [a for a in (oz or {}).get("asamalar", []) if a.get("olculdu")]
    deney = x["site"] in ("_deneyler", "rag_degerlendirme") or (
        x["tur"] == "Salt okunur" and not (k / "rapor.json").exists() and any(k.glob("*__*__r*")))
    return {"klasor": str(k), "site": x["site"], "zaman": x["zaman"],
            "tur": "Deney" if deney else x["tur"], "durum": x["durum"],
            "raporlar": [{"ad": ad, "dosya": Path(y).name} for ad, y in x["raporlar"]],
            "puanlar": [{"adi": a["adi"], "puan": a["puanlar"]["sayfa"]} for a in asamalar],
            "cozum_orani": asamalar[-1].get("cozum_orani") if asamalar else None,
            "cozulen": asamalar[-1].get("cozulen") if asamalar else None,
            "cozulebilir": asamalar[-1].get("cozulebilir") if asamalar else None,
            "sayaclar": (oz or {}).get("sayaclar") or None, "sayilar": (oz or {}).get("sayilar") or None,
            "geri_alindi": bool((oz or {}).get("geri_alindi"))}


def plan_verisi(klasor):
    plan = pl.plani_oku(klasor)
    onceki = pl.kararlari_oku(klasor)
    diffler = pl.diff_bloklari(klasor)
    degisiklikler = []
    for d in plan["degisiklikler"]:
        degisiklikler.append({
            **{k: d.get(k) for k in ("id", "kategori", "risk", "bulgu", "bulgu_aciklamasi", "url", "dosya", "konum",
                                     "yeni", "gerekce", "kaynaklar", "uretici", "etki", "yer_tutucu", "guven",
                                     "guven_nedenleri", "zorunlu_onay", "durum", "durum_nedeni", "asama",
                                     "onay_turu")},
            "duzenlenebilir": bool(d.get("duzenleme")), "durum_metni": pl.durum_metni(d),
            "gecersiz_neden": (d.get("dogrulama") or {}).get("neden", ""), "diff": diffler.get(d["id"], "")})
    return {"klasor": str(klasor), "bilgi": {k: v for k, v in sn.klasor_bilgisi(Path(klasor)).items()
                                             if k in ("site", "zaman", "durum")},
            "degisiklikler": degisiklikler, "elle": plan.get("elle") or [], "atlanan": plan.get("atlanan") or [],
            "secimler": pl.baslangic_secimleri(plan, onceki), "kural_hepsi": onceki["kural_hepsi"],
            "kilitli": pl.kilitli_mi(plan), "esik": pl.esik(plan, onceki), "ozet": pl.rapor_ozeti(klasor),
            "kategoriler": pl.KATEGORI_ADI, "bulgu_durum_adi": pl.BULGU_DURUM_ADI,
            "onaylar_var": (Path(klasor) / "onaylar.json").exists(),
            "otomatik_var": any(d.get("onay_turu") == "otomatik" for d in plan["degisiklikler"]),
            "rapor_var": (Path(klasor) / "yonetici_raporu.html").exists()}


def bilgi_tabani_verisi(kok):
    """ogretme/ klasorunun salt okunur ozeti."""
    ogretme = Path(kok) / "ogretme"
    parcalar = _json_oku(ogretme / "bilgi_tabani.json") or []
    alanlar, kaynaklar = {}, {}
    for p in parcalar:
        alanlar[p.get("alan", "?")] = alanlar.get(p.get("alan", "?"), 0) + 1
        baslik = (p.get("kaynak") or "").split("/")[2] if "//" in (p.get("kaynak") or "") else "?"
        kaynaklar[baslik] = kaynaklar.get(baslik, 0) + 1
    tarihler = sorted(p["erisim_tarihi"] for p in parcalar if p.get("erisim_tarihi"))
    guncelleme = sorted(p["kaynak_guncelleme"] for p in parcalar if p.get("kaynak_guncelleme"))
    onbellek = _json_oku(ogretme / "bilgi_tabani_gomme_cache.json") or {}
    kalibrasyon = _json_oku(ogretme / "kalibrasyon.json") or {}
    gb = ogretme / "geri_bildirim.jsonl"
    return {"parca": len(parcalar), "alanlar": sorted(alanlar.items(), key=lambda x: -x[1]),
            "kaynaklar": sorted(kaynaklar.items(), key=lambda x: -x[1]),
            "son_erisim": tarihler[-1] if tarihler else None, "ilk_erisim": tarihler[0] if tarihler else None,
            "en_eski_kaynak": guncelleme[0] if guncelleme else None,
            "onbellek": {m: len(v) for m, v in (onbellek.get("modeller") or {}).items()},
            "ornek": len(_json_oku(ogretme / "ornekler.json") or []),
            "kalibrasyon": kalibrasyon.get("alanlar") or {},
            "geri_bildirim": sum(1 for _ in gb.open(encoding="utf-8")) if gb.exists() else 0}


def uygulama_olustur(cekirdek, jeton, pencere_kutusu=None):
    c = cekirdek
    app = Flask(__name__, static_folder=None)
    pencere_kutusu = pencere_kutusu if pencere_kutusu is not None else {}

    def _sonuc_yolu(metin):
        """Yalnizca sonuclar/ altindaki bir klasor kabul edilir."""
        kok = c.kok()
        if not kok or not metin:
            raise KullaniciHatasi("Sonuç yok", "Sonuç klasörü seçilmedi.")
        yol = Path(metin).resolve()
        if not yol.is_relative_to((kok / "sonuclar").resolve()) or not yol.is_dir():
            raise KullaniciHatasi("Geçersiz klasör", "Sonuç klasörü bulunamadı: " + str(metin))
        return yol

    @app.before_request
    def _kapi():
        # DNS yeniden baglama ve baska sitelerden gelen isteklere karsi
        host = request.host.split(":")[0]
        if host != "127.0.0.1":
            return Response("yalnızca 127.0.0.1", status=403)
        if request.path == "/" and request.args.get("jeton") == jeton:
            return None
        if request.cookies.get("jeton") != jeton:
            return Response("oturum jetonu gerekli", status=403)
        if request.method != "GET" and request.headers.get("X-Jeton") != jeton:
            return Response("oturum jetonu gerekli", status=403)
        return None

    @app.errorhandler(KullaniciHatasi)
    def _kullanici(e):
        return jsonify({"hata": e.ileti, "baslik": e.baslik}), 400

    @app.errorhandler(OSError)
    @app.errorhandler(ValueError)
    @app.errorhandler(KeyError)
    def _okuma(e):
        return jsonify({"hata": "Dosya okunamadı ya da bozuk: " + str(e), "baslik": "Okuma hatası"}), 400

    @app.route("/")
    def ana():
        r = send_from_directory(ARAYUZ, "index.html")
        r.set_cookie("jeton", jeton, httponly=True, samesite="Strict")
        r.headers["Cache-Control"] = "no-store"
        return r

    @app.route("/varlik/<path:ad>")
    def varlik(ad):
        r = send_from_directory(ARAYUZ, ad)
        r.headers["Cache-Control"] = "no-store"
        return r

    @app.route("/api/baslangic")
    def baslangic():
        return jsonify({"ayar": c.ayar, "hatalar": ay.dogrula(c.ayar), "jeton": jeton, "ret_nedenleri": pl.RET_NEDENLERI,
                        "ayar_dosyasi": str(c.ayar_dosyasi or ay.ayar_dosyasi()), "varsayilan": ay.VARSAYILAN,
                        "plan_klasoru": str(c.plan_klasoru) if c.plan_klasoru else None,
                        "uygulama_adi": ay.UYGULAMA_ADI})

    @app.route("/api/durum")
    def durum():
        son = request.args.get("son", 0, type=int)
        with c.kilit:
            s = c.is_
            lm = c.durum["lm"]
            return jsonify({
                "lm": lm, "lm_iletisi": dr.lm_iletisi(lm, c.durum["lm_url"]) if lm else None, "lm_url": c.durum["lm_url"],
                "test": c.durum["test"], "web": c.durum["web"],
                "test_bizim": c.sunucular["test"] is not None, "web_bizim": c.sunucular["web"] is not None,
                "is": {"ad": s.ad, "iptal_edilebilir": s.iptal_edilebilir, "baslangic": s.baslangic,
                       "asama": c.asama} if s else None,
                "gunluk": c.gunluk_sonrasi(son),
                "bildirimler": [b for b in c.bildirimler if b["n"] > son],
                "biten": c.biten_is_sayisi,
                "son_is": {k: c.son_is[k] for k in ("ad", "kod", "iptal", "sure")} if c.son_is else None,
                "plan_klasoru": str(c.plan_klasoru) if c.plan_klasoru else None,
                "salt_sonuc": str(c.salt_sonuc) if c.salt_sonuc else None})

    @app.route("/api/modeller")
    def modeller():
        return jsonify(c.lm_modelleri())

    @app.route("/api/tara", methods=["POST"])
    def tara():
        v = request.get_json()
        c.tara(v["mod"], (v.get("adres") or "").split(), v.get("kok", "").strip(), bool(v.get("model")),
               v.get("sohbet", "").strip(), v.get("gomme", "").strip(), int(v.get("sayfa") or 60),
               int(v.get("derinlik") or 6), bool(v.get("site_modu")))
        return jsonify({"tamam": True})

    @app.route("/api/iptal", methods=["POST"])
    def iptal():
        c.iptal()
        return jsonify({"tamam": True})

    @app.route("/api/plan")
    def plan():
        klasor = _sonuc_yolu(request.args.get("klasor"))
        if not (klasor / "degisiklikler.json").exists():
            raise KullaniciHatasi("Plan yok", "Bu sonuç bir yönetici modu planı içermiyor.")
        return jsonify(plan_verisi(klasor))

    @app.route("/api/plan/sec", methods=["POST"])
    def plan_sec():
        c.plan_klasoru = _sonuc_yolu(request.get_json().get("klasor"))
        return jsonify({"tamam": True})

    @app.route("/api/onayla", methods=["POST"])
    def onayla():
        v = request.get_json()
        klasor = _sonuc_yolu(v.get("klasor"))
        argumanlar, uyarilar = pl.onay_argumanlari(pl.plani_oku(klasor), pl.kararlari_oku(klasor), v.get("secimler") or {},
                                                   bool(v.get("kural_hepsi")))
        if uyarilar and not v.get("zorla"):
            return jsonify({"uyarilar": uyarilar})
        if not argumanlar:
            raise KullaniciHatasi("Kaydedilecek karar yok", "Hiçbir öneri için karar verilmedi.")
        c.onaylari_kaydet(klasor, argumanlar)
        return jsonify({"tamam": True})

    @app.route("/api/uygula/ozet")
    def uygula_ozet():
        return jsonify(c.uygulama_ozeti(_sonuc_yolu(request.args.get("klasor"))))

    @app.route("/api/uygula", methods=["POST"])
    def uygula():
        c.uygula(_sonuc_yolu(request.get_json().get("klasor")))
        return jsonify({"tamam": True})

    @app.route("/api/sonuclar")
    def sonuclar():
        kok = c.kok()
        return jsonify({"liste": [sonuc_satiri(c, x) for x in (sn.listele(kok) if kok else [])]})

    @app.route("/api/geri-al/bilgi")
    def geri_al_bilgi():
        site = _sonuc_yolu(request.args.get("klasor")).parent
        bilgi = sn.son_uygulama(site)
        return jsonify({"site": site.name, "alinabilir": sn.geri_alinabilir(site), "zaman": (bilgi or {}).get("zaman"),
                        "sonuc": Path(bilgi["sonuc"]).name if bilgi else None,
                        "kok": ((bilgi or {}).get("adaptor") or {}).get("kok", "")})

    @app.route("/api/geri-al", methods=["POST"])
    def geri_al():
        c.geri_al(_sonuc_yolu(request.get_json().get("klasor")).parent)
        return jsonify({"tamam": True})

    @app.route("/rapor")
    def rapor():
        klasor, ad = _sonuc_yolu(request.args.get("klasor")), request.args.get("dosya", "")
        if ad not in RAPOR_DOSYALARI or not (klasor / ad).exists():
            return Response("Rapor bulunamadı.", status=404, mimetype="text/plain")
        tur = METIN_TURU.get(Path(ad).suffix, "text/html; charset=utf-8")
        return send_file(klasor / ad, mimetype=tur, max_age=0)

    @app.route("/api/klasor-ac", methods=["POST"])
    def klasor_ac():
        dosya_ac(_sonuc_yolu(request.get_json().get("klasor")))
        return jsonify({"tamam": True})

    @app.route("/api/tarayicida-ac", methods=["POST"])
    def tarayicida_ac():
        import webbrowser
        hedef = request.get_json().get("hedef")
        port = c.ayar["test_portu" if hedef == "test" else "web_portu"]
        webbrowser.open(f"http://127.0.0.1:{port}/")
        return jsonify({"tamam": True})

    @app.route("/api/sunucu", methods=["POST"])
    def sunucu():
        v = request.get_json()
        if v.get("ad") not in c.sunucular:
            raise KullaniciHatasi("Sunucu", "Bilinmeyen sunucu.")
        if v.get("islem") == "baslat":
            c.sunucu_baslat(v["ad"])
        else:
            c.sunucu_durdur(v["ad"])
        return jsonify({"tamam": True})

    @app.route("/api/test/<islem>", methods=["POST"])
    def test_islem(islem):
        if islem == "degerlendir":
            c.degerlendir(_sonuc_yolu(request.get_json().get("klasor")))
        elif islem in ("dogrula", "sifirla", "hash_karsilastir"):
            getattr(c, islem)()
        else:
            raise KullaniciHatasi("Test sitesi", "Bilinmeyen işlem.")
        return jsonify({"tamam": True})

    @app.route("/api/bilgi-tabani")
    def bilgi_tabani():
        kok = c.kok()
        if not kok:
            raise KullaniciHatasi("Proje klasörü yok", "Ayarlar ekranından proje klasörünü seçin.")
        return jsonify(bilgi_tabani_verisi(kok))

    @app.route("/api/bilgi-tabani/gomme", methods=["POST"])
    def gomme():
        c.gomme_yenile()
        return jsonify({"tamam": True})

    @app.route("/api/ayarlar", methods=["POST"])
    def ayarlar():
        c.ayarlari_kaydet(request.get_json())
        return jsonify({"ayar": c.ayar})

    @app.route("/api/tema", methods=["POST"])
    def tema():
        c.ayarlari_kaydet({"tema": request.get_json().get("tema", "")})
        return jsonify({"tamam": True})

    @app.route("/api/klasor-sec", methods=["POST"])
    def klasor_sec():
        pencere = pencere_kutusu.get("pencere")
        if pencere is None:
            raise KullaniciHatasi("Klasör seçimi", "Klasör seçimi yalnızca uygulama penceresinde çalışır; yolu elle yazın.")
        import webview
        secilen = pencere.create_file_dialog(webview.FileDialog.FOLDER)
        return jsonify({"klasor": secilen[0] if secilen else None})

    return app


class Sunucu:
    """Rastgele bir portta, yalnizca 127.0.0.1'de calisan arka plan sunucusu."""

    def __init__(self, cekirdek, pencere_kutusu=None, port=0):
        self.jeton = secrets.token_urlsafe(24)
        logging.getLogger("werkzeug").setLevel(logging.ERROR)   # 500 ms'lik yoklama gunlugu doldurmasin
        self._s = make_server("127.0.0.1", port, uygulama_olustur(cekirdek, self.jeton, pencere_kutusu), threaded=True)
        self.port = self._s.server_port
        threading.Thread(target=self._s.serve_forever, daemon=True).start()

    @property
    def adres(self):
        return f"http://127.0.0.1:{self.port}/?jeton={self.jeton}"

    def kapat(self):
        self._s.shutdown()


def calistir_arayuz(ayar_dosyasi=None):
    """Uygulama penceresini acar; pencere kapanana kadar bekler, sonra alt surecleri kapatir."""
    import webview
    c = Cekirdek(ayar_dosyasi)
    kutu = {}
    s = Sunucu(c, kutu)
    pencere = webview.create_window(ay.UYGULAMA_ADI, s.adres, width=1360, height=860, min_size=(1100, 680),
                                    background_color="#F9FBFC")
    kutu["pencere"] = pencere
    pencere_kapanisi_bagla(c, pencere)
    webview.start(gui="edgechromium", private_mode=True)
    c.kapat()
    s.kapat()
    return c


def pencere_kapanisi_bagla(c, pencere):
    def kapaniyor():
        olabilir, ileti = c.kapanabilir_mi()
        if not olabilir:
            pencere.create_confirmation_dialog("Bekleyin", ileti)
            return False
        if ileti and not pencere.create_confirmation_dialog("Çıkılsın mı?", ileti):
            return False
        return True
    pencere.events.closing += kapaniyor
