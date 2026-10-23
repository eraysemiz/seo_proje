#!/usr/bin/env python3
"""Çaylıbahçe test sitesini yerelde sunar (yalnizca 127.0.0.1).

Kullanim:
    py test_sitesi/sunucu.py              # http://127.0.0.1:8080
    py test_sitesi/sunucu.py --port 8081

Belge koku test_sitesi/site/ klasorudur. Yonlendirmeler ve hata sayfalari gibi sunucu
ayarlari sunucu_ayarlari.json'dadir (barindirma ayari: belge kokunun disinda tutulur).
"""
import argparse
import gzip
import json
import mimetypes
import posixpath
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

BURASI = Path(__file__).resolve().parent
KOK = BURASI / "site"
AYARLAR = json.loads((BURASI / "sunucu_ayarlari.json").read_text(encoding="utf-8"))
SIKISTIRILAN = ("text/", "application/javascript", "application/json", "application/xml", "image/svg+xml")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/javascript", ".js")


def dosya_bul(yol):
    """Istek yolunu belge kokundeki dosyaya cevirir; kok disina cikan yollar reddedilir.
    (dosya veya None, dizin icin '/' eksikse yonlendirilecek adres) dondurur."""
    temiz = posixpath.normpath(unquote(yol))
    if temiz.startswith("..") or "\x00" in temiz:
        return None, None
    aday = (KOK / temiz.lstrip("/")).resolve()
    if aday != KOK and KOK not in aday.parents:
        return None, None
    # Windows dosya sistemi buyuk/kucuk harf ayirmaz; sunucu Linux'taki gibi harf duyarli davranir
    # (resolve() Windows'ta diskteki harfleri dondurdugu icin istenen yolun parcalari karsilastirilir)
    gecerli = KOK
    for parca in [p for p in temiz.split("/") if p not in ("", ".")]:
        if not gecerli.is_dir() or parca not in {p.name for p in gecerli.iterdir()}:
            return None, None
        gecerli = gecerli / parca
    if aday.is_dir():
        if not yol.endswith("/"):
            return None, yol + "/"
        aday = aday / "index.html"
    return (aday if aday.is_file() else None), None


class Isleyici(BaseHTTPRequestHandler):
    server_version = "CaylibahceTest/1.0"

    def log_message(self, bicim, *args):
        if not AYARLAR.get("sessiz"):
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), bicim % args))

    def _gonder(self, durum, govde=b"", tur="text/html; charset=utf-8", basliklar=None, bas_istegi=False):
        sikistir = govde and tur.startswith(SIKISTIRILAN) and "gzip" in (self.headers.get("Accept-Encoding") or "")
        if sikistir:
            govde = gzip.compress(govde)
        self.send_response(durum)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        if sikistir:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        for ad, deger in (basliklar or {}).items():
            self.send_header(ad, deger)
        self.end_headers()
        if not bas_istegi:
            self.wfile.write(govde)

    def _sablon(self, ad):
        return (BURASI / "sablonlar" / ad).read_bytes()

    def _isle(self, bas_istegi=False):
        yol = urlsplit(self.path).path
        hedef = AYARLAR["yonlendirmeler"].get(yol)
        if hedef:
            self._gonder(hedef["kod"], basliklar={"Location": hedef["hedef"]}, bas_istegi=bas_istegi)
            return
        dosya, dizin_yonu = dosya_bul(yol)
        if dizin_yonu:
            self._gonder(301, basliklar={"Location": dizin_yonu}, bas_istegi=bas_istegi)
            return
        if dosya:
            tur = mimetypes.guess_type(dosya.name)[0] or "application/octet-stream"
            if tur.startswith("text/") or tur in ("application/javascript", "application/json", "application/xml",
                                                  "image/svg+xml"):
                tur += "; charset=utf-8"
            self._gonder(200, dosya.read_bytes(), tur, bas_istegi=bas_istegi)
            return
        # urun klasorunde bulunamayan sayfalar icin magaza yazilimi bir "urun bulunamadi" sayfasi gosterir
        if any(yol.startswith(onek) for onek in AYARLAR["urun_bulunamadi_onekleri"]):
            self._gonder(200, self._sablon("urun_bulunamadi.html"), bas_istegi=bas_istegi)
            return
        self._gonder(404, self._sablon("404.html"), bas_istegi=bas_istegi)

    def do_GET(self):
        self._isle()

    def do_HEAD(self):
        self._isle(bas_istegi=True)


def main():
    ap = argparse.ArgumentParser(description="Çaylıbahçe test sitesi (yalnızca yerel)")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    sunucu = ThreadingHTTPServer(("127.0.0.1", args.port), Isleyici)
    print(f"Test sitesi çalışıyor: http://127.0.0.1:{args.port}/  (belge kökü: {KOK})")
    print("Durdurmak için Ctrl+C")
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
