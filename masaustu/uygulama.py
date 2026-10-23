"""Tkinter masaustu arayuzu: betikleri alt surec olarak calistirir, ciktiyi canli gosterir.

Arayuz yalnizca ana is parcaciginda guncellenir; alt surec ciktilari ve durum denetimleri bir
kuyruk uzerinden aktarilir. Ayni anda tek bir is calisir (tarama, dogrulama, sifirlama vb.);
test sitesi ve web arayuzu sunuculari bundan bagimsiz arka plan surecleridir.
"""
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import ayarlar as ay
from . import durum, ses
from . import plan as pl
from . import sonuclar as sn
from .surecler import Surec, betik_komutu

BETIKLER = {
    "yonet": "yonet.py",
    "web": "calistir.py",
    "sunucu": "test_sitesi/sunucu.py",
    "dogrula": "test_sitesi_degerlendirme/dogrula.py",
    "sifirla": "test_sitesi_degerlendirme/sifirla.py",
    "degerlendir": "test_sitesi_degerlendirme/degerlendir.py",
    "salt": "masaustu/salt_okunur.py",
}
IKON = Path(__file__).resolve().parent / "ikon.ico"
DURUM_ARALIGI_SN = 4


def hata_iletisi(satirlar, kod):
    """Basarisiz bir isin ciktisindan kullaniciya gosterilecek anlasilir Turkce ileti."""
    for s in reversed(satirlar):
        if s.strip().startswith("HATA:"):
            return s.strip()[5:].strip()
    metin = "\n".join(satirlar)
    if "10048" in metin or "Address already in use" in metin or "address is not available" in metin:
        return "Port kullanımda: başka bir program (ya da daha önce başlatılmış bir sunucu) bu portu kullanıyor."
    if "Traceback" in metin:
        son = next((s.strip() for s in reversed(satirlar) if s.strip()), "")
        if son.startswith("ModuleNotFoundError"):
            return "Gerekli bir Python modülü bulunamadı (" + son.split(":", 1)[-1].strip() + ")."
        return "Beklenmeyen hata: " + son
    return f"İşlem {kod} çıkış koduyla bitti. Ayrıntılar çıktı panelinde."


def dosya_ac(yol):
    yol = Path(yol)
    try:
        os.startfile(str(yol))
    except OSError:
        # .diff / .md icin ilisik program yoksa Not Defteri ile acilir
        subprocess.Popen(["notepad.exe", str(yol)])


