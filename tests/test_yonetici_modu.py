"""Yonetici modu (Mod 1) ve uc kategorili siniflandirma testleri. Ag ve dil modeli kullanilmaz."""
import json
import os

import pytest

from conftest import html_yap, sahte_canli
from seo_app import duzeltme as dz
from seo_app import html_konum as hk
from seo_app import kategoriler as kat
from seo_app import yonetici
from seo_app.kurallar import ACIKLAMA, cozum_yolu
from seo_app.yazma import YerelDosyaAdaptoru, YolGuvenligiHatasi, adaptor_olustur
from seo_app.yz_oneri import dogrula_jsonld, dogrula_metin

TEMEL = "http://site.test/"
SAYFA = ('<!DOCTYPE html>\n<html>\n<head>\n<title>Çay Demleme Rehberi ve Öneriler | Örnek</title>\n'
         '<meta name="robots" content="noindex, follow">\n</head>\n<body>\n<main>\n<h1>Çay demleme</h1>\n'
         '<p>Demlik ısıtılır, çay 185 TL değerindeki pakettendir.</p>\n<h1>Servis</h1>\n</main>\n</body>\n</html>\n')


# ------------------------------------------------------------------ siniflandirma
def test_her_bulgu_turunun_tek_bir_kategorisi_var():
    tablo = kat.kategori_tablosu()
    assert set(ACIKLAMA) <= set(tablo)
    assert {v["kategori"] for v in tablo.values()} == {"kural", "yz", "elle"}
    assert kat.kategori("html_lang_yok") == "kural" and kat.kategori("charset_yok") == "kural"
    assert kat.kategori("kirik_ic_link") == "kural" and kat.kategori("gorsel_boyut_yok") == "kural"
    assert kat.kategori("title_yok") == "yz" and kat.kategori("icerik_az") == "yz"
    assert kat.kategori("https_yok") == "elle" and kat.kategori("gorsel_buyuk") == "elle"
    assert kat.kategori("bilinmeyen_kod") == "elle"


def test_yapisal_kararlar_yuksek_riskli_ve_etkisi_aciklanmis():
    for kod in ("canonical_yok", "canonical_capraz", "noindex", "meta_refresh", "hreflang_gecersiz",
                "hreflang_donus_yok", "icerik_tekrar", "robots_sayfayi_engelliyor"):
        assert kat.kategori(kod) == "yz" and kat.risk(kod) == "yuksek"
    for kod, (k, r) in kat.KATEGORI.items():
        if r == "yuksek":
            assert kat.ETKI.get(kod), kod


def test_siniflandirma_analiz_akisini_degistirmez():
    # modele hangi sorunlarin gidecegini belirleyen cozum_yolu ayni kalir
    assert cozum_yolu("title_yok") == "model"
    assert cozum_yolu("canonical_yok") == "kural"
    assert cozum_yolu("https_yok") == "elle"


def test_html_rapor_uc_kategoriyi_gosterir():
    from seo_app.rapor import html_rapor
    ozet = [{"sorun": k, "aciklama": "x", "duzeltme": "", "ciddiyet": "dusuk", "katman": "sayfa", "cozum_yolu": "elle",
             "sayfa_sayisi": 1, "ornek_sayfalar": []} for k in ("html_lang_yok", "title_yok", "https_yok", "noindex")]
    metin = html_rapor([], ozet)
    for ad in ("Kural çözer", "YZ önerir", "Elle düzeltilir", "yüksek risk"):
        assert ad in metin


