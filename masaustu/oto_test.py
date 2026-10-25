"""Arayuz uzerinden tam test dongusu (kendi kendini sinama).

Gercek pencere acilir ve dugmelerin cagirdigi yontemler sirayla calistirilir; onay/hata
diyaloglari otomatik yanitlanip rapora yazilir. Senaryo ayri bir is parcaciginda yurur, arayuz
islemleri ana is parcacigina aktarilir; boylece olay dongusunun uzun islerde takilip takilmadigi
(en uzun bekleme suresi) de olculur. Sonunda uygulama kapatilir ve baslatilan sureclerin
kapandigi denetlenir.

    py masaustu/baslat.py --oto-test rapor.json
    "SEO_Denetim.exe" --oto-test rapor.json
"""
import json
import os
import sys
import threading
import time
import traceback
import types
import urllib.request
from pathlib import Path

import tkinter as tk

from . import durum
from . import plan as pl
from . import uygulama as arayuz

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
    def __init__(self, uyg, rapor_yolu):
        self.u = uyg
        self.rapor_yolu = Path(rapor_yolu)
        self.rapor = {"frozen": bool(getattr(sys, "frozen", False)), "python": sys.version.split()[0],
                      "calistirilabilir": sys.executable, "proje_koku": uyg.ayar["proje_koku"],
                      "adimlar": [], "diyaloglar": []}
        self._en_uzun = 0.0
        self._son_tik = time.perf_counter()
        uyg.onay_sor = lambda b, i: self._diyalog("onay", b, i, True)
        uyg.hata_goster = lambda b, i: self._diyalog("hata", b, i)
        uyg.bilgi_goster = lambda b, i: self._diyalog("bilgi", b, i)
        arayuz.webbrowser = types.SimpleNamespace(open=lambda *a, **k: True)   # testte tarayici acilmasin
        uyg.k.after(50, self._tik)

    # ---- yardimcilar
    def _diyalog(self, tur, baslik, ileti, yanit=None):
        self.rapor["diyaloglar"].append({"tur": tur, "baslik": baslik, "ileti": ileti})
        return yanit

    def _tik(self):
        simdi = time.perf_counter()
        self._en_uzun = max(self._en_uzun, simdi - self._son_tik)
        self._son_tik = simdi
        self.u.k.after(50, self._tik)

    def ui(self, fn, *a):
        bitti, kutu = threading.Event(), {}

        def calis():
            try:
                kutu["r"] = fn(*a)
            except Exception as e:           # noqa: BLE001 - senaryo is parcacigina aktarilir
                kutu["e"] = e
            finally:
                bitti.set()
        self.u.k.after(0, calis)
        if not bitti.wait(60):
            raise TimeoutError("arayüz 60 sn yanıt vermedi")
        if "e" in kutu:
            raise kutu["e"]
        return kutu.get("r")

    def is_calistir(self, fn, *a, sure=ADIM_SURESI):
        """fn bir is baslatir (dugme); isin bitmesini bekler ve ozetini dondurur. Baslamadan once
        yapilan denetimler arka planda calistigi icin bitis, biten is sayacindan anlasilir."""
        once = self.ui(lambda: self.u.biten_is_sayisi)
        self.ui(fn, *a)
        bitis = time.time() + sure
        while time.time() < bitis:
            if self.ui(lambda: self.u.biten_is_sayisi) > once:
                return self.u.son_is
            time.sleep(0.2)
        raise TimeoutError("iş zamanında bitmedi")

    def bekle(self, kosul, sure=20):
        bitis = time.time() + sure
        while time.time() < bitis:
            if kosul():
                return True
            time.sleep(0.25)
        return False

    def adim(self, ad, fn):
        self._en_uzun = 0.0
        self._son_tik = time.perf_counter()
        bas = time.time()
        kayit = {"ad": ad}
        try:
            kayit.update(fn() or {})
        except Exception as e:               # noqa: BLE001
            kayit.update({"basarili": False, "hata": f"{type(e).__name__}: {e}",
                          "iz": traceback.format_exc()})
        kayit["sure_sn"] = round(time.time() - bas, 1)
        kayit["arayuz_en_uzun_takilma_ms"] = round(self._en_uzun * 1000)
        self.rapor["adimlar"].append(kayit)
        print(("✓ " if kayit.get("basarili") else "✗ ") + ad, flush=True)
        return kayit

    def _is_sonucu(self, son, beklenen=None, cikti=True):
        satirlar = son["satirlar"] if son else []
        tamam = bool(son) and son["kod"] == 0 and not son["iptal"]
        if beklenen:
            tamam = tamam and any(beklenen in s for s in satirlar)
        return {"basarili": tamam, "kod": son and son["kod"], "pid": son and son["pid"],
                **({"cikti": satirlar} if cikti else {"cikti_son": satirlar[-8:]})}

    # ---- adimlar
    def calistir(self):
        u = self.u
        a = u.ayar
        site_url = f"http://127.0.0.1:{a['test_portu']}/"
        lm = durum.lm_durumu(a["lm_url"], [a["sohbet_modeli"], a["gomme_modeli"]])
        self.rapor["lm"] = {"erisim": lm["erisim"], "eksik": lm["eksik"], "yuklu_degil": lm["yuklu_degil"]}
        self.rapor["durum_cubugu_ilk"] = self.ui(lambda: u.lm_etiketi.cget("text"))

        def lm_kapali_analiz():
            # LM Studio aciksa kapali durum, adres kullanilmayan bir porta cevrilerek benzetilir
            gercek = a["lm_url"]
            benzetim = lm["erisim"]
            if benzetim:
                a["lm_url"] = "http://127.0.0.1:9/v1"
            try:
                self.ui(u._durum_istegi.set)
                self.bekle(lambda: "erişilemiyor" in self.ui(lambda: u.lm_etiketi.cget("text")), 15)
                cubuk = self.ui(lambda: u.lm_etiketi.cget("text"))
                onceki = len(self.rapor["diyaloglar"])

                def bas():
                    u.mod.set("yonetici")
                    u._mod_degisti()
                    u.model_kullan.set(True)
                    u.site_url.set(site_url)
                    u.taramayi_baslat()
                self.ui(bas)
                self.bekle(lambda: len(self.rapor["diyaloglar"]) > onceki, 15)
                yeni = self.rapor["diyaloglar"][onceki:]
                baslamadi = self.ui(lambda: u.is_ is None)
            finally:
                a["lm_url"] = gercek
                self.ui(u._durum_istegi.set)
            return {"basarili": baslamadi and "erişilemiyor" in cubuk and any(d["tur"] == "hata" for d in yeni),
                    "benzetim": benzetim, "ileti": yeni[-1]["ileti"] if yeni else None, "durum_cubugu": cubuk}
        self.adim("LM Studio kapalıyken modelli analiz anlaşılır hata veriyor", lm_kapali_analiz)

        def test_baslat():
            self.ui(u.test_sitesini_baslat)
            acik = self.bekle(lambda: durum.port_acik(a["test_portu"]), 20)
            self.bekle(lambda: "çalışıyor" in self.ui(lambda: u.test_etiketi.cget("text")), 10)
            return {"basarili": acik, "http": http_kodu(site_url), "pid": u.sunucular["test"].pid,
                    "durum_cubugu": self.ui(lambda: u.test_etiketi.cget("text"))}
        self.adim("Test sitesi başlat", test_baslat)

        self.adim("Doğrula", lambda: self._is_sonucu(self.is_calistir(u.dogrula), "47/47"))

        model_var = (lm["erisim"] and not lm["eksik"] and not lm["yuklu_degil"]
                     and os.environ.get("SEO_OTO_MODELSIZ") != "1")

        def yonetici_tara():
            def bas():
                u.mod.set("yonetici")
                u._mod_degisti()
                u.model_kullan.set(model_var)
                u.site_url.set(site_url)
                u.site_koku.set(a["site_koku"])
                u.taramayi_baslat()
            son = self.is_calistir(bas)
            sonuc = self._is_sonucu(son, "Sonuç klasörü:", cikti=False)
            sonuc["plan_klasoru"] = str(self.ui(lambda: u.plan_klasoru))
            sonuc["model"] = self.ui(u.model_kullan.get)
            # otomatik asama: guven esigini gecenler onaysiz yazildi ve site yeniden tarandi
            k = Path(sonuc["plan_klasoru"])
            plan = pl.plani_oku(k)
            oz = pl.rapor_ozeti(k)
            sonuc["otomatik_uygulanan"] = sum(1 for d in plan["degisiklikler"]
                                              if d["durum"] == "uygulandi" and d.get("asama") == "otomatik")
            sonuc["asamalar"] = pl.asamalar(plan)
            sonuc["ozet"] = pl.ozet_satirlari(oz)
            sonuc["arayuz_ozeti"] = self.ui(lambda: u.plan_ozeti.cget("text"))
            sonuc["basarili"] = (sonuc["basarili"] and sonuc["otomatik_uygulanan"] > 0 and sonuc["asamalar"] == ["otomatik"]
                                 and (k / "sonra_otomatik" / "rapor.json").exists() and "Otomatik" in sonuc["arayuz_ozeti"])
            return sonuc
        tarama = self.adim("Yönetici taraması", yonetici_tara)
        klasor = Path(tarama.get("plan_klasoru") or "")

        def onay():
            def ac():
                p = arayuz.OnayPenceresi(u, klasor)
                p.kural_hepsi.set(True)
                yz = next((d for d in p.plan["degisiklikler"] if d["kategori"] == "yz" and d["risk"] != "yuksek"
                           and d["durum"] not in ("gecersiz", "uygulandi")), None)
                if yz:
                    p.secimler[yz["id"]]["karar"] = "onay"
                # otomatik asamada yazilmis bir degisiklik reddedilir: onayli asamada geri cekilmeli
                geri = next((d for d in p.plan["degisiklikler"] if d["durum"] == "uygulandi"
                             and d.get("asama") == "otomatik"), None)
                if geri:
                    p.secimler[geri["id"]]["karar"] = "ret"
                    kutu["geri_cekilecek"] = geri["id"]
                kutu["gosterim"] = p._karar_gosterimi(geri) if geri else None
                p._agaci_yenile()
                arg, _ = pl.onay_argumanlari(p.plan, p.onceki, p.secimler, True)
                p.kaydet()
                kutu["argumanlar"] = arg
            kutu = {}
            sonuc = self._is_sonucu(self.is_calistir(ac), "Kararlar kaydedildi")
            argumanlar = kutu.get("argumanlar")
            kararlar = pl.kararlari_oku(klasor)
            sonuc.update({"argumanlar": argumanlar, "kural_hepsi": kararlar["kural_hepsi"],
                          "onaylanan": pl.onaylanan_sayisi(pl.plani_oku(klasor), kararlar),
                          "geri_cekilecek": kutu.get("geri_cekilecek"), "gosterim": kutu.get("gosterim"),
                          "geri_cekilecek_sayisi": pl.geri_cekilecek_sayisi(pl.plani_oku(klasor), kararlar)})
            return sonuc
        self.adim("Onay ekranı → kararları kaydet", onay)

        def uygula():
            sonuc = self._is_sonucu(self.is_calistir(u.uygula), "Aşamalara göre metrikler", cikti=False)
            sonuc["uygulama_json"] = (klasor / "uygulama.json").exists()
            plan = pl.plani_oku(klasor)
            oz = pl.rapor_ozeti(klasor)
            sonuc["asamalar"] = pl.asamalar(plan)
            sonuc["ozet"] = pl.ozet_satirlari(oz)
            sonuc["arayuz_ozeti"] = self.ui(lambda: u.plan_ozeti.cget("text"))
            i = self.rapor["adimlar"][-1].get("geri_cekilecek") if self.rapor["adimlar"] else None
            d = next((x for x in plan["degisiklikler"] if x["id"] == i), None)
            sonuc["geri_cekilen_durum"] = d and d["durum"]
            sonuc["basarili"] = (sonuc["basarili"] and sonuc["asamalar"] == ["otomatik", "onayli"]
                                 and (not i or sonuc["geri_cekilen_durum"] == "reddedildi")
                                 and "Onaylı düzeltmeler sonrası" in sonuc["arayuz_ozeti"])
            return sonuc
        self.adim("Uygula", uygula)

        def degerlendir():
            def bas():
                u._deg_listesi()
                etiket = next(k for k, v in u._deg_secenekleri.items() if Path(v) == klasor)
                u.deg_klasoru.set(etiket)
                u.degerlendir()
            sonuc = self._is_sonucu(self.is_calistir(bas), "Rapor:")
            sonuc["tablo"] = [s for s in sonuc["cikti"] if s.startswith("| ") and "|" in s[2:]]
            return sonuc
        self.adim("Değerlendir", degerlendir)

        def geri_al():
            sonuc = self._is_sonucu(self.is_calistir(u.geri_al, klasor.parent), "eşleşiyor")
            oz = pl.rapor_ozeti(klasor)
            sonuc["durumlar"] = {d: n for d, n in (oz or {}).get("sayilar", {}).items() if n}
            sonuc["ozet"] = pl.ozet_satirlari(oz)
            sonuc["basarili"] = (sonuc["basarili"] and bool(oz and oz["geri_alindi"])
                                 and set(sonuc["durumlar"]) <= {"onay_bekliyor", "elle", "basarisiz"})
            return sonuc
        self.adim("Geri al", geri_al)

        def iptal():
            def bas():
                u.mod.set("salt")
                u._mod_degisti()
                u.model_kullan.set(False)
                u.site_url.set(site_url)
                u.site_modu.set(True)
                u.taramayi_baslat()
            once = self.ui(lambda: u.biten_is_sayisi)
            self.ui(bas)
            self.bekle(lambda: self.ui(lambda: u.is_ is not None), 15)
            time.sleep(3)
            pid = self.ui(lambda: u.is_ and u.is_.pid)
            calisiyordu = bool(pid) and surec_yasiyor(pid)
            self.ui(u.iptal)
            self.bekle(lambda: self.ui(lambda: u.biten_is_sayisi) > once, 30)
            son = self.u.son_is
            kapandi = self.bekle(lambda: not surec_yasiyor(pid), 10)
            return {"basarili": calisiyordu and son["iptal"] and kapandi, "pid": pid,
                    "iptal_edildi": son["iptal"], "surec_kapandi": kapandi}
        self.adim("Uzun işlem sırasında iptal", iptal)

        self.adim("Sıfırla", lambda: self._is_sonucu(self.is_calistir(u.sifirla), "eşleşiyor"))
        self.adim("Hash karşılaştır", lambda: self._is_sonucu(self.is_calistir(u.sifirla_kontrol), "eşleşiyor"))
        self.adim("Doğrula (sıfırlama sonrası)", lambda: self._is_sonucu(self.is_calistir(u.dogrula), "47/47"))

        def web():
            if durum.port_acik(a["web_portu"]):
                return {"basarili": False, "hata": "web portu zaten kullanımda"}
            self.ui(u.web_baslat_)
            acik = self.bekle(lambda: durum.port_acik(a["web_portu"]), 30)
            return {"basarili": acik and http_kodu(f"http://127.0.0.1:{a['web_portu']}/") == 200,
                    "pid": u.sunucular["web"] and u.sunucular["web"].pid}
        self.adim("Web arayüzünü başlat", web)

        # kapanis: test sitesi ve web arayuzu acikken uygulama kapatilir
        self.rapor["kapanis_oncesi_sunucular"] = self.ui(lambda: {k: s.pid for k, s in u.sunucular.items() if s})
        self.rapor["baslatilan_pidler"] = list(u.baslatilan_pidler)
        self.ui(lambda: u.kapat(sor=False))


