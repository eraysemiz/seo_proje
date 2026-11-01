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
  4. secim: genel yonerge en fazla GENEL_KOTA parca; her sorunlu alandan en az bir parca, kalan yer en
     yuksek puanlilarla; BENZERLIK_ESIGI verilirse esigin altindaki dolgu atilir; toplam metin
     BAGLAM_SINIRI karakteri asarsa once dolgu parcalari cikarilir

Few-shot ornekleri (ornek_sec): sorun kodu ortusmesi + cesitlilik. ornekler.json'a ek olarak kullanicinin
yonetici modunda onayladigi/duzenledigi model onerileri (geri_bildirim.jsonl, baska sitelerden) aday olur.
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
ORNEK_BUTCESI = 2400      # few-shot orneklerinin toplam karakter ust siniri (~600 token); bilgi parcalarindan ayri
# Genel yonerge kotasi ve benzerlik esigi, 27 Ekim olcumu (133 sayfa, qwen3-embedding-0.6b, k=5, 65 parca):
# kotasiz MRR 0,972 -> kota 1 ile 0,977 (sorun isabeti 0,934 ayni). Esik 0,30-0,40 hicbir parcayi atmadi;
# 0,50 / 0,55 / 0,60 sorun isabetini 0,919 / 0,852 / 0,707'ye dusurdu. Bu yuzden esik kapali.
GENEL_KOTA = 1            # getirmede genel yonerge parcasi en fazla bu kadar (kalan yer sorunlu alanlarin)
BENZERLIK_ESIGI = None    # kosinus bu degerin altindaki dolgu parcasi atilir (None: esik yok)
GERI_BILDIRIM = "geri_bildirim.jsonl"   # yonetici modunda kullanicinin onayladigi/duzenledigi model onerileri
# ornek girdisinde her zaman kalan alanlar; digerleri yalnizca ilgili alan sorunluysa kalir
ORNEK_ALAN_GIRDISI = {"meta_description": "meta_description", "h1": "h1", "img_alt": "alt_metni_eksik_gorseller"}
# Yalnizca getirme icin: modelin metin yazmadigi bulgulari (canonical, kopya icerik, adres, baglanti metni...)
# bilgi tabaninin ilgili alanina baglar. Modele giden alanlar ve dogrulama (kurallar.ALAN_SORUN) degismez;
# Mod 2'de modele yalnizca ALAN_SORUN bulgulari gittigi icin bu eslemeler orada istemi degistirmez.
BILGI_ALANI_SORUN = {
    "title": ("title_tekrar", "title_h1_uyumsuz", "title_icerikle_uyumsuz"),
    "meta_description": ("meta_tekrar",),
    "h1": ("h1_tekrar", "h1_bos", "h1_birden_fazla", "baslik_atlamasi", "bos_baslik"),
    "img_alt": ("alt_metni_anlamsiz",),
    "canonical": ("canonical_yok", "canonical_capraz", "canonical_coklu", "canonical_bos", "canonical_kirik",
                  "canonical_goreli", "icerik_tekrar", "icerik_benzer"),
    "url": ("url_buyuk_harf", "url_aciklayici_degil"),
    "icerik": ("icerik_az", "anahtar_kelime_doldurma", "icerik_eski", "tarih_bilgisi_yok",
               "uzun_metin_ara_baslik_yok", "js_bagimli_icerik"),
    "baglanti": ("genel_baglanti_metni", "bos_baglanti_metni", "ic_baglanti_yok", "kullanici_baglantisi_isaretsiz",
                 "kirik_ic_link", "ic_link_yonlendirme"),
    "robots_sitemap": ("robots_yok", "robots_tum_siteyi_engelliyor", "robots_sayfayi_engelliyor",
                       "robots_sitemap_bildirilmemis", "robots_kaynak_engelliyor", "robots_bilinmeyen_yonerge",
                       "sitemap_yok", "sayfa_sitemapte_yok", "yetim_sayfa", "derin_sayfa", "noindex", "sayfa_nofollow"),
    "yapisal_veri": ("yapisal_veri_yok", "yapisal_veri_gecersiz", "yapisal_veri_eksik_alan", "schema_kurum_turu_yok",
                     "breadcrumb_yok", "schema_kurum_logo_yok", "schema_sosyal_profil_yok", "yapisal_veri_onerilen_alan"),
    "video": ("video_baslik_yok",),
    "hreflang": ("hreflang_gecersiz", "hreflang_x_default_yok", "hreflang_kendine_referans_yok", "hreflang_donus_yok"),
    "yonlendirme": ("meta_refresh", "js_yonlendirme", "uzun_yonlendirme_zinciri", "yonlendirme_dongusu",
                    "cok_fazla_yonlendirme", "gecersiz_yonlendirme", "gecici_yonlendirme", "yumusak_404",
                    "sitemap_yonlendirme", "ic_link_yonlendirme"),
    "javascript": ("js_bagimli_icerik", "js_yonlendirme", "render_engelleyen_kaynak"),
    "gorsel": ("gorsel_boyut_yok", "gorsel_eski_format", "gorsel_lazy_yok", "ilk_gorsel_lazy", "gorsel_buyuk",
               "kirik_gorsel"),
}

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
    """Getirmede aday parcalarin alanlari: modelin duzenledigi alanlar (ALAN_SORUN) ve modelin metin
    yazmadigi bulgular icin yalnizca getirmede kullanilan bilgi alanlari (BILGI_ALANI_SORUN)."""
    kodlar = [i["sorun"] for i in issues]
    alanlar = [a for a in IZINLI_ALANLAR if any(x in kodlar for x in ALAN_SORUN[a])]
    return alanlar + [a for a, sorunlar in BILGI_ALANI_SORUN.items()
                      if a not in alanlar and any(x in kodlar for x in sorunlar)]


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


