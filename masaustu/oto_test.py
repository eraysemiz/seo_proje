"""Arayuz uzerinden tam test dongusu (kendi kendini sinama).

Gercek pencere acilir ve dugmelere gercekten tiklanir (DOM uzerinden); onay pencereleri otomatik yanitlanip
rapora yazilir. Gosterilen sayilar yonetici_raporu.json ve HTML raporla karsilastirilir, arayuzun en uzun
takilma suresi olculur. Sonunda uygulama kapatilir ve baslatilan sureclerin kapandigi denetlenir.
Dil modeli kullanilmaz; SEO_OTO_MODELLI=1 ve hazir LM Studio ile modelli calisir.

    py masaustu/baslat.py --oto-test rapor.json
    "SEO_Denetim.exe" --oto-test rapor.json
"""
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

from . import api, durum
from . import ayarlar as ay
from . import plan as pl
from .cekirdek import Cekirdek

ADIM_SURESI = 900


def surec_yasiyor(pid):
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = ctypes.c_void_p
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    kod = ctypes.c_ulong()
    k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(kod))
    k32.CloseHandle(ctypes.c_void_p(h))
    return kod.value == 259                  # STILL_ACTIVE


def http_kodu(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as y:
            return y.status
    except Exception as e:                   # noqa: BLE001 - rapora yazilir
        return type(e).__name__


class Senaryo:
    def __init__(self, cekirdek, pencere, sunucu, rapor_yolu):
        self.c, self.p, self.s = cekirdek, pencere, sunucu
        self.rapor_yolu = Path(rapor_yolu)
        self.rapor = {"frozen": bool(getattr(sys, "frozen", False)), "python": sys.version.split()[0],
                      "calistirilabilir": sys.executable, "proje_koku": cekirdek.ayar["proje_koku"],
                      "adimlar": [], "diyaloglar": [], "sayi_eslesmeleri": []}

    # ---- pencere yardimcilari
    def js(self, kod):
        return self.p.evaluate_js(kod)

    def bekle(self, kosul, sure=20):
        bitis = time.time() + sure
        while time.time() < bitis:
            if kosul():
                return True
            time.sleep(0.2)
        return False

    def var(self, secici, sure=20):
        return self.bekle(lambda: self.js(f"!!document.querySelector({json.dumps(secici)})"), sure)

    def tikla(self, secici, sure=20):
        kosul = f"(()=>{{const b=document.querySelector({json.dumps(secici)});return !!b&&!b.disabled}})()"
        if not self.bekle(lambda: self.js(kosul), sure):
            raise TimeoutError("düğme yok ya da kapalı: " + secici)
        self.js(f"document.querySelector({json.dumps(secici)}).click()")

    def metin(self, secici):
        return self.js(f"(document.querySelector({json.dumps(secici)})||{{}}).textContent||''")

    def git(self, ekran):
        self.js(f"location.hash='#/{ekran}'")
        self.bekle(lambda: self.js(f"!!document.querySelector('#menu-{ekran}[aria-current=page]')"), 10)
        time.sleep(0.5)

    def modal(self, yanit="#modal-evet", sure=20):
        """Acilan pencereyi kaydeder ve yanitlar; basligi ve iletiyi dondurur."""
        if not self.var(".modal", sure):
            raise TimeoutError("onay penceresi açılmadı")
        d = {"baslik": self.metin(".modal h2"), "ileti": self.metin(".modal p")}
        self.rapor["diyaloglar"].append(d)
        self.tikla(yanit)
        self.bekle(lambda: not self.js("!!document.querySelector('.modal')"), 5)
        return d

    def is_bekle(self, baslat, sure=ADIM_SURESI):
        once = self.c.biten_is_sayisi
        baslat()
        if not self.bekle(lambda: self.c.biten_is_sayisi > once, sure):
            raise TimeoutError("iş zamanında bitmedi")
        time.sleep(1.2)                      # arayuz yoklamasi yeni durumu gorsun
        return self.c.son_is

    def adim(self, ad, fn):
        self.js("window.__takilma=0")
        bas = time.time()
        kayit = {"ad": ad}
        try:
            kayit.update(fn() or {})
        except Exception as e:               # noqa: BLE001
            kayit.update({"basarili": False, "hata": f"{type(e).__name__}: {e}", "iz": traceback.format_exc()})
        kayit["sure_sn"] = round(time.time() - bas, 1)
        kayit["arayuz_en_uzun_takilma_ms"] = self.js("Math.round(window.__takilma||0)")
        self.rapor["adimlar"].append(kayit)
        print(("✓ " if kayit.get("basarili") else "✗ ") + ad, flush=True)
        return kayit

    def _is_sonucu(self, son, beklenen=None):
        satirlar = son["satirlar"] if son else []
        tamam = bool(son) and son["kod"] == 0 and not son["iptal"]
        if beklenen:
            tamam = tamam and any(beklenen in s for s in satirlar)
        return {"basarili": tamam, "kod": son and son["kod"], "pid": son and son["pid"], "cikti_son": satirlar[-8:]}

    def sayilari_karsilastir(self, klasor, an):
        """Ekrandaki sayilar = yonetici_raporu.json = HTML rapor."""
        oz = pl.rapor_ozeti(klasor)
        s, son = oz["sayaclar"], [a for a in oz["asamalar"] if a.get("olculdu")][-1]
        self.git("analiz")
        self.var("#k-aktif")
        ekran = {"aktif": self.metin("#k-aktif"), "cozulen": self.metin("#k-cozulen"), "oran": self.metin("#k-oran"),
                 "serit": {k: self.metin(f'[data-sayi="{k}"]') for k, n in oz["sayilar"].items() if n},
                 "puan": self.metin(f'[data-puan="{son["ad"]}"]')}
        json_ = {"aktif": str(s["aktif"]), "cozulen": str(s["cozulen"]), "oran": f"%{round(100 * son['cozum_orani'])}",
                 "serit": {k: str(n) for k, n in oz["sayilar"].items() if n}, "puan": str(son["puanlar"]["sayfa"])}
        html = (Path(klasor) / "yonetici_raporu.html").read_text(encoding="utf-8")
        html_var = {k: bool(re.search(rf"(?<![\d]){re.escape(json_[k])}(?![\d])", html))
                    for k in ("aktif", "cozulen", "oran", "puan")}
        tamam = ekran == json_ and all(html_var.values())
        self.rapor["sayi_eslesmeleri"].append({"an": an, "ekran": ekran, "json": json_, "html_rapor_iceriyor": html_var,
                                               "eslesti": tamam})
        return tamam

    # ---- adimlar
    def calistir(self):
        c = self.c
        a = c.ayar
        site_url = f"http://127.0.0.1:{a['test_portu']}/"
        self.js("(()=>{let s=performance.now();setInterval(()=>{const n=performance.now();"
                "window.__takilma=Math.max(window.__takilma||0,n-s-100);s=n},100)})()")
        lm = durum.lm_durumu(a["lm_url"], [a["sohbet_modeli"], a["gomme_modeli"]])
        modelli = os.environ.get("SEO_OTO_MODELLI") == "1" and lm["erisim"] and not lm["eksik"] and not lm["yuklu_degil"]
        self.rapor["modelli"] = modelli

        def lm_kapali():
            # kapali LM Studio, adres kullanilmayan bir porta cevrilerek benzetilir; LM Studio'ya istek gitmez
            gercek = a["lm_url"]
            a["lm_url"] = "http://127.0.0.1:9/v1"
            try:
                c.durum_yenile()
                self.bekle(lambda: "kapalı" in self.metin("#d-lm"), 15)
                cubuk = self.metin("#d-lm")
                self.git("analiz")
                self.js("document.querySelector('#mod-yonetici').click()")
                time.sleep(0.4)
                if not self.js("document.querySelector('#f-model').checked"):
                    self.tikla("#f-model")
                    time.sleep(0.4)
                self.tikla("#tara")
                d = self.modal("#modal-tamam")
                baslamadi = c.is_ is None
            finally:
                a["lm_url"] = gercek
                c.durum_yenile()
            return {"basarili": baslamadi and "kapalı" in cubuk and "ulaşılamadı" in d["ileti"], "ileti": d["ileti"],
                    "durum_cubugu": cubuk}
        self.adim("LM Studio kapalıyken modelli analiz anlaşılır hata veriyor", lm_kapali)

        def test_baslat():
            self.git("test")
            self.tikla("#t-baslat")
            acik = self.bekle(lambda: durum.port_acik(a["test_portu"]), 20)
            self.bekle(lambda: "açık" in self.metin("#d-test"), 10)
            return {"basarili": acik, "http": http_kodu(site_url), "pid": c.sunucular["test"].pid,
                    "durum_cubugu": self.metin("#d-test")}
        self.adim("Test sitesi başlat", test_baslat)

        self.adim("Doğrula", lambda: self._is_sonucu(self.is_bekle(lambda: self.tikla("#t-dogrula")), "47/47"))

        def tara():
            self.git("analiz")
            self.tikla("#mod-yonetici")
            time.sleep(0.4)
            secili = self.js("document.querySelector('#f-model').checked")
            if secili != bool(modelli):
                self.tikla("#f-model")
                time.sleep(0.4)
            son = self.is_bekle(lambda: self.tikla("#tara"))
            sonuc = self._is_sonucu(son, "Sonuç klasörü:")
            sonuc["plan_klasoru"] = str(c.plan_klasoru)
            plan = pl.plani_oku(c.plan_klasoru)
            sonuc["otomatik_uygulanan"] = sum(1 for d in plan["degisiklikler"]
                                              if d["durum"] == "uygulandi" and d.get("asama") == "otomatik")
            sonuc["asamalar"] = pl.asamalar(plan)
            sonuc["sayilar_eslesti"] = self.sayilari_karsilastir(c.plan_klasoru, "otomatik sonrası")
            sonuc["basarili"] = (sonuc["basarili"] and sonuc["otomatik_uygulanan"] > 0 and sonuc["asamalar"] == ["otomatik"]
                                 and sonuc["sayilar_eslesti"])
            return sonuc
        tarama = self.adim("Yönetici taraması ve özet kartları", tara)
        klasor = Path(tarama.get("plan_klasoru") or ".")
        kutu = {}

        def onay():
            self.git("onay")
            self.var(".satir")
            # bekleyen bir oneriyi onayla (yuksek riskli degil ve yer tutucusuz)
            plan = pl.plani_oku(klasor)
            yz = next((d for d in plan["degisiklikler"] if d["risk"] != "yuksek" and not d.get("yer_tutucu")
                       and d["durum"] not in ("gecersiz", "uygulandi", "basarisiz", "reddedildi")), None)
            if yz:
                self.tikla(f'.satir[data-id="{yz["id"]}"]')
                self.var("#k-onay")
                self.tikla("#k-onay")
            self.var("#diff")
            kutu["yan_yana_diff"] = self.js("document.querySelectorAll('#diff .bas').length") == 2
            # arama ve filtre gercekten suzer
            once = self.js("document.querySelectorAll('.satir').length")
            self.js("(()=>{const a=document.querySelector('#f-ara');a.value='zzzyok';a.dispatchEvent(new Event('input'))})()")
            time.sleep(0.2)
            suzuldu = self.js("document.querySelectorAll('.satir').length") == 0
            self.js("(()=>{const a=document.querySelector('#f-ara');a.value='';a.dispatchEvent(new Event('input'))})()")
            # otomatik asamada yazilmis bir degisiklik reddedilir: onayli asamada geri cekilmeli
            self.tikla('[data-sekme="uygulanan"]')
            time.sleep(0.5)
            geri = next(d for d in plan["degisiklikler"] if d["durum"] == "uygulandi" and d.get("asama") == "otomatik")
            self.tikla(f'.satir[data-id="{geri["id"]}"]')
            self.var("#k-ret")
            self.tikla("#k-ret")
            kutu["geri"] = geri["id"]
            self.tikla("#kural-hepsi")
            time.sleep(0.2)
            son = self.is_bekle(lambda: self.tikla("#kaydet"))
            sonuc = self._is_sonucu(son, "Kararlar kaydedildi")
            kararlar = pl.kararlari_oku(klasor)
            sonuc.update({"onayli": yz and yz["id"], "geri_cekilecek": geri["id"], "liste_uzunlugu": once,
                          "arama_suzdu": suzuldu, "yan_yana_diff": kutu["yan_yana_diff"],
                          "onaylanan": pl.onaylanan_sayisi(pl.plani_oku(klasor), kararlar)})
            sonuc["basarili"] = sonuc["basarili"] and suzuldu and kutu["yan_yana_diff"]
            return sonuc
        self.adim("Onay ekranı: karar, arama, yan yana diff, kaydet", onay)

        def uygula():
            self.git("onay")
            self.var("#uygula")

            def bas():
                self.tikla("#uygula")
                self.modal()
            son = self.is_bekle(bas)
            sonuc = self._is_sonucu(son, "Aşamalara göre metrikler")
            plan = pl.plani_oku(klasor)
            d = next(x for x in plan["degisiklikler"] if x["id"] == kutu.get("geri"))
            sonuc.update({"asamalar": pl.asamalar(plan), "geri_cekilen_durum": d["durum"],
                          "sayilar_eslesti": self.sayilari_karsilastir(klasor, "onay sonrası")})
            sonuc["basarili"] = (sonuc["basarili"] and sonuc["asamalar"] == ["otomatik", "onayli"]
                                 and d["durum"] == "reddedildi" and sonuc["sayilar_eslesti"])
            return sonuc
        self.adim("Onaylı aşamayı uygula", uygula)

        def degerlendir():
            self.git("test")
            self.var("#t-deg-sec")
            self.js("(()=>{const s=document.querySelector('#t-deg-sec');s.value=" + json.dumps(str(klasor)) +
                    ";s.dispatchEvent(new Event('change'))})()")
            time.sleep(0.5)
            return self._is_sonucu(self.is_bekle(lambda: self.tikla("#t-deg")), "Rapor:")
        self.adim("Değerlendir", degerlendir)

        def sonuclar():
            self.git("sonuclar")
            secici = f'tr[data-k={json.dumps(str(klasor), ensure_ascii=False)}]'
            if not self.var(secici):
                raise TimeoutError("sonuç listede yok")
            self.tikla(secici)
            self.var("#rapor-cerceve")
            yuklendi = self.bekle(lambda: self.js("(()=>{const f=document.querySelector('#rapor-cerceve');return !!(f&&f.contentDocument&&f.contentDocument.body&&f.contentDocument.body.textContent.length>200)})()"), 20)
            satir = self.js(f"document.querySelector({json.dumps(secici)}).innerText")
            oz = pl.rapor_ozeti(klasor)
            puanlar = " → ".join(str(a["puanlar"]["sayfa"]) for a in oz["asamalar"] if a.get("olculdu"))
            return {"basarili": yuklendi and puanlar in satir, "satir": satir, "puan_yolu": puanlar}
        self.adim("Sonuçlar: rapor uygulama içinde", sonuclar)

        def geri_al():
            self.var("#s-geri")

            def bas():
                self.tikla("#s-geri")
                self.modal()
            sonuc = self._is_sonucu(self.is_bekle(bas), "eşleşiyor")
            oz = pl.rapor_ozeti(klasor)
            sonuc["durumlar"] = {d: n for d, n in (oz or {}).get("sayilar", {}).items() if n}
            sonuc["basarili"] = (sonuc["basarili"] and bool(oz and oz["geri_alindi"])
                                 and set(sonuc["durumlar"]) <= {"onay_bekliyor", "elle", "basarisiz"})
            return sonuc
        self.adim("Geri al", geri_al)

        def iptal():
            self.git("analiz")
            self.tikla("#mod-salt")
            time.sleep(0.4)
            if self.js("document.querySelector('#f-model').checked"):
                self.tikla("#f-model")
                time.sleep(0.4)
            once = c.biten_is_sayisi
            self.js("(()=>{const a=document.querySelector('#f-adres');a.value=" + json.dumps(site_url) +
                    ";a.dispatchEvent(new Event('input',{bubbles:true}))})()")
            self.tikla("#tara")
            self.bekle(lambda: c.is_ is not None, 15)
            # calisirken ikinci is engellenir (cakisma)
            time.sleep(1)
            dugme_kapali = self.js("document.querySelector('#tara').disabled")
            time.sleep(2)
            pid = c.is_ and c.is_.pid
            calisiyordu = bool(pid) and surec_yasiyor(pid)
            self.tikla("#iptal")
            self.bekle(lambda: c.biten_is_sayisi > once, 30)
            kapandi = self.bekle(lambda: not surec_yasiyor(pid), 10)
            self.tikla("#mod-yonetici")
            return {"basarili": calisiyordu and c.son_is["iptal"] and kapandi and dugme_kapali, "pid": pid,
                    "surec_kapandi": kapandi, "cakisma_dugmesi_kapali": dugme_kapali}
        self.adim("Uzun işlem sırasında iptal", iptal)

        def sifirla():
            self.git("test")

            def bas():
                self.tikla("#t-sifirla")
                self.modal()
            return self._is_sonucu(self.is_bekle(bas), "eşleşiyor")
        self.adim("Sıfırla", sifirla)
        self.adim("Hash karşılaştır", lambda: self._is_sonucu(self.is_bekle(lambda: self.tikla("#t-hash")), "eşleşiyor"))
        self.adim("Doğrula (sıfırlama sonrası)", lambda: self._is_sonucu(self.is_bekle(lambda: self.tikla("#t-dogrula")), "47/47"))

        def ekranlar():
            sonuc = {}
            for ekran, secici in (("bilgi", "#b-gomme"), ("ayarlar", "#a-kaydet"), ("onay", ".onay-ust"), ("sonuclar", "#s-ara")):
                self.git(ekran)
                sonuc[ekran] = self.var(secici, 10)
            self.git("ayarlar")
            self.tikla("#a-koyu")
            koyu = self.bekle(lambda: self.js("document.documentElement.dataset.tema") == "koyu", 5)
            self.tikla("#a-acik")
            return {"basarili": all(sonuc.values()) and koyu, "ekranlar": sonuc, "koyu_tema": koyu}
        self.adim("Bilgi tabanı, Ayarlar ve tema", ekranlar)

        def web():
            if durum.port_acik(a["web_portu"]):
                return {"basarili": False, "hata": "web portu zaten kullanımda"}
            self.git("ayarlar")
            self.tikla("#a-web-baslat")
            acik = self.bekle(lambda: durum.port_acik(a["web_portu"]), 30)
            return {"basarili": acik and http_kodu(f"http://127.0.0.1:{a['web_portu']}/") == 200,
                    "pid": c.sunucular["web"] and c.sunucular["web"].pid}
        self.adim("Tarayıcı arayüzünü başlat", web)

        # kapanis: test sitesi ve web arayuzu acikken uygulama kapatilir
        self.rapor["kapanis_oncesi_sunucular"] = {k: s.pid for k, s in c.sunucular.items() if s}
        self.rapor["baslatilan_pidler"] = list(c.baslatilan_pidler)


def calistir(rapor_yolu, ayar_dosyasi=None):
    import webview
    c = Cekirdek(ayar_dosyasi)
    kutu = {}
    s = api.Sunucu(c, kutu)
    pencere = webview.create_window(ay.UYGULAMA_ADI, s.adres, width=1360, height=860)
    kutu["pencere"] = pencere
    senaryo = Senaryo(c, pencere, s, rapor_yolu)

    def yurut():
        try:
            senaryo.bekle(lambda: pencere.evaluate_js("!!(window.SEO&&window.SEO.durum)"), 30)
            senaryo.calistir()
        except Exception:                    # noqa: BLE001
            senaryo.rapor["beklenmeyen"] = traceback.format_exc()
        finally:
            pencere.destroy()
    webview.start(yurut, gui="edgechromium", private_mode=True)
    c.kapat()
    s.kapat()

    time.sleep(1)
    pidler = senaryo.rapor.get("baslatilan_pidler", c.baslatilan_pidler)
    a = c.ayar
    senaryo.rapor["kapanis"] = {"yasayan_surecler": [p for p in pidler if surec_yasiyor(p)],
                                "test_portu_acik": durum.port_acik(a["test_portu"]),
                                "web_portu_acik": durum.port_acik(a["web_portu"])}
    adimlar = senaryo.rapor["adimlar"]
    senaryo.rapor["ozet"] = {"adim": len(adimlar), "basarili": sum(bool(x.get("basarili")) for x in adimlar),
                             "tamamlandi": "beklenmeyen" not in senaryo.rapor,
                             "temiz_kapanis": not any(senaryo.rapor["kapanis"].values())}
    Path(rapor_yolu).write_text(json.dumps(senaryo.rapor, ensure_ascii=False, indent=2), encoding="utf-8")
    ozet = senaryo.rapor["ozet"]
    return 0 if ozet["adim"] == ozet["basarili"] and ozet["tamamlandi"] and ozet["temiz_kapanis"] else 1
