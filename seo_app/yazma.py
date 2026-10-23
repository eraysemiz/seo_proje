"""Yonetici modunda siteye yazma katmani.

Siteye yapilan her erisim SiteAdaptoru arayuzunden gecer: oku, yaz, listele, yedekle, geri_al.
Simdilik yalnizca yerel dosya sistemi adaptoru vardir (YerelDosyaAdaptoru). FTP/SFTP ya da bir
CMS API'si icin ayni arayuzu uygulayan bir sinif yazilip ADAPTORLER sozlugune eklenmesi yeterlidir;
yonetici akisi (yonetici.py) adaptorun turunu bilmez.

Guvenlik: adaptor yalnizca kurulurken verilen koke yazabilir. Mutlak yollar, '..' parcalari,
sembolik baglantilar ve Windows baglanti noktalari (junction) uzerinden kok disina cikis reddedilir
(YolGuvenligiHatasi). Yedek klasoru kokun icinde olamaz (yedek sitenin parcasi gibi sunulmasin).
Standart modda (Mod 2) bu modul hic kullanilmaz.
"""
import hashlib
import json
import os
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath


class YolGuvenligiHatasi(PermissionError):
    """Yapilandirilan hedefin disina erisim denemesi."""


def ozet_hash(veri):
    return hashlib.sha256(veri).hexdigest()


class SiteAdaptoru(ABC):
    """Siteye erisim arayuzu. Yollar her zaman koke gore, '/' ayracli goreli yollardir."""
    tur = "soyut"

    @abstractmethod
    def oku(self, yol) -> bytes: ...

    @abstractmethod
    def yaz(self, yol, veri: bytes) -> None: ...

    @abstractmethod
    def var_mi(self, yol) -> bool: ...

    @abstractmethod
    def listele(self) -> list: ...

    @abstractmethod
    def yedekle(self, hedef_klasor) -> dict:
        """Sitenin tam yedegini alir; {yol: sha256} manifestini dondurur."""

    @abstractmethod
    def geri_al(self, yedek_klasor) -> dict:
        """Siteyi yedekteki haline dondurur; dogrulama ozetini dondurur."""

    def hashler(self) -> dict:
        return {y: ozet_hash(self.oku(y)) for y in self.listele()}

    def tanim(self) -> dict:
        return {"tur": self.tur}


def goreli_yol_denetle(yol):
    """Adaptore verilen yolun yalnizca kok altinda kalan goreli bir yol oldugunu denetler."""
    if not isinstance(yol, str) or not yol or "\x00" in yol:
        raise YolGuvenligiHatasi("Geçersiz yol: " + repr(yol))
    duz = yol.replace("\\", "/")
    p = PurePosixPath(duz)
    if duz.startswith("/") or p.is_absolute() or (len(duz) > 1 and duz[1] == ":"):
        raise YolGuvenligiHatasi("Mutlak yola yazılamaz: " + yol)
    if any(parca in ("..", "") for parca in duz.split("/")):
        raise YolGuvenligiHatasi("Hedef dışına çıkan yol reddedildi: " + yol)
    return duz


