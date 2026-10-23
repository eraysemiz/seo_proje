"""Yonetici modunda "YZ önerir" icerik onerileri: yerel model + RAG + dogrulama.

Model yalnizca sayfanin kendi metninden ve bilgi tabani (RAG) parcalarindan yararlanir. Sitede
bulunmayan bir olgu (fiyat, adres, telefon, urun ozelligi, tarih, istatistik...) gerekiyorsa
"[doğrulanmalı: ...]" yer tutucusu yazar; yer tutuculu oneri, deger elle doldurulmadan uygulanamaz.

Her oneri uygulanmadan once dogrulanir (dogrula_metin / dogrula_jsonld):
  - bicim: HTML etiketi yok, uzunluk alana uygun, JSON-LD gecerli JSON ve zorunlu alanlari tam
  - dil: sayfanin dilinde (Turkce sayfa icin Turkce), bozuk kodlanmis karakter (Ã, Ä±, �) yok,
    sayfada Turkce harfle gecen kelimeler harfleri dusurulerek (cay/çay) yazilmamis
  - uydurma: sayfa ve kaynak metninde gecmeyen sayi/fiyat yok; dogrulanamayan nitelemeler
    (lider, en iyi...) yok; kisa alanlarda sayfada gecmeyen icerik kelimesi sinirli
Dogrulamadan gecemeyen oneri uygulanmaz ve nedeniyle raporlanir.
"""
import json
import re

from .cikarma import GENEL_KOKLER, SCHEMA_ZORUNLU, URUN_EN_AZ_BIRI, kokler, tr_lower
from .kurallar import ACIKLAMA
from .llm import _cagri, _yasakli_ifadeler, json_ayikla

YER_TUTUCU = re.compile(r"\[doğrulanmalı:[^\]]*\]", re.I)
BOZUK_KODLAMA = re.compile(r"Ã.|Ä.|Å.|Â|�")
SAYI = re.compile(r"\d+(?:[.,]\d+)*")
TR_HARFLER = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
TR_SIK = {"ve", "bir", "bu", "için", "ile", "da", "de", "olarak", "en", "çok", "daha", "gibi", "her", "sayfa"}
EN_SIK = {"the", "and", "of", "with", "for", "your", "our", "to", "is", "are", "from", "in"}

ALAN_SINIRI = {"title": (30, 60), "meta_description": (70, 160), "h1": (5, 70), "img_alt": (3, 125),
               "baglanti_metni": (3, 80)}
ALAN_TANIMI = {
    "title": "sayfa başlığı (title): düz metin, 30-60 karakter, sayfanın konusu başta, sonunda ' | <site adı>'",
    "meta_description": "meta açıklama: düz metin, 70-160 karakter, sayfanın sunduğu bilgiyi özetleyen tek iki cümle",
    "h1": "sayfanın ana başlığı (H1): düz metin, 5-70 karakter",
    "img_alt": "görsel alt metni: görselin ne gösterdiğini anlatan kısa düz metin, 3-125 karakter",
    "baglanti_metni": "bağlantı metni: gidilen sayfanın konusunu anlatan kısa düz metin",
}

SISTEM = (
    "Sen titiz bir SEO editörüsün. Görevin, verilen web sayfası için tek bir düzeltme önerisi yazmak.\n"
    "KURALLAR:\n"
    "1. Yalnızca SAYFA_VERISI ve KAYNAKLAR içinde geçen olguları kullan. Fiyat, adres, telefon, tarih, "
    "ürün özelliği, ölçü, istatistik, ödül, sertifika gibi bu verilerde geçmeyen hiçbir bilgiyi UYDURMA.\n"
    "2. Öneri için gerekli bir olgu verilerde yoksa onu uydurmak yerine '[doğrulanmalı: <eksik bilgi>]' "
    "biçiminde bir yer tutucu yaz (ör. '[doğrulanmalı: posta kodu]').\n"
    "3. 'lider', 'en iyi', 'öncü', 'uzman', 'dünya çapında' gibi doğrulanamayan övgüler yazma.\n"
    "4. Sayfanın dilinde yaz; Türkçe metinde Türkçe karakterleri (ç, ğ, ı, İ, ö, ş, ü) doğru kullan.\n"
    "5. KAYNAKLAR yazım yönergesidir, sayfa bilgisi değildir; oradaki örnek ifadeleri sayfaya aitmiş gibi "
    "yazma. Yararlandığın kaynak parçalarının kimliklerini 'kaynaklar' listesine yaz.\n"
    "Cevabın YALNIZCA şu biçimde tek bir JSON nesnesi olsun: "
    '{"deger": ..., "gerekce": "kısa gerekçe", "kaynaklar": ["t01"]}'
)


