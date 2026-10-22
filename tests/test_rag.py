"""RAG hatti: bilgi tabani, sorgu, hibrit getirme, yeniden siralama, istem ve kaynak atfi.
Gomme modeli yerine kelime torbasindan uretilen belirlenimci (deterministic) vektorler kullanilir."""
import hashlib
import json
import math
import re
import shutil

import pytest
from conftest import KOK, html_yap, sahte_canli

import rag_degerlendir
from seo_app import boru, llm, ogretme
from seo_app.cikarma import extract
from seo_app.rag_olcum import ALTIN_PARCALAR, olc, sorun_isabeti

URL = "http://localhost:1234/v1"
GOMME = "text-embedding-qwen3-embedding-0.6b"
TURKCE = set("çğıİöşü")
CAGRILAR = []            # sahte gomme modeline yapilan cagrilar: (adres, metin sayisi)


def _vektor(metin, boyut=64):
    """Kelime koklerini sabit boyutlu bir torbaya dagitir; ortak kelime = yuksek benzerlik."""
    v = [0.0] * boyut
    for w in re.findall(r"\w+", metin.lower()):
        v[int(hashlib.md5(w[:5].encode()).hexdigest(), 16) % boyut] += 1.0
    return v


@pytest.fixture
def klasor(tmp_path, monkeypatch):
    """Bilgi tabaninin gecici kopyasi (onbellek gercek klasore yazilmasin) ve sahte gomme modeli."""
    hedef = tmp_path / "ogretme"
    shutil.copytree(KOK / "ogretme", hedef, ignore=shutil.ignore_patterns("bilgi_tabani_gomme_cache.json"))
    CAGRILAR.clear()

    def sahte_embed(url, model, metinler, timeout=60):
        CAGRILAR.append((url, len(metinler)))
        return [_vektor(m) for m in metinler]

    monkeypatch.setattr(ogretme, "_embed", sahte_embed)
    ogretme._KB_BELLEK.clear()
    ogretme._VEKTOR_BELLEK.clear()
    return hedef


def _sayfa(**ek):
    d = {"title": "Kısa", "site_adi": "Örnek Kurum", "icerik_ozeti": "Kurumun duyuruları ve iletişim bilgileri."}
    d.update(ek)
    return d


