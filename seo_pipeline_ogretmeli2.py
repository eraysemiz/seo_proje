#!/usr/bin/env python3
"""
Yerel LLM (LM Studio) ile otomatik SEO denetimi ve iyilestirme hatti  (v2)

Akis: HTML -> veri cikarma -> kural denetimi -> (LLM) iyilestirme onerisi -> koda uygulama
      -> duzeltilmis HTML + rapor.json

Ornek:
  py seo_pipeline.py snapshots --out sonuc_baseline --no-llm
  py seo_pipeline.py snapshots --out sonuc_qwen --url http://localhost:1235/v1
  py seo_pipeline.py snapshots --out sonuc_qwen --url http://localhost:1235/v1 --max-tokens 6000

Gereksinim: pip install requests beautifulsoup4 lxml
"""
import argparse, hashlib, json, math, os, re, sys, time
from pathlib import Path
from urllib.parse import unquote
import requests
from bs4 import BeautifulSoup

# ------------------------------------------------------------ 1. VERI CIKARMA
ALT_LIMIT = 12

def tr_lower(x):
    return x.replace("İ", "i").replace("I", "ı").lower()

def kokler(metin):
    """Metindeki 5+ harfli kelimelerin ilk 5 harfi (Turkce ek farklarini yumusatir)."""
    return {w[:5] for w in re.findall(r"[a-zçğıöşü0-9]+", tr_lower(metin)) if len(w) >= 5}

# her sayfada bulunabilecek genel SEO/kurum sozcukleri (sadakat denetiminde sayilmaz)
GENEL_KOKLER = {"resmi", "sites", "anasa", "sayfa", "hizme", "bilgi", "haber", "duyur", "kurum", "hakkı"}

def sayfa_url_bul(html):
    """Chrome 'farkli kaydet' dosyalarinin basindaki  saved from url=(NNNN)https://...  yorumundan adresi okur."""
    m = re.search(r"saved from url=\(\d+\)\s*(\S+)", html[:2000])
    return m.group(1).split("#")[0] if m else None   # bir sayfada modelden en fazla kac gorsel icin alt metin istenir

def _baglam(img):
    """Gorselin etrafindaki metinsel ipuclari (model gorseli goremez)."""
    parca = []
    for k in ("title", "aria-label"):
        if img.get(k): parca.append(f"{k}: {img[k][:60]}")
    a = img.find_parent("a")
    if a:
        t = a.get_text(" ", strip=True)
        if t: parca.append("baglanti metni: " + t[:60])
        if a.get("href"): parca.append("baglanti: " + a["href"][:80])
    fig = img.find_parent("figure")
    if fig and fig.find("figcaption"):
        parca.append("aciklama: " + fig.find("figcaption").get_text(" ", strip=True)[:80])
    return "; ".join(parca)[:220]

def _dosya_adi(src):
    return os.path.basename(unquote(src.split("?")[0]))[:60]

