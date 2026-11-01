"""Ogrenme dongusu, kalibrasyon, few-shot secimi, kalip denetimi ve olcum araclari. Ag ve dil modeli yok;
ornek sayfalar kurgusaldir (test sitesine ait degildir)."""
import json
from pathlib import Path

from conftest import kalibre_et
from seo_app import duzeltme as dz
from seo_app import geri_bildirim, gsc, guven, istatistik, kalibrasyon, ogretme, trend
from seo_app.kurallar import ALAN_SORUN, IZINLI_ALANLAR
from seo_app.llm import dogrula
from seo_app.yazma import YerelDosyaAdaptoru
from seo_app.yz_oneri import YZIstemcisi, dogrula_metin, kalip_denetimi

KOK = Path(__file__).resolve().parent.parent
TEMEL = "http://site.test/"
SAYFA = ('<!DOCTYPE html>\n<html lang="tr">\n<head>\n</head>\n<body>\n<main>\n<h1>Kış tırmanışı eğitimi</h1>\n'
         '<p>Kartaltepe Dağcılık Kulübü kış tırmanışı eğitimi kazma ve krampon kullanımını anlatır.</p>\n'
         '</main>\n</body>\n</html>\n')


class SahteYZ:
    model = "sahte-model"

    def __init__(self, deger):
        self.deger = deger

    def iste(self, gorev, d, kodlar, sayfa_verisi, dil="tr"):
        return {"deger": self.deger, "gerekce": "sahte", "kaynaklar": [{"id": "t01"}],
                "kaynak_metni": "Başlık 30-60 karakter olmalı."}


def _plan(tmp_path, deger, esik=None):
    kok = tmp_path / "site"
    kok.mkdir(exist_ok=True)
    (kok / "index.html").write_text(SAYFA, encoding="utf-8")
    kayit = [{"ad": TEMEL, "site_url": TEMEL, "durum_kodu": 200, "sorunlar": [{"sorun": "title_yok", "katman": "sayfa"}]}]
    plan = dz.plan_uret(kayit, [], YerelDosyaAdaptoru(kok), TEMEL, yz=SahteYZ(deger), esik=esik)
    return next(d for d in plan["degisiklikler"] if d["bulgu"] == "title_yok"), plan


# ------------------------------------------------------------------ kalibrasyon
def test_kalibre_edilmemis_model_onerisi_otomatik_uygulanmaz(tmp_path):
    d, _ = _plan(tmp_path, "Kış Tırmanışı Eğitimi | Kartaltepe Dağcılık Kulübü")
    assert d["dogrulama"]["gecti"] and d["guven"] < guven.ESIK and d["onay_turu"] != "otomatik"
    assert any("ölçülmüş doğruluk yok" in n for n in d["guven_nedenleri"])


def test_olculmus_dogruluk_esigi_gecerse_otomatik(monkeypatch, tmp_path):
    kalibre_et(monkeypatch, tmp_path)                      # 100/100 dogru: alt sinir ~0,96
    d, _ = _plan(tmp_path, "Kış Tırmanışı Eğitimi | Kartaltepe Dağcılık Kulübü")
    assert d["guven"] >= guven.ESIK and d["onay_turu"] == "otomatik"


def test_az_ornekle_yuksek_oran_esigi_gecmez(monkeypatch, tmp_path):
    kalibre_et(monkeypatch, tmp_path, alanlar=("title",), dogru=30, n=30)   # %100 ama n=30: alt sinir ~0,89
    assert kalibrasyon.model_tabani("title")[1]
    kalibre_et(monkeypatch, tmp_path, alanlar=("title",), dogru=27, n=30)   # %90, alt sinir ~0,74
    taban, kalibre, _ = kalibrasyon.model_tabani("title")
    assert kalibre and taban < guven.ESIK
    kalibre_et(monkeypatch, tmp_path, alanlar=("title",), dogru=20, n=20)   # en az ornek sayisinin altinda
    assert not kalibrasyon.model_tabani("title")[1]


def test_paragraf_olcumden_bagimsiz_onay_ister(monkeypatch, tmp_path):
    kalibre_et(monkeypatch, tmp_path, alanlar=("paragraf",))
    assert kalibrasyon.model_tabani("paragraf")[0] <= kalibrasyon.PARAGRAF_TAVANI < guven.ESIK