class YZHatasi(RuntimeError):
    pass


def yer_tutucu_var(metin):
    return bool(YER_TUTUCU.search(metin if isinstance(metin, str) else json.dumps(metin, ensure_ascii=False)))


def _sayilar(metin):
    """Metindeki sayilar, binlik ayraci ve ondalik bicimi farkini yok sayan bicimde."""
    # "1.250", "1250" ve "1250.00" ayni sayi sayilir
    return {re.sub(r"[.,]", "", re.sub(r"[.,]0+$", "", s)) for s in SAYI.findall(YER_TUTUCU.sub(" ", metin or ""))}


def _asciilestirilmis(kaynak_metin):
    """Kaynakta Turkce harfle gecen kelimelerin harfleri dusurulmus bicimleri -> dogru bicim."""
    harita = {}
    for k in re.findall(r"[a-zçğıöşüâîû]+", tr_lower(kaynak_metin or "")):
        a = k.translate(TR_HARFLER)
        if a != k and len(k) >= 3:
            harita.setdefault(a, k)
    return harita


def dil_denetimi(metin, dil, kaynak_metin):
    """Dil ve Turkce karakter denetimi. Hata nedeni ya da '' dondurur."""
    if BOZUK_KODLAMA.search(metin):
        return "bozuk_karakter_kodlamasi"
    kelime = re.findall(r"[a-zçğıöşüâîû]+", tr_lower(metin))
    if (dil or "tr").startswith("tr"):
        en, tr = sum(k in EN_SIK for k in kelime), sum(k in TR_SIK for k in kelime)
        if en >= 2 and en > tr:
            return "dil_uyumsuz: Türkçe sayfa için İngilizce metin"
        harita = _asciilestirilmis(kaynak_metin)
        hatali = sorted({f"{k}→{harita[k]}" for k in kelime if k in harita})
        if hatali:
            return "turkce_karakter_eksik: " + ", ".join(hatali[:4])
    return ""


def uydurma_denetimi(metin, kaynak_metin, d=None, kisa_alan=False):
    """Kaynakta gecmeyen sayilar ve dogrulanamayan nitelemeler. Hata nedeni ya da '' dondurur."""
    yeni = _sayilar(metin) - _sayilar(kaynak_metin)
    if yeni:
        return "kaynakta_olmayan_sayi: " + ", ".join(sorted(yeni)[:4])
    yasakli = _yasakli_ifadeler(YER_TUTUCU.sub(" ", metin), d or {})
    if yasakli:
        return "dogrulanamayan_niteleme: " + ", ".join(yasakli)
    if kisa_alan and d is not None:
        bilinen = kokler(kaynak_metin) | set(d.get("kelime_kokleri") or ())
        bilinmeyen = sorted(k for k in kokler(YER_TUTUCU.sub(" ", metin)) if k not in bilinen and k not in GENEL_KOKLER)
        if len(bilinmeyen) >= 2:
            return "sayfada_olmayan_ifade: " + ", ".join(bilinmeyen[:4])
    return ""


def dogrula_metin(alan, deger, kaynak_metin, dil="tr", d=None):
    """Kisa metin alani (title, meta_description, h1, img_alt, baglanti_metni) ve paragraf.
    (gecerli_mi, neden, yer_tutucu_var_mi) dondurur."""
    if not isinstance(deger, str) or not deger.strip():
        return False, "bos_deger", False
    v = deger.strip()
    if alan != "paragraf" and ("<" in v or ">" in v):
        return False, "html_etiketi_iceriyor", False
    if alan == "paragraf" and re.search(r"<[a-z/!]", v, re.I):
        return False, "html_etiketi_iceriyor", False
    if alan in ALAN_SINIRI:
        en_az, en_cok = ALAN_SINIRI[alan]
        if not en_az <= len(v) <= en_cok:
            return False, f"{alan}_uzunluk_{len(v)} (beklenen {en_az}-{en_cok})", False
    elif alan == "paragraf":
        n = len(v.split())
        if not 60 <= n <= 260:
            return False, f"paragraf_kelime_sayisi_{n} (beklenen 60-260)", False
    neden = dil_denetimi(v, dil, kaynak_metin)
    if neden:
        return False, neden, False
    neden = uydurma_denetimi(v, kaynak_metin, d, kisa_alan=alan in ("title", "meta_description", "h1"))
    if neden:
        return False, neden, False
    return True, "", yer_tutucu_var(v)