def calistir(rapor_yolu, ayar_dosyasi=None):
    pencere = tk.Tk()
    uyg = arayuz.Uygulama(pencere, ayar_dosyasi)
    senaryo = Senaryo(uyg, rapor_yolu)

    def yurut():
        try:
            senaryo.calistir()
        except Exception:                    # noqa: BLE001
            senaryo.rapor["beklenmeyen"] = traceback.format_exc()
            try:
                senaryo.ui(lambda: uyg.kapat(sor=False))
            except Exception:                # noqa: BLE001
                pass
    threading.Thread(target=yurut, daemon=True).start()
    pencere.mainloop()

    time.sleep(1)
    pidler = senaryo.rapor.get("baslatilan_pidler", uyg.baslatilan_pidler)
    a = uyg.ayar
    senaryo.rapor["kapanis"] = {
        "yasayan_surecler": [p for p in pidler if surec_yasiyor(p)],
        "test_portu_acik": durum.port_acik(a["test_portu"]),
        "web_portu_acik": durum.port_acik(a["web_portu"]),
    }
    adimlar = senaryo.rapor["adimlar"]
    senaryo.rapor["ozet"] = {"adim": len(adimlar), "basarili": sum(bool(x.get("basarili")) for x in adimlar),
                             "tamamlandi": "beklenmeyen" not in senaryo.rapor,
                             "temiz_kapanis": not any(senaryo.rapor["kapanis"].values())}
    Path(rapor_yolu).write_text(json.dumps(senaryo.rapor, ensure_ascii=False, indent=2), encoding="utf-8")
    ozet = senaryo.rapor["ozet"]
    return 0 if ozet["adim"] == ozet["basarili"] and ozet["tamamlandi"] and ozet["temiz_kapanis"] else 1
