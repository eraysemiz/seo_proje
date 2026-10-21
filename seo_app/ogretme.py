"""Deney kosullarina gore modele verilen ek baglam ('ogretme' metni).

Kosullar:
  sifir       : ek bilgi yok
  ornek       : few-shot ornekler (ornekler.json)
  bilgi       : SEO bilgi tabanindan ilgili parcalar (RAG)
  ornek+bilgi : ikisi birden

'bilgi' kosulunun iki alt yontemi vardir:
  - gomme (embedding) modeli verilirse  -> anlamsal getirme (kosinus benzerligi)
  - verilmezse veya ulasilamazsa        -> anahtar kelime eslestirmesi (seo_kurallari.json)
"""
import hashlib
import json
import math
from pathlib import Path

import requests

from .kurallar import ALAN_SORUN, IZINLI_ALANLAR

KOSULLAR = ("sifir", "ornek", "bilgi", "ornek+bilgi")


def _embed(url, model, metinler, timeout=60):
    """LM Studio /v1/embeddings ucundan vektorleri alir. Birden fazla metni tek istekte gonderir."""
    r = requests.post(url + "/embeddings", json={"model": model, "input": metinler}, timeout=timeout)
    r.raise_for_status()
    veri = sorted(r.json()["data"], key=lambda x: x["index"])
    return [x["embedding"] for x in veri]


def _kosinus(a, b):
    pay = sum(x * y for x, y in zip(a, b))
    pa = math.sqrt(sum(x * x for x in a))
    pb = math.sqrt(sum(y * y for y in b))
    return pay / (pa * pb) if pa and pb else 0.0


def _hash(model, metin):
    return hashlib.sha256((model + "||" + metin).encode()).hexdigest()[:16]


def bilgi_tabani_gomme(klasor, embed_url, embed_model):
    """Bilgi tabanindaki her parcanin vektorunu getirir; onbellekte yoksa hesaplayip kaydeder."""
    klasor = Path(klasor)
    parcalar = json.loads((klasor / "bilgi_tabani.json").read_text(encoding="utf-8"))
    cache_yolu = klasor / "bilgi_tabani_gomme_cache.json"
    cache = json.loads(cache_yolu.read_text(encoding="utf-8")) if cache_yolu.exists() else {}
    eksik = [p for p in parcalar if _hash(embed_model, p["icerik"]) not in cache]
    if eksik:
        vektorler = _embed(embed_url, embed_model, [p["icerik"] for p in eksik])
        for p, v in zip(eksik, vektorler):
            cache[_hash(embed_model, p["icerik"])] = v
        cache_yolu.write_text(json.dumps(cache), encoding="utf-8")
    for p in parcalar:
        p["_vektor"] = cache[_hash(embed_model, p["icerik"])]
    return parcalar


def anlamsal_getir(d, issues, klasor, embed_url, embed_model, k=4, esik=0.2):
    """Sayfanin sorunlarina ve icerigine en alakali k bilgi parcasini anlamsal benzerlikle secer."""
    kodlar = [i["sorun"] for i in issues]
    sorgu = ("Sayfa basligi: " + (d["title"] or "yok") + ". Tespit edilen SEO sorunlari: " +
             ", ".join(kodlar) + ". Sayfa konusu: " + d["text_sample"][:300])
    parcalar = bilgi_tabani_gomme(klasor, embed_url, embed_model)
    sorgu_v = _embed(embed_url, embed_model, [sorgu])[0]
    puanli = sorted(parcalar, key=lambda p: -_kosinus(sorgu_v, p["_vektor"]))
    secili = [p for p in puanli if _kosinus(sorgu_v, p["_vektor"]) >= esik][:k]
    return secili or puanli[:1]   # hicbiri esigi gecmezse en yakin olani yine de ver


def ogretme_metni(kosul, d, issues, klasor, k, embed_url, embed_model):
    """Sistem istemine eklenecek ek baglami uretir. (metin, bilgi) dondurur.
    Gomme modeli secildiyse ve ulasilamazsa hata firlatilir; anahtar kelime yontemine
    yalnizca gomme modeli hic secilmediginde gecilir (sessiz geri donus yok)."""
    kodlar = [i["sorun"] for i in issues]
    bilgi = {"ornek": 0, "kural": 0, "yontem": None}
    if kosul == "sifir":
        return "", bilgi
    klasor = Path(klasor)
    alanlar = [a for a in IZINLI_ALANLAR if any(x in kodlar for x in ALAN_SORUN[a])]
    parcalar = []
    if "bilgi" in kosul:
        if embed_model:
            try:
                secili = anlamsal_getir(d, issues, klasor, embed_url, embed_model, k)
            except (requests.RequestException, KeyError, ValueError) as e:
                raise RuntimeError("Gömme modeline ulaşılamadı: " + embed_model + " (" + embed_url + "). "
                                   "Ayrıntı: " + type(e).__name__) from e
            bilgi["yontem"] = "anlamsal"
        else:
            kurallar = json.loads((klasor / "seo_kurallari.json").read_text(encoding="utf-8"))
            secili = [{"icerik": "[" + r["alan"] + "] " + r["kural"]} for r in kurallar
                      if r["alan"] in alanlar or r["alan"] == "genel"]
            bilgi["yontem"] = "anahtar_kelime"
        parcalar.append("\n\nSEO BILGI TABANI (bu bilgilere dayanarak oneri uret):\n" +
                        "\n".join("- " + p["icerik"] for p in secili))
        bilgi["kural"] = len(secili)
    if "ornek" in kosul:
        ornekler = json.loads((klasor / "ornekler.json").read_text(encoding="utf-8"))
        puan = lambda o: sum(1 for f in o["cikti"]["fixes"] if f["alan"] in alanlar)
        secili_o = sorted(ornekler, key=lambda o: -puan(o))[:k]
        parcalar.append(
            "\n\nORNEKLER (yalnizca bicim ve ton icin; icerigini KOPYALAMA, kendi sayfanin verisini kullan):\n" +
            "\n\n".join("Ornek " + str(i + 1) +
                        "\nGirdi: " + json.dumps(o["girdi"], ensure_ascii=False) +
                        "\nCikti: " + json.dumps(o["cikti"], ensure_ascii=False)
                        for i, o in enumerate(secili_o)))
        bilgi["ornek"] = len(secili_o)
    return "".join(parcalar), bilgi
