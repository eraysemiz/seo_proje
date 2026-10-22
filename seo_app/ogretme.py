"""Deney kosullarina gore modele verilen ek baglam ('ogretme' metni).

Kosullar:
  sifir       : ek bilgi yok
  ornek       : few-shot ornekler (ornekler.json)
  bilgi       : SEO bilgi tabanindan ilgili parcalar (RAG)
  ornek+bilgi : ikisi birden

'bilgi' kosulunun iki alt yontemi vardir:
  - gomme (embedding) modeli verilirse  -> hibrit getirme (bilgi_getir)
  - verilmezse                          -> anahtar kelime eslestirmesi (seo_kurallari.json)

Hibrit getirme hatti (bilgi_getir):
  1. metadata on filtresi: yalnizca sayfanin sorunlu alanlarina (title, meta, h1, img_alt) ve
     genel yonergelere ait parcalar aday olur
  2. sorgu: sorunlarin Turkce aciklamalari + sayfa basligi + menuden ayiklanmis icerik ozeti;
     gomme modeli ailesine uygun sorgu/belge onekleri eklenir
  3. siralama: BM25 (sozcuksel) ve kosinus (anlamsal) siralamalari RRF ile birlestirilir;
     yeniden siralama (rerank) modeli verilirse son sirayi o belirler
  4. secim: her sorunlu alandan en az bir parca, kalan yer en yuksek puanlilarla; toplam metin
     BAGLAM_SINIRI karakteri asarsa once dolgu parcalari cikarilir
"""
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

import requests

from .cikarma import kelimeler
from .kurallar import ACIKLAMA, ALAN_SORUN, IZINLI_ALANLAR
from .llm import istek_adresi

KOSULLAR = ("sifir", "ornek", "bilgi", "ornek+bilgi")
GENEL_ALAN = "genel"
BAGLAM_SINIRI = 1600     # isteme eklenen bilgi parcalarinin toplam karakter ust siniri
RRF_K = 60               # Reciprocal Rank Fusion sabiti (Cormack ve ark. 2009)
# Siralamalarin RRF agirliklari. rag_degerlendir.py olcumunde (60 sayfa, qwen3-embedding-0.6b, k=5)
# sorun isabeti: yalniz vektor 0,931; esit agirlikli hibrit 0,707; BM25 agirligi 0,1 ile 0,939.
# Kucuk bilgi tabaninda BM25 gurultulu oldugundan yalnizca esitlik bozucu olarak katilir.
RRF_AGIRLIK = {"bm25": 0.1, "vektor": 1.0}
ORNEK_METIN_SINIRI = 120  # few-shot orneklerindeki metin_ozeti kisaltmasi
# ornek girdisinde her zaman kalan alanlar; digerleri yalnizca ilgili alan sorunluysa kalir
ORNEK_ALAN_GIRDISI = {"meta_description": "meta_description", "h1": "h1", "img_alt": "alt_metni_eksik_gorseller"}

_KB_BELLEK = {}          # bilgi tabani dosyasi -> (degisiklik zamani, parcalar, surum, bm25 dizini)
_VEKTOR_BELLEK = {}      # (surum, gomme modeli) -> {parca id: birim vektor}


# ------------------------------------------------------------------ gomme modeli
def _onekler(model):
    """Gomme modelinin egitildigi sorgu/belge onekleri. Onek kullanilmazsa bu modeller
    sorgu ile belgeyi ayni uzayda daha zayif eslestirir."""
    m = (model or "").lower()
    if "qwen3" in m and "embed" in m:
        return ("Instruct: Bir web sayfasının SEO sorunlarını düzeltirken uyulacak yönergeyi bul\nQuery: ", "")
    if "e5" in m:
        return ("query: ", "passage: ")
    if "nomic" in m:
        return ("search_query: ", "search_document: ")
    return ("", "")