def extract(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    meta = soup.find("meta", attrs={"name": "description"})
    body = soup.body or soup
    for t in body(["script", "style", "noscript"]):
        t.decompose()
    text = re.sub(r"\s+", " ", body.get_text(" ", strip=True))
    imgs = soup.find_all("img")
    return {
        "lang": (soup.html.get("lang") if soup.html else None),
        "title": soup.title.get_text(strip=True) if soup.title else None,
        "meta_description": meta.get("content", "").strip() if meta else None,
        "canonical": bool(soup.find("link", rel="canonical")),
        "h1": [h.get_text(strip=True) for h in soup.find_all("h1")],
        "h2": [h.get_text(strip=True) for h in soup.find_all("h2")][:5],
        "img_total": len(imgs),
        "img_no_alt": [i.get("src", "") for i in imgs if not (i.get("alt") or "").strip()],
        "img_baglam": {i.get("src", ""): _baglam(i) for i in imgs if not (i.get("alt") or "").strip()},
        "word_count": len(text.split()),
        "text_sample": text[:800],
        "kelime_kokleri": kokler(" ".join([
            text, soup.title.get_text(" ") if soup.title else "",
            meta.get("content", "") if meta else ""])),
    }

# ------------------------------------------------------------ 2. KURAL DENETIMI
def rule_checks(d: dict) -> list:
    issues = []
    def add(kod, ciddiyet, ayrinti=""):
        issues.append({"sorun": kod, "ciddiyet": ciddiyet, "ayrinti": ayrinti})
    t = d["title"]
    if not t: add("title_yok", "yuksek")
    elif len(t) < 30: add("title_kisa", "orta", f"{len(t)} karakter")
    elif len(t) > 60: add("title_uzun", "orta", f"{len(t)} karakter")
    m = d["meta_description"]
    if not m: add("meta_description_yok", "yuksek")
    elif len(m) < 70: add("meta_description_kisa", "orta", f"{len(m)} karakter")
    elif len(m) > 160: add("meta_description_uzun", "orta", f"{len(m)} karakter")
    if len(d["h1"]) == 0: add("h1_yok", "yuksek")
    elif len(d["h1"]) > 1: add("h1_birden_fazla", "orta", f"{len(d['h1'])} adet")
    if d["img_no_alt"]: add("img_alt_eksik", "orta", f"{len(d['img_no_alt'])}/{d['img_total']} gorsel")
    if not d["canonical"]: add("canonical_yok", "dusuk")
    if not d["lang"]: add("html_lang_yok", "dusuk")
    if d["word_count"] < 300: add("icerik_az", "dusuk", f"{d['word_count']} kelime")
    return issues

# ------------------------------------------------------------ 3. LLM (LM STUDIO)
IZINLI_ALANLAR = ("title", "meta_description", "h1", "img_alt")
KURAL_SORUNLARI = ("canonical_yok", "html_lang_yok", "h1_birden_fazla")
# her alan hangi kural sorunlariyla iliskili (gereksiz degisikligi yakalamak icin)
ALAN_SORUN = {"title": ("title_yok", "title_kisa", "title_uzun"),
              "meta_description": ("meta_description_yok", "meta_description_kisa", "meta_description_uzun"),
              "h1": ("h1_yok",), "img_alt": ("img_alt_eksik",)}

SCHEMA = {
    "type": "object",
    "properties": {"fixes": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "alan": {"type": "string", "enum": list(IZINLI_ALANLAR)},
            "hedef": {"type": "string"},
            "yeni_deger": {"type": "string"},
            "gerekce": {"type": "string"}},
        "required": ["alan", "hedef", "yeni_deger", "gerekce"]}}},
    "required": ["fixes"],
}

SYSTEM = (
    "Sen deneyimli bir SEO denetcisisin. Sana bir web sayfasindan cikarilmis veriler ve "
    "tespit edilmis sorunlar verilecek. Sadece asagidaki 4 alan icin oneri uretebilirsin:\n"
    "- title: sadece duz metin, 30-60 karakter, HTML etiketi YOK.\n"
    "- meta_description: sadece duz metin, 70-160 karakter, HTML etiketi YOK.\n"
    "- h1: sayfada h1 yoksa, sayfaya uygun kisa duz metin (5-70 karakter), <h1> etiketi YAZMA.\n"
    "- img_alt: 'hedef' alanina alt_metni_eksik_gorseller listesindeki 'id' degerini (ornek g1) AYNEN yaz. "
    "yeni_deger o gorsel icin kisa duz metin olsun; yalnizca dosya_adi ve baglam bilgisinden anlasilanlari yaz, "
    "bilgi yoksa genel ve dogru bir ifade kullan (ornek: 'Duyuru gorseli'). Her gorsel icin ayri oneri ver.\n"
    "tespit_edilen_sorunlar listesindeki canonical disindaki HER sorun icin, sinirda olsa bile "
    "(ornegin 29 karakterlik title), bir oneri uret. Canonical, robots ve diger sorunlar icin oneri URETME. "
    "Ayni alan icin birden fazla oneri verme (img_alt haric). Sayfa verisinde gecmeyen hicbir bilgi veya "
    "iddia ekleme: title, meta_description ve h1 icinde yalnizca sayfa verisinde (title, meta, h1, h2, metin_ozeti) "
    "gecen kavramlari kullan; 'uzmanlasmis', 'basarili', 'lider' gibi dogrulanamayan nitelemeler yazma, "
    "'bizim/universitemiz' gibi birinci kisi anlatim kullanma. Metin Turkce olsun. title, meta_description ve h1 icin 'hedef' bos birakilir. "
    "Cevabin SADECE su bicimde tek bir JSON nesnesi olsun, baska hicbir sey yazma: "
    '{"fixes":[{"alan":"title|meta_description|h1|img_alt","hedef":"","yeni_deger":"...","gerekce":"..."}]}'
)

