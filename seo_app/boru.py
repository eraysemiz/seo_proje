"""Tek bir sayfanin tam analiz akisi ve toplu calistirma.

Akis:
  canli URL
    -> veri cikarma
    -> kural denetimi (sayfa katmani) + canli denetim (site katmani)
    -> dil modelinden oneri (yalnizca title / meta_description / h1 / img_alt)
    -> onerilerin dogrulanmasi ve uygulanmasi
    -> kural tabanli duzeltmeler (canonical, lang, fazla h1, viewport, og)
    -> yeniden denetim ve karsilastirma

Modele yalnizca cozum yolu 'model' olan sorunlar (title, meta_description, h1, img_alt)
gonderilir. Kural ve elle sinifindaki sorunlar (canonical, lang, icerik_az, site katmani...)
modelden istenmez; boylece model cozemeyecegi sorunlar icin gereksiz oneri uretip reddedilmez.
"""
import csv
import io
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from . import canli
from .bagimsiz import pagespeed_seo
from .cikarma import extract, yapisal_veri
from .kurallar import ek_html_denetimi, odak_terim_denetimi, puan, puanlar, rule_checks, site_geneli
from .llm import llm_fixes
from .ogretme import ogretme_metni
from .uygula import apply_fixes, kural_duzelt

VARSAYILAN_AYARLAR = {
    "url": "http://localhost:1234/v1",
    "model": None,
    "kosul": "ornek+bilgi",      # sabit: few-shot ornekler + bilgi tabani; kullaniciya sorulmaz
    "embed_model": None,
    "embed_url": None,
    "retry": 1,
    "max_tokens": 3000,
    "timeout": 600,
    "ornek_sayisi": 3,
    "json_schema": False,
    "dil": "tr",
    "uy_robots": True,
    "bekleme_sn": 1.0,
    "zaman_asimi": canli.VARSAYILAN_ZAMAN_ASIMI,
    "bagimsiz_olcum": False,      # PageSpeed (Lighthouse) SEO puani da alinsin mi
}