def _embed(url, model, metinler, timeout=60):
    """LM Studio /v1/embeddings ucundan vektorleri alir. Birden fazla metni tek istekte gonderir."""
    r = requests.post(istek_adresi(url) + "/embeddings", json={"model": model, "input": metinler}, timeout=timeout)
    r.raise_for_status()
    veri = sorted(r.json()["data"], key=lambda x: x["index"])
    return [x["embedding"] for x in veri]


def _birim(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def _kosinus(a, b):
    """Birim vektorler icin kosinus benzerligi = ic carpim."""
    return sum(x * y for x, y in zip(a, b))


def _hash(model, metin):
    return hashlib.sha256((model + "||" + metin).encode()).hexdigest()[:16]


def belge_metni(p):
    return (p.get("baslik", "") + ". " + p["icerik"]).strip(". ")


# ------------------------------------------------------------------ bilgi tabani
def _belirtecler(metin):
    """BM25 icin belirtecler: Turkce kucuk harf, 4+ harfli kelimelerin ilk 5 harfi (ek farklarini yumusatir)."""
    return [w[:5] for w in kelimeler(metin) if len(w) >= 4]


def bilgi_tabani(klasor):
    """Bilgi tabanini dosya degismedikce bellekten verir. (parcalar, surum, bm25) dondurur.
    surum: dosya iceriginin ozeti; rapora yazilir, hangi bilgi tabaniyla calisildigi izlenir."""
    yol = Path(klasor) / "bilgi_tabani.json"
    mt = yol.stat().st_mtime_ns
    onceki = _KB_BELLEK.get(str(yol))
    if onceki and onceki[0] == mt:
        return onceki[1:]
    ham = yol.read_bytes()
    parcalar = json.loads(ham.decode("utf-8"))
    surum = hashlib.sha256(ham).hexdigest()[:12]
    belgeler = [_belirtecler(belge_metni(p) + " " + " ".join(p.get("etiketler", []))) for p in parcalar]
    df = Counter(t for b in belgeler for t in set(b))
    bm25 = {"belgeler": belgeler, "df": df, "n": len(belgeler),
            "ort": (sum(map(len, belgeler)) / len(belgeler)) if belgeler else 1.0}
    _KB_BELLEK[str(yol)] = (mt, parcalar, surum, bm25)
    return parcalar, surum, bm25


def bm25_puanlari(sorgu, bm25, k1=1.5, b=0.75):
    """Okapi BM25; her parca icin bir puan (bilgi tabani sirasiyla)."""
    q = set(_belirtecler(sorgu))
    puanlar = []
    for belge in bm25["belgeler"]:
        tf = Counter(belge)
        p = 0.0
        for t in q:
            if not tf[t]:
                continue
            idf = math.log(1 + (bm25["n"] - bm25["df"][t] + 0.5) / (bm25["df"][t] + 0.5))
            p += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(belge) / bm25["ort"]))
        puanlar.append(p)
    return puanlar