def _embed(url, model, metinler, timeout=60):
    """LM Studio /v1/embeddings ucundan vektorleri alir. Birden fazla metni tek istekte gonderir."""
    r = requests.post(f"{url}/embeddings", json={"model": model, "input": metinler}, timeout=timeout)
    r.raise_for_status()
    veri = sorted(r.json()["data"], key=lambda x: x["index"])
    return [x["embedding"] for x in veri]

def _kosinus(a, b):
    pay = sum(x * y for x, y in zip(a, b))
    pa = math.sqrt(sum(x * x for x in a)); pb = math.sqrt(sum(y * y for y in b))
    return pay / (pa * pb) if pa and pb else 0.0

def _embed_cache_yukle(yol):
    return json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}

def _hash(model, metin):
    return hashlib.sha256(f"{model}||{metin}".encode()).hexdigest()[:16]

def bilgi_tabani_gomme(klasor, embed_url, embed_model):
    """Bilgi tabanindaki her parcanin vektorunu getirir; cache'de yoksa hesaplayip kaydeder."""
    klasor = Path(klasor)
    parcalar = json.loads((klasor / "bilgi_tabani.json").read_text(encoding="utf-8"))
    cache_yolu = klasor / "bilgi_tabani_gomme_cache.json"
    cache = _embed_cache_yukle(cache_yolu)
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

KOSULLAR = ("sifir", "ornek", "bilgi", "ornek+bilgi")

def ogretme_metni(kosul, d, issues, klasor, k, embed_url, embed_model):
    """Deney kosuluna gore sistem istemine eklenecek 'ogretme' metnini uretir.
    sifir: ek bilgi yok | ornek: few-shot | bilgi: anlamsal RAG (embedding; basarisizsa anahtar kelime) | ornek+bilgi: ikisi."""
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
                bilgi["yontem"] = "anlamsal"
            except Exception as e:
                print(f"\n   UYARI: gomme modeline ulasilamadi ({e}); anahtar kelime eslestirmesine dusuluyor.")
                secili = None
        else:
            secili = None
        if secili is None:
            kurallar = json.loads((klasor / "seo_kurallari.json").read_text(encoding="utf-8"))
            secili = [{"icerik": f"[{r['alan']}] {r['kural']}"} for r in kurallar if r["alan"] in alanlar or r["alan"] == "genel"]
            bilgi["yontem"] = "anahtar_kelime"
        parcalar.append("\n\nSEO BILGI TABANI (bu bilgilere dayanarak oneri uret):\n" +
                        "\n".join(f"- {p['icerik']}" for p in secili))
        bilgi["kural"] = len(secili)
    if "ornek" in kosul:
        ornekler = json.loads((klasor / "ornekler.json").read_text(encoding="utf-8"))
        puan = lambda o: sum(1 for f in o["cikti"]["fixes"] if f["alan"] in alanlar)
        secili_o = sorted(ornekler, key=lambda o: -puan(o))[:k]
        parcalar.append("\n\nORNEKLER (yalnizca bicim ve ton icin; icerigini KOPYALAMA, kendi sayfanin verisini kullan):\n" +
                        "\n\n".join(f"Ornek {i+1}\nGirdi: {json.dumps(o['girdi'], ensure_ascii=False)}\nCikti: {json.dumps(o['cikti'], ensure_ascii=False)}"
                                    for i, o in enumerate(secili_o)))
        bilgi["ornek"] = len(secili_o)
    return "".join(parcalar), bilgi

def get_model(url):
    r = requests.get(f"{url}/models", timeout=10)
    r.raise_for_status()
    models = [m["id"] for m in r.json()["data"]]
    if not models:
        sys.exit("LM Studio'da yuklu model yok.")
    return models[0]

def json_ayikla(metin: str):
    """<think> bloklarini temizler, metindeki ilk JSON nesnesini okur."""
    metin = re.sub(r"<think>.*?</think>", "", metin, flags=re.S)
    metin = re.sub(r"<think>.*", "", metin, flags=re.S)      # kapanmamis dusunme blogu
    a, b = metin.find("{"), metin.rfind("}")
    if a == -1 or b <= a:
        return None
    try:
        return json.loads(metin[a:b + 1])
    except json.JSONDecodeError:
        return None

