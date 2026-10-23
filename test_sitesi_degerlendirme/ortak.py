"""Degerlendirme betiklerinin ortak yardimcilari (yollar, hash, HTTP)."""
import hashlib
import json
from pathlib import Path

BURASI = Path(__file__).resolve().parent
PROJE = BURASI.parent
ORIJINAL = BURASI / "orijinal_site"
CANLI = PROJE / "test_sitesi" / "site"
MANIFEST = BURASI / "orijinal_hashler.json"
SORUNLAR = BURASI / "sorunlar.json"
TABAN = "http://127.0.0.1:8080"


def klasor_hashleri(kok):
    """{goreli_yol: sha256} — klasordeki tum dosyalar (alt klasorler dahil)."""
    kok = Path(kok)
    return {p.relative_to(kok).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(kok.rglob("*")) if p.is_file()}


def manifest_oku():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def sorunlari_oku():
    return json.loads(SORUNLAR.read_text(encoding="utf-8"))