def test_kalibrasyon_kullanici_gormeden_uygulananlari_saymaz():
    alanlar = kalibrasyon.hesapla([{"alan": "title", "etiket": "dogru"}, {"alan": "title", "etiket": "kismen"}],
                                  [{"alan": "title", "karar": "onay"}, {"alan": "title", "karar": "duzenle"},
                                   {"alan": "title", "karar": "otomatik"}])
    assert alanlar["title"]["n"] == 4 and alanlar["title"]["dogru"] == 2


def test_bilgi_tabani_okunamazsa_oneri_gorunur_ve_guveni_duser(tmp_path):
    yz = YZIstemcisi("http://127.0.0.1:9/v1", "m", tmp_path / "yok")
    parcalar, hata = yz._kaynaklar({"title": "x"}, ["title_yok"])
    assert parcalar == [] and hata and yz.kaynak_hatalari == [hata]
    d = {"dogrulama": {"gecti": True, "neden": ""}, "uretici": "model", "bulgu": "title_yok",
         "duzenleme": {"alan": "title"}, "yeni": "x", "kaynak_hatasi": hata}
    temiz = {**d, "kaynak_hatasi": ""}
    assert guven.degerlendir(d)["guven"] < guven.degerlendir(temiz)["guven"]
    assert any("bilgi tabanı okunamadı" in n for n in d["guven_nedenleri"])


# ------------------------------------------------------------------ kalip denetimi
def test_marka_tekrari_ve_bos_kalip_reddedilir():
    assert kalip_denetimi("title", "Çaylıbahçe: Çay Bahçesi ve Kahvaltı | Çaylıbahçe").startswith("marka_tekrari")
    assert kalip_denetimi("title", "Menü | Kurum Adı | Kurum Adı").startswith("marka_tekrari")
    assert kalip_denetimi("title", "Ana Sayfa | Kartaltepe", "Kartaltepe").startswith("bos_kalip")
    assert kalip_denetimi("h1", "Hoş Geldiniz").startswith("bos_kalip")
    assert kalip_denetimi("img_alt", "resim").startswith("bos_kalip")
    assert kalip_denetimi("title", "Kurs Programı ve Kurs Ücretleri | Arı Kursu") == ""
    assert kalip_denetimi("title", "Kış Tırmanışı Eğitimi | Kartaltepe", "Kartaltepe") == ""


def test_kalip_denetimi_iki_modda_da_calisir():
    kaynak = "Çaylıbahçe çay bahçesi kahvaltı menüsü"
    gecti, neden, _ = dogrula_metin("title", "Çaylıbahçe: Çay Bahçesi Kahvaltı Menüsü | Çaylıbahçe", kaynak)
    assert not gecti and neden.startswith("marka_tekrari")
    from seo_app.cikarma import extract
    d = extract("<html><head><title>x</title></head><body><h1>Çaylıbahçe</h1><p>" + kaynak + "</p></body></html>")
    ok, neden = dogrula({"alan": "title", "yeni_deger": "Çaylıbahçe: Çay Bahçesi Kahvaltı Menüsü | Çaylıbahçe"},
                        d, ["title_kisa"], set(), {})
    assert not ok and neden.startswith("marka_tekrari")


# ------------------------------------------------------------------ few-shot secimi
def _ornekler():
    return json.loads((KOK / "ogretme" / "ornekler.json").read_text(encoding="utf-8"))


def _alanlar(kodlar):
    return [a for a in IZINLI_ALANLAR if any(x in kodlar for x in ALAN_SORUN[a])]