def dogrula(f, d, sorun_kodlari, kabul_edilen, gorsel_id):
    """Onerinin biciminin ve gerekliliginin kontrolu. (gecerli_mi, neden) dondurur."""
    if not isinstance(f, dict) or f.get("alan") not in IZINLI_ALANLAR:
        return False, "gecersiz_alan"
    v = f.get("yeni_deger")
    if not isinstance(v, str) or not v.strip():
        return False, "bos_deger"
    v = v.strip()
    if "<" in v or ">" in v:
        return False, "html_etiketi_iceriyor"
    alan, hedef = f["alan"], (f.get("hedef") or "").strip()
    if not any(k in sorun_kodlari for k in ALAN_SORUN[alan]):
        return False, "sorun_yok_gereksiz_degisiklik"
    if alan == "title" and not 30 <= len(v) <= 60:
        return False, f"title_uzunluk_{len(v)}"
    if alan == "meta_description" and not 70 <= len(v) <= 160:
        return False, f"meta_uzunluk_{len(v)}"
    if alan == "h1" and not 5 <= len(v) <= 70:
        return False, f"h1_uzunluk_{len(v)}"
    if alan in ("title", "meta_description", "h1"):
        bilinmeyen = sorted(k for k in kokler(v) if k not in d["kelime_kokleri"] and k not in GENEL_KOKLER)
        if len(bilinmeyen) >= 2:                      # sayfada gecmeyen en az 2 icerik kelimesi
            return False, "sayfada_olmayan_ifade: " + ", ".join(bilinmeyen)
    if alan == "img_alt":
        if hedef not in gorsel_id:
            return False, "hedef_gorsel_listede_yok"
        if not 3 <= len(v) <= 125:
            return False, f"alt_uzunluk_{len(v)}"
    anahtar = (alan, hedef if alan == "img_alt" else "")
    if anahtar in kabul_edilen:
        return False, "ayni_alan_tekrar"
    return True, ""

def _cagri(url, payload, timeout):
    """Akisli (stream) istek: uzun uretimde zaman asimi olmaz."""
    t0 = time.time()
    icerik, dusunme, bitis, n = [], [], None, 0
    ilk, son_t, parca = None, None, 0        # ilk token zamani, son token zamani, token parcasi sayisi
    with requests.post(f"{url}/chat/completions", json=payload, stream=True, timeout=(10, timeout)) as r:
        r.raise_for_status()
        r.encoding = "utf-8"
        for satir in r.iter_lines(decode_unicode=True):
            if not satir or not satir.startswith("data:"):
                continue
            veri = satir[5:].strip()
            if veri == "[DONE]":
                break
            try:
                ch = json.loads(veri)["choices"][0]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            delta = ch.get("delta") or {}
            if delta.get("content"): icerik.append(delta["content"])
            if delta.get("reasoning_content"): dusunme.append(delta["reasoning_content"])
            if delta.get("content") or delta.get("reasoning_content"):
                son_t = time.time(); parca += 1
                if ilk is None: ilk = son_t
            if ch.get("finish_reason"): bitis = ch["finish_reason"]
            n += 1
            if n % 40 == 0:
                print(f"\r   ... {time.time()-t0:.0f} sn | dusunme {sum(map(len, dusunme))} kr | cevap {sum(map(len, icerik))} kr",
                      end="", flush=True)
    print("\r" + " " * 70 + "\r", end="")
    hiz = round((parca - 1) / (son_t - ilk), 1) if ilk and son_t and parca > 2 and son_t > ilk else None
    return {"icerik": "".join(icerik), "dusunme": "".join(dusunme), "bitis": bitis, "sure": time.time() - t0,
            "ilk_token_sn": round(ilk - t0, 2) if ilk else None,   # istemin islenme suresi (prompt processing)
            "parca": parca, "uretim_hizi": hiz}                      # yaklasik token/sn (1 parca ~ 1 token)

def _eksik_alanlar(kodlar, gecerli):
    return [a for a in IZINLI_ALANLAR
            if any(k in kodlar for k in ALAN_SORUN[a]) and not any(f["alan"] == a for f in gecerli)]