def _turler(nesne):
    t = nesne.get("@type")
    return [str(x) for x in t] if isinstance(t, list) else [str(t)]


def _degerler(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _degerler(v)
    elif isinstance(x, list):
        for v in x:
            yield from _degerler(v)
    elif x is not None:
        yield str(x)


def _teklif_bicimi(x):
    """schema.org Offer: price nokta ondalikli sayi (binlik ayracsiz), priceCurrency ISO 4217 kodu (TRY, 'TL' degil)."""
    if isinstance(x, list):
        return next((n for n in map(_teklif_bicimi, x) if n), "")
    if not isinstance(x, dict):
        return ""
    fiyat = str(x.get("price", "")).strip()
    # "1.250" Turkcede bin iki yuz elli demektir; nokta ondalik okunursa 1,25 olur. Uc haneli kusurat binlik ayraci sayilir.
    if "price" in x and not yer_tutucu_var(fiyat) and \
            (not re.fullmatch(r"\d+(\.\d{1,2})?", fiyat)):
        return "fiyat_bicimi: '" + str(x["price"]) + "' (nokta ondalıklı sayı olmalı, ör. 1250.00)"
    if "priceCurrency" in x and not yer_tutucu_var(str(x["priceCurrency"])) and \
            not re.fullmatch(r"[A-Z]{3}", str(x["priceCurrency"]).strip()):
        return "para_birimi_bicimi: '" + str(x["priceCurrency"]) + "' (ISO 4217 kodu olmalı, ör. TRY)"
    return next((n for n in map(_teklif_bicimi, x.values()) if n), "")


def dogrula_jsonld(deger, beklenen_tur, kaynak_metin, site_kok, dil="tr"):
    """JSON-LD nesnesi. (gecerli_mi, neden, yer_tutucu_var_mi, nesne) dondurur."""
    if isinstance(deger, str):
        try:
            deger = json.loads(deger)
        except json.JSONDecodeError as e:
            return False, "gecersiz_json: " + str(e)[:60], False, None
    if not isinstance(deger, dict):
        return False, "jsonld_nesne_degil", False, None
    if "schema.org" not in str(deger.get("@context", "")):
        return False, "context_schema_org_degil", False, None
    turler = _turler(deger)
    if beklenen_tur and not set(beklenen_tur) & set(turler):
        return False, "beklenmeyen_tur: " + ", ".join(turler), False, None
    for t in turler:
        for alan in SCHEMA_ZORUNLU.get(t, ()):
            if deger.get(alan) in (None, "", [], {}):
                return False, f"zorunlu_alan_eksik: {t}.{alan}", False, None
        if t == "Product" and not any(deger.get(a) for a in URUN_EN_AZ_BIRI):
            return False, "zorunlu_alan_eksik: Product.offers/review/aggregateRating", False, None
    neden = _teklif_bicimi(deger)
    if neden:
        return False, neden, False, None
    metin = " ".join(_degerler(deger))
    for parca in _degerler(deger):
        if re.match(r"^https?://", parca) and not parca.startswith(site_kok) and parca not in kaynak_metin \
                and "schema.org" not in parca:
            return False, "dogrulanamayan_adres: " + parca[:60], False, None
    neden = uydurma_denetimi(" ".join(p for p in _degerler(deger) if not re.match(r"^https?://", p)), kaynak_metin)
    if neden:
        return False, neden, False, None
    neden = BOZUK_KODLAMA.search(metin) and "bozuk_karakter_kodlamasi"
    if neden:
        return False, neden, False, None
    return True, "", yer_tutucu_var(deger), deger


class YZIstemcisi:
    """LM Studio uzerinden tek gorevlik oneri istekleri. Bilgi tabanindan (RAG) ilgili parcalar
    her istege eklenir; modelin yazdigi kaynak kimlikleri verilen parcalarla sinirlanir."""

    def __init__(self, url, model, ogretme_klasoru, embed_model=None, embed_url=None, max_tokens=4000,
                 timeout=600, bilgi_k=4):
        if not model:
            raise YZHatasi("Dil modeli seçilmedi.")
        self.url, self.model, self.klasor = url, model, ogretme_klasoru
        self.embed_model, self.embed_url = embed_model, embed_url or url
        self.max_tokens, self.timeout, self.bilgi_k = max_tokens, timeout, bilgi_k
        self.cagri_sayisi = 0

    def _kaynaklar(self, d, kodlar):
        from .ogretme import bilgi_getir
        try:
            parcalar, _ = bilgi_getir(d, [{"sorun": k} for k in kodlar], self.klasor, self.embed_url,
                                      self.embed_model, self.bilgi_k)
        except Exception:                           # bilgi tabani okunamazsa oneri kaynaksiz uretilir
            return []
        return parcalar

    def iste(self, gorev, d, kodlar, sayfa_verisi, dil="tr"):
        """{"deger", "gerekce", "kaynaklar", "kaynak_metni"} dondurur; model cevabi okunamazsa YZHatasi."""
        parcalar = self._kaynaklar(d, kodlar)
        kaynak_satirlari = ["[" + p["id"] + "] " + p.get("baslik", "") + ": " + p["icerik"] for p in parcalar]
        istem = {"gorev": gorev, "sayfa_dili": dil, "duzeltilecek_sorunlar": [ACIKLAMA.get(k, k) for k in kodlar],
                 "SAYFA_VERISI": sayfa_verisi, "KAYNAKLAR": kaynak_satirlari}
        payload = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens, "stream": True,
                   "messages": [{"role": "system", "content": SISTEM},
                                {"role": "user", "content": json.dumps(istem, ensure_ascii=False)}]}
        self.cagri_sayisi += 1
        try:
            cevap = _cagri(self.url, payload, self.timeout)
        except Exception as e:
            raise YZHatasi("Modele ulaşılamadı: " + type(e).__name__) from e
        obj = json_ayikla(cevap["icerik"])
        if not isinstance(obj, dict) or "deger" not in obj:
            raise YZHatasi("Model geçerli JSON döndürmedi" + (" (token sınırı)" if cevap["bitis"] == "length" else ""))
        izinli = {p["id"] for p in parcalar}
        kaynaklar = [k for k in obj.get("kaynaklar") or [] if isinstance(k, str) and k in izinli]
        bilgi = [{"id": p["id"], "baslik": p.get("baslik"), "kaynak": p.get("kaynak")} for p in parcalar
                 if p["id"] in kaynaklar]
        return {"deger": obj["deger"], "gerekce": str(obj.get("gerekce") or "")[:400], "kaynaklar": bilgi,
                "kaynak_metni": " ".join(p["icerik"] for p in parcalar)}