def test_ornek_secimi_sorun_koduna_gore_ve_cesitli():
    o = _ornekler()
    sec = ogretme.ornek_sec(o, ["alt_metni_anlamsiz"], _alanlar(["alt_metni_anlamsiz"]), 2, tohum="a")
    assert "alt_metni_anlamsiz" in sec[0]["girdi"]["tespit_edilen_sorunlar"]
    assert any(g.get("mevcut_alt") for g in sec[0]["girdi"]["alt_metni_eksik_gorseller"])
    ciftler, rehber = set(), 0
    for kodlar in (["title_kisa"], ["meta_description_yok"], ["img_alt_eksik"], ["h1_yok"]):
        for t in ("Ürünler", "İletişim", "Hakkımızda", "Blog", "Duyurular"):
            sec = ogretme.ornek_sec(o, kodlar, _alanlar(kodlar), 2, tohum=t)
            markalar = [ogretme._marka(x) for x in sec if ogretme._marka(x)]
            assert len(markalar) == len(set(markalar))                   # ayni kurumdan iki ornek yok
            ciftler.add(tuple(o.index(x) for x in sec))
            rehber += any((x.get("kaynak") or {}).get("etiket") == "google-starter-guide" for x in sec)
    assert len(ciftler) > 4 and rehber > 0


def test_ornek_butcesi_ve_kimlikler(tmp_path):
    import shutil
    shutil.copytree(KOK / "ogretme", tmp_path / "o", ignore=shutil.ignore_patterns("*cache*"))
    d = {"title": "Kurs", "h1": [], "icerik_ozeti": ""}
    metin, bilgi = ogretme.ogretme_metni("ornek", d, [{"sorun": "title_kisa"}, {"sorun": "img_alt_eksik"}],
                                         tmp_path / "o", 5, "", None)
    ornek_kismi = metin.split("ORNEKLER")[1]
    assert len(ornek_kismi) < ogretme.ORNEK_BUTCESI + 400 and bilgi["ornek"] == len(bilgi["ornek_kimlikleri"])


def test_geri_bildirim_ornekleri_ayni_siteyi_disarida_birakir(tmp_path):
    satirlar = [{"karar": "onay", "alan": "title", "bulgu": "title_kisa", "son_deger": "Kış Tırmanışı Eğitimi | Kartaltepe",
                 "site": "http://kartaltepe.test/", "sayfa": {"title": "Eğitim"}},
                {"karar": "ret", "alan": "title", "bulgu": "title_kisa", "son_deger": None, "site": "http://b.test/"},
                {"karar": "duzenle", "alan": "meta_description", "bulgu": "meta_description_yok",
                 "son_deger": "Açıklama metni", "site": "http://c.test/", "sayfa": {}}]
    (tmp_path / ogretme.GERI_BILDIRIM).write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in satirlar),
                                                  encoding="utf-8")
    hepsi = ogretme.geri_bildirim_ornekleri(tmp_path)
    assert len(hepsi) == 2                                                # ret ornek olmaz
    baska = ogretme.geri_bildirim_ornekleri(tmp_path, "https://www.kartaltepe.test/egitim")
    assert [x["kaynak"]["site"] for x in baska] == ["c.test"]


# ------------------------------------------------------------------ ogrenme dongusu
def _karar_plani():
    def model(i, durum="oneriliyor", onay=None):
        return {"id": i, "uretici": "model", "bulgu": "title_kisa", "url": TEMEL, "eski": "Kurs", "yeni": "Öneri " + i,
                "duzenleme": {"alan": "title", "deger": "Öneri " + i}, "durum": durum, "onay_kaynagi": onay,
                "guven": 0.75, "kaynaklar": [{"id": "t02"}]}
    plan = {"tarama": {"zaman": "sonuc_1"}, "hedef": {"temel_url": TEMEL},
            "degisiklikler": [model("D001"), model("D002"), model("D003"), model("D004", "uygulandi", "otomatik"),
                              model("D005"), {"id": "D006", "uretici": "kural", "bulgu": "charset_yok"}]}
    kararlar = {"kararlar": {"D001": {"karar": "onay"}, "D002": {"karar": "onay", "deger": "Düzeltilmiş"},
                             "D003": {"karar": "ret", "neden": "uydurma bilgi"}, "D006": {"karar": "onay"}}}
    return plan, kararlar