def llm_fixes(d, issues, model, filename, url, max_tokens, timeout, use_schema, retry=1, few_shot=""):
    kodlar = [i["sorun"] for i in issues]
    # model uzun src yollarini bozabildigi icin gorselleri kisa kimliklerle (g1, g2...) adlandiriyoruz
    gorsel_id = {f"g{i+1}": src for i, src in enumerate(d["img_no_alt"][:ALT_LIMIT])}
    gorseller = [{"id": k, "dosya_adi": _dosya_adi(src), "baglam": d["img_baglam"].get(src, "")}
                 for k, src in gorsel_id.items()]
    veri = {"dosya": filename, "title": d["title"], "meta_description": d["meta_description"],
            "h1": d["h1"], "h2": d["h2"], "alt_metni_eksik_gorseller": gorseller,
            "metin_ozeti": d["text_sample"], "tespit_edilen_sorunlar": issues}
    sistem = {"role": "system", "content": SYSTEM + few_shot}
    mesajlar = [sistem, {"role": "user", "content": json.dumps(veri, ensure_ascii=False)}]

    gecerli, reddedilen, kabul = [], [], set()
    denemeler, toplam_sure, ilk_json, son = [], 0.0, None, None
    for deneme in range(retry + 1):
        payload = {"model": model, "temperature": 0, "max_tokens": max_tokens,
                   "stream": True, "messages": mesajlar}
        if use_schema:
            payload["response_format"] = {"type": "json_schema",
                "json_schema": {"name": "seo_fixes", "strict": "true", "schema": SCHEMA}}
        son = _cagri(url, payload, timeout)
        toplam_sure += son["sure"]
        obj = json_ayikla(son["icerik"])
        liste_var = isinstance(obj, dict) and isinstance(obj.get("fixes"), list)
        if ilk_json is None:
            ilk_json = liste_var
        yeni_red, kabul_say = [], 0
        if liste_var:
            for f in obj["fixes"]:
                ok_f, neden = dogrula(f, d, kodlar, kabul, gorsel_id)
                if ok_f:
                    f["yeni_deger"] = f["yeni_deger"].strip()
                    f.setdefault("gerekce", "")
                    h = (f.get("hedef") or "").strip()
                    f["hedef"] = h
                    if f["alan"] == "img_alt":
                        f["hedef_src"] = gorsel_id[h]
                    kabul.add((f["alan"], h if f["alan"] == "img_alt" else ""))
                    gecerli.append(f); kabul_say += 1
                else:
                    yeni_red.append({"deneme": deneme + 1, "neden": neden, "oneri": f})
        reddedilen += yeni_red
        denemeler.append({"deneme": deneme + 1, "sure_sn": round(son["sure"], 2), "bitis_nedeni": son["bitis"],
                          "kabul": kabul_say, "reddedilen": len(yeni_red),
                          "dusunme_karakter": len(son["dusunme"]), "cevap_karakter": len(son["icerik"]),
                          "istem_karakter": sum(len(m["content"]) for m in mesajlar),
                          "ilk_token_sn": son["ilk_token_sn"], "uretilen_parca": son["parca"],
                          "uretim_hizi_tps": son["uretim_hizi"]})
        eksik = _eksik_alanlar(kodlar, gecerli)
        if not eksik or deneme == retry:
            break
        geri = {"gorev": "Onceki cevapta asagidaki alanlar icin gecerli oneri yok. SADECE bu alanlar icin, "
                         "kurallara uyan oneri uret ve ayni JSON bicimini kullan.",
                "eksik_alanlar": eksik,
                "reddedilme_nedenleri": [r["neden"] for r in yeni_red],
                "sayfa_verisi": veri}
        mesajlar = [sistem, {"role": "user", "content": json.dumps(geri, ensure_ascii=False)}]

    return {
        "fixes": gecerli, "reddedilen": reddedilen, "json_gecerli": bool(ilk_json),
        "sure_sn": round(toplam_sure, 2), "bitis_nedeni": son["bitis"],
        "dusunme_karakter": sum(x["dusunme_karakter"] for x in denemeler),
        "cevap_karakter": sum(x["cevap_karakter"] for x in denemeler),
        "denemeler": denemeler, "ham": son["icerik"][:1500], "dusunme_basi": son["dusunme"][:300],
    }

