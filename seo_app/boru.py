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

from . import canli, rapor as rapor_modulu, tarama
from .bagimsiz import cwv_sorunlari, pagespeed_seo
from .cikarma import extract, yapisal_veri
from .kurallar import (cozum_yolu, ek_html_denetimi, kanonik_birlestirmeleri, odak_terim_denetimi, puan, puanlar,
                       rule_checks, site_geneli, site_ozeti, tekillestir, yumusak_404_supheli)
from .llm import llm_fixes
from .ogretme import ogretme_metni
from .render import render_et
from .uygula import apply_fixes, kural_duzelt

VARSAYILAN_AYARLAR = {
    "url": "http://127.0.0.1:1234/v1",   # localhost Windows'ta once IPv6'ya cozulur, her istege ~2 sn ekler
    "model": None,
    "kosul": "ornek+bilgi",      # sabit: few-shot ornekler + bilgi tabani; kullaniciya sorulmaz
    "embed_model": None,
    "embed_url": None,
    "retry": 1,
    "max_tokens": 3000,
    "timeout": 600,
    "ornek_sayisi": 2,            # few-shot ornek; yazim kurallari bilgi tabanindan geldigi icin 2 ornek bicim/ton icin yeter
    "bilgi_sayisi": 5,            # getirilecek bilgi parcasi; olcumde k=3 -> 5 sorun isabetini 0,56'dan 0,94'e cikardi
    "rerank_url": None,           # istege bagli yeniden siralama sunucusu (/rerank); yoksa LM Studio adresi
    "rerank_model": None,
    "json_schema": False,
    "dil": "tr",
    "uy_robots": True,
    "bekleme_sn": 1.0,
    "zaman_asimi": canli.VARSAYILAN_ZAMAN_ASIMI,
    "bagimsiz_olcum": False,      # PageSpeed (Lighthouse) SEO puani ve Core Web Vitals da alinsin mi
    # dil modeli hic cagrilmadan yalnizca denetim; kullanicinin acik secimi olmalidir (model
    # secilmemisse tarama sessizce modelsiz devam etmez, hata verir)
    "yalnizca_denetim": False,
    "tarama_modu": "liste",       # "liste": yalnizca verilen adresler; "site": site ici baglantilar izlenir
    "en_fazla_sayfa": 50,         # site modunda taranacak en fazla sayfa
    "en_fazla_derinlik": 3,       # site modunda baslangic sayfasindan en fazla kac tiklama ileri gidilir
    "sitemap_tohum": True,        # site modunda sitemap adresleri de (ikincil oncelikle) taransin
    "link_denetimi": True,        # sayfadaki baglanti ve gorsellerin durum kodu / boyutu denetlensin
    "link_siniri": 60,            # sayfa basina denetlenecek en fazla site ici baglanti
    "js_render": False,           # sayfa kurulu Chrome/Edge ile render edilip oyle denetlensin
    "ssl_zorunlu": False,         # sertifika dogrulanamazsa dogrulamasiz yeniden denenmesin
    "oto_esik": 0.8,              # yonetici modu: guven puani bu degeri gecen duzeltmeler onaysiz uygulanir (guven.py)
}
GORSEL_DENETIM_SINIRI = 15        # sayfa basina boyutu/durumu denetlenen en fazla gorsel
BUYUK_GORSEL_BAYT = 200 * 1024


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


def _site_sorunu(kod, ciddiyet, ayrinti=""):
    return {"sorun": kod, "ciddiyet": ciddiyet, "ayrinti": ayrinti, "katman": "site", "cozum_yolu": cozum_yolu(kod)}


def _kisa(adresler, n=2):
    return ", ".join(a[:70] for a in adresler[:n]) + (" …" if len(adresler) > n else "")