def test_geri_bildirim_kararlari_dogru_siniflar_ve_bir_kez_yazar(tmp_path):
    plan, kararlar = _karar_plani()
    k = {g["degisiklik"]: g for g in geri_bildirim.kayitlar(plan, kararlar)}
    assert set(k) == {"D001", "D002", "D003", "D004"}                      # karar yok (D005) ve kural (D006) yok
    assert k["D001"]["karar"] == "onay" and k["D002"]["karar"] == "duzenle" and k["D002"]["son_deger"] == "Düzeltilmiş"
    assert k["D003"]["karar"] == "ret" and k["D003"]["ret_nedeni"] == "uydurma bilgi"
    assert k["D004"]["karar"] == "otomatik" and k["D001"]["kaynaklar"] == ["t02"]
    assert geri_bildirim.kaydet(plan, kararlar, tmp_path) == 4
    assert geri_bildirim.kaydet(plan, kararlar, tmp_path) == 0
    assert geri_bildirim.kaydet(plan, kararlar, "") == 0
    assert geri_bildirim.ret_ozeti(geri_bildirim.oku(tmp_path)) == [{"alan": "title", "neden": "uydurma bilgi", "sayi": 1}]


def test_masaustu_ret_nedeni_komut_satirina_gecer():
    from masaustu import plan as pl
    plan, _ = _karar_plani()
    for d in plan["degisiklikler"]:
        d.setdefault("risk", "dusuk")
        d.setdefault("kategori", "yz")
        d.setdefault("durum", "oneriliyor")
    secimler = {"D003": {"karar": "ret", "neden": "uydurma bilgi"}, "D001": {"karar": "ret"}}
    arg, _ = pl.onay_argumanlari(plan, {"kural_hepsi": False, "kararlar": {}}, secimler, False)
    assert "D003=uydurma bilgi" in arg and "D001" in arg
    assert pl.RET_NEDENLERI == geri_bildirim.RET_NEDENLERI


# ------------------------------------------------------------------ getirme: genel kota
def test_genel_kota_genel_parca_sayisini_sinirlar():
    d = {"title": "Kurs", "h1": [], "icerik_ozeti": "kurs programı"}
    sorunlar = [{"sorun": "title_kisa"}]
    secili, bilgi = ogretme.bilgi_getir(d, sorunlar, KOK / "ogretme", "", None, 5, siralama=("bm25",))
    assert sum(p["alan"] == "genel" for p in secili) <= ogretme.GENEL_KOTA == bilgi["genel_kota"]
    secili2, _ = ogretme.bilgi_getir(d, sorunlar, KOK / "ogretme", "", None, 5, siralama=("bm25",), genel_kota=None)
    assert len(secili2) >= len(secili)


def test_yz_kodlarinin_en_az_iki_bilgi_parcasi_var():
    from collections import Counter
    from seo_app import kategoriler as kat
    kb = json.loads((KOK / "ogretme" / "bilgi_tabani.json").read_text(encoding="utf-8"))
    say = Counter(p["alan"] for p in kb)
    alan_of = {}
    for a, kodlar in list(ALAN_SORUN.items()) + list(ogretme.BILGI_ALANI_SORUN.items()):
        for k in kodlar:
            alan_of.setdefault(k, []).append(a)
    kodlar = set(dz.SAYFA_URETICI) | set(dz.TITLE_KODLARI) | set(dz.META_KODLARI) | {"h1_yok"}
    eksik = [k for k in kodlar if kat.kategori(k) == "yz" and sum(say[a] for a in alan_of.get(k, [])) < 2]
    assert not eksik, eksik
    yeni = [p for p in kb if p.get("kaynak_guncelleme")]
    assert yeni and all(p["kaynak"].startswith("https://developers.google.com/") and len(p["icerik"]) <= 400
                        for p in yeni)


# ------------------------------------------------------------------ istatistik ve olcum araclari
def test_istatistik_yardimcilari():
    assert istatistik.cohen_kappa(list("aabb"), list("aabb")) == 1.0
    assert abs(istatistik.cohen_kappa(list("aabb"), list("abab"))) < 1e-9
    assert istatistik.wilson_alt(0, 0) == 0.0 and 0.78 < istatistik.wilson_alt(45, 50) < 0.79   # %90 dogru, n=50: alt sinir esigin altinda
    b = istatistik.bootstrap_fark([1, 1, 1, 1], [0, 0, 0, 0])
    assert b["fark"] == 1 and b["alt"] == 1 and b["n"] == 4