# ------------------------------------------------------------ 4. DUZELTMELERI UYGULAMA
def apply_fixes(html: str, fixes: list) -> str:
    soup = BeautifulSoup(html, "lxml")
    for f in fixes:
        v = f["yeni_deger"].strip()
        if not v:
            continue
        if f["alan"] == "title":
            if soup.title: soup.title.string = v
            elif soup.head:
                tag = soup.new_tag("title"); tag.string = v; soup.head.append(tag)
        elif f["alan"] == "meta_description":
            tag = soup.find("meta", attrs={"name": "description"})
            if tag: tag["content"] = v
            elif soup.head:
                soup.head.append(soup.new_tag("meta", attrs={"name": "description", "content": v}))
        elif f["alan"] == "h1":
            if not soup.find("h1") and soup.body:
                tag = soup.new_tag("h1"); tag.string = v
                soup.body.insert(0, tag)
        elif f["alan"] == "img_alt":
            for img in soup.find_all("img"):
                if img.get("src") == f.get("hedef_src", f.get("hedef")) and not (img.get("alt") or "").strip():
                    img["alt"] = v
    return str(soup)

def kural_duzelt(html, kodlar, site_url, dil):
    """Model gerektirmeyen, belirli (deterministik) duzeltmeler. (yeni_html, uygulananlar) dondurur."""
    soup = BeautifulSoup(html, "lxml")
    uygulanan = []
    if "canonical_yok" in kodlar and site_url and soup.head:
        soup.head.append(soup.new_tag("link", rel="canonical", href=site_url))
        uygulanan.append(f"canonical_eklendi: {site_url}")
    if "html_lang_yok" in kodlar and soup.html:
        soup.html["lang"] = dil
        uygulanan.append(f"html_lang_eklendi: {dil}")
    if "h1_birden_fazla" in kodlar:
        h1ler = soup.find_all("h1")
        for h in h1ler[1:]:
            h.name = "h2"
        uygulanan.append(f"h1_fazlalari_h2_yapildi: {max(len(h1ler) - 1, 0)}")
    return str(soup), uygulanan