# ------------------------------------------------------------------ bilgi tabani
def test_bilgi_tabani_turkce_kaynakli_ve_benzersiz():
    parcalar = json.loads((KOK / "ogretme" / "bilgi_tabani.json").read_text(encoding="utf-8"))
    kimlikler = [p["id"] for p in parcalar]
    assert len(kimlikler) == len(set(kimlikler))
    for p in parcalar:
        assert p["alan"] and p["baslik"] and p["kaynak"].startswith("https://") and p["kaynak_basligi"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", p["erisim_tarihi"])
    assert TURKCE <= set("".join(p["baslik"] + p["icerik"] for p in parcalar))   # eski taban Turkce karaktersizdi
    assert set().union(*ALTIN_PARCALAR.values()) <= set(kimlikler)    # olcumun altin parcalari tabanda var


def test_bilgi_tabani_dosya_degismedikce_bellekten_gelir(klasor):
    a = ogretme.bilgi_tabani(klasor)
    assert ogretme.bilgi_tabani(klasor)[0] is a[0]
    yol = klasor / "bilgi_tabani.json"
    veri = json.loads(yol.read_text(encoding="utf-8"))
    veri[0]["icerik"] += " Ek cümle."
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    b = ogretme.bilgi_tabani(klasor)
    assert b[1] != a[1] and b[0][0]["icerik"].endswith("Ek cümle.")    # surum ozeti degisir


# ------------------------------------------------------------------ sorgu ve onekler
def test_istekler_localhost_yerine_ipv4_adresine_gider():
    assert llm.istek_adresi("http://localhost:1234/v1") == "http://127.0.0.1:1234/v1"
    assert llm.istek_adresi("http://localhost") == "http://127.0.0.1"
    assert llm.istek_adresi("http://localhostx.com/v1") == "http://localhostx.com/v1"
    assert llm.istek_adresi("http://192.168.1.5:1234/v1") == "http://192.168.1.5:1234/v1"


def test_sorgu_kodlar_yerine_turkce_aciklama_ve_icerik_ozeti_kullanir():
    s = ogretme.sorgu_olustur(_sayfa(text_sample="MENÜ MENÜ"), [{"sorun": "title_kisa"}, {"sorun": "h1_yok"}])
    assert "title_kisa" not in s and "Sayfa başlığı çok kısa" in s and "Sayfada H1 başlığı yok" in s
    assert "duyuruları" in s and "MENÜ" not in s and "Site: Örnek Kurum" in s


def test_gomme_modeline_gore_onekler():
    assert ogretme._onekler(GOMME)[0].startswith("Instruct:") and ogretme._onekler(GOMME)[1] == ""
    assert ogretme._onekler("multilingual-e5-large") == ("query: ", "passage: ")
    assert ogretme._onekler("nomic-embed-text") == ("search_query: ", "search_document: ")
    assert ogretme._onekler("bge-m3") == ("", "")


# ------------------------------------------------------------------ getirme
def test_metadata_filtresi_ve_her_alan_kapsanir(klasor):
    sorunlar = [{"sorun": "title_uzun"}, {"sorun": "meta_description_kisa"}, {"sorun": "img_alt_eksik"}]
    secili, bilgi = ogretme.bilgi_getir(_sayfa(), sorunlar, klasor, URL, GOMME, 5)
    alanlar = [p["alan"] for p in secili]
    assert {"title", "meta_description", "img_alt"} <= set(alanlar)
    assert set(alanlar) <= {"title", "meta_description", "img_alt", "genel"}    # site/canonical parcasi yok
    assert len(secili) <= 5 and bilgi["yontem"] == "hibrit" and bilgi["kb_surum"]
    assert [p["id"] for p in secili] == [p["id"] for p in bilgi["parcalar"]]
    assert all(p["kaynak"] and p["kosinus"] is not None for p in bilgi["parcalar"])
    assert not any(k.startswith("_") for p in secili for k in p)


def test_baglam_butcesi_once_dolgu_parcalarini_cikarir(klasor, monkeypatch):
    monkeypatch.setattr(ogretme, "BAGLAM_SINIRI", 700)
    sorunlar = [{"sorun": "title_kisa"}, {"sorun": "h1_yok"}]
    secili, _ = ogretme.bilgi_getir(_sayfa(), sorunlar, klasor, URL, GOMME, 6)
    assert {"title", "h1"} <= {p["alan"] for p in secili}                        # zorunlu kapsama korunur
    assert len(secili) < 6


def test_siralama_secenegi_ve_gommesiz_bm25(klasor):
    sorunlar = [{"sorun": "img_alt_eksik"}]
    _, b1 = ogretme.bilgi_getir(_sayfa(), sorunlar, klasor, URL, GOMME, 3, siralama=("vektor",))
    _, b2 = ogretme.bilgi_getir(_sayfa(), sorunlar, klasor, URL, None, 3)
    assert b1["yontem"] == "vektor" and b2["yontem"] == "bm25"
    assert all(p["kosinus"] is None for p in b2["parcalar"])


def test_bm25_ilgili_parcayi_one_alir():
    parcalar, _, bm25 = ogretme.bilgi_tabani(KOK / "ogretme")
    puan = ogretme.bm25_puanlari("bağlantı logo sosyal medya simgesi alt metin", bm25)
    en_iyi = parcalar[max(range(len(puan)), key=puan.__getitem__)]
    assert en_iyi["id"] == "g03"


def test_onbellek_model_basina_tutulur_ve_budanir(klasor):
    cache_yolu = klasor / "bilgi_tabani_gomme_cache.json"
    cache_yolu.write_text(json.dumps({"eski_duz_bicim": [1, 2]}), encoding="utf-8")
    ogretme.bilgi_getir(_sayfa(), [{"sorun": "h1_yok"}], klasor, URL, GOMME, 3)
    cache = json.loads(cache_yolu.read_text(encoding="utf-8"))
    n = len(json.loads((klasor / "bilgi_tabani.json").read_text(encoding="utf-8")))
    assert set(cache) == {"bicim", "modeller"} and len(cache["modeller"][GOMME]) == n
    # yeni surec: vektorler diskten gelir, yalnizca sorgu gomulur
    ogretme._VEKTOR_BELLEK.clear()
    CAGRILAR.clear()
    ogretme.bilgi_getir(_sayfa(), [{"sorun": "h1_yok"}], klasor, URL, GOMME, 3)
    assert [x[1] for x in CAGRILAR] == [1]
    # artik bilgi tabaninda olmayan parcanin vektoru onbellekten silinir
    yol = klasor / "bilgi_tabani.json"
    yol.write_text(json.dumps(json.loads(yol.read_text(encoding="utf-8"))[1:], ensure_ascii=False), encoding="utf-8")
    ogretme._VEKTOR_BELLEK.clear()
    ogretme.bilgi_getir(_sayfa(), [{"sorun": "h1_yok"}], klasor, URL, GOMME, 3)
    assert len(json.loads(cache_yolu.read_text(encoding="utf-8"))["modeller"][GOMME]) == n - 1


def test_yeniden_siralama_sirayi_belirler(klasor, monkeypatch):
    istekler = []

    class Yanit:
        def __init__(self, veri): self.veri = veri
        def raise_for_status(self): pass
        def json(self): return self.veri

    def sahte_post(url, json=None, timeout=None):
        istekler.append((url, json))
        # son belgeye en yuksek puan: yeniden siralama ilk siraya onu almali
        n = len(json["documents"])
        return Yanit({"results": [{"index": i, "relevance_score": i / n} for i in range(n)]})

    monkeypatch.setattr(ogretme.requests, "post", sahte_post)
    secili, bilgi = ogretme.bilgi_getir(_sayfa(), [{"sorun": "title_kisa"}], klasor, URL, GOMME, 2,
                                        rerank_url="http://localhost:8012/v1", rerank_model="bge-reranker-v2-m3")
    url, govde = istekler[-1]
    assert url == "http://127.0.0.1:8012/v1/rerank" and govde["model"] == "bge-reranker-v2-m3"
    assert bilgi["yontem"] == "hibrit+rerank"
    # en yuksek puani alan (adaylarin sonuncusu) title parcasi kapsama icin ilk secilmeli
    son_aday = [p for p in ogretme.bilgi_tabani(klasor)[0] if p["alan"] in ("title", "genel")][-1]
    assert secili[0]["id"] == son_aday["id"] and bilgi["parcalar"][0]["puan"] == max(
        p["puan"] for p in bilgi["parcalar"])


def test_yeniden_siralama_ulasilamazsa_sessizce_gecilmez(klasor, monkeypatch):
    def kapali(*a, **k):
        raise ogretme.requests.ConnectionError("kapali")
    monkeypatch.setattr(ogretme.requests, "post", kapali)
    with pytest.raises(RuntimeError, match="Yeniden sıralama modeline ulaşılamadı"):
        ogretme.bilgi_getir(_sayfa(), [{"sorun": "title_kisa"}], klasor, URL, GOMME, 2,
                            rerank_url=URL, rerank_model="bge-reranker-v2-m3")


# ------------------------------------------------------------------ istem
def test_istem_sirasi_kimlikler_ve_sikistirilmis_ornekler(klasor):
    sorunlar = [{"sorun": "h1_yok"}]
    metin, bilgi = ogretme.ogretme_metni("ornek+bilgi", _sayfa(), sorunlar, klasor, 3, URL, GOMME, bilgi_k=4)
    assert metin.index("ORNEKLER") < metin.index("SEO BILGI TABANI")       # sabit kisim once
    assert bilgi["kimlikler"] and all("[" + i + "]" in metin for i in bilgi["kimlikler"])
    ornekler = metin.split("SEO BILGI TABANI")[0]
    for satir in re.findall(r"Girdi: (\{.*\})", ornekler):
        girdi = json.loads(satir)
        assert len(girdi.get("metin_ozeti", "")) <= ogretme.ORNEK_METIN_SINIRI
        assert girdi["tespit_edilen_sorunlar"] == ["h1_yok"] or "h1_yok" not in girdi["tespit_edilen_sorunlar"]
    for satir in re.findall(r"Cikti: (\{.*\})", ornekler):
        alanlar = {f["alan"] for f in json.loads(satir)["fixes"]}
        assert alanlar == {"h1"} or "h1" not in alanlar


def test_istem_eski_bicimden_kisadir(klasor):
    """Ayni sayfa icin yeni istem eski (tam JSON ornekli) istemden kisa olmali."""
    sorunlar = [{"sorun": "title_kisa"}, {"sorun": "meta_description_yok"}, {"sorun": "h1_yok"}]
    yeni, _ = ogretme.ogretme_metni("ornek", _sayfa(), sorunlar, klasor, 3, URL, GOMME)
    # eski ogretme_metni: ayni secim (sorunlu alanlarla en cok eslesen 3 ornek), tam girdi/cikti JSON'u
    alanlar = {"title", "meta_description", "h1"}
    ornekler = json.loads((klasor / "ornekler.json").read_text(encoding="utf-8"))
    secili = sorted(ornekler, key=lambda o: -sum(1 for f in o["cikti"]["fixes"] if f["alan"] in alanlar))[:3]
    eski = ("\n\nORNEKLER (yalnizca bicim ve ton icin; icerigini KOPYALAMA, kendi sayfanin verisini kullan):\n" +
            "\n\n".join("Ornek " + str(i + 1) + "\nGirdi: " + json.dumps(o["girdi"], ensure_ascii=False) +
                        "\nCikti: " + json.dumps(o["cikti"], ensure_ascii=False) for i, o in enumerate(secili)))
    assert len(yeni) < len(eski)
    # yalnizca h1 sorunu olan sayfada sikistirma belirgin: ilgisiz alanlarin onerileri atilir
    yalniz_h1, _ = ogretme.ogretme_metni("ornek", _sayfa(), [{"sorun": "h1_yok"}], klasor, 3, URL, GOMME)
    assert len(yalniz_h1) < 0.8 * len(eski)


# ------------------------------------------------------------------ kaynak atfi
def test_oneri_kaynaklari_verilen_kimliklerle_sinirlanir(monkeypatch):
    cevap = {"fixes": [{"alan": "h1", "hedef": "", "yeni_deger": "Bilgisayar Mühendisliği",
                        "gerekce": "ana konu", "kaynaklar": ["h01", "x99", 5]}]}

    def sahte_cagri(url, payload, timeout, ilerleme=None):
        return {"icerik": json.dumps(cevap), "dusunme": "", "bitis": "stop", "sure": 0.1,
                "ilk_token_sn": 0.05, "parca": 5, "uretim_hizi": 50.0}

    monkeypatch.setattr(llm, "_cagri", sahte_cagri)
    d = extract(html_yap(h1="", title="Bilgisayar Mühendisliği Bölümü Ders Programı Sayfası"))
    sonuc = llm.llm_fixes(d, [{"sorun": "h1_yok"}], "m", "x", URL, 100, 10, False, retry=0,
                          kaynak_kimlikleri=["h01", "h03"])
    assert sonuc["fixes"][0]["kaynaklar"] == ["h01"] and sonuc["gecersiz_kaynak"] == 2


def test_modele_zenginlestirilmis_sayfa_verisi_gider(monkeypatch):
    giden = {}

    def sahte_cagri(url, payload, timeout, ilerleme=None):
        giden.update(json.loads(payload["messages"][1]["content"]))
        return {"icerik": '{"fixes": []}', "dusunme": "", "bitis": "stop", "sure": 0.1,
                "ilk_token_sn": 0.05, "parca": 1, "uretim_hizi": None}

    monkeypatch.setattr(llm, "_cagri", sahte_cagri)
    html = ('<html><head><title>Duyurular | Örnek Kurum</title></head><body><ul><li><a href="/">Menü A</a></li>'
            '<li><a href="/b">Menü B</a></li></ul><main><h3>Kayıt</h3><p>' + "Kayıt takvimi ve belgeler. " * 20 +
            "</p></main></body></html>")
    llm.llm_fixes(extract(html), [{"sorun": "h1_yok"}], "m", "x", URL, 100, 10, False, retry=0)
    assert giden["site_adi"] == "Örnek Kurum" and giden["h3"] == ["Kayıt"]
    assert giden["metin_ozeti"].startswith("Kayıt") and "Menü" not in giden["metin_ozeti"]
    assert "kaynaklar" in llm.SYSTEM and "yonergesidir, sayfa bilgisi degildir" in llm.SYSTEM


# ------------------------------------------------------------------ cikarma
@pytest.mark.parametrize("title,head,beklenen", [
    ("Erkek Giyim Modelleri | AVVA", "", "AVVA"),
    ("Düzce Üniversitesi | Anasayfa", "", "Düzce Üniversitesi"),
    ("Kütüphane", "", None),
    ("Duyurular - Kurum", '<meta property="og:site_name" content="Resmî Ad">', "Resmî Ad"),
])
def test_site_adi_yalnizca_sayfa_verisinden(title, head, beklenen):
    d = extract(f"<html><head><title>{title}</title>{head}</head><body><p>metin</p></body></html>")
    assert d["site_adi"] == beklenen


# ------------------------------------------------------------------ olcum ve kayit
def test_olcum_metrikleri():
    secili = [{"id": "t02", "alan": "title"}, {"id": "n01", "alan": "genel"}, {"id": "s01", "alan": "canonical"}]
    o = olc(secili, ["title", "h1"])
    assert o["kapsama"] == 0.5 and round(o["isabet"], 3) == 0.667 and o["mrr"] == 1.0
    assert sorun_isabeti(secili, ["title_kisa", "h1_yok"]) == 0.5
    assert sorun_isabeti([{"id": "b01", "konu": "title"}], ["title_kisa"]) is None   # eski taban


def test_degerlendirme_seti_ve_betik_calisir(klasor, monkeypatch):
    kayitlar = json.loads(rag_degerlendir.VERI.read_text(encoding="utf-8"))
    assert len(kayitlar) >= 30 and all(k["sorunlar"] for k in kayitlar)
    monkeypatch.setattr(rag_degerlendir, "KOK", klasor.parent)
    ort, satirlar = rag_degerlendir.degerlendir(URL, GOMME, 5)
    assert ort["kapsama"] == 1.0 and ort["isabet"] == 1.0 and 0 <= ort["sorun_isabeti"] <= 1
    assert len(satirlar) == len(kayitlar)


def test_rapor_getirilen_parcalari_ve_kaynak_kimliklerini_tasir(monkeypatch, tmp_path):
    sahte_canli(monkeypatch, {"https://ornek.edu.tr": html_yap(h1="")})
    gelen = {}
    parcalar = [{"id": "h01", "alan": "h1", "baslik": "b", "kaynak": "https://x", "kaynak_basligi": "k",
                 "puan": 0.1, "kosinus": 0.5}]
    monkeypatch.setattr(boru, "ogretme_metni", lambda *a, **k: (
        "", {"ornek": 0, "kural": 1, "yontem": "hibrit", "parcalar": parcalar, "kimlikler": ["h01"],
             "kb_surum": "abc", "getirme_ms": 3.0}))

    def sahte_llm(d, issues, *a, **k):
        gelen.update(k)
        return {"fixes": [], "reddedilen": [], "yok_sayilan": [], "json_gecerli": True, "sure_sn": 1.0,
                "bitis_nedeni": "stop", "dusunme_karakter": 0, "cevap_karakter": 1, "denemeler": [],
                "ham": "", "dusunme_basi": ""}

    monkeypatch.setattr(boru, "llm_fixes", sahte_llm)
    k = boru.analiz_et({"url": "ornek.edu.tr"}, {"model": "m"}, str(tmp_path))
    assert gelen["kaynak_kimlikleri"] == ["h01"]
    assert k["ogretme_parcalar"] == parcalar and k["kb_surum"] == "abc" and k["getirme_ms"] == 3.0
    assert math.isclose(boru.VARSAYILAN_AYARLAR["bilgi_sayisi"], 5)
    assert "127.0.0.1" in boru.VARSAYILAN_AYARLAR["url"]