# ------------------------------------------------------------------ adaptor ve yol guvenligi
def test_adaptor_okur_yazar_listeler(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.html").write_text("x", encoding="utf-8")
    a = YerelDosyaAdaptoru(tmp_path)
    assert a.listele() == ["a/b.html"]
    a.yaz("a/c.txt", "çay".encode("utf-8"))
    assert a.oku("a/c.txt").decode("utf-8") == "çay"
    assert a.var_mi("a/c.txt") and not a.var_mi("yok.txt")


@pytest.mark.parametrize("yol", ["../disari.txt", "a/../../disari.txt", "/etc/passwd", "C:/Windows/x.txt",
                                 "C:\\Windows\\x.txt", "..\\disari.txt", "", "a\x00b"])
def test_hedef_disina_yazma_engellenir(tmp_path, yol):
    kok = tmp_path / "site"
    kok.mkdir()
    a = YerelDosyaAdaptoru(kok)
    with pytest.raises(YolGuvenligiHatasi):
        a.yaz(yol, b"x")
    assert not (tmp_path / "disari.txt").exists()


def test_sembolik_baglanti_uzerinden_yazma_engellenir(tmp_path):
    kok, disari = tmp_path / "site", tmp_path / "disari"
    kok.mkdir()
    disari.mkdir()
    try:
        os.symlink(disari, kok / "kisayol", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("bu sistemde sembolik bağlantı oluşturulamıyor")
    a = YerelDosyaAdaptoru(kok)
    with pytest.raises(YolGuvenligiHatasi):
        a.yaz("kisayol/x.txt", b"x")
    assert not (disari / "x.txt").exists()
    assert "kisayol/x.txt" not in a.listele()


def test_yedek_kok_icinde_olamaz_ve_geri_alma_hashle_dogrulanir(tmp_path):
    kok = tmp_path / "site"
    kok.mkdir()
    (kok / "index.html").write_text("ilk", encoding="utf-8")
    a = YerelDosyaAdaptoru(kok)
    with pytest.raises(YolGuvenligiHatasi):
        a.yedekle(kok / "yedek")
    once = a.hashler()
    a.yedekle(tmp_path / "yedek")
    a.yaz("index.html", b"degisti")
    a.yaz("yeni.html", b"eklendi")
    sonuc = a.geri_al(tmp_path / "yedek")
    assert sonuc["eslesiyor"] and sonuc["silinen"] == ["yeni.html"]
    assert a.hashler() == once


def test_desteklenmeyen_adaptor_turu():
    with pytest.raises(NotImplementedError):
        adaptor_olustur("ftp", sunucu="x")


def test_hedef_dogrula_araci_ve_gecersiz_hedefleri_reddeder(tmp_path):
    with pytest.raises(yonetici.YoneticiHatasi):
        yonetici.hedef_dogrula(str(yonetici.PROJE_KOK), TEMEL)             # aracin kendi klasoru
    with pytest.raises(yonetici.YoneticiHatasi):
        yonetici.hedef_dogrula(str(yonetici.PROJE_KOK / "seo_app"), TEMEL)
    with pytest.raises(yonetici.YoneticiHatasi):
        yonetici.hedef_dogrula(str(tmp_path / "yok"), TEMEL)
    with pytest.raises(yonetici.YoneticiHatasi):
        yonetici.hedef_dogrula(str(tmp_path), "ftp://x")
    sonuc = tmp_path / "sonuclar"
    (sonuc / "site").mkdir(parents=True)
    with pytest.raises(yonetici.YoneticiHatasi):
        yonetici.hedef_dogrula(str(sonuc / "site"), TEMEL, sonuc)
    with pytest.raises(yonetici.YoneticiHatasi):
        yonetici.hedef_dogrula(str(tmp_path), TEMEL, sonuc)            # kok sonuc klasorunu kapsiyor
    (tmp_path / "site2").mkdir()
    adaptor, temel = yonetici.hedef_dogrula(str(tmp_path / "site2"), "http://site.test", sonuc)
    assert temel == "http://site.test/"
    with pytest.raises(yonetici.YoneticiHatasi):
        yonetici.adresleri_denetle([{"url": "http://baska.test/"}], temel)


# ------------------------------------------------------------------ konumlar
def test_konum_tarayici_ve_ardisik_degisiklik_eslemesi():
    m = "0123456789abcdefghij"
    dolu = []
    for parcalar in ([(10, 10, "X")], [(10, 10, "Y")], [(12, 14, "ZZZ")], [(5, 10, "-")]):
        esli = []
        for a, b, y in parcalar:
            ea = dz._esle(a, dolu, False)
            esli.append((ea, ea if a == b else dz._esle(b, dolu, True), y))
        m = dz.metne_uygula(m, esli)
        dolu += [(a, b, len(y) - (b - a)) for a, b, y in parcalar]
    assert m == "01234-XYabZZZefghij"
    ogeler = hk.tara(SAYFA)
    h1 = hk.bul(ogeler, "h1")
    assert [SAYFA[o.bas:o.kap_son] for o in h1] == ["<h1>Çay demleme</h1>", "<h1>Servis</h1>"]
    assert hk.yapi_hatalari(SAYFA) == 0 and hk.yapi_hatalari(SAYFA.replace("</main>", "")) == 1


# ------------------------------------------------------------------ YZ onerisi dogrulamasi
KAYNAK = "Çay demleme rehberi. Demlik ısıtılır, çay paketi 185 TL. Çaylıbahçe Of ilçesinde."


def test_uydurma_sayi_ve_niteleme_reddedilir():
    assert dogrula_metin("title", "Çay Demleme Rehberi: 185 TL Paket | Örnek", KAYNAK)[0]
    gecti, neden, _ = dogrula_metin("title", "Çay Demleme Rehberi: 99 TL Paket | Örnek", KAYNAK)
    assert not gecti and neden.startswith("kaynakta_olmayan_sayi")
    gecti, neden, _ = dogrula_metin("meta_description", "Türkiye'nin en iyi çay demleme rehberi; demlik ısıtma ve "
                                                        "çay paketi hakkında bilgiler burada.", KAYNAK)
    assert not gecti and "dogrulanamayan_niteleme" in neden


def test_dil_ve_turkce_karakter_denetimi():
    gecti, neden, _ = dogrula_metin("title", "Cay Demleme Rehberi ve Demlik Bilgisi", KAYNAK)
    assert not gecti and neden.startswith("turkce_karakter_eksik")
    gecti, neden, _ = dogrula_metin("title", "The best guide for tea and your kettle", KAYNAK)
    assert not gecti
    gecti, neden, _ = dogrula_metin("title", "Ã‡ay Demleme Rehberi ve Demlik Bilgisi", KAYNAK)
    assert not gecti and neden == "bozuk_karakter_kodlamasi"
    assert not dogrula_metin("title", "Çay", KAYNAK)[0]                   # uzunluk
    assert not dogrula_metin("title", "<b>Çay Demleme Rehberi</b> ve Demlik", KAYNAK)[0]


def test_yer_tutucu_isaretlenir():
    gecti, _, yer = dogrula_metin("meta_description", "Çay demleme rehberi; demlik ısıtma adımları ve paket bilgisi. "
                                                      "Adres: [doğrulanmalı: açık adres]", KAYNAK)
    assert gecti and yer


def test_jsonld_dogrulamasi():
    iyi = {"@context": "https://schema.org", "@type": "Product", "name": "Çay paketi",
           "offers": {"@type": "Offer", "price": "185", "priceCurrency": "TRY"}}
    assert dogrula_jsonld(iyi, ["Product"], KAYNAK, "http://site.test")[0]
    assert not dogrula_jsonld("{bozuk", ["Product"], KAYNAK, "http://site.test")[0]
    assert not dogrula_jsonld({**iyi, "offers": None}, ["Product"], KAYNAK, "http://site.test")[0]
    uydurma = {**iyi, "offers": {"@type": "Offer", "price": "240", "priceCurrency": "TRY"}}
    assert dogrula_jsonld(uydurma, ["Product"], KAYNAK, "http://site.test")[1].startswith("kaynakta_olmayan_sayi")
    assert not dogrula_jsonld({**iyi, "url": "https://baska-site.example/x"}, ["Product"], KAYNAK, "http://site.test")[0]
    # fiyat sayfadakiyle ayni olsa da schema.org bicimi zorunlu: "1.250" / "TL" yerine 1250 / TRY
    kaynak = KAYNAK + " Demlik seti 1.250 TL."
    yanlis = {**iyi, "offers": {"@type": "Offer", "price": "1.250", "priceCurrency": "TRY"}}
    assert dogrula_jsonld(yanlis, ["Product"], kaynak, "http://site.test")[1].startswith("fiyat_bicimi")
    yanlis = {**iyi, "offers": {"@type": "Offer", "price": "1250", "priceCurrency": "TL"}}
    assert dogrula_jsonld(yanlis, ["Product"], kaynak, "http://site.test")[1].startswith("para_birimi_bicimi")
    dogru = {**iyi, "offers": {"@type": "Offer", "price": "1250.00", "priceCurrency": "TRY"}}
    assert dogrula_jsonld(dogru, ["Product"], kaynak, "http://site.test")[0]
    kurum = {"@context": "https://schema.org", "@type": "Organization", "name": "Çaylıbahçe",
             "address": "[doğrulanmalı: posta adresi]"}
    gecti, _, yer, _ = dogrula_jsonld(kurum, ["Organization"], KAYNAK, "http://site.test")
    assert gecti and yer


# ------------------------------------------------------------------ plan ve uygulama
def _site(tmp_path, metin=SAYFA):
    kok = tmp_path / "site"
    kok.mkdir()
    (kok / "index.html").write_text(metin, encoding="utf-8")
    return YerelDosyaAdaptoru(kok)


def _kayitlar(*kodlar):
    return [{"ad": TEMEL, "site_url": TEMEL, "durum_kodu": 200,
             "sorunlar": [{"sorun": k, "katman": "site" if k == "https_yok" else "sayfa"} for k in kodlar]}]


ELLE = 1.01   # esik 1'in ustunde: hicbir degisiklik otomatik onayli gelmez (elle onay akisini sinamak icin)


def _plan(a, yz=None, kodlar=("html_lang_yok", "viewport_yok", "h1_birden_fazla", "noindex", "https_yok"), esik=ELLE):
    return dz.plan_uret(_kayitlar(*kodlar), [], a, TEMEL, yz=yz, esik=esik)


def _bul(plan, bulgu):
    return next(d for d in plan["degisiklikler"] if d["bulgu"] == bulgu)


def test_plan_siteye_yazmaz_ve_kategorilere_ayirir(tmp_path):
    a = _site(tmp_path)
    once = a.hashler()
    plan = _plan(a)
    assert a.hashler() == once
    kodlar = {d["bulgu"]: (d["kategori"], d["risk"]) for d in plan["degisiklikler"]}
    assert kodlar["charset_yok"] == ("kural", "dusuk")          # yonetici modunun dosya duzeyi denetimi
    assert kodlar["html_lang_yok"][0] == "kural" and kodlar["h1_birden_fazla"][0] == "kural"
    assert kodlar["noindex"] == ("yz", "yuksek") and _bul(plan, "noindex")["etki"]
    assert [e["bulgu"] for e in plan["elle"]] == ["https_yok"]
    d = _bul(plan, "html_lang_yok")
    for alan in ("dosya", "konum", "eski", "yeni", "gerekce", "bulgu", "kategori", "risk", "parcalar"):
        assert alan in d
    assert "Kural çözer" in dz.onizleme_diff(plan, lambda f: a.oku(f).decode("utf-8"))


def test_yalnizca_onaylananlar_uygulanir_ve_yuksek_risk_ayri_onay_ister(tmp_path):
    a = _site(tmp_path)
    plan = _plan(a)
    noindex = _bul(plan, "noindex")["id"]
    sonuc = dz.uygula(plan, {"kural_hepsi": True, "kararlar": {noindex: {"karar": "onay"}}}, a,
                      tmp_path / "yedek", tmp_path / "gunluk.jsonl")
    metin = a.oku("index.html").decode("utf-8")
    assert '<html lang="tr">' in metin and '<meta charset="utf-8">' in metin and "<h2>Servis</h2>" in metin
    assert "noindex" in metin                                    # risk onayi verilmedi
    assert _bul(plan, "noindex")["durum"] == "onay_bekliyor"
    assert sonuc["uygulanan"] == 4 and hk.yapi_hatalari(metin) == 0
    satirlar = [json.loads(s) for s in (tmp_path / "gunluk.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {s["durum"] for s in satirlar} == {"uygulandi", "onay_bekliyor"}


def test_onaysiz_hicbir_sey_yazilmaz(tmp_path):
    a = _site(tmp_path)
    once = a.hashler()
    plan = _plan(a)
    sonuc = dz.uygula(plan, {}, a, tmp_path / "yedek", tmp_path / "g.jsonl")
    assert sonuc["uygulanan"] == 0 and a.hashler() == once and not (tmp_path / "yedek").exists()


def test_yz_onerisi_toplu_onayla_uygulanmaz(tmp_path):
    a = _site(tmp_path)
    plan = _plan(a)
    dz.uygula(plan, {"kural_hepsi": True}, a, tmp_path / "yedek", tmp_path / "g.jsonl")
    assert _bul(plan, "noindex")["durum"] == "onay_bekliyor"


def test_risk_onayiyla_yuksek_riskli_degisiklik_uygulanir(tmp_path):
    a = _site(tmp_path)
    plan = _plan(a)
    noindex = _bul(plan, "noindex")["id"]
    dz.uygula(plan, {"kararlar": {noindex: {"karar": "onay", "risk_onay": True}}}, a, tmp_path / "y", tmp_path / "g")
    assert 'content="index, follow"' in a.oku("index.html").decode("utf-8")


def test_plandan_sonra_degisen_dosyaya_yazilmaz(tmp_path):
    a = _site(tmp_path)
    plan = _plan(a)
    a.yaz("index.html", SAYFA.replace("Servis", "Sunum").encode("utf-8"))
    dz.uygula(plan, {"kural_hepsi": True}, a, tmp_path / "y", tmp_path / "g")
    assert all(d["durum"] != "uygulandi" for d in plan["degisiklikler"])
    assert "plandan sonra değişmiş" in _bul(plan, "html_lang_yok")["durum_nedeni"]


def test_belgeyi_bozan_degisiklik_uygulanmaz(tmp_path):
    a = _site(tmp_path)
    plan = _plan(a)
    d = _bul(plan, "html_lang_yok")
    metin = a.oku("index.html").decode("utf-8")
    bas = metin.index("</main>")
    d["parcalar"] = [{"bas": bas, "son": bas + len("</main>"), "eski": "</main>", "yeni": ""}]
    dz.uygula(plan, {"kararlar": {d["id"]: {"karar": "onay"}}}, a, tmp_path / "y", tmp_path / "g")
    assert d["durum"] == "basarisiz" and "HTML yapısı" in d["durum_nedeni"]
    assert "</main>" in a.oku("index.html").decode("utf-8")


class SahteYZ:
    """YZIstemcisi yerine: sirayla verilen cevaplari dondurur, son cevap tekrarlanir (model ve ag yok).
    Gelen gorevler (yeniden deneme isteği dahil) kaydedilir."""
    model = "sahte-model"

    def __init__(self, *cevaplar):
        self.cevaplar = list(cevaplar)
        self.gorevler = []

    def iste(self, gorev, d, kodlar, sayfa_verisi, dil="tr"):
        self.gorevler.append(gorev)
        deger = self.cevaplar.pop(0) if len(self.cevaplar) > 1 else self.cevaplar[0]
        return {"deger": deger, "gerekce": "sahte gerekçe", "kaynaklar": [{"id": "t01"}],
                "kaynak_metni": "Başlık 30-60 karakter olmalı."}


def test_model_onerisi_uydurma_icerirse_uygulanamaz(tmp_path):
    a = _site(tmp_path, SAYFA.replace("<title>Çay Demleme Rehberi ve Öneriler | Örnek</title>\n", ""))
    plan = _plan(a, SahteYZ("Çay Demleme Rehberi: 2024'ün 7 Sırrı | Örnek"), kodlar=("title_yok",))
    d = _bul(plan, "title_yok")
    assert d["durum"] == "gecersiz" and d["dogrulama"]["neden"].startswith("kaynakta_olmayan_sayi")
    dz.uygula(plan, {"kararlar": {d["id"]: {"karar": "onay"}}}, a, tmp_path / "y", tmp_path / "g")
    assert "<title>" not in a.oku("index.html").decode("utf-8")


def test_yer_tutuculu_oneri_duzenlenmeden_uygulanamaz(tmp_path):
    a = _site(tmp_path)
    oneri = "Çay demleme: demlik ısıtılır, çay 185 TL değerindeki pakettendir. [doğrulanmalı: teslimat süresi]"
    plan = _plan(a, SahteYZ(oneri), kodlar=("meta_description_yok",))
    d = _bul(plan, "meta_description_yok")
    assert d["yer_tutucu"] and d["durum"] == "oneriliyor" and d["kategori"] == "yz"
    plan2 = json.loads(json.dumps(plan))
    dz.uygula(plan, {"kararlar": {d["id"]: {"karar": "onay"}}}, a, tmp_path / "y1", tmp_path / "g")
    assert _bul(plan, "meta_description_yok")["durum"] == "basarisiz"
    assert 'name="description"' not in a.oku("index.html").decode("utf-8")
    # kullanici yer tutucuyu sayfadaki bilgiyle doldurursa deger yeniden dogrulanir ve uygulanir
    duz = "Çay demleme: demlik ısıtılır, çay 185 TL değerindeki pakettendir ve servis edilir."
    dz.uygula(plan2, {"kararlar": {d["id"]: {"karar": "onay", "deger": duz}}}, a, tmp_path / "y2", tmp_path / "g")
    assert _bul(plan2, "meta_description_yok")["durum"] == "uygulandi"
    assert f'content="{duz}"' in a.oku("index.html").decode("utf-8")


def test_duzenlenen_deger_dogrulamadan_gecmezse_uygulanmaz(tmp_path):
    a = _site(tmp_path, SAYFA.replace("<title>Çay Demleme Rehberi ve Öneriler | Örnek</title>\n", ""))
    plan = _plan(a, SahteYZ("Çay Demleme, Demlik ve Servis Adımları"), kodlar=("title_yok",))
    d = _bul(plan, "title_yok")
    assert d["durum"] == "oneriliyor"
    dz.uygula(plan, {"kararlar": {d["id"]: {"karar": "onay", "deger": "Kısa"}}}, a, tmp_path / "y", tmp_path / "g")
    assert d["durum"] == "basarisiz" and "doğrulamadan geçmedi" in d["durum_nedeni"]


def test_tam_akis_geri_alma_hash_eslesir(tmp_path):
    a = _site(tmp_path)
    once = a.hashler()
    plan = _plan(a)
    klasor = tmp_path / "sonuclar" / "site.test" / "sonuc_1"
    klasor.mkdir(parents=True)
    plan["tarama"] = {"hedefler": [{"url": TEMEL}], "ayarlar": {}, "ogretme_klasoru": "", "zaman": "sonuc_1"}
    for bos in ("rapor.json",):
        (klasor / bos).write_text("[]", encoding="utf-8")
    (klasor / "degisiklikler.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    rapor = yonetici.uygula_ve_dogrula(klasor, {"kural_hepsi": True}, tmp_path / "sonuclar", tekrar_tara=False)
    assert a.hashler() != once and rapor["durumlar"]["kural"]["uygulandi"]
    diff = (klasor / "uygulanan.diff").read_text(encoding="utf-8")
    assert diff.startswith("# ===== Aşama: Onaylı") and "\n--- a/index.html" in diff
    assert (klasor / "yonetici_raporu.html").exists()
    with pytest.raises(yonetici.YoneticiHatasi):
        yonetici.uygula_ve_dogrula(klasor, {"kural_hepsi": True}, tmp_path / "sonuclar", tekrar_tara=False)
    sonuc = yonetici.geri_al(klasor.parent)
    assert sonuc["eslesiyor"] and a.hashler() == once
    with pytest.raises(yonetici.YoneticiHatasi):
        yonetici.geri_al(klasor.parent)                         # ayni uygulama iki kez geri alinmaz


# ------------------------------------------------------------------ Mod 2: yazma yok
def test_standart_mod_siteye_hic_yazmaz(monkeypatch, tmp_path):
    from seo_app import boru, yazma

    def yasak(*a, **k):
        raise AssertionError("standart modda yazma katmanı çağrıldı")
    for ad in ("yaz", "yedekle", "geri_al", "__init__"):
        monkeypatch.setattr(yazma.YerelDosyaAdaptoru, ad, yasak)
    sahte_canli(monkeypatch, {"https://ornek.test/": html_yap()})
    rapor = boru.topluca_analiz([{"url": "https://ornek.test/"}], {"yalnizca_denetim": True}, "ogretme", tmp_path,
                                gunluk=lambda m: None)
    assert rapor and not rapor[0].get("hata")


def test_yonetici_uclari_standart_modda_kapali():
    from seo_app import web
    istemci = web.uygulama.test_client()
    web.DURUM.update({"calisiyor": False, "mod": "standart", "yonetici": None})
    for yol in ("/api/yonetici/uygula", "/api/yonetici/geri-al"):
        r = istemci.post(yol, json={"kararlar": {"kural_hepsi": True}})
        assert r.status_code == 409 and "Yönetici modu etkin değil" in r.get_json()["hata"]
    assert istemci.get("/api/yonetici/plan").status_code == 409


def test_yonetici_taramasi_gecersiz_hedefle_baslamaz(monkeypatch):
    from seo_app import web
    monkeypatch.setattr(web, "_tarama_isi", lambda *a, **k: None)
    web.DURUM["calisiyor"] = False
    istemci = web.uygulama.test_client()
    r = istemci.post("/api/tara", json={"adresler": "http://127.0.0.1:8080/", "yalnizca_denetim": True,
                                        "mod": "yonetici", "kok": str(yonetici.PROJE_KOK), "temel_url": "http://127.0.0.1:8080/"})
    assert r.status_code == 400
    r = istemci.post("/api/tara", json={"adresler": "http://baska.test/", "yalnizca_denetim": True, "mod": "yonetici",
                                        "kok": "test_sitesi/site", "temel_url": "http://127.0.0.1:8080/"})
    assert r.status_code == 400 and "temel adresin altındaki" in r.get_json()["hata"]
    r = istemci.post("/api/tara", json={"adresler": "http://127.0.0.1:8080/", "yalnizca_denetim": True, "mod": "kotu"})
    assert r.status_code == 400


def test_kategori_ucu():
    from seo_app import web
    d = web.uygulama.test_client().get("/api/kategoriler").get_json()
    assert d["adlar"]["yz"] == "YZ önerir" and d["kodlar"]["noindex"]["risk"] == "yuksek"