def site_adi(url):
    """Sonuc klasoru icin alan adi: https://www.ornek.com.tr/x -> ornek.com.tr.
    Uluslararasi (IDN) alan adlari punycode'a cevrilir; dosya sistemi icin yalnizca ASCII kalir."""
    host = (urlparse(canli.normalize(url)).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    return re.sub(r"[^a-z0-9.-]+", "_", host).strip("._") or "site"


def zaman_damgasi():
    """Tarama klasorunun adi: sonuc_YYYY-MM-DD_HH-MM-SS."""
    return "sonuc_" + time.strftime("%Y-%m-%d_%H-%M-%S")


def _guvenli_ad(metin):
    """Dosya adi olarak kullanilabilecek sade bir ad uretir."""
    metin = re.sub(r"\.html?$", "", metin, flags=re.I)
    ad = re.sub(r"[^\w.-]+", "_", metin).strip("_")     # \w Turkce harfleri de kapsar
    return (ad or "sayfa")[:80]


def analiz_et(kaynak, ayarlar, ogretme_klasoru, cikti_klasoru=None, gunluk=None):
    """Tek bir canli adresi bastan sona analiz eder ve rapor kaydi dondurur.

    kaynak: {"url": "..."}
    """
    a = {**VARSAYILAN_AYARLAR, **(ayarlar or {})}
    if not a["model"]:
        # her tarama dil modeliyle yapilir; modelsiz calismaya sessizce gecilmez
        raise ValueError("Dil modeli belirtilmedi.")
    yaz = gunluk or (lambda m: None)
    t_basla = time.time()
    kayit = {}

    # ------------------------------------------------ 1. HTML'i elde et
    url = canli.normalize(kaynak["url"])
    kayit["ad"] = url
    kayit["url"] = url

    def _robots_engelli(adres):
        r = canli.robots_bilgisi(canli.kok(adres), a["zaman_asimi"])
        return a["uy_robots"] and canli.sayfa_engelli_mi(r, adres, canli.AJAN_BELIRTECI)

    def _atla(adres):
        kayit.update({"atlandi": "robots.txt bu adresin taranmasına izin vermiyor: " + adres,
                      "hata": None, "sure_toplam_sn": round(time.time() - t_basla, 2)})
        yaz("ATLANDI (robots.txt): " + adres)
        return kayit

    if _robots_engelli(url):
        return _atla(url)
    yaz("İndiriliyor: " + url)
    getirme = canli.sayfa_getir(url, a["zaman_asimi"])
    if not getirme.get("basarili"):
        kayit.update({"hata": getirme.get("hata"), "sure_toplam_sn": round(time.time() - t_basla, 2)})
        yaz("HATA: " + str(getirme.get("hata")))
        return kayit
    # yonlendirme baska bir host'a goturduyse o host'un robots kurallari da gecerlidir
    son = getirme.get("son_url") or url
    if canli.kok(son) != canli.kok(url) and _robots_engelli(son):
        return _atla(son)
    html = getirme["html"]
    site_sorunlari, site_bilgi = canli.canli_denetim(getirme, a["zaman_asimi"])
    kayit["site_bilgi"] = site_bilgi
    kayit["durum_kodu"] = getirme.get("durum_kodu")
    site_url = son                                    # canonical ve karisik icerik denetimi icin

    # ------------------------------------------------ 2. Denetim
    # 4xx/5xx donen bir sayfanin HTML'i sunucunun hata sayfasidir; sayfa katmani denetlenmez
    hata_sayfasi = (getirme.get("durum_kodu") or 0) >= 400
    kayit["hata_sayfasi"] = hata_sayfasi
    d = extract(html)
    sayfa_url = site_url
    temel = [] if hata_sayfasi else rule_checks(d)
    # modele gitmeyen HTML denetimleri
    ek = [] if hata_sayfasi else ek_html_denetimi(yapisal_veri(html), sayfa_url) + odak_terim_denetimi(d)
    # sayfalar arasi tekrar denetimi (site_geneli) icin ozgun degerler
    kayit.update({"title": d["title"], "meta_description": d["meta_description"], "h1": d["h1"]})
    model_sorunlari = [i for i in temel if i["cozum_yolu"] == "model"]   # modele giden liste
    sayfa_sorunlari = temel + ek
    once_tum = sayfa_sorunlari + site_sorunlari
    kayit.update({
        "sorunlar": once_tum,
        "once_sorun_sayisi": len(once_tum),
        "once_puan": puan(once_tum),                 # eski olcek, deney karsilastirmasi icin korunur
        "once_puanlar": puanlar(once_tum, sayfa_olculdu=not hata_sayfasi),
        "img_bos_alt": d["img_bos_alt"],              # bilgi notu: dekoratif gorsel, sorun sayilmaz
        "sayfa_sorun_sayisi": len(sayfa_sorunlari),
        "site_sorun_sayisi": len(site_sorunlari),
        "model": None,
    })

    # ------------------------------------------------ 3. Dil modeli onerileri
    yeni_html = html
    if model_sorunlari:
        ogr, ogr_bilgi = ogretme_metni(a["kosul"], d, model_sorunlari, ogretme_klasoru, a["ornek_sayisi"],
                                       a["embed_url"] or a["url"], a["embed_model"])
        ilerleme = lambda sn, dus, cev: yaz("   model çalışıyor: " + str(sn) + " sn, " +
                                            str(cev) + " karakter cevap")
        res = llm_fixes(d, model_sorunlari, a["model"], kayit["ad"], a["url"], a["max_tokens"],
                        a["timeout"], a["json_schema"], a["retry"], few_shot=ogr, ilerleme=ilerleme)
        kayit.update(res)
        kayit["model"] = a["model"]
        kayit["kosul"] = a["kosul"]
        kayit["ogretme_ornek_sayisi"] = ogr_bilgi["ornek"]
        kayit["ogretme_kural_sayisi"] = ogr_bilgi["kural"]
        kayit["ogretme_yontemi"] = ogr_bilgi["yontem"]
        yeni_html = apply_fixes(html, res["fixes"])
        if res["bitis_nedeni"] == "length" and not res["cevap_karakter"]:
            yaz("UYARI: token sınırı düşünmeye harcandı, cevap boş. max_tokens değerini artırın.")

    # ------------------------------------------------ 4. Kural tabanli duzeltmeler
    once_kodlar = [i["sorun"] for i in once_tum]
    yeni_html, kural = kural_duzelt(yeni_html, once_kodlar, site_url, a["dil"])
    kayit["site_url"] = site_url
    kayit["kural_duzeltmeleri"] = kural

    # ------------------------------------------------ 5. Yeniden denetim
    d2 = extract(yeni_html)
    sonra_sayfa = [] if hata_sayfasi else (rule_checks(d2) + ek_html_denetimi(yapisal_veri(yeni_html), sayfa_url) +
                                           odak_terim_denetimi(d2))
    sonra_tum = sonra_sayfa + site_sorunlari     # site katmani HTML duzenlemesiyle degismez
    sonra_kodlar = [i["sorun"] for i in sonra_tum]
    kayit.update({
        "sonra_sorun_sayisi": len(sonra_tum),
        "sonra_puan": puan(sonra_tum),
        "sonra_puanlar": puanlar(sonra_tum, sayfa_olculdu=not hata_sayfasi),
        "cozulen_sorunlar": [x for x in once_kodlar if x not in sonra_kodlar],
        "kalan_sorunlar": [x for x in once_kodlar if x in sonra_kodlar],
        "yeni_cikan_sorunlar": [x for x in sonra_kodlar if x not in once_kodlar],
    })
    modelle = [i["sorun"] for i in once_tum if i["cozum_yolu"] == "model"]
    kuralla = [i["sorun"] for i in once_tum if i["cozum_yolu"] == "kural"]
    elle = [i["sorun"] for i in once_tum if i["cozum_yolu"] == "elle"]
    kayit["modelle_cozulebilir"] = modelle
    kayit["kuralla_cozulebilir"] = kuralla
    kayit["elle_gereken"] = elle
    oran = lambda lst: round(len([x for x in lst if x not in sonra_kodlar]) / len(lst), 2) if lst else None
    kayit["cozum_orani"] = oran(modelle)                 # yalnizca modelin isi
    kayit["toplam_cozum_orani"] = oran(modelle + kuralla)

    # ------------------------------------------------ 6. Bagimsiz olcum (istege bagli)
    if a["bagimsiz_olcum"] and not hata_sayfasi:
        yaz("PageSpeed (Lighthouse) SEO puanı alınıyor: " + kayit["url"])
        olcum = pagespeed_seo(getirme.get("son_url") or kayit["url"])
        kayit["lighthouse"] = {"once": olcum,
                               "sonra": None,   # duzeltilmis HTML yerel dosya; API canli adres ister
                               "sonra_aciklama": "düzeltilmiş sayfa yerel olduğu için ölçülemez"}
        if olcum["hata"]:
            yaz("UYARI: PageSpeed ölçümü alınamadı: " + olcum["hata"])

    # ------------------------------------------------ 7. Ciktiyi kaydet
    if cikti_klasoru:
        Path(cikti_klasoru).mkdir(parents=True, exist_ok=True)
        hedef = Path(cikti_klasoru) / ("duzeltilmis_" + _guvenli_ad(kayit["ad"]) + ".html")
        hedef.write_text(yeni_html, encoding="utf-8")
        kayit["duzeltilmis_dosya"] = hedef.name
    kayit["sure_toplam_sn"] = round(time.time() - t_basla, 2)
    return kayit


def hedefleri_hazirla(adresler_metni):
    """Her satirinda bir adres bulunan metni hedef listesine cevirir (bos ve # ile baslayan satirlar atlanir)."""
    hedefler = []
    for satir in (adresler_metni or "").splitlines():
        satir = satir.strip()
        if satir and not satir.startswith("#"):
            hedefler.append({"url": satir})
    return hedefler


def csv_uret(sonuclar):
    """Sayfa basina bir satirlik ozet tablo (noktali virgul ayracli, Excel ile acilir)."""
    sutunlar = ["ad", "durum_kodu", "model", "kosul", "ogretme_yontemi",
                "once_sorun_sayisi", "sonra_sorun_sayisi", "once_puan", "sonra_puan",
                "sayfa_sorun_sayisi", "site_sorun_sayisi", "cozum_orani", "toplam_cozum_orani",
                "sure_sn", "sure_toplam_sn", "hata"]
    puan_alanlari = [(an, kap) for an in ("once", "sonra")
                     for kap in ("sayfa", "site", "icerik", "teknik", "guvenlik", "performans")]
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=";")
    yazici.writerow(sutunlar + ["kabul_edilen_oneri", "reddedilen_oneri", "yok_sayilan_oneri",
                                "cozulen", "kalan", "lighthouse_seo_once", "lighthouse_seo_sonra"] +
                    [f"{an}_{kap}_puani" for an, kap in puan_alanlari])

    def lh_puan(k, an):
        p = ((k.get("lighthouse") or {}).get(an) or {}).get("seo_puani")
        return "" if p is None else p                     # 0 gecerli bir puandir, bos yazilmaz

    for k in sonuclar:
        yazici.writerow([k.get(s, "") for s in sutunlar] + [
            len(k.get("fixes", [])), len(k.get("reddedilen", [])), len(k.get("yok_sayilan", [])),
            ", ".join(k.get("cozulen_sorunlar", [])), ", ".join(k.get("kalan_sorunlar", [])),
            lh_puan(k, "once"), lh_puan(k, "sonra")] +
            ["" if (k.get(an + "_puanlar") or {}).get(kap) is None else k[an + "_puanlar"][kap]
             for an, kap in puan_alanlari])
    return tampon.getvalue()