def metin_gorevi(alan, ek=""):
    return ("Bu sayfa için yeni bir " + ALAN_TANIMI[alan] + " yaz. 'deger' alanına yalnızca metni yaz." +
            (" " + ek if ek else ""))


PARAGRAF_GOREVI = ("Sayfanın ana içeriği çok kısa. Sayfanın konusunu genişleten 1-2 paragraf yaz (toplam 80-180 "
                   "kelime). Yalnızca SAYFA_VERISI ve DIGER_SAYFALARDAN içindeki bilgileri kullan; bilgi yoksa genel "
                   "ve doğru ifadeler kullan, sayı ve özellik uydurma. Paragrafları boş satırla ayır; HTML yazma. "
                   "'deger' alanına yalnızca paragraf metnini yaz.")


def jsonld_gorevi(tur, mevcut=None):
    zorunlu = list(SCHEMA_ZORUNLU.get(tur, ()))
    if tur == "Product":
        zorunlu.append("offers (price, priceCurrency)")
    metin = (f"Bu sayfa için schema.org '{tur}' türünde bir JSON-LD nesnesi yaz. '@context' "
             f"'https://schema.org' olsun. Zorunlu alanlar: {', '.join(zorunlu) or 'name'}. Değerleri yalnızca "
             "SAYFA_VERISI'nden al; sayfada olmayan bir değer gerekiyorsa '[doğrulanmalı: ...]' yer tutucusu yaz. "
             "'deger' alanına JSON nesnesinin kendisini yaz.")
    if mevcut:
        metin += " Sayfadaki mevcut (hatalı ya da eksik) blok MEVCUT_BLOK alanındadır; ondaki doğru değerleri koru."
    return metin