def parca_vektorleri(klasor, parcalar, surum, embed_url, embed_model):
    """Parcalarin birim vektorleri. Bellekte yoksa disk onbelleginden, orada da yoksa gomme
    modelinden alinir. Onbellek model basina tutulur ve yalnizca guncel parcalari saklar."""
    anahtar = (surum, embed_model)
    if anahtar in _VEKTOR_BELLEK:
        return _VEKTOR_BELLEK[anahtar]
    _, belge_onek = _onekler(embed_model)
    metinler = {p["id"]: belge_onek + belge_metni(p) for p in parcalar}
    hashler = {pid: _hash(embed_model, m) for pid, m in metinler.items()}
    cache_yolu = Path(klasor) / "bilgi_tabani_gomme_cache.json"
    try:
        cache = json.loads(cache_yolu.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if not isinstance(cache.get("modeller"), dict):        # eski duz bicim ya da bozuk dosya
        cache = {"bicim": 2, "modeller": {}}
    eski = cache["modeller"].get(embed_model, {})
    eksik = [pid for pid in metinler if hashler[pid] not in eski]
    if eksik:
        yeni = _embed(embed_url, embed_model, [metinler[pid] for pid in eksik])
        eski.update({hashler[pid]: v for pid, v in zip(eksik, yeni)})
    guncel = {hashler[pid]: eski[hashler[pid]] for pid in metinler}
    if eksik or len(eski) != len(guncel):                    # artik bilgi tabaninda olmayanlar silinir
        cache["modeller"][embed_model] = guncel
        cache_yolu.write_text(json.dumps(cache), encoding="utf-8")
    vektorler = {pid: _birim(guncel[hashler[pid]]) for pid in metinler}
    _VEKTOR_BELLEK[anahtar] = vektorler
    return vektorler


# ------------------------------------------------------------------ getirme
def beklenen_alanlar(issues):
    kodlar = [i["sorun"] for i in issues]
    return [a for a in IZINLI_ALANLAR if any(x in kodlar for x in ALAN_SORUN[a])]


def sorgu_olustur(d, issues):
    """Getirme sorgusu: sorun kodlari yerine Turkce aciklamalari, menu yerine icerik ozeti kullanilir."""
    sorunlar = "; ".join(ACIKLAMA.get(i["sorun"], i["sorun"]) for i in issues)
    metin = (d.get("icerik_ozeti") or d.get("text_sample") or "")[:300]
    site = (". Site: " + d["site_adi"]) if d.get("site_adi") else ""
    return ("Sayfa başlığı: " + (d.get("title") or "yok") + site + ". Düzeltilecek sorunlar: " + sorunlar +
            ". Sayfa içeriği: " + metin)


def _rrf(siralamalar):
    """Agirlikli Reciprocal Rank Fusion: {ad: siralama} icin her konumun tersini agirligiyla toplar."""
    puan = Counter()
    for ad, sira in siralamalar.items():
        for konum, pid in enumerate(sira):
            puan[pid] += RRF_AGIRLIK.get(ad, 1.0) / (RRF_K + konum + 1)
    return puan


def yeniden_sirala(url, model, sorgu, parcalar, timeout=30):
    """Yeniden siralama (rerank) modeli: llama.cpp sunucusunun --reranking modu gibi
    /rerank ucunu (Jina/Cohere bicimi) sunan yerel bir sunucu. {parca id: puan} dondurur."""
    try:
        r = requests.post(istek_adresi(url).rstrip("/") + "/rerank", timeout=timeout,
                          json={"model": model, "query": sorgu, "top_n": len(parcalar),
                                "documents": [belge_metni(p) for p in parcalar]})
        r.raise_for_status()
        return {parcalar[x["index"]]["id"]: float(x["relevance_score"]) for x in r.json()["results"]}
    except (requests.RequestException, KeyError, ValueError, IndexError) as e:
        raise RuntimeError("Yeniden sıralama modeline ulaşılamadı: " + str(model) + " (" + str(url) + "). "
                           "Ayrıntı: " + type(e).__name__) from e


def _kapsayarak_sec(sirali, beklenen, k):
    """Her beklenen alandan en iyi parcayi alir, kalan yeri en yuksek puanlilarla doldurur.
    (secili, kapsama icin secilen id'ler) dondurur."""
    secili, zorunlu = [], set()
    for alan in beklenen:
        p = next((p for p in sirali if p.get("alan") == alan and p not in secili), None)
        if p and len(secili) < k:
            secili.append(p)
            zorunlu.add(p["id"])
    for p in sirali:
        if len(secili) >= k:
            break
        if p not in secili:
            secili.append(p)
    sira = {p["id"]: i for i, p in enumerate(sirali)}
    return sorted(secili, key=lambda p: sira[p["id"]]), zorunlu


def bilgi_getir(d, issues, klasor, embed_url, embed_model, k, rerank_url=None, rerank_model=None,
                siralama=("bm25", "vektor")):
    """Hibrit getirme. (secili parcalar, kayit bilgisi) dondurur; ayrintilar modul aciklamasinda.
    siralama: birlestirilecek siralamalar; olcumde tek basina bm25 ya da vektor denemek icin."""
    t0 = time.perf_counter()
    parcalar, surum, bm25 = bilgi_tabani(klasor)
    beklenen = beklenen_alanlar(issues)
    aday_idx = [i for i, p in enumerate(parcalar) if p.get("alan") in beklenen or p.get("alan") == GENEL_ALAN]
    aday_idx = aday_idx or list(range(len(parcalar)))
    sorgu = sorgu_olustur(d, issues)

    bm = bm25_puanlari(sorgu, bm25)
    sozcuk_sira = [parcalar[i]["id"] for i in sorted(aday_idx, key=lambda i: -bm[i])]
    kosinus = {}
    siralamalar = {"bm25": sozcuk_sira} if "bm25" in siralama else {}
    yontem = "bm25" if siralamalar else ""
    if embed_model and "vektor" in siralama:
        vektorler = parca_vektorleri(klasor, parcalar, surum, embed_url, embed_model)
        sorgu_onek, _ = _onekler(embed_model)
        qv = _birim(_embed(embed_url, embed_model, [sorgu_onek + sorgu])[0])
        kosinus = {parcalar[i]["id"]: _kosinus(qv, vektorler[parcalar[i]["id"]]) for i in aday_idx}
        siralamalar["vektor"] = sorted(kosinus, key=lambda pid: -kosinus[pid])
        yontem = "hibrit" if yontem else "vektor"
    puan = _rrf(siralamalar)
    if rerank_model:
        adaylar = [parcalar[i] for i in aday_idx]
        puan = yeniden_sirala(rerank_url, rerank_model, sorgu, adaylar)
        yontem += "+rerank"
    sirali = sorted((parcalar[i] for i in aday_idx), key=lambda p: -puan[p["id"]])

    secili, zorunlu = _kapsayarak_sec(sirali, beklenen, k)
    # baglam butcesi: once kapsama icin zorunlu olmayan (dolgu) parcalar, en dusuk puanlidan baslayarak cikar
    while sum(len(belge_metni(p)) for p in secili) > BAGLAM_SINIRI:
        dolgu = [p for p in secili if p["id"] not in zorunlu]
        if not dolgu:
            break
        secili.remove(dolgu[-1])

    bilgi = {
        "yontem": yontem, "kb_surum": surum, "aday_sayisi": len(aday_idx),
        "getirme_ms": round((time.perf_counter() - t0) * 1000, 1),
        "parcalar": [{"id": p["id"], "alan": p.get("alan"), "baslik": p.get("baslik"),
                      "kaynak": p.get("kaynak"), "kaynak_basligi": p.get("kaynak_basligi"),
                      "puan": round(puan[p["id"]], 4),
                      "kosinus": round(kosinus[p["id"]], 4) if p["id"] in kosinus else None}
                     for p in secili],
    }
    return [{x: p[x] for x in p if not x.startswith("_")} for p in secili], bilgi


# ------------------------------------------------------------------ istem metni
def _ornek_metni(o, alanlar):
    """Few-shot ornegini sikistirir: yalnizca sayfanin sorunlu alanlarina ait girdi, sorun ve oneriler;
    bos alanlar ve h2 atilir, metin ozeti kisaltilir. Yazim kurallari bilgi tabanindan geldigi icin
    ornek yalnizca bicim ve tonu gosterir."""
    atilacak = {"h2"} | {g for a, g in ORNEK_ALAN_GIRDISI.items() if a not in alanlar}
    girdi = {a: v for a, v in o["girdi"].items() if v not in ("", [], None) and a not in atilacak}
    if "metin_ozeti" in girdi:
        girdi["metin_ozeti"] = girdi["metin_ozeti"][:ORNEK_METIN_SINIRI]
    ilgili = [s for s in o["girdi"].get("tespit_edilen_sorunlar", []) if any(s in ALAN_SORUN[a] for a in alanlar)]
    if ilgili:
        girdi["tespit_edilen_sorunlar"] = ilgili
    fixes = [f for f in o["cikti"]["fixes"] if f["alan"] in alanlar] or o["cikti"]["fixes"]
    # gorsel bicimini gostermek icin tek gorsel ve onun onerisi yeter
    if girdi.get("alt_metni_eksik_gorseller"):
        girdi["alt_metni_eksik_gorseller"] = girdi["alt_metni_eksik_gorseller"][:1]
        kalan = {g.get("id") for g in girdi["alt_metni_eksik_gorseller"]}
        fixes = [f for f in fixes if f["alan"] != "img_alt" or f.get("hedef") in kalan]
    return ("Girdi: " + json.dumps(girdi, ensure_ascii=False) +
            "\nCikti: " + json.dumps({"fixes": fixes}, ensure_ascii=False))


def ogretme_metni(kosul, d, issues, klasor, k, embed_url, embed_model,
                  bilgi_k=None, rerank_url=None, rerank_model=None):
    """Sistem istemine eklenecek ek baglami uretir. (metin, bilgi) dondurur.
    k: few-shot ornek sayisi; bilgi_k: getirilecek bilgi parcasi sayisi (verilmezse k).
    Siralama sabitten degiskene dogrudur (ornekler, sonra bilgi parcalari); boylece LM Studio'nun
    istem onbellegi ayni onekli istemlerde yeniden kullanilabilir.
    Gomme modeli secildiyse ve ulasilamazsa hata firlatilir; anahtar kelime yontemine
    yalnizca gomme modeli hic secilmediginde gecilir (sessiz geri donus yok)."""
    kodlar = [i["sorun"] for i in issues]
    bilgi = {"ornek": 0, "kural": 0, "yontem": None, "parcalar": [], "kimlikler": []}
    if kosul == "sifir":
        return "", bilgi
    klasor = Path(klasor)
    alanlar = [a for a in IZINLI_ALANLAR if any(x in kodlar for x in ALAN_SORUN[a])]
    parcalar = []
    if "ornek" in kosul:
        ornekler = json.loads((klasor / "ornekler.json").read_text(encoding="utf-8"))
        puan = lambda o: sum(1 for f in o["cikti"]["fixes"] if f["alan"] in alanlar)
        secili_o = sorted(ornekler, key=lambda o: -puan(o))[:k]
        parcalar.append(
            "\n\nORNEKLER (yalnizca bicim ve ton icin; icerigini KOPYALAMA, kendi sayfanin verisini kullan):\n" +
            "\n\n".join("Ornek " + str(i + 1) + "\n" + _ornek_metni(o, alanlar) for i, o in enumerate(secili_o)))
        bilgi["ornek"] = len(secili_o)
    if "bilgi" in kosul:
        if embed_model:
            try:
                secili, getirme = bilgi_getir(d, issues, klasor, embed_url, embed_model, bilgi_k or k,
                                              rerank_url, rerank_model)
            except (requests.RequestException, KeyError, ValueError) as e:
                raise RuntimeError("Gömme modeline ulaşılamadı: " + embed_model + " (" + embed_url + "). "
                                   "Ayrıntı: " + type(e).__name__) from e
            bilgi.update({x: getirme[x] for x in ("yontem", "parcalar", "kb_surum", "getirme_ms")})
            bilgi["kimlikler"] = [p["id"] for p in secili]
            satirlar = ["[" + p["id"] + "] " + p.get("baslik", "") + ": " + p["icerik"] for p in secili]
        else:
            kurallar = [r for r in json.loads((klasor / "seo_kurallari.json").read_text(encoding="utf-8"))
                        if r["alan"] in alanlar or r["alan"] == "genel"]
            satirlar = ["[" + r["alan"] + "] " + r["kural"] for r in kurallar]
            bilgi["yontem"] = "anahtar_kelime"
        parcalar.append("\n\nSEO BILGI TABANI (yazim yonergeleri; sayfa bilgisi degildir. Onerinin dayandigi "
                        "parcalarin kimligini 'kaynaklar' alanina yaz):\n" + "\n".join("- " + s for s in satirlar))
        bilgi["kural"] = len(satirlar)
    return "".join(parcalar), bilgi
