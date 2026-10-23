#!/usr/bin/env python3
"""Uygulama ikonunu (masaustu/ikon.ico) yalnizca standart kutuphaneyle uretir: mavi zemin
uzerinde buyutec. 16/32/48 piksel DIB ve 256 piksel PNG goruntu icerir (Tk ve Windows Gezgini
ikisini de okur). Kendi ikonunuzu kullanmak icin masaustu/ikon.ico dosyasini degistirin.

    py masaustu/ikon_uret.py
"""
import math
import struct
import sys
import zlib
from pathlib import Path

HEDEF = Path(__file__).resolve().parent / "ikon.ico"
ZEMIN = (31, 111, 235)
CIZGI = (255, 255, 255)


def _kapsama(mesafe):
    # kenardan uzakliga gore yumusatma: icerde 1, disarda 0, kenarda dogrusal gecis
    return max(0.0, min(1.0, 0.5 - mesafe))


def _piksel(x, y, n):
    s = 256 / n
    px, py = (x + 0.5) * s, (y + 0.5) * s
    # yuvarlatilmis kare zemin
    r = 44
    qx, qy = max(abs(px - 128) - (128 - 8 - r), 0), max(abs(py - 128) - (128 - 8 - r), 0)
    zemin = _kapsama((math.hypot(qx, qy) - r) / s)
    if not zemin:
        return (0, 0, 0, 0)
    # buyutec halkasi ve sapi
    halka = _kapsama((abs(math.hypot(px - 112, py - 112) - 58) - 13) / s)
    t = max(0.0, min(1.0, ((px - 156) * 1 + (py - 156) * 1) / (2 * 52 ** 2) * 52))
    sx, sy = 156 + t * 52, 156 + t * 52
    sap = _kapsama((math.hypot(px - sx, py - sy) - 15) / s) if px + py > 300 else 0.0
    c = max(halka, sap)
    renk = tuple(round(z * (1 - c) + k * c) for z, k in zip(ZEMIN, CIZGI))
    return (*renk, round(255 * zemin))


def goruntu(n):
    return [[_piksel(x, y, n) for x in range(n)] for y in range(n)]


def png(n):
    satirlar = b"".join(b"\x00" + bytes(v for p in satir for v in p) for satir in goruntu(n))

    def parca(tur, veri):
        return struct.pack(">I", len(veri)) + tur + veri + struct.pack(">I", zlib.crc32(tur + veri) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + parca(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)) +
            parca(b"IDAT", zlib.compress(satirlar, 9)) + parca(b"IEND", b""))


def dib(n):
    pikseller = goruntu(n)
    renk = b"".join(bytes((b, g, r, a)) for satir in reversed(pikseller) for (r, g, b, a) in satir)
    maske_satiri = ((n + 31) // 32) * 4
    return struct.pack("<IiiHHIIiiII", 40, n, 2 * n, 1, 32, 0, len(renk), 0, 0, 0, 0) + renk + b"\x00" * maske_satiri * n


def ico():
    goruntuler = [(16, dib(16)), (32, dib(32)), (48, dib(48)), (256, png(256))]
    bas = struct.pack("<HHH", 0, 1, len(goruntuler))
    konum = 6 + 16 * len(goruntuler)
    dizin, veri = b"", b""
    for n, g in goruntuler:
        dizin += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(g), konum + len(veri))
        veri += g
    return bas + dizin + veri


def main():
    HEDEF.write_bytes(ico())
    print("İkon yazıldı:", HEDEF)
    return 0


if __name__ == "__main__":
    sys.exit(main())
