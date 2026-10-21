"""Tek bir sayfanin tam analiz akisi ve toplu calistirma.

Akis:
  kaynak (canli URL veya kaydedilmis HTML)
    -> veri cikarma
    -> kural denetimi (sayfa katmani) + canli denetim (site katmani, yalnizca canli modda)
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
from .cikarma import extract, sayfa_url_bul, yapisal_veri
from .kurallar import puan, rule_checks, ek_html_denetimi
from .llm import llm_fixes
from .ogretme import ogretme_metni
from .uygula import apply_fixes, kural_duzelt

VARSAYILAN_AYARLAR = {
    "llm_kullan": True,
    "url": "http://localhost:1234/v1",
    "model": None,
    "kosul": "sifir",
    "embed_model": None,
    "embed_url": None,
    "retry": 1,
    "max_tokens": 3000,
    "timeout": 600,
    "ornek_sayisi": 3,
    "json_schema": False,
    "dil": "tr",
    "site_url": None,
    "uy_robots": True,
    "bekleme_sn": 1.0,
    "zaman_asimi": canli.VARSAYILAN_ZAMAN_ASIMI,
}


def _guvenli_ad(metin):
    """Dosya adi olarak kullanilabilecek sade bir ad uretir."""
    metin = re.sub(r"\.html?$", "", metin, flags=re.I)
    ad = re.sub(r"[^\w.-]+", "_", metin).strip("_")     # \w Turkce harfleri de kapsar
    return (ad or "sayfa")[:80]


def analiz_et(kaynak, ayarlar, ogretme_klasoru, cikti_klasoru=None, gunluk=None):
    """Tek bir sayfayi bastan sona analiz eder ve rapor kaydi dondurur.

    kaynak: {"tur": "canli", "url": "..."} veya {"tur": "dosya", "yol": "..."}
    """
    a = {**VARSAYILAN_AYARLAR, **(ayarlar or {})}
    yaz = gunluk or (lambda m: None)
    t_basla = time.time()
    kayit = {"kaynak_turu": kaynak["tur"]}

    # ------------------------------------------------ 1. HTML'i elde et
    getirme, site_sorunlari, site_bilgi = None, [], None
    if kaynak["tur"] == "canli":
        url = canli.normalize(kaynak["url"])
        kayit["ad"] = url
        kayit["url"] = url
        robots = canli.robots_bilgisi(canli.kok(url), a["zaman_asimi"])
        if a["uy_robots"] and canli.sayfa_engelli_mi(robots, url):
            kayit.update({"atlandi": "robots.txt bu adresin taranmasina izin vermiyor",
                          "hata": None, "sure_toplam_sn": round(time.time() - t_basla, 2)})
            yaz("ATLANDI (robots.txt): " + url)
            return kayit
        yaz("Indiriliyor: " + url)
        getirme = canli.sayfa_getir(url, a["zaman_asimi"])
        if not getirme.get("basarili"):
            kayit.update({"hata": getirme.get("hata"), "sure_toplam_sn": round(time.time() - t_basla, 2)})
            yaz("HATA: " + str(getirme.get("hata")))
            return kayit
        html = getirme["html"]
        site_sorunlari, site_bilgi = canli.canli_denetim(getirme, a["zaman_asimi"])
        kayit["site_bilgi"] = site_bilgi
        kayit["durum_kodu"] = getirme.get("durum_kodu")
        varsayilan_site_url = getirme.get("son_url")
    else:
        yol = Path(kaynak["yol"])
        kayit["ad"] = yol.name
        kayit["dosya"] = str(yol)
        html = yol.read_text(encoding="utf-8", errors="ignore")
        varsayilan_site_url = sayfa_url_bul(html)   # Chrome'un kaydettigi orijinal adres

    # ------------------------------------------------ 2. Denetim
    d = extract(html)
    temel = rule_checks(d)
    ek = ek_html_denetimi(yapisal_veri(html))   # modele gitmeyen HTML denetimleri
    model_sorunlari = [i for i in temel if i["cozum_yolu"] == "model"]   # modele giden liste
    sayfa_sorunlari = temel + ek
    once_tum = sayfa_sorunlari + site_sorunlari
    kayit.update({
        "sorunlar": once_tum,
        "once_sorun_sayisi": len(once_tum),
        "once_puan": puan(once_tum),
        "sayfa_sorun_sayisi": len(sayfa_sorunlari),
        "site_sorun_sayisi": len(site_sorunlari),
        "model": None,
    })

    # ------------------------------------------------ 3. Dil modeli onerileri
    yeni_html = html
    if a["llm_kullan"] and a["model"] and model_sorunlari:
        ogr, ogr_bilgi = ogretme_metni(a["kosul"], d, model_sorunlari, ogretme_klasoru, a["ornek_sayisi"],
                                       a["embed_url"] or a["url"], a["embed_model"], gunluk=yaz)
        ilerleme = lambda sn, dus, cev: yaz("   model calisiyor: " + str(sn) + " sn, " +
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
            yaz("UYARI: token siniri dusunmeye harcandi, cevap bos. max_tokens degerini artirin.")

    # ------------------------------------------------ 4. Kural tabanli duzeltmeler
    once_kodlar = [i["sorun"] for i in once_tum]
    site_url = a["site_url"] or varsayilan_site_url
    yeni_html, kural = kural_duzelt(yeni_html, once_kodlar, site_url, a["dil"])
    kayit["site_url"] = site_url
    kayit["kural_duzeltmeleri"] = kural

    # ------------------------------------------------ 5. Yeniden denetim
    d2 = extract(yeni_html)
    sonra_sayfa = rule_checks(d2) + ek_html_denetimi(yapisal_veri(yeni_html))
    sonra_tum = sonra_sayfa + site_sorunlari     # site katmani HTML duzenlemesiyle degismez
    sonra_kodlar = [i["sorun"] for i in sonra_tum]
    kayit.update({
        "sonra_sorun_sayisi": len(sonra_tum),
        "sonra_puan": puan(sonra_tum),
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

    # ------------------------------------------------ 6. Ciktiyi kaydet
    if cikti_klasoru:
        Path(cikti_klasoru).mkdir(parents=True, exist_ok=True)
        hedef = Path(cikti_klasoru) / ("duzeltilmis_" + _guvenli_ad(kayit["ad"]) + ".html")
        hedef.write_text(yeni_html, encoding="utf-8")
        kayit["duzeltilmis_dosya"] = hedef.name
    kayit["sure_toplam_sn"] = round(time.time() - t_basla, 2)
    return kayit


def hedefleri_hazirla(mod, adresler_metni, klasor_yolu):
    """Arayuzden gelen girdiyi analiz edilecek hedef listesine cevirir."""
    hedefler = []
    if mod == "canli":
        for satir in (adresler_metni or "").splitlines():
            satir = satir.strip()
            if satir and not satir.startswith("#"):
                hedefler.append({"tur": "canli", "url": satir})
    else:
        yol = Path(klasor_yolu)
        if yol.is_dir():
            for f in sorted(yol.iterdir()):
                if f.suffix.lower() in (".html", ".htm"):
                    hedefler.append({"tur": "dosya", "yol": str(f)})
        elif yol.is_file():
            hedefler.append({"tur": "dosya", "yol": str(yol)})
    return hedefler


def csv_uret(sonuclar):
    """Sayfa basina bir satirlik ozet tablo (noktali virgul ayracli, Excel ile acilir)."""
    sutunlar = ["ad", "kaynak_turu", "durum_kodu", "model", "kosul", "ogretme_yontemi",
                "once_sorun_sayisi", "sonra_sorun_sayisi", "once_puan", "sonra_puan",
                "sayfa_sorun_sayisi", "site_sorun_sayisi", "cozum_orani", "toplam_cozum_orani",
                "sure_sn", "sure_toplam_sn", "hata"]
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=";")
    yazici.writerow(sutunlar + ["kabul_edilen_oneri", "reddedilen_oneri", "yok_sayilan_oneri",
                                "cozulen", "kalan"])
    for k in sonuclar:
        yazici.writerow([k.get(s, "") for s in sutunlar] + [
            len(k.get("fixes", [])), len(k.get("reddedilen", [])), len(k.get("yok_sayilan", [])),
            ", ".join(k.get("cozulen_sorunlar", [])), ", ".join(k.get("kalan_sorunlar", []))])
    return tampon.getvalue()


def topluca_analiz(hedefler, ayarlar, ogretme_klasoru, cikti_klasoru, gunluk=None, iptal=None,
                   her_kayitta=None):
    """Hedefleri sirayla analiz eder, her adimda rapor.json dosyasini gunceller ve
    sonunda ozet.csv yazar. Web arayuzu ve deney kosucusu ayni dongu uzerinden calisir.
    her_kayitta(sira, kayit, rapor): her sayfa bittiginde cagrilir (arayuzun ilerleme durumu icin)."""
    a = {**VARSAYILAN_AYARLAR, **(ayarlar or {})}
    yaz = gunluk or (lambda m: None)
    cikti = Path(cikti_klasoru)
    cikti.mkdir(parents=True, exist_ok=True)
    rapor = []
    for i, hedef in enumerate(hedefler, 1):
        if iptal and iptal():
            yaz("Tarama durduruldu.")
            break
        ad = hedef.get("url") or Path(hedef.get("yol", "")).name
        yaz("[" + str(i) + "/" + str(len(hedefler)) + "] " + ad)
        try:
            kayit = analiz_et(hedef, a, ogretme_klasoru, cikti, gunluk=yaz)
        except Exception as e:                      # tek sayfanin hatasi tum taramayi durdurmasin
            kayit = {"ad": ad, "kaynak_turu": hedef["tur"], "hata": type(e).__name__ + ": " + str(e)}
            yaz("HATA: " + kayit["hata"])
        rapor.append(kayit)
        if her_kayitta:
            her_kayitta(i, kayit, rapor)
        (cikti / "rapor.json").write_text(json.dumps(rapor, ensure_ascii=False, indent=2,
                                                     default=str), encoding="utf-8")
        if hedef["tur"] == "canli" and i < len(hedefler) and a["bekleme_sn"]:
            time.sleep(a["bekleme_sn"])             # sunucuyu yormamak icin nazik bekleme
    (cikti / "ozet.csv").write_text(csv_uret(rapor), encoding="utf-8-sig")
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