class YerelDosyaAdaptoru(SiteAdaptoru):
    """Yerel bir klasorde duran sitenin belge koku (ornegin test_sitesi/site)."""
    tur = "yerel"

    def __init__(self, kok):
        kok_yolu = Path(kok)
        if not kok_yolu.is_dir():
            raise FileNotFoundError("Site kök klasörü bulunamadı: " + str(kok))
        if kok_yolu.is_symlink() or _baglanti_noktasi_mi(kok_yolu):
            raise YolGuvenligiHatasi("Site kökü sembolik bağlantı olamaz: " + str(kok))
        self.kok = kok_yolu.resolve()

    def tanim(self):
        return {"tur": self.tur, "kok": str(self.kok)}

    def _guvenli(self, yol):
        duz = goreli_yol_denetle(yol)
        hedef = self.kok
        for parca in duz.split("/"):
            hedef = hedef / parca
            # yol uzerindeki herhangi bir sembolik baglanti ya da junction kok disina cikabilir
            if hedef.is_symlink() or _baglanti_noktasi_mi(hedef):
                raise YolGuvenligiHatasi("Sembolik bağlantı üzerinden yazma reddedildi: " + yol)
        cozulmus = hedef.resolve()
        if cozulmus != self.kok and self.kok not in cozulmus.parents:
            raise YolGuvenligiHatasi("Hedef dışına yazma reddedildi: " + yol)
        return cozulmus

    def oku(self, yol):
        return self._guvenli(yol).read_bytes()

    def var_mi(self, yol):
        try:
            return self._guvenli(yol).is_file()
        except YolGuvenligiHatasi:
            return False

    def yaz(self, yol, veri):
        hedef = self._guvenli(yol)
        hedef.parent.mkdir(parents=True, exist_ok=True)
        # once ayni klasorde gecici dosyaya yazilir, sonra yerine konur: yarim yazilmis dosya kalmaz
        fd, gecici = tempfile.mkstemp(dir=hedef.parent, prefix=".yaziliyor_")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(veri)
            os.replace(gecici, hedef)
        except BaseException:
            Path(gecici).unlink(missing_ok=True)
            raise

    def listele(self):
        sonuc = []
        for kok, klasorler, dosyalar in os.walk(self.kok, followlinks=False):
            klasorler[:] = [k for k in klasorler if not (Path(kok, k).is_symlink() or _baglanti_noktasi_mi(Path(kok, k)))]
            for ad in dosyalar:
                p = Path(kok, ad)
                if not p.is_symlink():
                    sonuc.append(p.relative_to(self.kok).as_posix())
        return sorted(sonuc)

    def _kok_disi(self, klasor):
        klasor = Path(klasor).resolve()
        if klasor == self.kok or self.kok in klasor.parents:
            raise YolGuvenligiHatasi("Yedek klasörü site kökünün içinde olamaz: " + str(klasor))
        return klasor

    def yedekle(self, hedef_klasor):
        hedef = self._kok_disi(hedef_klasor)
        dosyalar = hedef / "dosyalar"
        dosyalar.mkdir(parents=True, exist_ok=False)
        manifest = {}
        for yol in self.listele():
            veri = self.oku(yol)
            (dosyalar / yol).parent.mkdir(parents=True, exist_ok=True)
            (dosyalar / yol).write_bytes(veri)
            manifest[yol] = ozet_hash(veri)
        (hedef / "manifest.json").write_text(json.dumps({
            "adaptor": self.tanim(), "zaman": time.strftime("%Y-%m-%d %H:%M:%S"), "dosyalar": manifest},
            ensure_ascii=False, indent=1), encoding="utf-8")
        return manifest

    def geri_al(self, yedek_klasor):
        yedek = self._kok_disi(yedek_klasor)
        bilgi = json.loads((yedek / "manifest.json").read_text(encoding="utf-8"))
        if Path(bilgi["adaptor"]["kok"]).resolve() != self.kok:
            raise YolGuvenligiHatasi("Yedek başka bir site köküne ait: " + bilgi["adaptor"]["kok"])
        manifest = bilgi["dosyalar"]
        silinen = [y for y in self.listele() if y not in manifest]
        for y in silinen:                           # uygulamadan sonra eklenen dosyalar kaldirilir
            self._guvenli(y).unlink()
        geri_yazilan = 0
        for yol, beklenen in manifest.items():
            veri = (yedek / "dosyalar" / yol).read_bytes()
            if ozet_hash(veri) != beklenen:
                raise ValueError("Yedekteki dosya bozulmuş: " + yol)
            if not self.var_mi(yol) or ozet_hash(self.oku(yol)) != beklenen:
                self.yaz(yol, veri)
                geri_yazilan += 1
        simdi = self.hashler()
        return {"eslesiyor": simdi == manifest, "dosya_sayisi": len(manifest),
                "geri_yazilan": geri_yazilan, "silinen": silinen}


def _baglanti_noktasi_mi(p):
    """Windows'ta junction da bir dizin baglantisidir (Python 3.12+ is_junction)."""
    try:
        return bool(getattr(p, "is_junction", lambda: False)())
    except OSError:
        return False


# FTP/SFTP/CMS adaptorleri ayni arayuzle eklenebilir; simdilik yalnizca yerel dosya sistemi vardir.
ADAPTORLER = {"yerel": YerelDosyaAdaptoru}


def adaptor_olustur(tur, **ayar):
    if tur not in ADAPTORLER:
        raise NotImplementedError("Bu erişim türü henüz desteklenmiyor: " + str(tur) +
                                  " (desteklenen: " + ", ".join(ADAPTORLER) + ")")
    return ADAPTORLER[tur](**ayar)