class Uygulama:
    def __init__(self, pencere, ayar_dosyasi=None):
        self.k = pencere
        self.ayar_dosyasi = ayar_dosyasi
        self.ayar = ay.yukle(ayar_dosyasi)
        self.olaylar = queue.Queue()
        self.is_ = None                      # calisan is (Surec)
        self.is_baslangic = None
        self.son_is = None                   # en son biten isin ozeti (testler ve hata iletisi icin)
        self.biten_is_sayisi = 0
        self.sunucular = {"test": None, "web": None}
        self.baslatilan_pidler = []
        self.plan_klasoru = None
        self.salt_sonuc = None
        self.lm = None
        self._durdur = threading.Event()
        self._durum_istegi = threading.Event()
        self._is_dugmeleri = []
        # oto-test bu uc kancayi degistirerek diyaloglari otomatik yanitlar
        self.onay_sor = self._onay_sor
        self.hata_goster = lambda baslik, ileti: messagebox.showerror(baslik, ileti, parent=self.k)
        self.bilgi_goster = lambda baslik, ileti: messagebox.showinfo(baslik, ileti, parent=self.k)

        self.k.title(ay.UYGULAMA_ADI)
        self.k.geometry("1100x780")
        self.k.minsize(900, 620)
        try:
            self.k.iconbitmap(default=str(IKON))
        except tk.TclError:
            pass
        self._arayuz()
        self.k.protocol("WM_DELETE_WINDOW", self.kapat)
        self.k.after(100, self._olaylari_isle)
        self.k.after(1000, self._saat)
        threading.Thread(target=self._durum_dongusu, daemon=True).start()
        hatalar = ay.dogrula(self.ayar)
        if hatalar:
            for h in hatalar:
                self.log("UYARI: " + h, "hata")
            self.sekmeler.select(self.sekme_ayar)

    # ------------------------------------------------------------------ yardimcilar
    def kok(self):
        return Path(self.ayar["proje_koku"]) if ay.proje_koku_mu(self.ayar["proje_koku"]) else None

    def _onay_sor(self, baslik, ileti):
        ses.cal("onay", self.ayar["ses"])
        return messagebox.askyesno(baslik, ileti, icon="warning", parent=self.k)

    def log(self, metin, etiket=None):
        self._log_toplu([(metin, etiket)])

    def _log_toplu(self, satirlar):
        self.cikti.configure(state="normal")
        for metin, etiket in satirlar:
            self.cikti.insert("end", metin + "\n", etiket or ())
        self.cikti.see("end")
        self.cikti.configure(state="disabled")

    def _satir_etiketi(self, m):
        if m.lstrip().startswith(("HATA", "BEKLENMEYEN", "Traceback")) or "UYUMSUZ" in m:
            return "hata"
        if m.lstrip().startswith(("UYARI", "✗")):
            return "uyari"
        if "✓" in m:
            return "tamam"
        return None

    # ------------------------------------------------------------------ is calistirma
    def calistir(self, ad, betik, argumanlar=(), bitince=None, iptal_edilebilir=True, sunucu=None):
        """Betigi alt surec olarak baslatir. sunucu verilmezse tek is yuvasini kullanir."""
        kok = self.kok()
        if not kok:
            self.hata_goster("Proje klasörü yok", "Proje klasörü bulunamadı. Ayarlar sekmesinden yonet.py'nin "
                                                   "bulunduğu klasörü seçin.")
            self.sekmeler.select(self.sekme_ayar)
            return None
        if sunucu is None and self.is_ is not None:
            self.hata_goster("İşlem sürüyor", "Şu anda '" + self.is_.ad + "' çalışıyor. Bitmesini bekleyin ya da "
                                              "İptal ile durdurun.")
            return None
        argv = betik_komutu(kok / BETIKLER[betik], *argumanlar)
        s = Surec(ad, argv, kok, iptal_edilebilir=iptal_edilebilir)
        s.satirlar = []
        s.bitince = bitince
        s.sunucu = sunucu
        s.satir = lambda m, s=s: self.olaylar.put(("satir", s, m))
        s.bitti = lambda kod, iptal, s=s: self.olaylar.put(("bitti", s, kod, iptal))
        self.log("▶ " + ad, "baslik")
        self.log("  " + " ".join([BETIKLER[betik], *map(str, argumanlar)]), "soluk")
        try:
            s.baslat()
        except OSError as e:
            self.log("HATA: süreç başlatılamadı: " + str(e), "hata")
            self.hata_goster(ad, "Süreç başlatılamadı: " + str(e))
            return None
        s.baslangic = time.time()
        self.baslatilan_pidler.append(s.pid)
        if sunucu:
            self.sunucular[sunucu] = s
        else:
            self.is_ = s
            self.is_baslangic = time.time()
        self._dugmeleri_guncelle()
        return s

    def arka_planda(self, is_, sonra):
        """is_() ayri is parcaciginda calisir (port ve LM Studio denetimi gibi bekletebilen isler;
        Windows'ta kapali porta baglanma zaman asimina kadar surer); sonra(sonuc) ana is parcaciginda."""
        threading.Thread(target=lambda: self.olaylar.put(("cagir", sonra, is_())), daemon=True).start()

    def iptal(self):
        s = self.is_
        if not s:
            return
        if not s.iptal_edilebilir:
            self.bilgi_goster("İptal edilemez", "'" + s.ad + "' siteye ya da sonuç klasörüne yazıyor; yarıda "
                                                "kesilirse dosyalar tutarsız kalabilir. Bitmesini bekleyin.")
            return
        self.log("■ İptal ediliyor: " + s.ad, "uyari")
        s.iptal()

    def _olaylari_isle(self):
        # cikti satirlari toplu eklenir; hizli yazan bir betik arayuzu bekletmesin diye tur basina
        # en fazla 400 olay islenir, kalanlar bir sonraki tura kalir
        bekleyen = []
        try:
            for _ in range(400):
                olay = self.olaylar.get_nowait()
                if olay[0] == "satir":
                    _, s, m = olay
                    s.satirlar.append(m)
                    bekleyen.append((("[" + s.ad + "] " if s.sunucu else "") + m, self._satir_etiketi(m)))
                    continue
                if bekleyen:
                    self._log_toplu(bekleyen)
                    bekleyen = []
                if olay[0] == "bitti":
                    self._bitti(*olay[1:])
                elif olay[0] == "durum":
                    self._durumu_goster(olay[1])
                elif olay[0] == "modeller":
                    self._modelleri_doldur(olay[1])
                elif olay[0] == "cagir":
                    olay[1](olay[2])
        except queue.Empty:
            pass
        if bekleyen:
            self._log_toplu(bekleyen)
        self.k.after(100, self._olaylari_isle)

    def _bitti(self, s, kod, iptal):
        sure = time.time() - s.baslangic
        if s.sunucu:
            if self.sunucular.get(s.sunucu) is s:
                self.sunucular[s.sunucu] = None
            if iptal:
                self.log("■ " + s.ad + " durduruldu.", "soluk")
            elif kod not in (0, None):
                self.log("✗ " + s.ad + " kapandı (kod " + str(kod) + ")", "hata")
                ses.cal("hata", self.ayar["ses"])
                self.hata_goster(s.ad, hata_iletisi(s.satirlar, kod))
            self._durum_istegi.set()
            self._dugmeleri_guncelle()
            return
        self.is_ = None
        self.son_is = {"ad": s.ad, "kod": kod, "iptal": iptal, "satirlar": list(s.satirlar), "sure": sure,
                       "pid": s.pid}
        self.biten_is_sayisi += 1
        self._dugmeleri_guncelle()
        if iptal:
            self.log(f"■ {s.ad} iptal edildi ({sure:.1f} sn)", "uyari")
            return
        if kod == 0:
            self.log(f"✓ {s.ad} tamamlandı ({sure:.1f} sn)", "tamam")
            ses.cal("bitti", self.ayar["ses"])
        else:
            ileti = hata_iletisi(s.satirlar, kod)
            self.log(f"✗ {s.ad} başarısız (kod {kod}): {ileti}", "hata")
            ses.cal("hata", self.ayar["ses"])
            self.hata_goster(s.ad, ileti)
        if s.bitince:
            s.bitince(kod, s.satirlar)
        self._sonuclari_yenile()

    def _saat(self):
        if self.is_:
            gecen = int(time.time() - self.is_baslangic)
            self.is_etiketi.configure(text=f"Çalışıyor: {self.is_.ad} ({gecen // 60:02d}:{gecen % 60:02d})")
        else:
            self.is_etiketi.configure(text="Boşta")
        self.k.after(1000, self._saat)

    def _dugmeleri_guncelle(self):
        mesgul = self.is_ is not None
        for d in self._is_dugmeleri:
            d.configure(state="disabled" if mesgul else "normal")
        self.iptal_dugmesi.configure(state="normal" if mesgul and self.is_.iptal_edilebilir else "disabled")
        calisan_test = self.sunucular["test"] is not None
        self.test_baslat.configure(state="disabled" if calisan_test else "normal")
        self.test_durdur.configure(state="normal" if calisan_test else "disabled")
        calisan_web = self.sunucular["web"] is not None
        self.web_baslat.configure(state="disabled" if calisan_web else "normal")
        self.web_durdur.configure(state="normal" if calisan_web else "disabled")
        self.plan_dugmeleri_guncelle()

    # ------------------------------------------------------------------ durum cubugu
    def _durum_dongusu(self):
        while not self._durdur.is_set():
            a = dict(self.ayar)
            gerekli = [a["sohbet_modeli"], a["gomme_modeli"]]
            d = {"lm": durum.lm_durumu(a["lm_url"], gerekli), "lm_url": a["lm_url"],
                 "test": durum.port_acik(a["test_portu"]), "web": durum.port_acik(a["web_portu"])}
            self.olaylar.put(("durum", d))
            self._durum_istegi.wait(DURUM_ARALIGI_SN)
            self._durum_istegi.clear()

    def _durumu_goster(self, d):
        self.lm = d["lm"]
        lm = d["lm"]
        if not lm["erisim"]:
            self.lm_etiketi.configure(text="● LM Studio: erişilemiyor", foreground="#c62828")
        elif lm["eksik"] or lm["yuklu_degil"]:
            eksik = lm["eksik"] + lm["yuklu_degil"]
            self.lm_etiketi.configure(text="● LM Studio: açık · eksik/yüklü değil: " + ", ".join(eksik),
                                      foreground="#ef6c00")
        else:
            self.lm_etiketi.configure(text="● LM Studio: açık · modeller hazır", foreground="#2e7d32")
        port = self.ayar["test_portu"]
        if d["test"]:
            dis = "" if self.sunucular["test"] else " (bu uygulama dışında başlatıldı)"
            metin, renk = f"● Test sitesi: çalışıyor http://127.0.0.1:{port}/{dis}", "#2e7d32"
        else:
            metin, renk = "● Test sitesi: durdu", "#757575"
        self.test_etiketi.configure(text=metin, foreground=renk)
        self.test_durum_etiketi.configure(text=metin.lstrip("● "), foreground=renk)
        web = f"● Web arayüzü: http://127.0.0.1:{self.ayar['web_portu']}/" if d["web"] else "● Web arayüzü: kapalı"
        self.web_etiketi.configure(text=web, foreground="#2e7d32" if d["web"] else "#757575")

    def modelleri_getir(self):
        url = self.ayar["lm_url"]
        self.log("Modeller LM Studio'dan alınıyor: " + url, "soluk")
        threading.Thread(target=lambda: self.olaylar.put(("modeller", durum.lm_durumu(url, []))), daemon=True).start()

    def _modelleri_doldur(self, d):
        if not d["erisim"]:
            ileti = durum.lm_iletisi(d, self.ayar["lm_url"])
            self.log("HATA: " + ileti, "hata")
            self.hata_goster("LM Studio", ileti)
            return
        sohbet = [m["id"] for m in d["modeller"] if "embed" not in m["id"].lower()]
        gomme = [m["id"] for m in d["modeller"] if "embed" in m["id"].lower()]
        self.sohbet_kutusu.configure(values=sohbet)
        self.gomme_kutusu.configure(values=[""] + gomme)
        yuklu = [m["id"] + (" (yüklü)" if m["yuklu"] else "") for m in d["modeller"]]
        self.log("Modeller: " + (", ".join(yuklu) or "yok"))

    # ------------------------------------------------------------------ arayuz
    def _arayuz(self):
        stil = ttk.Style(self.k)
        if "vista" in stil.theme_names():
            stil.theme_use("vista")
        stil.configure("Baslik.TLabel", font=("Segoe UI", 10, "bold"))
        stil.configure("Not.TLabel", foreground="#616161")

        bolme = ttk.PanedWindow(self.k, orient="vertical")
        bolme.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.sekmeler = ttk.Notebook(bolme)
        bolme.add(self.sekmeler, weight=3)

        self.sekme_analiz = ttk.Frame(self.sekmeler, padding=10)
        self.sekme_test = ttk.Frame(self.sekmeler, padding=10)
        self.sekme_sonuc = ttk.Frame(self.sekmeler, padding=10)
        self.sekme_ayar = ttk.Frame(self.sekmeler, padding=10)
        for sekme, ad in ((self.sekme_analiz, "Analiz"), (self.sekme_test, "Test sitesi"),
                          (self.sekme_sonuc, "Sonuçlar"), (self.sekme_ayar, "Ayarlar")):
            self.sekmeler.add(sekme, text=ad)

        alt = ttk.Frame(bolme)
        bolme.add(alt, weight=2)
        ust_cubuk = ttk.Frame(alt)
        ust_cubuk.pack(fill="x", pady=(6, 2))
        ttk.Label(ust_cubuk, text="Çıktı", style="Baslik.TLabel").pack(side="left")
        ttk.Button(ust_cubuk, text="Temizle", command=self._ciktiyi_temizle).pack(side="right")
        self.iptal_dugmesi = ttk.Button(ust_cubuk, text="İptal", command=self.iptal, state="disabled")
        self.iptal_dugmesi.pack(side="right", padx=4)
        self.cikti = scrolledtext.ScrolledText(alt, height=12, wrap="word", font=("Consolas", 9), state="disabled")
        self.cikti.pack(fill="both", expand=True)
        for etiket, renk in (("hata", "#c62828"), ("uyari", "#ef6c00"), ("tamam", "#2e7d32"),
                             ("soluk", "#757575"), ("baslik", "#1565c0")):
            self.cikti.tag_configure(etiket, foreground=renk)
        self.cikti.tag_configure("baslik", font=("Consolas", 9, "bold"))

        cubuk = ttk.Frame(self.k, padding=(8, 4))
        cubuk.pack(fill="x")
        self.lm_etiketi = ttk.Label(cubuk, text="● LM Studio: denetleniyor…")
        self.lm_etiketi.pack(side="left")
        ttk.Separator(cubuk, orient="vertical").pack(side="left", fill="y", padx=8)
        self.test_etiketi = ttk.Label(cubuk, text="● Test sitesi: denetleniyor…")
        self.test_etiketi.pack(side="left")
        ttk.Separator(cubuk, orient="vertical").pack(side="left", fill="y", padx=8)
        self.web_etiketi = ttk.Label(cubuk, text="● Web arayüzü: denetleniyor…")
        self.web_etiketi.pack(side="left")
        self.is_etiketi = ttk.Label(cubuk, text="Boşta")
        self.is_etiketi.pack(side="right")

        self._analiz_sekmesi()
        self._test_sekmesi()
        self._sonuc_sekmesi()
        self._ayar_sekmesi()
        self._dugmeleri_guncelle()

    def _ciktiyi_temizle(self):
        self.cikti.configure(state="normal")
        self.cikti.delete("1.0", "end")
        self.cikti.configure(state="disabled")

    def _dugme(self, ust, metin, komut, is_dugmesi=True, **kw):
        d = ttk.Button(ust, text=metin, command=komut, **kw)
        if is_dugmesi:
            self._is_dugmeleri.append(d)
        return d

    # ---- Analiz
    def _analiz_sekmesi(self):
        f = self.sekme_analiz
        f.columnconfigure(1, weight=1)
        self.mod = tk.StringVar(value="yonetici")
        satir = ttk.Frame(f)
        satir.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(satir, text="Mod:", style="Baslik.TLabel").pack(side="left")
        ttk.Radiobutton(satir, text="Yönetici (onaylanan düzeltmeleri siteye yazar)", value="yonetici",
                        variable=self.mod, command=self._mod_degisti).pack(side="left", padx=8)
        ttk.Radiobutton(satir, text="Salt okunur (yalnızca analiz, siteye yazmaz)", value="salt",
                        variable=self.mod, command=self._mod_degisti).pack(side="left", padx=8)

        ttk.Label(f, text="Site adresi:").grid(row=1, column=0, sticky="w")
        self.site_url = tk.StringVar(value=self.ayar["site_url"])
        ttk.Entry(f, textvariable=self.site_url).grid(row=1, column=1, sticky="ew", padx=6)
        self.adres_notu = ttk.Label(f, style="Not.TLabel")
        self.adres_notu.grid(row=2, column=1, sticky="w", padx=6)

        self.kok_etiketi = ttk.Label(f, text="Site kök klasörü:")
        self.kok_etiketi.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.site_koku = tk.StringVar(value=self.ayar["site_koku"])
        self.kok_girisi = ttk.Entry(f, textvariable=self.site_koku)
        self.kok_girisi.grid(row=3, column=1, sticky="ew", padx=6, pady=(6, 0))
        self.kok_gozat = ttk.Button(f, text="Gözat…", command=self._site_koku_sec)
        self.kok_gozat.grid(row=3, column=2, pady=(6, 0))

        model = ttk.LabelFrame(f, text="Dil modeli (LM Studio)", padding=8)
        model.grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)
        model.columnconfigure(1, weight=1)
        self.model_kullan = tk.BooleanVar(value=True)
        ttk.Checkbutton(model, text="Dil modeli kullan (YZ önerileri). Kapalıysa yalnızca denetim yapılır.",
                        variable=self.model_kullan).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(model, text="Sohbet modeli:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.sohbet_modeli = tk.StringVar(value=self.ayar["sohbet_modeli"])
        self.sohbet_kutusu = ttk.Combobox(model, textvariable=self.sohbet_modeli)
        self.sohbet_kutusu.grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(model, text="Modelleri getir", command=self.modelleri_getir).grid(row=1, column=2, pady=(6, 0))
        ttk.Label(model, text="Gömme modeli:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.gomme_modeli = tk.StringVar(value=self.ayar["gomme_modeli"])
        self.gomme_kutusu = ttk.Combobox(model, textvariable=self.gomme_modeli)
        self.gomme_kutusu.grid(row=2, column=1, sticky="ew", padx=6, pady=(6, 0))

        tarama = ttk.LabelFrame(f, text="Tarama", padding=8)
        tarama.grid(row=5, column=0, columnspan=3, sticky="ew")
        self.site_modu = tk.BooleanVar(value=True)
        self.site_modu_kutusu = ttk.Checkbutton(tarama, text="Site modu (site içi bağlantıları izle)",
                                                variable=self.site_modu)
        self.site_modu_kutusu.pack(side="left")
        ttk.Label(tarama, text="En fazla sayfa:").pack(side="left", padx=(16, 4))
        self.sayfa = tk.IntVar(value=60)
        ttk.Spinbox(tarama, from_=1, to=500, width=5, textvariable=self.sayfa).pack(side="left")
        ttk.Label(tarama, text="Derinlik:").pack(side="left", padx=(16, 4))
        self.derinlik = tk.IntVar(value=6)
        ttk.Spinbox(tarama, from_=0, to=10, width=4, textvariable=self.derinlik).pack(side="left")
        self._dugme(tarama, "Taramayı başlat", self.taramayi_baslat).pack(side="right")

        self.yonetici_cercevesi = ttk.LabelFrame(f, text="Yönetici modu adımları", padding=8)
        self.yonetici_cercevesi.grid(row=6, column=0, columnspan=3, sticky="ew", pady=10)
        self.plan_etiketi = ttk.Label(self.yonetici_cercevesi, text="Plan: henüz yok (önce tarayın ya da "
                                                                     "Sonuçlar sekmesinden bir plan açın)")
        self.plan_etiketi.pack(anchor="w")
        dugmeler = ttk.Frame(self.yonetici_cercevesi)
        dugmeler.pack(anchor="w", pady=(6, 0))
        self.onay_dugmesi = self._dugme(dugmeler, "1. Önizle ve onayla…", self.onay_ekrani)
        self.onay_dugmesi.pack(side="left")
        self.uygula_dugmesi = self._dugme(dugmeler, "2. Uygula (siteye yazar)…", self.uygula)
        self.uygula_dugmesi.pack(side="left", padx=6)
        self.plan_rapor_dugmesi = ttk.Button(dugmeler, text="Yönetici raporunu aç", command=self._plan_raporu)
        self.plan_rapor_dugmesi.pack(side="left")

        self.salt_cercevesi = ttk.LabelFrame(f, text="Salt okunur sonuç", padding=8)
        self.salt_etiketi = ttk.Label(self.salt_cercevesi, text="Henüz tarama yok.")
        self.salt_etiketi.pack(side="left")
        self.salt_rapor_dugmesi = ttk.Button(self.salt_cercevesi, text="Raporu aç", command=self._salt_raporu,
                                             state="disabled")
        self.salt_rapor_dugmesi.pack(side="right")

        web = ttk.LabelFrame(f, text="Tarayıcı arayüzü (calistir.py)", padding=8)
        web.grid(row=8, column=0, columnspan=3, sticky="ew")
        ttk.Label(web, text="Mevcut web arayüzünü yerel sunucu olarak başlatır.", style="Not.TLabel").pack(side="left")
        ttk.Button(web, text="Tarayıcıda aç",
                   command=lambda: webbrowser.open(f"http://127.0.0.1:{self.ayar['web_portu']}/")).pack(side="right")
        self.web_durdur = ttk.Button(web, text="Durdur", command=lambda: self.sunucuyu_durdur("web"))
        self.web_durdur.pack(side="right", padx=4)
        self.web_baslat = ttk.Button(web, text="Başlat", command=self.web_baslat_)
        self.web_baslat.pack(side="right")
        self._mod_degisti()

    def _mod_degisti(self):
        yonetici = self.mod.get() == "yonetici"
        durum_ = "normal" if yonetici else "disabled"
        for w in (self.kok_girisi, self.kok_gozat):
            w.configure(state=durum_)
        self.site_modu_kutusu.configure(state="disabled" if yonetici else "normal")
        if yonetici:
            self.adres_notu.configure(text="Sitenin temel adresi. Yazma yalnızca aşağıdaki kök klasöre yapılır.")
            self.salt_cercevesi.grid_remove()
            self.yonetici_cercevesi.grid()
        else:
            self.adres_notu.configure(text="Birden fazla adres için boşlukla ayırın. Siteye hiçbir şey yazılmaz.")
            self.yonetici_cercevesi.grid_remove()
            self.salt_cercevesi.grid(row=7, column=0, columnspan=3, sticky="ew", pady=10)

    def _site_koku_sec(self):
        kok = self.kok()
        secilen = filedialog.askdirectory(parent=self.k, title="Sitenin kök klasörünü seçin",
                                          initialdir=str(kok) if kok else None)
        if secilen:
            p = Path(secilen)
            try:
                p = p.relative_to(kok)
            except (TypeError, ValueError):
                pass
            self.site_koku.set(str(p))

    def taramayi_baslat(self):
        adresler = self.site_url.get().split()
        if not adresler:
            self.hata_goster("Adres yok", "Taranacak site adresini girin.")
            return
        model = self.model_kullan.get()
        if not model:
            self._taramaya_devam(adresler, model, None)
            return
        if not self.sohbet_modeli.get().strip():
            self.hata_goster("Model seçilmedi", "Sohbet modeli seçin ya da 'Dil modeli kullan' seçeneğini kapatın.")
            return
        # model secildiyse tarama baslamadan LM Studio ve modeller denetlenir; sorun varsa tarama
        # baslamaz (betikler de ayni denetimi yapar, bu yalnizca daha erken ve anlasilir uyari)
        url = self.ayar["lm_url"]
        modeller = [self.sohbet_modeli.get().strip(), self.gomme_modeli.get().strip()]
        self.log("LM Studio ve modeller denetleniyor: " + url, "soluk")
        self.arka_planda(lambda: durum.lm_durumu(url, modeller), lambda d: self._taramaya_devam(adresler, model, d))

    def _taramaya_devam(self, adresler, model, lm):
        if lm is not None:
            ileti = durum.lm_iletisi(lm, self.ayar["lm_url"])
            if ileti:
                self.log("HATA: " + ileti, "hata")
                ses.cal("hata", self.ayar["ses"])
                self.hata_goster("Tarama başlatılamadı", ileti + "\n\nModelsiz denemek için 'Dil modeli kullan' "
                                                         "seçeneğini kapatın.")
                return
        model_arg = (["--model", self.sohbet_modeli.get().strip()] +
                     (["--embed-model", self.gomme_modeli.get().strip()] if self.gomme_modeli.get().strip() else []) +
                     ["--lm-url", self.ayar["lm_url"]]) if model else []
        if self.mod.get() == "yonetici":
            if len(adresler) != 1:
                self.hata_goster("Tek adres", "Yönetici modunda sitenin tek bir temel adresi verilir.")
                return
            argumanlar = ["tara", "--kok", self.site_koku.get().strip(), "--url", adresler[0],
                          "--sayfa", self.sayfa.get(), "--derinlik", self.derinlik.get(), *model_arg]
            self.calistir("Yönetici taraması", "yonet", argumanlar, bitince=self._plan_hazir)
        else:
            argumanlar = ["--adres", *adresler, "--sayfa", self.sayfa.get(), "--derinlik", self.derinlik.get(),
                          *(["--site-modu"] if self.site_modu.get() else []),
                          *(model_arg if model else ["--yalnizca-denetim"])]
            self.calistir("Salt okunur tarama", "salt", argumanlar, bitince=self._salt_bitti)

    def _cikti_klasoru(self, satirlar):
        for s in reversed(satirlar):
            if s.startswith("Sonuç klasörü:"):
                p = Path(s.split(":", 1)[1].strip())
                return p if p.is_absolute() else self.kok() / p
        return None

    def _plan_hazir(self, kod, satirlar):
        if kod == 0:
            self.plan_sec(self._cikti_klasoru(satirlar))

    def plan_sec(self, klasor):
        self.plan_klasoru = Path(klasor) if klasor else None
        if self.plan_klasoru:
            bilgi = sn.klasor_bilgisi(self.plan_klasoru)
            self.plan_etiketi.configure(text=f"Plan: {self._goreli(self.plan_klasoru)} · durum: {bilgi['durum']}")
        self.plan_dugmeleri_guncelle()

    def plan_dugmeleri_guncelle(self):
        var = self.plan_klasoru is not None and (self.plan_klasoru / "degisiklikler.json").exists()
        mesgul = self.is_ is not None
        self.onay_dugmesi.configure(state="normal" if var and not mesgul else "disabled")
        onayli = var and ((self.plan_klasoru / "onaylar.json").exists() or self._otomatik_var())
        self.uygula_dugmesi.configure(state="normal" if onayli and not mesgul else "disabled")
        rapor = var and (self.plan_klasoru / "yonetici_raporu.html").exists()
        self.plan_rapor_dugmesi.configure(state="normal" if rapor else "disabled")

    def _otomatik_var(self):
        try:
            plan = pl.plani_oku(self.plan_klasoru)
        except (OSError, ValueError):
            return False
        return any(d.get("onay_turu") == "otomatik" for d in plan["degisiklikler"])

    def _plan_raporu(self):
        if self.plan_klasoru:
            dosya_ac(self.plan_klasoru / "yonetici_raporu.html")

    def _salt_bitti(self, kod, satirlar):
        if kod == 0:
            self.salt_sonuc = self._cikti_klasoru(satirlar)
            self.salt_etiketi.configure(text="Sonuç: " + str(self._goreli(self.salt_sonuc)))
            self.salt_rapor_dugmesi.configure(state="normal")

    def _salt_raporu(self):
        if self.salt_sonuc:
            dosya_ac(self.salt_sonuc / "rapor.html")

    def _goreli(self, p):
        try:
            return Path(p).relative_to(self.kok())
        except (TypeError, ValueError):
            return p

    def onay_ekrani(self):
        if not self.plan_klasoru:
            return
        try:
            OnayPenceresi(self, self.plan_klasoru)
        except (OSError, ValueError, KeyError) as e:
            self.hata_goster("Plan okunamadı", "degisiklikler.json okunamadı: " + str(e))

    def onaylari_kaydet(self, klasor, argumanlar, bitince=None):
        return self.calistir("Onayları kaydet", "yonet", ["onayla", self._goreli(klasor), *argumanlar],
                             iptal_edilebilir=False, bitince=bitince)

    def uygula(self):
        klasor = self.plan_klasoru
        if not klasor:
            return
        plan = pl.plani_oku(klasor)
        sayi = pl.onaylanan_sayisi(plan, pl.kararlari_oku(klasor))
        kok = ((plan.get("hedef") or {}).get("adaptor") or {}).get("kok")
        ileti = (f"Onaylanan {sayi} değişiklik siteye yazılacak" + (f":\n{kok}" if kok else ".") +
                 "\n\nYazmadan önce tam yedek alınır; geri almak için Sonuçlar → 'Son uygulamayı geri al'. "
                 "Bu işlem yarıda kesilemez.\n\nDevam edilsin mi?")
        if sayi == 0:
            self.hata_goster("Onaylı değişiklik yok", "Uygulanacak onaylı değişiklik yok (otomatik onaylı da yok). "
                                                      "Önce onay ekranından önerileri onaylayın.")
            return
        oto = sum(1 for d in plan["degisiklikler"] if pl.otomatik_mi(d, pl.esik(plan, pl.kararlari_oku(klasor))))
        if oto:
            ileti = ileti.replace("siteye yazılacak", f"siteye yazılacak ({oto} tanesi güven eşiğini geçtiği için "
                                                      "otomatik onaylı)", 1)
        if self.onay_sor("Siteye yazılsın mı?", ileti):
            self.calistir("Uygula", "yonet", ["uygula", self._goreli(klasor)], iptal_edilebilir=False,
                          bitince=lambda kod, s: self.plan_sec(klasor))

    def web_baslat_(self):
        port = self.ayar["web_portu"]
        self.arka_planda(lambda: durum.port_acik(port), self._web_baslat_devam)

    def _web_baslat_devam(self, acik):
        if acik:
            self.hata_goster("Port kullanımda", f"{self.ayar['web_portu']} portunda zaten bir sunucu çalışıyor.")
            return
        self.calistir("Web arayüzü", "web", ["--port", self.ayar["web_portu"], "--acma"], sunucu="web")
        self.k.after(2500, lambda: webbrowser.open(f"http://127.0.0.1:{self.ayar['web_portu']}/")
                     if self.sunucular["web"] else None)

    # ---- Test sitesi
    def _test_sekmesi(self):
        f = self.sekme_test
        f.columnconfigure(0, weight=1)
        sunucu = ttk.LabelFrame(f, text="Sunucu (yalnızca 127.0.0.1)", padding=8)
        sunucu.grid(row=0, column=0, sticky="ew")
        self.test_durum_etiketi = ttk.Label(sunucu, text="Denetleniyor…")
        self.test_durum_etiketi.pack(side="left")
        ttk.Button(sunucu, text="Tarayıcıda aç",
                   command=lambda: webbrowser.open(f"http://127.0.0.1:{self.ayar['test_portu']}/")).pack(side="right")
        self.test_durdur = ttk.Button(sunucu, text="Durdur", command=lambda: self.sunucuyu_durdur("test"))
        self.test_durdur.pack(side="right", padx=4)
        self.test_baslat = ttk.Button(sunucu, text="Başlat", command=self.test_sitesini_baslat)
        self.test_baslat.pack(side="right")

        isler = ttk.LabelFrame(f, text="Test işlemleri", padding=8)
        isler.grid(row=1, column=0, sticky="ew", pady=10)
        aciklamalar = (
            ("Doğrula", self.dogrula, "Kayıtlı 47 sorunun sitede gerçekten var olduğunu denetler (dogrula.py)."),
            ("Sıfırla…", self.sifirla, "Siteyi sorunlu orijinal haline döndürür ve hash'leri doğrular (sifirla.py)."),
            ("Hash karşılaştır", self.sifirla_kontrol, "Siteyi değiştirmeden orijinalle karşılaştırır "
                                                       "(sifirla.py --kontrol)."),
        )
        for i, (metin, komut, aciklama) in enumerate(aciklamalar):
            self._dugme(isler, metin, komut, width=18).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(isler, text=aciklama, style="Not.TLabel").grid(row=i, column=1, sticky="w", padx=8)

        deg = ttk.LabelFrame(f, text="Değerlendir (degerlendir.py)", padding=8)
        deg.grid(row=2, column=0, sticky="ew")
        deg.columnconfigure(1, weight=1)
        ttk.Label(deg, text="Yönetici modu sonucu:").grid(row=0, column=0, sticky="w")
        self.deg_klasoru = tk.StringVar()
        self.deg_kutusu = ttk.Combobox(deg, textvariable=self.deg_klasoru, state="readonly")
        self.deg_kutusu.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(deg, text="Yenile", command=self._deg_listesi).grid(row=0, column=2)
        satir = ttk.Frame(deg)
        satir.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._dugme(satir, "Değerlendir", self.degerlendir).pack(side="left")
        ttk.Button(satir, text="Değerlendirme raporunu aç", command=self._deg_raporu).pack(side="left", padx=6)
        ttk.Label(deg, text="Uygulama sonrası tarama içeren (uygulanmış) sonuçlar önce gelir.",
                  style="Not.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._deg_listesi()

    def _deg_listesi(self):
        kok = self.kok()
        kayitlar = [x for x in sn.listele(kok) if x["site"] == "127.0.0.1" and x["tur"] == "Yönetici"] if kok else []
        kayitlar.sort(key=lambda x: x["durum"] != "uygulandı")      # listele en yeniyi uste koyar; sira korunur
        self._deg_secenekleri = {f"{x['zaman']} · {x['durum']}": x["klasor"] for x in kayitlar}
        self.deg_kutusu.configure(values=list(self._deg_secenekleri))
        if self._deg_secenekleri and self.deg_klasoru.get() not in self._deg_secenekleri:
            self.deg_klasoru.set(next(iter(self._deg_secenekleri)))

    def test_sitesini_baslat(self):
        port = self.ayar["test_portu"]
        self.arka_planda(lambda: durum.port_acik(port), lambda acik: self._test_baslat_devam(port, acik))

    def _test_baslat_devam(self, port, acik):
        if acik:
            self.hata_goster("Port kullanımda", f"{port} portunda zaten bir sunucu çalışıyor (test sitesi başka bir "
                                                "pencereden başlatılmış olabilir).")
            return
        self.calistir("Test sitesi", "sunucu", ["--port", port], sunucu="test")
        self.k.after(800, self._durum_istegi.set)

    def sunucuyu_durdur(self, ad):
        s = self.sunucular.get(ad)
        if s:
            s.iptal()

    def dogrula(self):
        self.arka_planda(lambda: durum.port_acik(self.ayar["test_portu"]), self._dogrula_devam)

    def _dogrula_devam(self, acik):
        if not acik:
            self.hata_goster("Test sitesi kapalı", "Doğrulama için önce test sitesini başlatın.")
            return
        self.calistir("Doğrula", "dogrula")

    def sifirla(self):
        if self.onay_sor("Test sitesi sıfırlansın mı?",
                         "test_sitesi/site/ klasörü orijinal sorunlu kopyayla değiştirilecek. Uygulanmış "
                         "düzeltmeler silinir (sonuç klasörlerindeki yedekler kalır).\n\nDevam edilsin mi?"):
            self.calistir("Sıfırla", "sifirla", iptal_edilebilir=False)

    def sifirla_kontrol(self):
        self.calistir("Hash karşılaştır", "sifirla", ["--kontrol"])

    def degerlendir(self):
        klasor = getattr(self, "_deg_secenekleri", {}).get(self.deg_klasoru.get())
        if not klasor:
            self.hata_goster("Sonuç yok", "Değerlendirilecek yönetici modu sonucu yok. Önce test sitesini tarayıp "
                                          "uygulayın.")
            return
        self._deg_son = klasor
        self.calistir("Değerlendir", "degerlendir", ["--sonuc", self._goreli(klasor)])

    def _deg_raporu(self):
        klasor = getattr(self, "_deg_secenekleri", {}).get(self.deg_klasoru.get())
        if klasor and (klasor / "degerlendirme.md").exists():
            dosya_ac(klasor / "degerlendirme.md")
        else:
            self.hata_goster("Rapor yok", "Bu sonuç için henüz değerlendirme raporu yok.")

    # ---- Sonuclar
    def _sonuc_sekmesi(self):
        f = self.sekme_sonuc
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        ust = ttk.Frame(f)
        ust.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(ust, text="sonuclar/ klasöründeki taramalar (en yeni üstte)", style="Not.TLabel").pack(side="left")
        ttk.Button(ust, text="Yenile", command=self._sonuclari_yenile).pack(side="right")
        sutunlar = ("zaman", "site", "tur", "durum", "raporlar")
        self.agac = ttk.Treeview(f, columns=sutunlar, show="headings", selectmode="browse")
        for s, baslik, gen in (("zaman", "Zaman", 150), ("site", "Site", 170), ("tur", "Tür", 100),
                               ("durum", "Durum", 100), ("raporlar", "Raporlar", 380)):
            self.agac.heading(s, text=baslik)
            self.agac.column(s, width=gen, stretch=s == "raporlar")
        self.agac.grid(row=1, column=0, sticky="nsew")
        kaydirma = ttk.Scrollbar(f, orient="vertical", command=self.agac.yview)
        kaydirma.grid(row=1, column=1, sticky="ns")
        self.agac.configure(yscrollcommand=kaydirma.set)
        self.agac.bind("<<TreeviewSelect>>", lambda e: self._secim_degisti())
        self.agac.bind("<Double-1>", lambda e: self._raporu_ac())

        alt = ttk.Frame(f)
        alt.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.rapor_secimi = tk.StringVar()
        self.rapor_kutusu = ttk.Combobox(alt, textvariable=self.rapor_secimi, state="readonly", width=22)
        self.rapor_kutusu.pack(side="left")
        ttk.Button(alt, text="Raporu aç", command=self._raporu_ac).pack(side="left", padx=4)
        ttk.Button(alt, text="Klasörü aç", command=self._klasoru_ac).pack(side="left")
        ttk.Button(alt, text="Planı Analiz sekmesinde aç", command=self._plani_analizde_ac).pack(side="left", padx=4)
        self.geri_al_dugmesi = self._dugme(alt, "Son uygulamayı geri al…", self.geri_al)
        self.geri_al_dugmesi.pack(side="right")
        self.geri_al_notu = ttk.Label(f, style="Not.TLabel")
        self.geri_al_notu.grid(row=3, column=0, sticky="w", pady=(4, 0))
        self._sonuc_kayitlari = {}
        self._sonuclari_yenile()

    def _sonuclari_yenile(self):
        kok = self.kok()
        secili = self.agac.selection()
        self.agac.delete(*self.agac.get_children())
        self._sonuc_kayitlari = {}
        for x in sn.listele(kok) if kok else []:
            iid = str(x["klasor"])
            self._sonuc_kayitlari[iid] = x
            self.agac.insert("", "end", iid=iid, values=(x["zaman"], x["site"], x["tur"], x["durum"],
                                                         ", ".join(ad for ad, _ in x["raporlar"])))
        if secili and secili[0] in self._sonuc_kayitlari:
            self.agac.selection_set(secili[0])
        self._secim_degisti()
        if hasattr(self, "deg_kutusu"):
            self._deg_listesi()

    def _secili(self):
        s = self.agac.selection()
        return self._sonuc_kayitlari.get(s[0]) if s else None

    def _secim_degisti(self):
        x = self._secili()
        raporlar = [ad for ad, _ in x["raporlar"]] if x else []
        self.rapor_kutusu.configure(values=raporlar)
        self.rapor_secimi.set(raporlar[0] if raporlar else "")
        if x:
            site = x["klasor"].parent
            bilgi = sn.son_uygulama(site)
            if bilgi and sn.geri_alinabilir(site):
                self.geri_al_notu.configure(text=f"{x['site']}: son uygulama {bilgi.get('zaman', '')} "
                                                 f"({Path(bilgi['sonuc']).name}) geri alınabilir.")
            elif bilgi:
                self.geri_al_notu.configure(text=f"{x['site']}: son uygulama zaten geri alındı.")
            else:
                self.geri_al_notu.configure(text=f"{x['site']}: geri alınacak uygulama yok.")
        else:
            self.geri_al_notu.configure(text="")

    def _raporu_ac(self):
        x = self._secili()
        if not x:
            return
        yol = dict(x["raporlar"]).get(self.rapor_secimi.get())
        if yol:
            dosya_ac(yol)
        else:
            self.hata_goster("Rapor yok", "Bu klasörde açılacak rapor yok.")

    def _klasoru_ac(self):
        x = self._secili()
        if x:
            dosya_ac(x["klasor"])

    def _plani_analizde_ac(self):
        x = self._secili()
        if not x or x["tur"] != "Yönetici":
            self.hata_goster("Plan yok", "Yalnızca yönetici modu sonuçlarının planı açılabilir.")
            return
        self.mod.set("yonetici")
        self._mod_degisti()
        self.plan_sec(x["klasor"])
        self.sekmeler.select(self.sekme_analiz)

    def geri_al(self, site_klasoru=None):
        if site_klasoru is None:
            x = self._secili()
            if not x:
                self.hata_goster("Seçim yok", "Önce listeden geri alınacak sitenin bir sonucunu seçin.")
                return
            site_klasoru = x["klasor"].parent
        bilgi = sn.son_uygulama(site_klasoru)
        if not (bilgi and sn.geri_alinabilir(site_klasoru)):
            self.hata_goster("Geri alınacak uygulama yok", "Bu site için geri alınabilir bir uygulama yok.")
            return
        kok = (bilgi.get("adaptor") or {}).get("kok", "")
        if self.onay_sor("Son uygulama geri alınsın mı?",
                         f"{Path(bilgi['sonuc']).name} uygulamasıyla yazılan dosyalar yedekten geri yüklenecek:\n"
                         f"{kok}\n\nDevam edilsin mi?"):
            self.calistir("Geri al", "yonet", ["geri-al", self._goreli(site_klasoru)], iptal_edilebilir=False,
                          bitince=lambda kod, s: self.plan_sec(self.plan_klasoru))

    # ---- Ayarlar
    def _ayar_sekmesi(self):
        f = self.sekme_ayar
        f.columnconfigure(1, weight=1)
        self.ayar_degiskenleri = {}
        alanlar = (("proje_koku", "Proje klasörü (yonet.py'nin bulunduğu klasör)"),
                   ("lm_url", "LM Studio adresi"), ("sohbet_modeli", "Varsayılan sohbet modeli"),
                   ("gomme_modeli", "Varsayılan gömme modeli"), ("site_url", "Varsayılan site adresi"),
                   ("site_koku", "Varsayılan site kök klasörü"), ("test_portu", "Test sitesi portu"),
                   ("web_portu", "Web arayüzü portu"))
        for i, (anahtar, etiket) in enumerate(alanlar):
            ttk.Label(f, text=etiket + ":").grid(row=i, column=0, sticky="w", pady=3)
            v = tk.StringVar(value=str(self.ayar[anahtar]))
            self.ayar_degiskenleri[anahtar] = v
            ttk.Entry(f, textvariable=v).grid(row=i, column=1, sticky="ew", padx=6)
        ttk.Button(f, text="Gözat…", command=self._proje_koku_sec).grid(row=0, column=2)
        self.ses_acik = tk.BooleanVar(value=bool(self.ayar["ses"]))
        ttk.Checkbutton(f, text="İş bitince, hata olunca ve onay sorulurken ses çal",
                        variable=self.ses_acik).grid(row=len(alanlar), column=1, sticky="w", pady=6)
        dugmeler = ttk.Frame(f)
        dugmeler.grid(row=len(alanlar) + 1, column=1, sticky="w", pady=6)
        ttk.Button(dugmeler, text="Kaydet", command=self.ayarlari_kaydet).pack(side="left")
        ttk.Button(dugmeler, text="Varsayılanlar", command=self._varsayilanlar).pack(side="left", padx=6)
        ttk.Label(f, text="Ayar dosyası: " + str(ay.ayar_dosyasi() if not self.ayar_dosyasi else self.ayar_dosyasi),
                  style="Not.TLabel").grid(row=len(alanlar) + 2, column=0, columnspan=3, sticky="w", pady=(12, 0))

    def _proje_koku_sec(self):
        secilen = filedialog.askdirectory(parent=self.k, title="Proje klasörünü seçin (yonet.py'nin bulunduğu)")
        if secilen:
            self.ayar_degiskenleri["proje_koku"].set(str(Path(secilen)))

    def _varsayilanlar(self):
        for k, v in self.ayar_degiskenleri.items():
            if k != "proje_koku":
                v.set(str(ay.VARSAYILAN[k]))
        self.ses_acik.set(ay.VARSAYILAN["ses"])

    def ayarlari_kaydet(self):
        yeni = {k: v.get().strip() for k, v in self.ayar_degiskenleri.items()}
        yeni["ses"] = self.ses_acik.get()
        hatalar = ay.dogrula(yeni)
        if hatalar:
            self.hata_goster("Ayarlar kaydedilmedi", "\n".join(hatalar))
            return False
        yeni["test_portu"], yeni["web_portu"] = int(yeni["test_portu"]), int(yeni["web_portu"])
        self.ayar.update(yeni)
        yol = ay.kaydet(self.ayar, self.ayar_dosyasi)
        self.log("Ayarlar kaydedildi: " + str(yol), "tamam")
        self._durum_istegi.set()
        self._sonuclari_yenile()
        return True

    # ------------------------------------------------------------------ kapanis
    def kapat(self, sor=True):
        if self.is_ and not self.is_.iptal_edilebilir:
            self.bilgi_goster("Bekleyin", "'" + self.is_.ad + "' yazma işlemi sürüyor; bitince kapatabilirsiniz.")
            return False
        if self.is_ and sor and not self.onay_sor("Çıkılsın mı?", "'" + self.is_.ad + "' çalışıyor. İptal edilip "
                                                                    "uygulama kapatılsın mı?"):
            return False
        for s in [self.is_, *self.sunucular.values()]:
            if s:
                s.iptal()
        for s in [self.is_, *self.sunucular.values()]:
            if s:
                s.bekle(5)
        self._durdur.set()
        self._durum_istegi.set()
        self.k.destroy()
        return True


class OnayPenceresi:
    """Yonetici modu onay ekrani: kategoriye gore gruplu degisiklikler, diff, karar.
    Kararlar 'Kaydet' ile `yonet.py onayla` uzerinden kaydedilir."""

    KARAR_METNI = {"onay": "✔ Onay", "ret": "✖ Ret", None: "—"}

    def __init__(self, uyg, klasor):
        self.uyg, self.klasor = uyg, Path(klasor)
        self.plan = pl.plani_oku(klasor)
        self.onceki = pl.kararlari_oku(klasor)
        self.diffler = pl.diff_bloklari(klasor)
        self.secimler = pl.baslangic_secimleri(self.plan, self.onceki)
        self.degisiklik = {d["id"]: d for d in self.plan["degisiklikler"]}
        self.uygulanmis = (self.klasor / "uygulama.json").exists()

        self.p = tk.Toplevel(uyg.k)
        self.p.title("Önizleme ve onay — " + self.klasor.name)
        self.p.geometry("1200x760")
        self.p.transient(uyg.k)
        try:
            self.p.iconbitmap(str(IKON))
        except tk.TclError:
            pass

        ust = ttk.Frame(self.p, padding=8)
        ust.pack(fill="x")
        sayilar = {k: sum(d["kategori"] == k for d in self.plan["degisiklikler"]) for k in ("kural", "yz")}
        yuksek = sum(d["risk"] == "yuksek" for d in self.plan["degisiklikler"])
        self.esik = pl.esik(self.plan, self.onceki)
        oto = sum(1 for d in self.plan["degisiklikler"] if pl.otomatik_mi(d, self.esik))
        ttk.Label(ust, text=f"{sayilar['kural']} Kural çözer · {sayilar['yz']} YZ önerir ({yuksek} yüksek risk) · "
                            f"{len(self.plan.get('elle', []))} Elle düzeltilir · güven eşiği {self.esik:.2f}: "
                            f"{oto} otomatik onaylı",
                  style="Baslik.TLabel").pack(side="left")
        self.kural_hepsi = tk.BooleanVar(value=self.onceki["kural_hepsi"])
        ttk.Checkbutton(ust, text="Kural çözer önerilerinin tümünü onayla", variable=self.kural_hepsi,
                        command=self._agaci_yenile).pack(side="right")
        if self.uygulanmis:
            ttk.Label(self.p, text="Bu plan zaten uygulandı; kararlar yalnızca görüntülenir.",
                      foreground="#ef6c00", padding=(8, 0)).pack(fill="x")

        bolme = ttk.PanedWindow(self.p, orient="horizontal")
        bolme.pack(fill="both", expand=True, padx=8, pady=4)
        sol = ttk.Frame(bolme)
        bolme.add(sol, weight=2)
        sutunlar = ("karar", "guven", "risk", "bulgu", "dosya", "durum")
        self.agac = ttk.Treeview(sol, columns=sutunlar, show="tree headings", selectmode="browse")
        self.agac.heading("#0", text="Değişiklik")
        self.agac.column("#0", width=150)
        for s, baslik, gen in (("karar", "Karar", 100), ("guven", "Güven", 55), ("risk", "Risk", 70),
                               ("bulgu", "Bulgu", 160), ("dosya", "Dosya", 150), ("durum", "Durum", 110)):
            self.agac.heading(s, text=baslik)
            self.agac.column(s, width=gen)
        self.agac.tag_configure("yuksek", foreground="#c62828")
        self.agac.tag_configure("gecersiz", foreground="#9e9e9e")
        self.agac.pack(side="left", fill="both", expand=True)
        kaydirma = ttk.Scrollbar(sol, orient="vertical", command=self.agac.yview)
        kaydirma.pack(side="right", fill="y")
        self.agac.configure(yscrollcommand=kaydirma.set)
        self.agac.bind("<<TreeviewSelect>>", lambda e: self._ayrinti())

        sag = ttk.Frame(bolme, padding=(8, 0))
        bolme.add(sag, weight=3)
        self.baslik = ttk.Label(sag, style="Baslik.TLabel", wraplength=640, justify="left")
        self.baslik.pack(anchor="w")
        self.aciklama = ttk.Label(sag, wraplength=640, justify="left")
        self.aciklama.pack(anchor="w", pady=(4, 0))
        self.etki = ttk.Label(sag, wraplength=640, justify="left", foreground="#c62828")
        self.etki.pack(anchor="w")
        karar = ttk.LabelFrame(sag, text="Karar", padding=6)
        karar.pack(fill="x", pady=6)
        self.karar = tk.StringVar(value="")
        self.karar_dugmeleri = [ttk.Radiobutton(karar, text=m, value=v, variable=self.karar, command=self._karar_degisti)
                                for v, m in (("onay", "Onayla"), ("ret", "Reddet"), ("", "Karar yok"))]
        for d in self.karar_dugmeleri:
            d.pack(side="left", padx=4)
        self.risk = tk.BooleanVar()
        self.risk_kutusu = ttk.Checkbutton(karar, text="Yüksek riski kabul ediyorum", variable=self.risk,
                                           command=self._karar_degisti)
        self.risk_kutusu.pack(side="left", padx=12)
        self.deger_cercevesi = ttk.Frame(sag)
        self.deger_cercevesi.pack(fill="x")
        ttk.Label(self.deger_cercevesi, text="Yeni değer (düzenlenebilir):").pack(anchor="w")
        self.deger = tk.StringVar()
        self.deger_girisi = ttk.Entry(self.deger_cercevesi, textvariable=self.deger)
        self.deger_girisi.pack(fill="x")
        self.deger.trace_add("write", lambda *a: self._deger_degisti())
        self.diff = scrolledtext.ScrolledText(sag, wrap="none", font=("Consolas", 9), height=20)
        self.diff.pack(fill="both", expand=True, pady=(6, 0))
        for etiket, renk in (("ekle", "#2e7d32"), ("sil", "#c62828"), ("konum", "#1565c0"), ("yorum", "#757575")):
            self.diff.tag_configure(etiket, foreground=renk)

        alt = ttk.Frame(self.p, padding=8)
        alt.pack(fill="x")
        self.uyari = ttk.Label(alt, foreground="#ef6c00")
        self.uyari.pack(side="left")
        ttk.Button(alt, text="Kapat", command=self.p.destroy).pack(side="right")
        self.kaydet_dugmesi = ttk.Button(alt, text="Kararları kaydet", command=self.kaydet,
                                         state="disabled" if self.uygulanmis else "normal")
        self.kaydet_dugmesi.pack(side="right", padx=6)
        self._secili = None
        self._yukleniyor = False
        self._agaci_kur()

    def _agaci_kur(self):
        for kategori in ("kural", "yz"):
            ogeler = [d for d in self.plan["degisiklikler"] if d["kategori"] == kategori]
            self.agac.insert("", "end", iid="#" + kategori, text=f"{pl.KATEGORI_ADI[kategori]} ({len(ogeler)})",
                             open=True)
            for d in ogeler:
                self.agac.insert("#" + kategori, "end", iid=d["id"], text=d["id"])
        elle = self.plan.get("elle", [])
        self.agac.insert("", "end", iid="#elle", text=f"{pl.KATEGORI_ADI['elle']} ({len(elle)})", open=False)
        for i, e in enumerate(elle):
            self.agac.insert("#elle", "end", iid=f"elle{i}", text=f"E{i + 1:02d}",
                             values=("—", "", "", e.get("bulgu_aciklamasi", ""), f"{len(e.get('sayfalar', []))} sayfa",
                                     "yalnızca rapor"))
        self._agaci_yenile()

    def _karar_gosterimi(self, d):
        k = self.secimler[d["id"]]["karar"]
        if d["durum"] == "gecersiz":
            return "uygulanamaz"
        if k is None and pl.otomatik_mi(d, self.esik):
            return "✔ Otomatik"
        if k is None and d["kategori"] == "kural" and self.kural_hepsi.get():
            return "✔ Onay (tümü)"
        return self.KARAR_METNI[k]

    def _agaci_yenile(self):
        for d in self.plan["degisiklikler"]:
            s = self.secimler[d["id"]]
            risk = ("⚠ yüksek" + (" ✓" if s["risk"] else "")) if d["risk"] == "yuksek" else d["risk"]
            etiketler = ("yuksek",) if d["risk"] == "yuksek" else ()
            if d["durum"] == "gecersiz":
                etiketler = ("gecersiz",)
            guven = f"{d['guven']:.2f}" if d.get("guven") is not None else ""
            self.agac.item(d["id"], values=(self._karar_gosterimi(d), guven, risk, d["bulgu"], d["dosya"],
                                            pl.DURUM_ADI.get(d["durum"], d["durum"])), tags=etiketler)

    def _ayrinti(self):
        sec = self.agac.selection()
        if not sec:
            return
        iid = sec[0]
        self._yukleniyor = True
        self.diff.configure(state="normal")
        self.diff.delete("1.0", "end")
        d = self.degisiklik.get(iid)
        if d:
            self._secili = iid
            self.baslik.configure(text=f"{iid} · {pl.KATEGORI_ADI[d['kategori']]} · {d.get('bulgu_aciklamasi') or d['bulgu']}")
            self.aciklama.configure(text=f"{d.get('url', '')}\nGerekçe: {d.get('gerekce', '')}" +
                                         (f"\nDoğrulama: {d['dogrulama']['neden']}" if d["durum"] == "gecersiz" else "") +
                                         (f"\nDurum: {d['durum_nedeni']}" if d.get("durum_nedeni") else ""))
            notlar = []
            if d.get("guven") is not None:
                notlar.append(f"Güven {d['guven']:.2f} (eşik {self.esik:.2f}) · " +
                              ("otomatik onaylı; istemiyorsanız Reddet" if pl.otomatik_mi(d, self.esik) else "onay gerekir"))
            if d.get("zorunlu_onay"):
                notlar.append("Her zaman onay: " + d["zorunlu_onay"])
            notlar += ["Güven notu: " + n for n in d.get("guven_nedenleri") or []]
            if d.get("risk") == "yuksek" and d.get("etki"):
                notlar.append("Olası etki: " + d["etki"])
            self.etki.configure(text="\n".join(notlar))
            for satir in self.diffler.get(iid, "(diff yok)").splitlines():
                etiket = ("konum" if satir.startswith("@@") else "yorum" if satir.startswith(("#", "---", "+++"))
                          else "ekle" if satir.startswith("+") else "sil" if satir.startswith("-") else None)
                self.diff.insert("end", satir + "\n", etiket or ())
            s = self.secimler[iid]
            self.karar.set(s["karar"] or "")
            self.risk.set(s["risk"])
            duzenlenebilir = bool(d.get("duzenleme"))
            self.deger.set(s["deger"] if s["deger"] is not None else (str(d.get("yeni", "")) if duzenlenebilir else ""))
            kilitli = self.uygulanmis or d["durum"] == "gecersiz"
            for b in self.karar_dugmeleri:
                b.configure(state="disabled" if kilitli else "normal")
            self.risk_kutusu.configure(state="normal" if d["risk"] == "yuksek" and not kilitli else "disabled")
            self.deger_girisi.configure(state="normal" if duzenlenebilir and not kilitli else "disabled")
        else:
            self._secili = None
            for b in self.karar_dugmeleri:
                b.configure(state="disabled")
            self.risk_kutusu.configure(state="disabled")
            self.deger_girisi.configure(state="disabled")
            self.etki.configure(text="")
            if iid.startswith("elle"):
                e = self.plan["elle"][int(iid[4:])]
                self.baslik.configure(text="Elle düzeltilir · " + e.get("bulgu_aciklamasi", ""))
                self.aciklama.configure(text="Yapılması gereken: " + str(e.get("duzeltme", "")))
                self.diff.insert("end", "Etkilenen sayfalar:\n" + "\n".join(e.get("sayfalar", [])))
            else:
                self.baslik.configure(text=self.agac.item(iid, "text"))
                self.aciklama.configure(text="Bir değişiklik seçin.")
        self.diff.configure(state="disabled")
        self._yukleniyor = False

    def _karar_degisti(self):
        if self._yukleniyor or not self._secili:
            return
        s = self.secimler[self._secili]
        s["karar"] = self.karar.get() or None
        s["risk"] = self.risk.get()
        self._agaci_yenile()

    def _deger_degisti(self):
        if self._yukleniyor or not self._secili or not self.degisiklik[self._secili].get("duzenleme"):
            return
        self.secimler[self._secili]["deger"] = self.deger.get()

    def kaydet(self):
        argumanlar, uyarilar = pl.onay_argumanlari(self.plan, self.onceki, self.secimler, self.kural_hepsi.get())
        eksik_risk = [d["id"] for d in self.plan["degisiklikler"] if d["risk"] == "yuksek"
                      and self.secimler[d["id"]]["karar"] == "onay" and not self.secimler[d["id"]]["risk"]]
        if eksik_risk:
            uyarilar.append("Risk onayı verilmeyen yüksek riskli öneriler uygulanmayacak: " + ", ".join(eksik_risk))
        if uyarilar and not self.uyg.onay_sor("Uyarılar", "\n\n".join(uyarilar) + "\n\nYine de kaydedilsin mi?"):
            return
        if not argumanlar:
            self.uyg.bilgi_goster("Kaydedilecek karar yok", "Hiçbir öneri için karar verilmedi.")
            return
        if self.uyg.onaylari_kaydet(self.klasor, argumanlar, bitince=self._kaydedildi):
            self.kaydet_dugmesi.configure(state="disabled")

    def _kaydedildi(self, kod, satirlar):
        if kod == 0:
            self.uyg.plan_sec(self.klasor)
            if self.p.winfo_exists():
                self.p.destroy()
        elif self.p.winfo_exists():
            self.kaydet_dugmesi.configure(state="normal")


def calistir_arayuz(ayar_dosyasi=None):
    pencere = tk.Tk()
    uyg = Uygulama(pencere, ayar_dosyasi)
    pencere.mainloop()
    return uyg