def baglanti_ve_gorsel_denetimi(yv, a, robots_engelli):
    """Sayfadaki baglanti ve gorsellerin durum kodu ve boyutu (canli). (sorunlar, ozet) dondurur.
    Site ici baglantilar oncelikli; dis baglantilar ve gorseller kendi sinirlariyla denetlenir.
    robots.txt'nin bu araca yasakladigi adresler istenmez."""
    baglar = yv.get("baglantilar") or []
    ic = list(dict.fromkeys(b["adres"] for b in baglar if b["ic"]))[:a["link_siniri"]]
    dis = list(dict.fromkeys(b["adres"] for b in baglar if not b["ic"]))[:max(10, a["link_siniri"] // 3)]
    gorsel = list(dict.fromkeys(g["src"] for g in yv.get("gorseller") or []
                                if g.get("src") and not g.get("veri_uri") and g["src"].startswith("http")))
    gorsel = gorsel[:GORSEL_DENETIM_SINIRI]
    izin = (lambda adres: not robots_engelli(adres)) if a["uy_robots"] else None
    durum = canli.baglantilari_denetle(ic + dis + gorsel, zaman_asimi=min(a["zaman_asimi"], 10),
                                       bekleme=a["bekleme_sn"] / 4, izin=izin)

    def kirik(adresler):
        return [x for x in adresler if (durum.get(x) or {}).get("hata") not in (None, "robots.txt") or
                ((durum.get(x) or {}).get("durum") or 0) >= 400]
    ozet = {"denetlenen": len(durum), "kirik_ic": kirik(ic)[:20], "kirik_dis": kirik(dis)[:20],
            "yonlendirilen_ic": [x for x in ic if (durum.get(x) or {}).get("yonlendirme") and x not in kirik(ic)][:20],
            "kirik_gorsel": kirik(gorsel)[:20],
            "buyuk_gorsel": [{"adres": x, "kb": round(durum[x]["boyut"] / 1024)} for x in gorsel
                             if (durum.get(x) or {}).get("boyut") and durum[x]["boyut"] > BUYUK_GORSEL_BAYT][:20]}
    sorunlar = []
    if ozet["kirik_ic"]:
        sorunlar.append(_site_sorunu("kirik_ic_link", "orta", f"{len(kirik(ic))} bağlantı: {_kisa(ozet['kirik_ic'])}"))
    if ozet["kirik_dis"]:
        sorunlar.append(_site_sorunu("kirik_dis_link", "dusuk", f"{len(kirik(dis))} bağlantı: {_kisa(ozet['kirik_dis'])}"))
    if ozet["yonlendirilen_ic"]:
        sorunlar.append(_site_sorunu("ic_link_yonlendirme", "dusuk",
                                     f"{len(ozet['yonlendirilen_ic'])} bağlantı: {_kisa(ozet['yonlendirilen_ic'])}"))
    if ozet["kirik_gorsel"]:
        sorunlar.append(_site_sorunu("kirik_gorsel", "orta", f"{len(ozet['kirik_gorsel'])} görsel: {_kisa(ozet['kirik_gorsel'])}"))
    if ozet["buyuk_gorsel"]:
        en = max(ozet["buyuk_gorsel"], key=lambda g: g["kb"])
        sorunlar.append(_site_sorunu("gorsel_buyuk", "dusuk",
                                     f"{len(ozet['buyuk_gorsel'])} görsel, en büyüğü {en['kb']} KB"))
    return sorunlar, ozet


def _sayfa_denetimi(html, d, sayfa_url, link_basligi):
    """Sayfa katmani: temel kurallar + HTML'den gorulebilen ek denetimler + odak terim uyumu."""
    yv = yapisal_veri(html, sayfa_url, link_basligi)
    temel = rule_checks(d)
    # canonical yalnizca HTTP Link basligiyla da bildirilebilir; o durumda eksik sayilmaz
    if any(c.get("kaynak") == "http" for c in yv.get("canonicallar") or []):
        temel = [i for i in temel if i["sorun"] != "canonical_yok"]
    return temel, ek_html_denetimi(yv, sayfa_url) + odak_terim_denetimi(d), yv


def analiz_et(kaynak, ayarlar, ogretme_klasoru, cikti_klasoru=None, gunluk=None):
    """Tek bir canli adresi bastan sona analiz eder ve rapor kaydi dondurur.

    kaynak: {"url": "..."}
    """
    a = {**VARSAYILAN_AYARLAR, **(ayarlar or {})}
    if not a["model"] and not a["yalnizca_denetim"]:
        # dil modeli kullanilmayacaksa bu acikca secilmelidir; modelsiz calismaya sessizce gecilmez
        raise ValueError("Dil modeli belirtilmedi. Modelsiz çalışmak için 'yalnızca denetim' seçeneğini açın.")
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
    # yonlendirmelerin her ara adresi de robots.txt'ye sorulur; yasakli ara adres istenmez
    getirme = canli.sayfa_getir(url, a["zaman_asimi"], izin=(lambda adr: not _robots_engelli(adr)),
                                ssl_zorunlu=a["ssl_zorunlu"])
    if not getirme.get("basarili"):
        if getirme.get("robots_engeli"):
            return _atla(getirme["robots_engeli"])
        kayit.update({"hata": getirme.get("hata"), "hata_turu": getirme.get("hata_turu"),
                      "sure_toplam_sn": round(time.time() - t_basla, 2)})
        if getirme.get("hata_turu") in ("yonlendirme_dongusu", "cok_fazla_yonlendirme"):
            # dongu bir erisim hatasi degil, sitenin yapilandirma sorunudur; raporda kodu ve zinciriyle gorunur
            kayit["sorunlar"] = canli.canli_denetim(getirme, a["zaman_asimi"])[0]
            kayit["site_bilgi"] = {"yonlendirme_zinciri": getirme.get("yonlendirme_zinciri")}
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
    hata_sayfasi = (getirme.get("durum_kodu") or 0) >= 400
    kayit["hata_sayfasi"] = hata_sayfasi

    # ------------------------------------------------ 1b. JavaScript render (istege bagli)
    render_sorunlari = []
    if a["js_render"] and not hata_sayfasi:
        yaz("Render ediliyor (Chrome/Edge): " + site_url)
        islenmis, hata = render_et(site_url, canli.KULLANICI_AJANI)
        if islenmis:
            ham_kelime, render_kelime = extract(html)["word_count"], extract(islenmis)["word_count"]
            kayit["render"] = {"ham_kelime": ham_kelime, "render_kelime": render_kelime}
            if render_kelime > max(2 * ham_kelime, ham_kelime + 150):
                render_sorunlari.append({"sorun": "js_bagimli_icerik", "ciddiyet": "orta", "katman": "sayfa",
                                       "cozum_yolu": cozum_yolu("js_bagimli_icerik"),
                                       "ayrinti": f"ham HTML {ham_kelime} kelime, render sonrası {render_kelime} kelime"})
            html = islenmis               # arama motorunun gordugu bicim denetlenir ve duzeltilir
        else:
            kayit["render"] = {"hata": hata}
            yaz("UYARI: render yapılamadı, ham HTML denetleniyor: " + str(hata))

    # ------------------------------------------------ 2. Denetim
    # 4xx/5xx donen bir sayfanin HTML'i sunucunun hata sayfasidir; sayfa katmani denetlenmez
    d = extract(html)
    sayfa_url = site_url
    link_basligi = getirme.get("link_basligi")
    if hata_sayfasi:
        temel, ek, yv = [], [], {}
    else:
        temel, ek, yv = _sayfa_denetimi(html, d, sayfa_url, link_basligi)
        kayit["kanonik"] = next((urljoin(sayfa_url, c["href"]) for c in yv.get("canonicallar") or [] if c["href"]), None)
        supheli = yumusak_404_supheli(d)
        if supheli:
            kod = canli.yumusak_404_yoklama(sayfa_url, a["zaman_asimi"], izin=lambda adr: not _robots_engelli(adr))
            site_sorunlari.append(_site_sorunu(
                "yumusak_404", "yuksek" if kod == 200 else "orta",
                supheli + ("; aynı klasördeki var olmayan bir adres de 200 döndü" if kod == 200 else
                           f"; var olmayan adres {kod} döndü (sayfa içeriği hata bildiriyor)" if kod else "")))
        if a["link_denetimi"]:
            yaz("Bağlantılar ve görseller denetleniyor")
            bag_sorunlari, kayit["baglanti_denetimi"] = baglanti_ve_gorsel_denetimi(yv, a, _robots_engelli)
            site_sorunlari += bag_sorunlari
    baglar = yv.get("baglantilar") or []
    kayit["ic_baglantilar"] = list(dict.fromkeys(b["adres"] for b in baglar if b["ic"] and not b["nofollow"]))[:1000]
    kayit["ic_nofollow_baglantilar"] = list(dict.fromkeys(b["adres"] for b in baglar if b["ic"] and b["nofollow"]))[:200]
    kayit["baglanti_ozeti"] = {"ic": sum(1 for b in baglar if b["ic"]), "dis": sum(1 for b in baglar if not b["ic"]),
                               "nofollow": sum(1 for b in baglar if b["nofollow"])}
    kayit["hreflang_baglantilari"] = yv.get("hreflang_baglantilari") or []

    # ------------------------------------------------ 2b. Bagimsiz olcum ve Core Web Vitals (istege bagli)
    if a["bagimsiz_olcum"] and not hata_sayfasi:
        yaz("PageSpeed (Lighthouse) SEO puanı ve Core Web Vitals alınıyor: " + kayit["url"])
        olcum = pagespeed_seo(getirme.get("son_url") or kayit["url"])
        kayit["lighthouse"] = {"once": olcum,
                               "sonra": None,   # duzeltilmis HTML yerel dosya; API canli adres ister
                               "sonra_aciklama": "düzeltilmiş sayfa yerel olduğu için ölçülemez"}
        site_sorunlari += cwv_sorunlari(olcum)
        if olcum.get("atlandi"):
            yaz("PageSpeed atlandı: " + olcum["hata"])
        elif olcum["hata"]:
            yaz("UYARI: PageSpeed ölçümü alınamadı: " + olcum["hata"])

    # sayfalar arasi tekrar denetimi (site_geneli) icin ozgun degerler
    kayit.update({"title": d["title"], "meta_description": d["meta_description"], "h1": d["h1"],
                  "icerik_imzasi": d.get("icerik_imzasi") or [], "icerik_kelime_sayisi": d.get("icerik_kelime_sayisi")})
    model_sorunlari = [i for i in temel if i["cozum_yolu"] == "model"]   # modele giden liste
    sayfa_sorunlari = temel + ek + render_sorunlari
    # noindex sayfanin sitemap'te listelenmesi celiskili bir sinyaldir
    if site_bilgi.get("sitemapte") and any(i["sorun"] == "noindex" for i in sayfa_sorunlari + site_sorunlari):
        site_sorunlari.append(_site_sorunu("noindex_sitemapte", "orta"))
    # ayni kod iki kaynaktan gelebilir (meta + X-Robots-Tag noindex); bir kez sayilir
    once_tum = tekillestir(sayfa_sorunlari + site_sorunlari)
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
    if model_sorunlari and a["yalnizca_denetim"]:
        yaz("Yalnızca denetim: dil modeli çağrılmadı (" + str(len(model_sorunlari)) + " model sorunu öneri bekliyor)")
    elif model_sorunlari:
        ogr, ogr_bilgi = ogretme_metni(a["kosul"], d, model_sorunlari, ogretme_klasoru, a["ornek_sayisi"],
                                       a["embed_url"] or a["url"], a["embed_model"], bilgi_k=a["bilgi_sayisi"],
                                       rerank_url=a["rerank_url"] or a["url"], rerank_model=a["rerank_model"])
        ilerleme = lambda sn, dus, cev: yaz("   model çalışıyor: " + str(sn) + " sn, " +
                                            str(cev) + " karakter cevap")
        res = llm_fixes(d, model_sorunlari, a["model"], kayit["ad"], a["url"], a["max_tokens"],
                        a["timeout"], a["json_schema"], a["retry"], few_shot=ogr, ilerleme=ilerleme,
                        kaynak_kimlikleri=ogr_bilgi.get("kimlikler", ()))
        kayit.update(res)
        kayit["model"] = a["model"]
        kayit["kosul"] = a["kosul"]
        kayit["ogretme_ornek_sayisi"] = ogr_bilgi["ornek"]
        kayit["ogretme_kural_sayisi"] = ogr_bilgi["kural"]
        kayit["ogretme_yontemi"] = ogr_bilgi["yontem"]
        # hangi bilgi parcalarinin getirildigi ve hangi bilgi tabani surumuyle calisildigi (degerlendirme icin)
        kayit["ogretme_parcalar"] = ogr_bilgi.get("parcalar", [])
        kayit["getirme_ms"] = ogr_bilgi.get("getirme_ms")
        kayit["kb_surum"] = ogr_bilgi.get("kb_surum")
        yeni_html = apply_fixes(html, res["fixes"])
        if res["bitis_nedeni"] == "length" and not res["cevap_karakter"]:
            yaz("UYARI: token sınırı düşünmeye harcandı, cevap boş. max_tokens değerini artırın.")
    kayit["yalnizca_denetim"] = bool(a["yalnizca_denetim"])

    # ------------------------------------------------ 4. Kural tabanli duzeltmeler
    once_kodlar = [i["sorun"] for i in once_tum]
    yeni_html, kural = kural_duzelt(yeni_html, once_kodlar, site_url, a["dil"])
    kayit["site_url"] = site_url
    kayit["kural_duzeltmeleri"] = kural

    # ------------------------------------------------ 5. Yeniden denetim
    d2 = extract(yeni_html)
    if hata_sayfasi:
        sonra_sayfa = []
    else:
        temel2, ek2, _ = _sayfa_denetimi(yeni_html, d2, sayfa_url, link_basligi)
        sonra_sayfa = temel2 + ek2
        # render ile tespit edilen JS bagimliligi HTML duzenlemesiyle degismez
        sonra_sayfa += render_sorunlari
    # site katmani HTML duzenlemesiyle degismez
    sonra_tum = tekillestir(sonra_sayfa + site_sorunlari)
    sonra_kodlar = [i["sorun"] for i in sonra_tum]
    kayit.update({
        "sonra_sorunlar": sonra_tum,                 # tarama geneli bulgularla puan yeniden hesaplanirken kullanilir
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
    kayit["cozum_orani"] = None if a["yalnizca_denetim"] else oran(modelle)   # yalnizca modelin isi
    kayit["toplam_cozum_orani"] = oran(modelle + kuralla)

    # ------------------------------------------------ 6. Ciktiyi kaydet
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
    ek_sutunlar = ["derinlik", "gelen_baglanti", "ic_baglanti", "dis_baglanti", "kirik_ic_link", "kirik_dis_link",
                   "performans_puani", "lcp_ms", "inp_ms", "cls"]
    yazici.writerow(sutunlar + ["kabul_edilen_oneri", "reddedilen_oneri", "yok_sayilan_oneri",
                                "cozulen", "kalan", "lighthouse_seo_once", "lighthouse_seo_sonra"] +
                    [f"{an}_{kap}_puani" for an, kap in puan_alanlari] + ek_sutunlar)

    def lh_puan(k, an):
        p = ((k.get("lighthouse") or {}).get(an) or {}).get("seo_puani")
        return "" if p is None else p                     # 0 gecerli bir puandir, bos yazilmaz

    def bos(x):
        return "" if x is None else x

    for k in sonuclar:
        lh = (k.get("lighthouse") or {}).get("once") or {}
        cwv = lh.get("cwv") or {}
        bd = k.get("baglanti_denetimi") or {}
        bo = k.get("baglanti_ozeti") or {}
        yazici.writerow([k.get(s, "") for s in sutunlar] + [
            len(k.get("fixes", [])), len(k.get("reddedilen", [])), len(k.get("yok_sayilan", [])),
            ", ".join(k.get("cozulen_sorunlar", [])), ", ".join(k.get("kalan_sorunlar", [])),
            lh_puan(k, "once"), lh_puan(k, "sonra")] +
            ["" if (k.get(an + "_puanlar") or {}).get(kap) is None else k[an + "_puanlar"][kap]
             for an, kap in puan_alanlari] +
            [bos(k.get("derinlik")), bos(k.get("gelen_baglanti")), bos(bo.get("ic")), bos(bo.get("dis")),
             len(bd.get("kirik_ic") or []) if bd else "", len(bd.get("kirik_dis") or []) if bd else "",
             bos(lh.get("performans_puani")), bos(cwv.get("lcp_ms")), bos(cwv.get("inp_ms")), bos(cwv.get("cls"))])
    return tampon.getvalue()


def _json_yaz(yol, veri):
    yol.write_text(json.dumps(veri, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def topluca_analiz(hedefler, ayarlar, ogretme_klasoru, sonuc_koku, alt_yol=None, gunluk=None, iptal=None,
                   her_kayitta=None, toplam_degisti=None, bulgular_hazir=None):
    """Hedefleri sirayla analiz eder. Her sayfanin ciktisi <sonuc_koku>/<site_adi>/<alt_yol>/
    klasorune yazilir (alt_yol verilmezse sonuc_<tarih_saat>); bir taramadaki tum siteler ayni
    alt_yol'u paylasir. Her site klasorunde rapor.json her adimda guncellenir; sonunda ozet.csv,
    site_geneli.json, site_ozeti.json ve rapor.html yazilir. Web arayuzu ve deney kosucusu ayni
    dongu uzerinden calisir.
    tarama_modu="site" ise verilen adresler baslangic kabul edilir ve site ici baglantilar
    (en_fazla_derinlik ve en_fazla_sayfa sinirlariyla) izlenir; sitemap adresleri ikincil kuyruga girer.
    her_kayitta(sira, kayit, rapor): her sayfa bittiginde cagrilir (arayuzun ilerleme durumu icin).
    toplam_degisti(n): site modunda tahmini toplam sayfa sayisi degistikce cagrilir.
    bulgular_hazir(bulgular): tarama geneli bulgu gruplari hesaplaninca cagrilir (arayuz ozeti icin)."""
    a = {**VARSAYILAN_AYARLAR, **(ayarlar or {})}
    yaz = gunluk or (lambda m: None)
    alt_yol = alt_yol or zaman_damgasi()
    site_modu = a["tarama_modu"] == "site"
    kuyruk = tarama.Kuyruk()
    for h in hedefler:
        kuyruk.ekle(canli.normalize(h["url"]), 0, "başlangıç")
    sinir = a["en_fazla_sayfa"] if site_modu else len(kuyruk)
    if site_modu:
        yaz("Site taraması: en fazla " + str(sinir) + " sayfa, " + str(a["en_fazla_derinlik"]) + " tıklama derinliği")
    rapor, site_kayitlari = [], {}                  # site klasoru -> o sitenin kayitlari
    sitemap_adresleri, tohumlanan = [], set()
    i = 0
    while len(kuyruk) and i < sinir:
        if iptal and iptal():
            yaz("Tarama durduruldu.")
            break
        adres, derinlik, kesif = kuyruk.al() or (None, None, None)
        if adres is None:
            break
        i += 1
        klasor = Path(sonuc_koku) / site_adi(adres) / alt_yol
        klasor.mkdir(parents=True, exist_ok=True)
        yaz("[" + str(i) + "/" + str(sinir if site_modu else len(hedefler)) + "] " + adres)
        try:
            kayit = analiz_et({"url": adres}, a, ogretme_klasoru, klasor, gunluk=yaz)
        except Exception as e:                      # tek sayfanin hatasi tum taramayi durdurmasin
            kayit = {"ad": adres, "hata": type(e).__name__ + ": " + str(e)}
            yaz("HATA: " + kayit["hata"])
        kayit["cikti_klasoru"] = str(klasor)
        kayit["derinlik"] = derinlik
        kayit["kesif_kaynagi"] = kesif
        if site_modu and not kayit.get("hata") and not kayit.get("atlandi"):
            kuyruk.goruldu(kayit.get("site_url"))
            kok_host = urlparse(kayit.get("site_url") or adres).hostname
            # nofollow sayfanin baglantilari izlenmez; sitemap'ten gelen sayfanin derinligi bilinmez
            izlenir = derinlik is not None and derinlik < a["en_fazla_derinlik"] and \
                not any(s["sorun"] == "sayfa_nofollow" for s in kayit.get("sorunlar") or [])
            if izlenir and not kayit.get("hata_sayfasi"):
                for hedef in kayit.get("ic_baglantilar") or []:
                    if tarama.taranabilir(hedef, kok_host):
                        kuyruk.ekle(hedef, derinlik + 1, "bağlantı")
            site_kok = canli.kok(kayit.get("site_url") or adres)
            if a["sitemap_tohum"] and site_kok not in tohumlanan:
                tohumlanan.add(site_kok)
                robots = canli.robots_bilgisi(site_kok, a["zaman_asimi"])
                tohumlar = canli.sitemap_bilgisi(site_kok, robots, a["zaman_asimi"]).get("tohumlar") or []
                sitemap_adresleri += tohumlar
                eklenen = sum(1 for t in tohumlar if tarama.taranabilir(t, kok_host) and
                              kuyruk.ekle(t, None, "sitemap", yedek=True))
                if eklenen:
                    yaz(str(eklenen) + " sitemap adresi ikincil kuyruğa eklendi")
            if toplam_degisti:
                toplam_degisti(min(sinir, i + len(kuyruk)))
        rapor.append(kayit)
        site_kayitlari.setdefault(klasor, []).append(kayit)
        if her_kayitta:
            her_kayitta(i, kayit, rapor)
        _json_yaz(klasor / "rapor.json", site_kayitlari[klasor])
        if len(kuyruk) and i < sinir and a["bekleme_sn"]:
            time.sleep(a["bekleme_sn"])             # sunucuyu yormamak icin nazik bekleme
    if site_modu and toplam_degisti:
        toplam_degisti(i)
    if site_modu and len(kuyruk):
        yaz("Sayfa sınırına ulaşıldı; kuyrukta " + str(len(kuyruk)) + " adres taranmadan kaldı.")
    # Sayfalar arasi tekrarlar ve baglanti grafigi tum tarama uzerinden hesaplanir (farkli alt alan
    # adlarindaki ayni meta aciklama da yakalanir); her site klasorune o siteyi ilgilendirenler yazilir.
    kanonik_birlestirmeleri(rapor)
    bulgular = site_geneli(rapor) + tarama.baglanti_bulgulari(rapor, sitemap_adresleri, site_modu)
    for k in rapor:
        k["tekrar_bulgulari"] = sorted({g["sorun"] for g in bulgular if k.get("ad") in g["sayfalar"]})
        # tarama geneli bulgular (tekrarlar, yetim sayfa...) ilgili sayfanin puanina da yansir
        if k.get("once_puanlar"):
            olculdu = not k.get("hata_sayfasi")
            k["once_puanlar"] = puanlar(k.get("sorunlar") or [], olculdu, k["tekrar_bulgulari"])
            k["sonra_puanlar"] = puanlar(k.get("sonra_sorunlar") or k.get("sorunlar") or [], olculdu,
                                         k["tekrar_bulgulari"])
    if bulgular:
        yaz(str(len(bulgular)) + " tarama geneli bulgu grubu bulundu (site_geneli.json).")
    if bulgular_hazir:
        bulgular_hazir(bulgular)
    for klasor, kayitlar in site_kayitlari.items():
        adlar = {k.get("ad") for k in kayitlar}
        site_bulgulari = [g for g in bulgular if adlar & set(g["sayfalar"]) or
                          (g["sorun"] == "yetim_sayfa" and any(site_adi(x) == klasor.parent.name for x in g["sayfalar"]))]
        ozet = site_ozeti(kayitlar, site_bulgulari)
        _json_yaz(klasor / "site_geneli.json", site_bulgulari)
        _json_yaz(klasor / "site_ozeti.json", ozet)
        _json_yaz(klasor / "rapor.json", kayitlar)
        (klasor / "ozet.csv").write_text(csv_uret(kayitlar), encoding="utf-8-sig")
        (klasor / "rapor.html").write_text(
            rapor_modulu.html_rapor(kayitlar, ozet, site_bulgulari, baslik=klasor.parent.name), encoding="utf-8")
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