def _json_yaz(yol, veri):
    yol.write_text(json.dumps(veri, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def topluca_analiz(hedefler, ayarlar, ogretme_klasoru, sonuc_koku, alt_yol=None, gunluk=None, iptal=None,
                   her_kayitta=None):
    """Hedefleri sirayla analiz eder. Her sayfanin ciktisi <sonuc_koku>/<site_adi>/<alt_yol>/
    klasorune yazilir (alt_yol verilmezse sonuc_<tarih_saat>); bir taramadaki tum siteler ayni
    alt_yol'u paylasir. Her site klasorunde rapor.json her adimda guncellenir, sonunda ozet.csv
    ve site_geneli.json yazilir. Web arayuzu ve deney kosucusu ayni dongu uzerinden calisir.
    her_kayitta(sira, kayit, rapor): her sayfa bittiginde cagrilir (arayuzun ilerleme durumu icin)."""
    a = {**VARSAYILAN_AYARLAR, **(ayarlar or {})}
    yaz = gunluk or (lambda m: None)
    alt_yol = alt_yol or zaman_damgasi()
    rapor, site_kayitlari = [], {}                  # site klasoru -> o sitenin kayitlari
    for i, hedef in enumerate(hedefler, 1):
        if iptal and iptal():
            yaz("Tarama durduruldu.")
            break
        ad = hedef["url"]
        klasor = Path(sonuc_koku) / site_adi(ad) / alt_yol
        klasor.mkdir(parents=True, exist_ok=True)
        yaz("[" + str(i) + "/" + str(len(hedefler)) + "] " + ad)
        try:
            kayit = analiz_et(hedef, a, ogretme_klasoru, klasor, gunluk=yaz)
        except Exception as e:                      # tek sayfanin hatasi tum taramayi durdurmasin
            kayit = {"ad": ad, "hata": type(e).__name__ + ": " + str(e)}
            yaz("HATA: " + kayit["hata"])
        kayit["cikti_klasoru"] = str(klasor)
        rapor.append(kayit)
        site_kayitlari.setdefault(klasor, []).append(kayit)
        if her_kayitta:
            her_kayitta(i, kayit, rapor)
        _json_yaz(klasor / "rapor.json", site_kayitlari[klasor])
        if i < len(hedefler) and a["bekleme_sn"]:
            time.sleep(a["bekleme_sn"])             # sunucuyu yormamak icin nazik bekleme
    # Sayfalar arasi tekrarlar tum tarama uzerinden hesaplanir (farkli alt alan adlarindaki
    # ayni meta aciklama da yakalanir); her site klasorune o siteyi ilgilendiren gruplar yazilir.
    tekrarlar = site_geneli(rapor)
    for k in rapor:
        k["tekrar_bulgulari"] = sorted({g["sorun"] for g in tekrarlar if k.get("ad") in g["sayfalar"]})
    if tekrarlar:
        yaz(str(len(tekrarlar)) + " tekrar eden title/meta/H1 grubu bulundu (site_geneli.json).")
    for klasor, kayitlar in site_kayitlari.items():
        adlar = {k.get("ad") for k in kayitlar}
        _json_yaz(klasor / "site_geneli.json", [g for g in tekrarlar if adlar & set(g["sayfalar"])])
        _json_yaz(klasor / "rapor.json", kayitlar)
        (klasor / "ozet.csv").write_text(csv_uret(kayitlar), encoding="utf-8-sig")
    return rapor


# --------------------------------------------------------------- test seti kesfi
def alt_siteleri_kesfet(baslangic_url, ayni_alan_adi=True, zaman_asimi=15):
    """Bir sayfadaki baglantilardan ayni kurumun alt sitelerini (alt alan adlarini) cikarir.
    Test setini elle toplamak yerine otomatik olusturmak icin kullanilir."""
    from bs4 import BeautifulSoup
    url = canli.normalize(baslangic_url)
    getirme = canli.sayfa_getir(url, zaman_asimi)
    if not getirme.get("basarili"):
        return {"hata": getirme.get("hata"), "adresler": []}
    taban = urlparse(getirme.get("son_url") or url)
    kok_alan = ".".join(taban.hostname.split(".")[-3:]) if taban.hostname else ""
    soup = BeautifulSoup(getirme["html"], "lxml")
    bulunan = {}
    for a_etiketi in soup.find_all("a", href=True):
        tam = urljoin(getirme.get("son_url") or url, a_etiketi["href"])
        p = urlparse(tam)
        if p.scheme not in ("http", "https") or not p.hostname:
            continue
        if ayni_alan_adi and kok_alan and not p.hostname.endswith(kok_alan):
            continue
        anahtar = p.scheme + "://" + p.netloc
        if anahtar not in bulunan:
            bulunan[anahtar] = (a_etiketi.get_text(" ", strip=True) or "")[:80]
    return {"hata": None, "kok_alan": kok_alan,
            "adresler": [{"adres": k, "baglanti_metni": v} for k, v in sorted(bulunan.items())]}
