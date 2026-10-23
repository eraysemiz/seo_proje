"""Durum cubugu denetimleri: LM Studio ve modeller, yerel sunucularin portlari.

seo_app.llm.model_durumlari ile ayni uclari okur (/api/v0/models, yoksa /v1/models); arayuz
sureci seo_app'i ice aktarmadigi icin yalnizca standart kutuphane kullanilir.
"""
import json
import re
import socket
import urllib.error
import urllib.request


def port_acik(port, host="127.0.0.1", sure=0.5):
    try:
        with socket.create_connection((host, int(port)), timeout=sure):
            return True
    except OSError:
        return False


def _getir(url, sure):
    with urllib.request.urlopen(url, timeout=sure) as y:
        return json.loads(y.read().decode("utf-8"))


def lm_durumu(url, modeller, sure=2.0):
    """{"erisim", "hata", "modeller": [{"id", "yuklu"}], "eksik", "yuklu_degil"} dondurur.
    yuklu None ise sunucu yukleme durumunu bildirmiyor demektir."""
    kok = re.sub(r"//localhost(?=[:/]|$)", "//127.0.0.1", url or "").rstrip("/")
    kok = kok[:-3] if kok.endswith("/v1") else kok
    try:
        try:
            liste = [{"id": m["id"], "yuklu": m.get("state") == "loaded"}
                     for m in _getir(kok + "/api/v0/models", sure).get("data", [])]
        except urllib.error.HTTPError:
            liste = [{"id": m["id"], "yuklu": None} for m in _getir(kok + "/v1/models", sure).get("data", [])]
    except (OSError, ValueError, KeyError) as e:
        return {"erisim": False, "hata": type(e).__name__, "modeller": [], "eksik": [], "yuklu_degil": []}
    durumlar = {m["id"]: m for m in liste}
    gerekli = [m for m in modeller if m]
    return {"erisim": True, "hata": None, "modeller": liste,
            "eksik": [m for m in gerekli if m not in durumlar],
            "yuklu_degil": [m for m in gerekli if m in durumlar and durumlar[m]["yuklu"] is False]}


def lm_iletisi(d, url):
    """Durum sozlugunu kullaniciya gosterilecek Turkce iletiye cevirir; sorun yoksa None."""
    if not d["erisim"]:
        return ("LM Studio sunucusuna ulaşılamadı (" + url + "). LM Studio'yu açıp Developer sekmesinden "
                "sunucuyu başlatın (Running) ve Ayarlar'daki adresin doğru olduğunu kontrol edin.")
    if d["eksik"]:
        return ("Model LM Studio'da bulunamadı: " + ", ".join(d["eksik"]) +
                ". Modeli indirin ya da Ayarlar'dan başka bir model seçin.")
    if d["yuklu_degil"]:
        return "Model LM Studio'da yüklü değil: " + ", ".join(d["yuklu_degil"]) + ". Modeli LM Studio'da yükleyin."
    return None