_VARSAYILAN = object()


def bilgi_getir(d, issues, klasor, embed_url, embed_model, k, rerank_url=None, rerank_model=None,
                siralama=("bm25", "vektor"), genel_kota=_VARSAYILAN, esik=_VARSAYILAN):
    """Hibrit getirme. (secili parcalar, kayit bilgisi) dondurur; ayrintilar modul aciklamasinda.
    siralama: birlestirilecek siralamalar; olcumde tek basina bm25 ya da vektor denemek icin.
    genel_kota / esik: GENEL_KOTA ve BENZERLIK_ESIGI yerine olcumde baska deger denemek icin (None: sinirsiz)."""
    genel_kota = GENEL_KOTA if genel_kota is _VARSAYILAN else genel_kota
    esik = BENZERLIK_ESIGI if esik is _VARSAYILAN else esik
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

    if genel_kota is not None:
        genel = [p for p in sirali if p.get("alan") == GENEL_ALAN]
        fazla = {p["id"] for p in genel[genel_kota:]} if len(sirali) > len(genel) else set()
        sirali = [p for p in sirali if p["id"] not in fazla]
    if esik is not None and kosinus:
        # kapsama icin her alanin en iyi parcasi esikten bagimsiz kalir; esik yalnizca dolguyu ayiklar
        ilk_alan = {}
        for p in sirali:
            ilk_alan.setdefault(p.get("alan"), p["id"])
        sirali = [p for p in sirali if kosinus.get(p["id"], 1) >= esik or ilk_alan.get(p.get("alan")) == p["id"]]
    secili, zorunlu = _kapsayarak_sec(sirali, beklenen, k)
    # baglam butcesi: once kapsama icin zorunlu olmayan (dolgu) parcalar, en dusuk puanlidan baslayarak cikar
    while sum(len(belge_metni(p)) for p in secili) > BAGLAM_SINIRI:
        dolgu = [p for p in secili if p["id"] not in zorunlu]
        if not dolgu:
            break
        secili.remove(dolgu[-1])

    bilgi = {
        "yontem": yontem, "kb_surum": surum, "aday_sayisi": len(aday_idx), "genel_kota": genel_kota, "esik": esik,
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


def _site_kimligi(x):
    from urllib.parse import urlparse
    h = (urlparse(x if "//" in (x or "") else "//" + (x or "")).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def geri_bildirim_ornekleri(klasor, haric_site=None):
    """Kullanicinin oldugu gibi onayladigi ya da duzenleyerek onayladigi model onerileri, few-shot ornegi
    biciminde. Ayni sitenin kayitlari haric tutulur: model bir sitenin kendi onaylanmis metnini ezberlemez."""
    yol = Path(klasor) / GERI_BILDIRIM
    if not yol.exists():
        return []
    haric = _site_kimligi(haric_site) if haric_site else ""
    sonuc = []
    for satir in yol.read_text(encoding="utf-8").splitlines():
        try:
            g = json.loads(satir)
        except ValueError:
            continue
        if g.get("karar") not in ("onay", "duzenle") or g.get("alan") not in IZINLI_ALANLAR or not g.get("son_deger"):
            continue
        if haric and _site_kimligi(g.get("site")) == haric:
            continue
        sayfa = g.get("sayfa") or {}
        gorseller = [sayfa["gorsel"]] if g["alan"] == "img_alt" and sayfa.get("gorsel") else []
        sonuc.append({"girdi": {"title": sayfa.get("title"), "meta_description": sayfa.get("meta_description"),
                                "h1": sayfa.get("h1") or [], "h2": [], "alt_metni_eksik_gorseller": gorseller,
                                "metin_ozeti": sayfa.get("metin_ozeti") or "",
                                "tespit_edilen_sorunlar": [g["bulgu"]]},
                      "cikti": {"fixes": [{"alan": g["alan"], "hedef": gorseller[0]["id"] if gorseller else "",
                                           "yeni_deger": g["son_deger"], "gerekce": "kullanıcı onayladı"}]},
                      "kaynak": {"etiket": "geri-bildirim", "site": _site_kimligi(g.get("site"))}})
    return sonuc


def _marka(o):
    """Ornegin geldigi kurum: kaynak sitesi ya da basliktaki son bolum (cesitlilik icin)."""
    k = o.get("kaynak") or {}
    if k.get("site"):
        return k["site"]
    t = (o["girdi"].get("title") or "").split("|")
    return t[-1].strip().lower() if len(t) > 1 else ""


def ornek_sec(ornekler, kodlar, alanlar, k, tohum=""):
    """Few-shot secimi: once sayfadaki sorun kodlarini en cok YENI kapsayan ornek, sonra sorunlu alan
    eslesmesi; ayni kurumdan ikinci ornek alinmaz. Esitlik dosya sirasiyla degil sayfaya bagli bir ozetle
    bozulur; boylece her sayfaya ayni iki ornek gitmez. Sorunlu alanlarla hic eslesmeyen ornek secilmez."""
    kodlar = set(kodlar)
    ortusme = [set(o["girdi"].get("tespit_edilen_sorunlar") or ()) & kodlar for o in ornekler]
    alan_puani = [sum(1 for f in o["cikti"]["fixes"] if f["alan"] in alanlar) for o in ornekler]
    karisim = [hashlib.sha256((tohum + "|" + str(i)).encode()).hexdigest() for i in range(len(ornekler))]
    secili, kapsanan, markalar = [], set(), set()
    while len(secili) < k:
        adaylar = [i for i in range(len(ornekler)) if i not in secili and alan_puani[i] > 0]
        if not adaylar:
            break
        i = min(adaylar, key=lambda i: (-len(ortusme[i] - kapsanan),
                                        bool(_marka(ornekler[i]) and _marka(ornekler[i]) in markalar),
                                        -len(ortusme[i]), karisim[i]))
        secili.append(i)
        kapsanan |= ortusme[i]
        markalar.add(_marka(ornekler[i]))
    return [ornekler[i] for i in secili]


def ogretme_metni(kosul, d, issues, klasor, k, embed_url, embed_model,
                  bilgi_k=None, rerank_url=None, rerank_model=None, site=None):
    """Sistem istemine eklenecek ek baglami uretir. (metin, bilgi) dondurur.
    k: few-shot ornek sayisi; bilgi_k: getirilecek bilgi parcasi sayisi (verilmezse k).
    Siralama sabitten degiskene dogrudur (ornekler, sonra bilgi parcalari); boylece LM Studio'nun
    istem onbellegi ayni onekli istemlerde yeniden kullanilabilir.
    Gomme modeli secildiyse ve ulasilamazsa hata firlatilir; anahtar kelime yontemine
    yalnizca gomme modeli hic secilmediginde gecilir (sessiz geri donus yok).
    site: sayfanin adresi; geri bildirim orneklerinden ayni sitenin kayitlarini disarida birakmak icin."""
    kodlar = [i["sorun"] for i in issues]
    bilgi = {"ornek": 0, "kural": 0, "yontem": None, "parcalar": [], "kimlikler": []}
    if kosul == "sifir":
        return "", bilgi
    klasor = Path(klasor)
    alanlar = [a for a in IZINLI_ALANLAR if any(x in kodlar for x in ALAN_SORUN[a])]
    parcalar = []
    if "ornek" in kosul:
        ornekler = json.loads((klasor / "ornekler.json").read_text(encoding="utf-8"))
        sabit = len(ornekler)
        ornekler += geri_bildirim_ornekleri(klasor, site)
        secili_o = ornek_sec(ornekler, kodlar, alanlar, k, tohum=(d.get("title") or "") + "|" + (site or ""))
        metinler = [_ornek_metni(o, alanlar) for o in secili_o]
        # ornek butcesi bilgi parcalarindan ayridir; asilirsa sondaki (en az kapsayan) ornek dusurulur
        while len(metinler) > 1 and sum(map(len, metinler)) > ORNEK_BUTCESI:
            metinler.pop()
        secili_o = secili_o[:len(metinler)]
        parcalar.append(
            "\n\nORNEKLER (yalnizca bicim ve ton icin; icerigini KOPYALAMA, kendi sayfanin verisini kullan):\n" +
            "\n\n".join("Ornek " + str(i + 1) + "\n" + m for i, m in enumerate(metinler)))
        bilgi["ornek"] = len(secili_o)
        sira = {id(o): i for i, o in enumerate(ornekler)}
        bilgi["ornek_kimlikleri"] = [sira[id(o)] + 1 if sira[id(o)] < sabit else "gb:" + o["kaynak"]["site"]
                                     for o in secili_o]
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