# ------------------------------------------------------------ 5. ANA AKIS
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("girdi", help="HTML/HTM dosyasi veya klasoru")
    ap.add_argument("--out", default="sonuclar")
    ap.add_argument("--url", default="http://localhost:1234/v1", help="LM Studio sunucu adresi (portunuzu yazin)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--no-llm", action="store_true", help="Sadece kural denetimi (baseline)")
    ap.add_argument("--max-tokens", type=int, default=3000, help="Dusunme + cevap icin toplam token siniri")
    ap.add_argument("--timeout", type=int, default=600, help="Iki veri parcasi arasinda en fazla bekleme (sn)")
    ap.add_argument("--retry", type=int, default=1, help="Eksik/gecersiz oneri icin en fazla kac kez yeniden sorulsun (0=kapali)")
    ap.add_argument("--site-url", default=None, help="canonical icin sayfa adresi (yoksa kayitli dosyadaki 'saved from url' yorumu kullanilir)")
    ap.add_argument("--dil", default="tr", help="html lang degeri eksikse eklenecek dil kodu")
    ap.add_argument("--kosul", choices=KOSULLAR, default="sifir",
                    help="ogretme kosulu: sifir | ornek (few-shot) | bilgi (kural tabani/RAG) | ornek+bilgi")
    ap.add_argument("--ogretme-klasoru", default=str(Path(__file__).resolve().parent / "ogretme"),
                    help="ornekler.json ve seo_kurallari.json klasoru")
    ap.add_argument("--ornek-sayisi", type=int, default=3, help="istemde kac ornek/bilgi parcasi gosterilsin")
    ap.add_argument("--embed-model", default=None, help="gomme (embedding) modeli kimligi; verilmezse 'bilgi' kosulu anahtar kelime eslestirmesine duser")
    ap.add_argument("--embed-url", default=None, help="gomme modeli sunucu adresi (varsayilan: --url ile ayni)")
    ap.add_argument("--json-schema", action="store_true", help="LM Studio yapilandirilmis cikti (bazi modellerde bos cevap verebilir)")
    args = ap.parse_args()

    girdi = Path(args.girdi)
    files = (sorted(f for f in girdi.iterdir() if f.suffix.lower() in (".html", ".htm"))
             if girdi.is_dir() else [girdi])
    if not files:
        sys.exit("Klasorde .html/.htm dosyasi bulunamadi: " + str(girdi.resolve()))
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    model = None if args.no_llm else (args.model or get_model(args.url))
    if model:
        print("Model:", model, "| max_tokens:", args.max_tokens, "| kosul:", args.kosul)

    rapor = []
    for fp in files:
        html = fp.read_text(encoding="utf-8", errors="ignore")
        d = extract(html)
        issues = rule_checks(d)
        kayit = {"dosya": fp.name, "model": model, "once_sorun_sayisi": len(issues), "sorunlar": issues}
        if model and issues:
            once = [i["sorun"] for i in issues]
            ogr, ogr_bilgi = ogretme_metni(args.kosul, d, issues, args.ogretme_klasoru, args.ornek_sayisi,
                                           args.embed_url or args.url, args.embed_model)
            res = llm_fixes(d, issues, model, fp.name, args.url, args.max_tokens, args.timeout, args.json_schema,
                            args.retry, few_shot=ogr)
            kayit.update(res)
            kayit["kosul"] = args.kosul
            kayit["ogretme_ornek_sayisi"] = ogr_bilgi["ornek"]
            kayit["ogretme_kural_sayisi"] = ogr_bilgi["kural"]
            kayit["ogretme_yontemi"] = ogr_bilgi["yontem"]
            yeni = apply_fixes(html, res["fixes"])
            site_url = args.site_url or sayfa_url_bul(html)
            yeni, kural = kural_duzelt(yeni, once, site_url, args.dil)
            kayit["site_url"] = site_url
            kayit["kural_duzeltmeleri"] = kural
            sonra = [i["sorun"] for i in rule_checks(extract(yeni))]
            kayit["sonra_sorun_sayisi"] = len(sonra)
            kayit["cozulen_sorunlar"] = [x for x in once if x not in sonra]
            kayit["kalan_sorunlar"] = [x for x in once if x in sonra]
            kayit["yeni_cikan_sorunlar"] = [x for x in sonra if x not in once]
            llm_k = [x for x in once if any(x in ALAN_SORUN[a] for a in IZINLI_ALANLAR)]
            kural_k = [x for x in once if x in KURAL_SORUNLARI]
            kayit["modelle_cozulebilir"] = llm_k
            kayit["kuralla_cozulebilir"] = kural_k
            kayit["elle_gereken"] = [x for x in once if x not in llm_k and x not in kural_k]
            oran = lambda lst: round(len([x for x in lst if x not in sonra]) / len(lst), 2) if lst else None
            kayit["cozum_orani"] = oran(llm_k)              # yalnizca modelin isi
            kayit["toplam_cozum_orani"] = oran(llm_k + kural_k)
            (out / f"fixed_{fp.stem}.html").write_text(yeni, encoding="utf-8")
            if res["bitis_nedeni"] == "length" and not res["cevap_karakter"]:
                print("   UYARI: token siniri dusunmeye harcandi, cevap bos. --max-tokens degerini artirin.")
        rapor.append(kayit)
        son = f" -> {kayit['sonra_sorun_sayisi']} sorun" if "sonra_sorun_sayisi" in kayit else ""
        sure = (f" ({kayit['sure_sn']} sn, {len(kayit['fixes'])} kabul, {len(kayit['reddedilen'])} reddedilen, {len(kayit['denemeler'])} deneme, model cozum orani {kayit['cozum_orani']}, toplam {kayit['toplam_cozum_orani']})"
                if "fixes" in kayit else "")
        hizlar = [x["uretim_hizi_tps"] for x in kayit.get("denemeler", []) if x.get("uretim_hizi_tps")]
        hiz = f" | uretim ~{round(sum(hizlar)/len(hizlar), 1)} t/s, ilk token {kayit['denemeler'][0]['ilk_token_sn']} sn" if hizlar else ""
        print(f"{fp.name}: {len(issues)} sorun{son}{sure}{hiz}")
        (out / "rapor.json").write_text(json.dumps(rapor, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Rapor:", out / "rapor.json")

if __name__ == "__main__":
    main()
