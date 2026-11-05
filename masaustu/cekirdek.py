"""Masaustu arayuzunun gorunumden bagimsiz cekirdegi: betikleri alt surec olarak calistirir, ciktiyi ve
durumu tutar. Ayni anda tek bir is calisir (tarama, dogrulama, sifirlama vb.); test sitesi ve web arayuzu
sunuculari bundan bagimsiz arka plan surecleridir. Analiz, puanlama ve duzeltme burada yapilmaz: hepsi
yonet.py ve digerlerinde; sayilar sonuc klasorlerindeki raporlardan okunur (plan.py, sonuclar.py).
"""
import os
import re
import subprocess
import threading
import time
from pathlib import Path

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
    "gomme": "masaustu/gomme_yenile.py",
}
DURUM_ARALIGI_SN = 4
GUNLUK_SINIRI = 5000
# yonet.py ve seo_app.yonetici'nin yazdigi satirlardan tarama asamasi; yalnizca gosterim icindir
ASAMA_DESENLERI = (
    ("yeniden_kontrol", re.compile(r"yeniden taranıyor")),
    ("otomatik", re.compile(r"Otomatik aşama|güven eşiğini geçen|tam yedeği alındı")),
    ("analiz", re.compile(r"Değişiklik planı hazırlanıyor|tarama geneli bulgu|model çalışıyor")),
    ("tarama", re.compile(r"\[\d+/\d+\]|İndiriliyor|Site taraması")),
)
ASAMA_SIRASI = ("tarama", "analiz", "otomatik", "yeniden_kontrol")


class KullaniciHatasi(Exception):
    """Arayuzde anlasilir ileti olarak gosterilir."""

    def __init__(self, baslik, ileti):
        super().__init__(ileti)
        self.baslik, self.ileti = baslik, ileti


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
    return f"İşlem {kod} çıkış koduyla bitti. Ayrıntılar günlükte."


def satir_turu(m):
    if m.lstrip().startswith(("HATA", "BEKLENMEYEN", "Traceback")) or "UYUMSUZ" in m:
        return "hata"
    if m.lstrip().startswith(("UYARI", "✗")):
        return "uyari"
    if "✓" in m:
        return "tamam"
    return None


def sonuc_klasoru(satirlar, kok):
    for s in reversed(satirlar):
        if s.startswith("Sonuç klasörü:"):
            p = Path(s.split(":", 1)[1].strip())
            return p if p.is_absolute() else Path(kok) / p
    return None


