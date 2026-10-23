"""Betikleri alt surec olarak calistirir ve ciktilarini satir satir okur.

Her surec kendi Windows Job Object'ine baglanir (KILL_ON_JOB_CLOSE): iptal edildiginde surec ve
onun baslattigi alt surecler (or. JS render icin Chrome) birlikte kapanir; uygulama beklenmedik
bicimde kapansa bile isletim sistemi tutamaci kapatirken hepsini sonlandirir.

.exe icinden calisirken Python yorumlayicisi .exe'nin kendisidir: betik `<exe> --betik <yol>`
ile calistirilir (bkz. baslat.py). Kaynaktan calisirken `python -u <yol>` kullanilir.
"""
import os
import subprocess
import sys
import threading

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _IoSayaclari(ctypes.Structure):
        _fields_ = [(ad, ctypes.c_ulonglong) for ad in ("ReadOperationCount", "WriteOperationCount",
                                                         "OtherOperationCount", "ReadTransferCount",
                                                         "WriteTransferCount", "OtherTransferCount")]

    class _TemelSinir(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _GenisSinir(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _TemelSinir), ("IoInfo", _IoSayaclari),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    _k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    _k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _GENIS_SINIR_BILGISI = 9
    _KAPANINCA_OLDUR = 0x2000

    def _is_nesnesi(surec_tutamaci):
        is_ = _k32.CreateJobObjectW(None, None)
        if not is_:
            return None
        bilgi = _GenisSinir()
        bilgi.BasicLimitInformation.LimitFlags = _KAPANINCA_OLDUR
        _k32.SetInformationJobObject(is_, _GENIS_SINIR_BILGISI, ctypes.byref(bilgi), ctypes.sizeof(bilgi))
        if not _k32.AssignProcessToJobObject(is_, int(surec_tutamaci)):
            _k32.CloseHandle(is_)
            return None
        return is_

    PENCERESIZ = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
else:                                       # testler ve gelistirme icin; uygulama Windows'a yoneliktir
    _k32 = None

    def _is_nesnesi(surec_tutamaci):
        return None

    PENCERESIZ = 0


def betik_komutu(betik, *argumanlar):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--betik", str(betik), *map(str, argumanlar)]
    return [sys.executable, "-u", str(betik), *map(str, argumanlar)]


def ortam():
    """Alt sureclerin Turkce karakterleri UTF-8 yazmasi ve ciktinin gecikmeden gelmesi icin."""
    return {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}


class Surec:
    """Tek bir alt surec. satir(metin) her cikti satirinda, bitti(kod, iptal) surec bitince
    okuma is parcaciginda cagrilir; arayuz bunlari kuyruk uzerinden ana is parcacigina tasir."""

    def __init__(self, ad, argv, cwd, satir=None, bitti=None, iptal_edilebilir=True):
        self.ad, self.argv, self.cwd = ad, argv, str(cwd)
        self.satir = satir or (lambda m: None)
        self.bitti = bitti or (lambda kod, iptal: None)
        self.iptal_edilebilir = iptal_edilebilir
        self.iptal_edildi = False
        self.kod = None
        self._p = None
        self._is = None
        self._okuyucu = None

    def baslat(self):
        self._p = subprocess.Popen(self.argv, cwd=self.cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=ortam(), creationflags=PENCERESIZ)
        if os.name == "nt":
            self._is = _is_nesnesi(self._p._handle)
        self._okuyucu = threading.Thread(target=self._oku, daemon=True)
        self._okuyucu.start()
        return self

    def _oku(self):
        for ham in iter(self._p.stdout.readline, b""):
            self.satir(ham.decode("utf-8", errors="replace").rstrip("\r\n"))
        self._p.stdout.close()
        self.kod = self._p.wait()
        self._tutamaci_kapat()
        self.bitti(self.kod, self.iptal_edildi)

    @property
    def calisiyor(self):
        return self._p is not None and self._p.poll() is None

    @property
    def pid(self):
        return self._p.pid if self._p else None

    def iptal(self):
        if not self.calisiyor:
            return
        self.iptal_edildi = True
        if self._is and _k32.TerminateJobObject(self._is, 1):
            return
        self._p.kill()

    def bekle(self, sure=None):
        if self._okuyucu:
            self._okuyucu.join(sure)
        return self.kod

    def _tutamaci_kapat(self):
        if self._is:
            _k32.CloseHandle(self._is)
            self._is = None