def test_deney_kaynak_isabeti_ve_kosul_farki():
    import deney
    kayit = {"modelle_cozulebilir": ["title_kisa"], "fixes": [{"alan": "title", "kaynaklar": ["t02"]},
                                                               {"alan": "title", "kaynaklar": ["n04"]},
                                                               {"alan": "title", "kaynaklar": []}],
             "reddedilen": [{"neden": "sayfada_olmayan_ifade: x"}, {"neden": "marka_tekrari: 'a'"}]}
    assert deney.kaynak_olcumu([kayit]) == (0.667, 0.5)
    assert deney.ret_orani([kayit], deney.UYDURMA_NEDENLERI) == 0.2
    olc = {("m", "ornek+bilgi", 1): {"a": {"cozum_orani": 1.0}, "b": {"cozum_orani": 1.0}},
           ("m", "sifir", 1): {"a": {"cozum_orani": 0.0}, "b": {"cozum_orani": 0.5}}}
    f = [x for x in deney.kosul_farklari(olc) if x["metrik"] == "cozum_orani"][0]
    assert f["kosul"] == "sifir" and f["fark"] == -0.75 and f["anlamli"] == "evet"


def test_etiketleme_kor_sablon_ve_birlestirme(tmp_path):
    import etiketle
    plan = {"tarama": {"ayarlar": {"model": "m"}}, "degisiklikler": [
        {"id": f"D{i:03d}", "uretici": "model", "url": TEMEL, "eski": "(yok)", "yeni": f"Öneri {i}",
         "duzenleme": {"alan": "title", "deger": f"Öneri {i}"}, "kaynaklar": []} for i in range(1, 4)]}
    (tmp_path / "degisiklikler.json").write_text(json.dumps(plan), encoding="utf-8")
    sablon, anahtar = etiketle.hazirla(tmp_path / "degisiklikler.json", tmp_path / "e" / "etiket_sablonu.csv")
    metin = sablon.read_text(encoding="utf-8-sig")
    assert "yonetici" not in metin and "kosul" not in metin.split("\n")[0]     # kor: kosul sablonda yok
    a, b = (tmp_path / "e" / "etiket_A.csv"), (tmp_path / "e" / "etiket_B.csv")
    satirlar = metin.strip().split("\n")
    a.write_text("\n".join([satirlar[0]] + [s.replace(";;;;", ";dogru;hayir;3;") for s in satirlar[1:]]),
                 encoding="utf-8-sig")
    b.write_text("\n".join([satirlar[0]] + [s.replace(";;;;", ";dogru;hayir;3;" if i else ";yanlis;evet;2;")
                                            for i, s in enumerate(satirlar[1:])]), encoding="utf-8-sig")
    birlesik = etiketle.birlestir([a, b])
    assert sorted(r["etiket"] for r in birlesik.values()) == ["dogru", "dogru", "yanlis"]   # anlasmazlikta kotu olan
    yol = tmp_path / "kal.json"
    alanlar = etiketle.kalibre([a, b], yol=yol)
    assert alanlar["title"] == {**alanlar["title"], "n": 3, "dogru": 2} and yol.exists()


def test_gsc_csv_ve_trend_gerileme(tmp_path):
    csv_metni = ("En çok tıklanan sayfalar,Tıklamalar,Gösterimler,TO,Konum\n"
                 "https://www.ornek.test/a/,12,1.200,\"1,0%\",\"8,4\"\nhttps://ornek.test/b,1,50,2%,20\n")
    g = gsc.oku(csv_metni)
    assert g["ornek.test/a"]["gosterim"] == 1200 and g["ornek.test/a"]["konum"] == 8.4
    rapor = [{"url": "http://ornek.test/a", "sorunlar": [{"sorun": "title_yok", "ciddiyet": "yuksek"}]},
             {"url": "http://ornek.test/b", "sorunlar": [{"sorun": "x", "ciddiyet": "yuksek"}] * 3},
             {"url": "http://ornek.test/c", "sorunlar": []}]
    o = gsc.oncelik(rapor, g)
    assert [x["url"][-1] for x in o] == ["a", "b", "c"] and o[0]["oncelik_puani"] == 3600
    onceki = {"ort_sayfa_puani": 80, "yuksek_sorun": 2, "kodlar": {"title_yok": ["a"]}}
    son = {"ort_sayfa_puani": 75, "yuksek_sorun": 4, "kodlar": {"title_yok": ["a"], "noindex": ["a", "b"]}}
    u = trend.karsilastir(onceki, son)
    assert len(u) == 3 and any("noindex" in x for x in u)
    assert trend.karsilastir(son, son) == []