class Cekirdek:
    def __init__(self, ayar_dosyasi=None):
        self.ayar_dosyasi = ayar_dosyasi
        self.ayar = ay.yukle(ayar_dosyasi)
        self.kilit = threading.RLock()
        self.is_ = None
        self.son_is = None
        self.biten_is_sayisi = 0
        self.sunucular = {"test": None, "web": None}
        self.baslatilan_pidler = []
        self.plan_klasoru = None
        self.salt_sonuc = None
        self.asama = None
        self.gunluk = []
        self._sira = 0
        self.bildirimler = []               # arayuzun gosterecegi hata iletileri (is sonucu)
        self.durum = {"lm": None, "lm_url": self.ayar["lm_url"], "test": False, "web": False}
        self._durdur = threading.Event()
        self._durum_istegi = threading.Event()
        threading.Thread(target=self._durum_dongusu, daemon=True).start()

    # ---- yardimcilar
    def kok(self):
        return Path(self.ayar["proje_koku"]) if ay.proje_koku_mu(self.ayar["proje_koku"]) else None

    def goreli(self, p):
        try:
            return Path(p).relative_to(self.kok())
        except (TypeError, ValueError):
            return p

    def log(self, metin, tur=None):
        with self.kilit:
            self._sira += 1
            self.gunluk.append({"n": self._sira, "m": metin, "t": tur})
            del self.gunluk[:-GUNLUK_SINIRI]

    def gunluk_sonrasi(self, n):
        with self.kilit:
            return [g for g in self.gunluk if g["n"] > n]

    def _bildir(self, baslik, ileti):
        with self.kilit:
            self._sira += 1
            self.bildirimler.append({"n": self._sira, "baslik": baslik, "ileti": ileti})
            del self.bildirimler[:-50]

    # ---- is calistirma
    def calistir(self, ad, betik, argumanlar=(), bitince=None, iptal_edilebilir=True, sunucu=None):
        """Betigi alt surec olarak baslatir. sunucu verilmezse tek is yuvasini kullanir."""
        kok = self.kok()
        if not kok:
            raise KullaniciHatasi("Proje klasörü yok", "Proje klasörü bulunamadı. Ayarlar ekranından yonet.py'nin "
                                                       "bulunduğu klasörü seçin.")
        with self.kilit:
            if sunucu is None and self.is_ is not None:
                raise KullaniciHatasi("İşlem sürüyor", "Şu anda '" + self.is_.ad + "' çalışıyor. Bitmesini bekleyin "
                                                       "ya da İptal ile durdurun.")
            s = Surec(ad, betik_komutu(kok / BETIKLER[betik], *argumanlar), kok, iptal_edilebilir=iptal_edilebilir)
            s.satirlar, s.bitince, s.sunucu = [], bitince, sunucu
            s.satir = lambda m, s=s: self._satir(s, m)
            s.bitti = lambda kod, iptal, s=s: self._bitti(s, kod, iptal)
            self.log("▶ " + ad, "baslik")
            self.log("  " + " ".join([BETIKLER[betik], *map(str, argumanlar)]), "soluk")
            try:
                s.baslat()
            except OSError as e:
                self.log("HATA: süreç başlatılamadı: " + str(e), "hata")
                raise KullaniciHatasi(ad, "Süreç başlatılamadı: " + str(e)) from e
            s.baslangic = time.time()
            self.baslatilan_pidler.append(s.pid)
            if sunucu:
                self.sunucular[sunucu] = s
            else:
                self.is_ = s
                self.asama = None
        return s

    def _satir(self, s, m):
        with self.kilit:
            s.satirlar.append(m)
            self.log(("[" + s.ad + "] " if s.sunucu else "") + m, satir_turu(m))
            if s is self.is_:
                for ad, desen in ASAMA_DESENLERI:
                    if desen.search(m):
                        if self.asama is None or ASAMA_SIRASI.index(ad) >= ASAMA_SIRASI.index(self.asama):
                            self.asama = ad
                        break

    def _bitti(self, s, kod, iptal):
        sure = time.time() - s.baslangic
        with self.kilit:
            if s.sunucu:
                if self.sunucular.get(s.sunucu) is s:
                    self.sunucular[s.sunucu] = None
                if iptal:
                    self.log("■ " + s.ad + " durduruldu.", "soluk")
                elif kod not in (0, None):
                    self.log("✗ " + s.ad + " kapandı (kod " + str(kod) + ")", "hata")
                    ses.cal("hata", self.ayar["ses"])
                    self._bildir(s.ad, hata_iletisi(s.satirlar, kod))
                self._durum_istegi.set()
                return
            self.is_ = None
            self.asama = None
            if iptal:
                self.log(f"■ {s.ad} iptal edildi ({sure:.1f} sn)", "uyari")
            elif kod == 0:
                self.log(f"✓ {s.ad} tamamlandı ({sure:.1f} sn)", "tamam")
                ses.cal("bitti", self.ayar["ses"])
            else:
                ileti = hata_iletisi(s.satirlar, kod)
                self.log(f"✗ {s.ad} başarısız (kod {kod}): {ileti}", "hata")
                ses.cal("hata", self.ayar["ses"])
                self._bildir(s.ad, ileti)
            if not iptal and s.bitince:
                s.bitince(kod, s.satirlar)
            # sayac en son artar: oto-test ve arayuz gorunce plan_klasoru gibi sonuclar yerindedir
            self.son_is = {"ad": s.ad, "kod": kod, "iptal": iptal, "satirlar": list(s.satirlar), "sure": sure,
                           "pid": s.pid}
            self.biten_is_sayisi += 1

    def iptal(self):
        s = self.is_
        if not s:
            return
        if not s.iptal_edilebilir:
            raise KullaniciHatasi("İptal edilemez", "'" + s.ad + "' siteye ya da sonuç klasörüne yazıyor; yarıda "
                                                    "kesilirse dosyalar tutarsız kalabilir. Bitmesini bekleyin.")
        self.log("■ İptal ediliyor: " + s.ad, "uyari")
        s.iptal()

    # ---- durum
    def _durum_dongusu(self):
        while not self._durdur.is_set():
            a = dict(self.ayar)
            self.durum = {"lm": durum.lm_durumu(a["lm_url"], [a["sohbet_modeli"], a["gomme_modeli"]]),
                          "lm_url": a["lm_url"], "test": durum.port_acik(a["test_portu"]),
                          "web": durum.port_acik(a["web_portu"])}
            self._durum_istegi.wait(DURUM_ARALIGI_SN)
            self._durum_istegi.clear()

    def durum_yenile(self):
        self._durum_istegi.set()

    def lm_modelleri(self):
        url = self.ayar["lm_url"]
        d = durum.lm_durumu(url, [])
        if not d["erisim"]:
            raise KullaniciHatasi("LM Studio", durum.lm_iletisi(d, url))
        return {"sohbet": [m["id"] for m in d["modeller"] if "embed" not in m["id"].lower()],
                "gomme": [m["id"] for m in d["modeller"] if "embed" in m["id"].lower()]}

    # ---- tarama
    def tara(self, mod, adresler, kok, model, sohbet, gomme, sayfa, derinlik, site_modu):
        if not adresler:
            raise KullaniciHatasi("Adres yok", "Taranacak site adresini girin.")
        if mod == "yonetici" and len(adresler) != 1:
            raise KullaniciHatasi("Tek adres", "Yönetici modunda sitenin tek bir temel adresi verilir.")
        if model:
            if not sohbet:
                raise KullaniciHatasi("Model seçilmedi", "Sohbet modeli seçin ya da 'Dil modeli kullan' seçeneğini "
                                                         "kapatın.")
            # tarama baslamadan LM Studio ve modeller denetlenir (betikler de ayni denetimi yapar)
            url = self.ayar["lm_url"]
            self.log("LM Studio ve modeller denetleniyor: " + url, "soluk")
            ileti = durum.lm_iletisi(durum.lm_durumu(url, [sohbet, gomme]), url)
            if ileti:
                self.log("HATA: " + ileti, "hata")
                ses.cal("hata", self.ayar["ses"])
                raise KullaniciHatasi("Tarama başlatılamadı", ileti + " Modelsiz denemek için 'Dil modeli kullan' "
                                                                      "seçeneğini kapatın.")
        model_arg = (["--model", sohbet, *(["--embed-model", gomme] if gomme else []),
                      "--lm-url", self.ayar["lm_url"]]) if model else []
        if mod == "yonetici":
            self.calistir("Yönetici taraması", "yonet",
                          ["tara", "--kok", kok, "--url", adresler[0], "--sayfa", sayfa, "--derinlik", derinlik,
                           *model_arg], bitince=self._plan_hazir)
        else:
            self.calistir("Salt okunur tarama", "salt",
                          ["--adres", *adresler, "--sayfa", sayfa, "--derinlik", derinlik,
                           *(["--site-modu"] if site_modu else []), *(model_arg or ["--yalnizca-denetim"])],
                          bitince=self._salt_bitti)

    def _plan_hazir(self, kod, satirlar):
        if kod == 0:
            self.plan_klasoru = sonuc_klasoru(satirlar, self.kok())

    def _salt_bitti(self, kod, satirlar):
        if kod == 0:
            self.salt_sonuc = sonuc_klasoru(satirlar, self.kok())

    # ---- onay ve uygulama
    def onaylari_kaydet(self, klasor, argumanlar):
        self.calistir("Onayları kaydet", "yonet", ["onayla", self.goreli(klasor), *argumanlar],
                      iptal_edilebilir=False)

    def uygulama_ozeti(self, klasor):
        plan = pl.plani_oku(klasor)
        kararlar = pl.kararlari_oku(klasor)
        return {"yazilacak": pl.onaylanan_sayisi(plan, kararlar),
                "geri_cekilecek": pl.geri_cekilecek_sayisi(plan, kararlar),
                "zaten": sum(1 for d in plan["degisiklikler"] if d["durum"] == "uygulandi"),
                "kok": ((plan.get("hedef") or {}).get("adaptor") or {}).get("kok") or ""}

    def uygula(self, klasor):
        o = self.uygulama_ozeti(klasor)
        if not (o["yazilacak"] or o["geri_cekilecek"] or o["zaten"]):
            raise KullaniciHatasi("Onaylı değişiklik yok", "Uygulanacak onaylı değişiklik yok. Önce Onay ekranından "
                                                           "önerileri onaylayın.")
        self.calistir("Uygula", "yonet", ["uygula", self.goreli(klasor)], iptal_edilebilir=False)

    def geri_al(self, site_klasoru):
        if not sn.geri_alinabilir(site_klasoru):
            raise KullaniciHatasi("Geri alınacak uygulama yok", "Bu site için geri alınabilir bir uygulama yok.")
        self.calistir("Geri al", "yonet", ["geri-al", self.goreli(site_klasoru)], iptal_edilebilir=False)

    # ---- test sitesi ve web arayuzu
    def sunucu_baslat(self, ad):
        port = self.ayar["test_portu" if ad == "test" else "web_portu"]
        if durum.port_acik(port):
            raise KullaniciHatasi("Port kullanımda", f"{port} portunda zaten bir sunucu çalışıyor. Başka bir "
                                                     "pencereden başlatılmış olabilir.")
        if ad == "test":
            self.calistir("Test sitesi", "sunucu", ["--port", port], sunucu="test")
        else:
            self.calistir("Web arayüzü", "web", ["--port", port, "--acma"], sunucu="web")
        threading.Timer(0.8, self._durum_istegi.set).start()

    def sunucu_durdur(self, ad):
        s = self.sunucular.get(ad)
        if s:
            s.iptal()

    def dogrula(self):
        if not durum.port_acik(self.ayar["test_portu"]):
            raise KullaniciHatasi("Test sitesi kapalı", "Doğrulama için önce test sitesini başlatın.")
        self.calistir("Doğrula", "dogrula")

    def sifirla(self):
        self.calistir("Sıfırla", "sifirla", iptal_edilebilir=False)

    def hash_karsilastir(self):
        self.calistir("Hash karşılaştır", "sifirla", ["--kontrol"])

    def degerlendir(self, klasor):
        self.calistir("Değerlendir", "degerlendir", ["--sonuc", self.goreli(klasor)])

    def gomme_yenile(self):
        if not self.ayar["gomme_modeli"]:
            raise KullaniciHatasi("Gömme modeli yok", "Ayarlar ekranından bir gömme modeli seçin.")
        self.calistir("Gömme önbelleğini yenile", "gomme", [self.ayar["gomme_modeli"], self.ayar["lm_url"]])

    # ---- ayarlar
    def ayarlari_kaydet(self, yeni):
        yeni = {k: (v.strip() if isinstance(v, str) else v) for k, v in yeni.items() if k in ay.VARSAYILAN}
        hatalar = ay.dogrula({**self.ayar, **yeni})
        if hatalar:
            raise KullaniciHatasi("Ayarlar kaydedilmedi", " ".join(hatalar))
        self.ayar.update(yeni)
        self.ayar["test_portu"], self.ayar["web_portu"] = int(self.ayar["test_portu"]), int(self.ayar["web_portu"])
        yol = ay.kaydet(self.ayar, self.ayar_dosyasi)
        self.log("Ayarlar kaydedildi: " + str(yol), "tamam")
        self._durum_istegi.set()

    # ---- kapanis
    def kapanabilir_mi(self):
        """(kapanabilir, soru ya da engel iletisi)."""
        s = self.is_
        if s and not s.iptal_edilebilir:
            return False, "'" + s.ad + "' yazma işlemi sürüyor; bitince kapatabilirsiniz."
        return True, ("'" + s.ad + "' çalışıyor. İptal edilip uygulama kapatılsın mı?") if s else ""

    def kapat(self):
        for s in [self.is_, *self.sunucular.values()]:
            if s:
                s.iptal()
        for s in [self.is_, *self.sunucular.values()]:
            if s:
                s.bekle(5)
        self._durdur.set()
        self._durum_istegi.set()


def dosya_ac(yol):
    yol = Path(yol)
    try:
        os.startfile(str(yol))
    except OSError:
        # .diff / .md icin ilisik program yoksa Not Defteri ile acilir
        subprocess.Popen(["notepad.exe", str(yol)])
