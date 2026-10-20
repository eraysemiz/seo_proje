"""LM Studio istemcisi: oneri uretme, bicim/sadakat dogrulamasi.

Model yalnizca sayfa katmanindaki dort alan icin oneri uretir: title, meta_description,
h1, img_alt. Canli erisim denetimlerinden (robots, sitemap, HTTPS, hiz...) gelen sorunlar
modele hic gonderilmez; bunlar kural tabanli duzeltme veya elle mudahale isidir.
"""
import json
import re
import time

import requests

from .cikarma import ALT_LIMIT, GENEL_KOKLER, dosya_adi, kokler
from .kurallar import ALAN_SORUN, IZINLI_ALANLAR

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


def modelleri_listele(url, timeout=10):
    r = requests.get(url + "/models", timeout=timeout)
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]


def model_durumlari(url, timeout=10):
    """Modellerin bellekte yuklu olup olmadigini dondurur.
    /v1/models, LM Studio'da 'anında yukleme' acikken indirilmis TUM modelleri listeler;
    gercek durum LM Studio'ya ozgu /api/v0/models ucundan okunur. Bu uc yoksa
    (baska bir sunucu) durum bilinmiyor (None) olarak isaretlenir."""
    kok = url.rstrip("/")
    kok = kok[:-3] if kok.endswith("/v1") else kok
    try:
        r = requests.get(kok + "/api/v0/models", timeout=timeout)
        r.raise_for_status()
        return [{"id": m["id"], "tur": m.get("type"), "yuklu": m.get("state") == "loaded"}
                for m in r.json().get("data", [])]
    except (requests.RequestException, KeyError, ValueError):
        return [{"id": m, "tur": "embeddings" if "embed" in m.lower() else None, "yuklu": None}
                for m in modelleri_listele(url, timeout)]


def get_model(url):
    modeller = modelleri_listele(url)
    if not modeller:
        raise RuntimeError("LM Studio'da yuklu model yok.")
    return modeller[0]


def json_ayikla(metin):
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
        return False, "title_uzunluk_" + str(len(v))
    if alan == "meta_description" and not 70 <= len(v) <= 160:
        return False, "meta_uzunluk_" + str(len(v))
    if alan == "h1" and not 5 <= len(v) <= 70:
        return False, "h1_uzunluk_" + str(len(v))
    if alan in ("title", "meta_description", "h1"):
        bilinmeyen = sorted(k for k in kokler(v) if k not in d["kelime_kokleri"] and k not in GENEL_KOKLER)
        if len(bilinmeyen) >= 2:                      # sayfada gecmeyen en az 2 icerik kelimesi
            return False, "sayfada_olmayan_ifade: " + ", ".join(bilinmeyen)
    if alan == "img_alt":
        if hedef not in gorsel_id:
            return False, "hedef_gorsel_listede_yok"
        if not 3 <= len(v) <= 125:
            return False, "alt_uzunluk_" + str(len(v))
    anahtar = (alan, hedef if alan == "img_alt" else "")
    if anahtar in kabul_edilen:
        return False, "ayni_alan_tekrar"
    return True, ""


def _cagri(url, payload, timeout, ilerleme=None):
    """Akisli (stream) istek: uzun uretimde zaman asimi olmaz."""
    t0 = time.time()
    icerik, dusunme, bitis, n = [], [], None, 0
    ilk, son_t, parca = None, None, 0        # ilk token zamani, son token zamani, token parcasi sayisi
    with requests.post(url + "/chat/completions", json=payload, stream=True, timeout=(10, timeout)) as r:
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
            if delta.get("content"):
                icerik.append(delta["content"])
            if delta.get("reasoning_content"):
                dusunme.append(delta["reasoning_content"])
            if delta.get("content") or delta.get("reasoning_content"):
                son_t = time.time()
                parca += 1
                if ilk is None:
                    ilk = son_t
            if ch.get("finish_reason"):
                bitis = ch["finish_reason"]
            n += 1
            if ilerleme and n % 40 == 0:
                ilerleme(round(time.time() - t0), sum(map(len, dusunme)), sum(map(len, icerik)))
    hiz = round((parca - 1) / (son_t - ilk), 1) if ilk and son_t and parca > 2 and son_t > ilk else None
    return {"icerik": "".join(icerik), "dusunme": "".join(dusunme), "bitis": bitis, "sure": time.time() - t0,
            "ilk_token_sn": round(ilk - t0, 2) if ilk else None,   # istemin islenme suresi
            "parca": parca, "uretim_hizi": hiz}                    # yaklasik token/sn (1 parca ~ 1 token)


def _eksik_alanlar(kodlar, gecerli):
    return [a for a in IZINLI_ALANLAR
            if any(k in kodlar for k in ALAN_SORUN[a]) and not any(f["alan"] == a for f in gecerli)]


def llm_fixes(d, issues, model, filename, url, max_tokens, timeout, use_schema,
              retry=1, few_shot="", ilerleme=None):
    """Modelden oneri ister, dogrular ve eksik kalan alanlar icin bir kez daha sorar."""
    kodlar = [i["sorun"] for i in issues]
    # model uzun src yollarini bozabildigi icin gorselleri kisa kimliklerle (g1, g2...) adlandiriyoruz
    gorsel_id = {"g" + str(i + 1): src for i, src in enumerate(d["img_no_alt"][:ALT_LIMIT])}
    gorseller = [{"id": k, "dosya_adi": dosya_adi(src), "baglam": d["img_baglam"].get(src, "")}
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
                                          "json_schema": {"name": "seo_fixes", "strict": "true",
                                                          "schema": SCHEMA}}
        son = _cagri(url, payload, timeout, ilerleme)
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
                    gecerli.append(f)
                    kabul_say += 1
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