def test_alt_metni_geri_bildirimi_gorselle_ornek_olur(tmp_path):
    d = {"id": "D001", "uretici": "model", "bulgu": "img_alt_eksik", "url": TEMEL, "eski": '<img src="/g/kovan-1.jpg">',
         "duzenleme": {"alan": "img_alt", "deger": "Arı kovanı"}, "durum": "oneriliyor"}
    plan = {"tarama": {"zaman": "s"}, "hedef": {"temel_url": "http://a.test/"}, "degisiklikler": [d]}
    geri_bildirim.kaydet(plan, {"kararlar": {"D001": {"karar": "onay"}}}, tmp_path)
    o = ogretme.geri_bildirim_ornekleri(tmp_path, "http://b.test/")[0]
    assert o["girdi"]["alt_metni_eksik_gorseller"][0]["dosya_adi"] == "kovan-1.jpg"
    assert o["cikti"]["fixes"][0] == {"alan": "img_alt", "hedef": "g1", "yeni_deger": "Arı kovanı",
                                      "gerekce": "kullanıcı onayladı"}


def test_deney_cok_siteli_sonuclari_birlestirir(tmp_path):
    import deney
    for site, cozum in (("a.test", (1.0, 0.0)), ("b.test", (1.0, 0.0)), ("c.test", (1.0, 1.0))):
        for kosul, oran in zip(("ornek_bilgi", "sifir"), cozum):
            k = tmp_path / site / "sonuc_1" / f"m__{kosul}__r1"
            k.mkdir(parents=True)
            (k / "rapor.json").write_text(json.dumps([{"ad": "http://" + site + "/", "model": "m", "cozum_orani": oran,
                                                       "toplam_cozum_orani": oran, "fixes": []}]), encoding="utf-8")
    hedef, satirlar, farklar = deney.birlesik_ozet(tmp_path, "sonuc_1")
    assert {x["kosul"]: x["sayfa"] for x in satirlar} == {"ornek+bilgi": 3, "sifir": 3}
    f = next(x for x in farklar if x["metrik"] == "cozum_orani")
    assert f["n"] == 3 and abs(f["fark"] + 2 / 3) < 1e-3 and (hedef / "kosul_farklari.csv").exists()


def test_deney_devam_biten_sayfalari_atlar(monkeypatch, tmp_path):
    import deney
    cagrilar = []

    def sahte_topluca(hedefler, ayarlar, ogretme, kok, alt_yol, gunluk=None):
        cagrilar.append((ayarlar["kosul"], [h["url"] for h in hedefler]))
        for h in hedefler:
            k = Path(kok) / deney.site_adi(h["url"]) / alt_yol
            k.mkdir(parents=True, exist_ok=True)
            (k / "rapor.json").write_text(json.dumps([{"ad": h["url"], "model": "m", "cozum_orani": 1.0}]),
                                          encoding="utf-8")
    monkeypatch.setattr(deney, "topluca_analiz", sahte_topluca)
    hedefler = [{"url": "https://a.test/"}, {"url": "https://b.test/"}]
    sahte_topluca(hedefler[:1], {"kosul": "sifir"}, None, tmp_path, "z/m__sifir__r1")   # yarida kalan deney
    cagrilar.clear()
    satirlar = deney.deney_calistir(hedefler, ["m"], ["sifir", "ornek+bilgi"], [1], {}, tmp_path, "z", None,
                                    gunluk=lambda m: None, devam=True)
    assert cagrilar == [("sifir", ["https://b.test/"]), ("ornek+bilgi", ["https://a.test/", "https://b.test/"])]
    assert all(len(v) == 2 for v in satirlar.values())                 # her site iki kombinasyonla ozetlendi
