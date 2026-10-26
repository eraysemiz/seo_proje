"""Google SEO Baslangic Rehberi'ne gore eklenen denetimler, duzelticiler, onem degisiklikleri, getirme
eslemesi ve bilgi tabani/ornek bankasi bicimi. Ag ve dil modeli kullanilmaz; ornekler kurgusaldir."""
import json
import re

from conftest import KOK

from seo_app import duzeltme as dz
from seo_app import guven, ogretme, puanlama
from seo_app.cikarma import anlamsiz_alt_mi, extract, yapisal_veri
from seo_app.kurallar import DUZELTME, aciklayici_olmayan_adres, cozum_yolu, ek_html_denetimi, rule_checks
from seo_app.yazma import YerelDosyaAdaptoru

TEMEL = "http://ornek.test/"
REHBER = "https://developers.google.com/search/docs/fundamentals/seo-starter-guide"


def _sayfa(govde="", head=""):
    return (f'<!DOCTYPE html>\n<html lang="tr">\n<head>\n<meta charset="utf-8">\n<title>Kırtasiye ürünleri ve defterler</title>\n'
            f'{head}</head>\n<body>\n<main>\n<h1>Defterler</h1>\n{govde}\n</main>\n</body>\n</html>\n')


def _ek_kodlar(html, url=TEMEL):
    return {i["sorun"]: i for i in ek_html_denetimi(yapisal_veri(html, url), url)}


def _temel_kodlar(html):
    return {i["sorun"]: i for i in rule_checks(extract(html))}


# ------------------------------------------------------------------ tespit
def test_aciklayici_olmayan_adres_kimligi_bulur_anahtar_kelime_istemez():
    for url in ("http://x.test/u/8f3a2c91e7d04b", "http://x.test/urun/993817", "http://x.test/?id=42",
                "http://x.test/index.php?p=17", "http://x.test/k/0b9c2e1a-7d4f-4c3e-9a1b-2f6d8e0c4a17"):
        assert aciklayici_olmayan_adres(url), url
    for url in ("http://x.test/", "http://x.test/blog/2024/05/kompost-yapimi", "http://x.test/defterler/a4.html",
                "http://x.test/urunler/?sirala=fiyat", "http://x.test/hakkimizda", "http://x.test/2024/"):
        assert aciklayici_olmayan_adres(url) is None, url
    assert "url_aciklayici_degil" in _ek_kodlar(_sayfa(), "http://x.test/u/8f3a2c91e7d04b")
    assert "url_aciklayici_degil" not in _ek_kodlar(_sayfa(), "http://x.test/defterler/spiralli-a4")


def test_anlamsiz_alt_metni_dosya_adi_ve_genel_sozcuk():
    assert anlamsiz_alt_mi("IMG_2041.jpg") and anlamsiz_alt_mi("resim") and anlamsiz_alt_mi("DSC00317")
    assert anlamsiz_alt_mi("kapak", "/img/kapak") and anlamsiz_alt_mi("Görsel")
    assert not anlamsiz_alt_mi("") and not anlamsiz_alt_mi(None) and not anlamsiz_alt_mi("Kırmızı spiralli defter")
    html = _sayfa('<img src="/a/IMG_2041.jpg" alt="IMG_2041.jpg"><img src="/a/b.png" alt="resim">'
                  '<img src="/a/c.png" alt=""><img src="/a/d.png" alt="Kareli defter">')
    d = extract(html)
    assert [g["sira"] for g in d["img_anlamsiz_alt"]] == [0, 1]
    k = _temel_kodlar(html)
    assert "2 görsel" in k["alt_metni_anlamsiz"]["ayrinti"] and "img_alt_eksik" not in k
    assert cozum_yolu("alt_metni_anlamsiz") == "model"           # model alt metnini yeniden yazar


def test_kullanici_bolumundeki_isaretsiz_dis_baglanti():
    html = _sayfa('<div class="yorumlar"><p>Güzel <a href="https://indirim.example/k">kod</a> '
                  '<a href="https://iyi.example/" rel="ugc">iyi</a> <a href="/defterler/">iç</a></p></div>'
                  '<p><a href="https://kaynak.example/">kaynak</a></p>')
    k = _ek_kodlar(html)
    assert "1 bağlantı" in k["kullanici_baglantisi_isaretsiz"]["ayrinti"]
    assert "indirim.example" in k["kullanici_baglantisi_isaretsiz"]["ayrinti"]
    assert "kullanici_baglantisi_isaretsiz" not in _ek_kodlar(_sayfa('<p><a href="https://kaynak.example/">k</a></p>'))


def test_uzun_metin_ara_baslik_ister():
    uzun = "<p>" + " ".join(["kompost"] * 720) + "</p>"
    assert "uzun_metin_ara_baslik_yok" in _temel_kodlar(_sayfa(uzun))
    assert "uzun_metin_ara_baslik_yok" not in _temel_kodlar(_sayfa("<h2>Malzemeler</h2>" + uzun))
    assert "uzun_metin_ara_baslik_yok" not in _temel_kodlar(_sayfa("<p>" + " ".join(["kompost"] * 400) + "</p>"))


def test_basliksiz_video():
    k = _ek_kodlar(_sayfa('<iframe src="https://www.youtube.com/embed/x7Q2"></iframe><video src="/v.mp4"></video>'))
    assert "2 video" in k["video_baslik_yok"]["ayrinti"]
    assert "video_baslik_yok" not in _ek_kodlar(_sayfa('<iframe src="https://www.youtube.com/embed/x" title="Zincir yağlama"></iframe>'
                                                      '<iframe src="https://maps.example/embed"></iframe>'))


# ------------------------------------------------------------------ rehberle celisen davranislarin duzeltilmesi
def test_rehbere_gore_onem_degisiklikleri():
    k = _temel_kodlar(_sayfa("<h1>İkinci</h1>"))
    assert k["h1_birden_fazla"]["ciddiyet"] == "dusuk"            # Google icin baslik sayisi belirleyici degil
    assert guven.KURAL_GUVENI["h1_birden_fazla"] < guven.ESIK      # otomatik uygulanmaz
    assert "300+" not in DUZELTME["icerik_az"] and "hedef değil" in DUZELTME["icerik_az"]
    assert "erişilebilirlik" in DUZELTME["baslik_atlamasi"].lower() or "ekran okuyucu" in DUZELTME["baslik_atlamasi"].lower()
    assert "icerik_tekrar" not in puanlama.TAVAN and puanlama.TARAMA_CIDDIYETI["icerik_tekrar"] == "orta"


# ------------------------------------------------------------------ duzelticiler
class SahteYZ:
    model = "sahte"

    def __init__(self, deger):
        self.deger, self.gorevler = deger, []

    def iste(self, gorev, d, kodlar, sayfa_verisi, dil="tr"):
        self.gorevler.append((gorev, kodlar, sayfa_verisi))
        return {"deger": self.deger, "gerekce": "g", "kaynaklar": [], "kaynak_metni": ""}


def _site(tmp_path, html):
    kok = tmp_path / "site"
    kok.mkdir()
    (kok / "index.html").write_text(html, encoding="utf-8")
    return YerelDosyaAdaptoru(kok)


def _kayit(*kodlar):
    return {"ad": TEMEL, "site_url": TEMEL, "durum_kodu": 200, "sorunlar": [{"sorun": k, "katman": "sayfa"} for k in kodlar]}


def _uygula(plan, a, tmp_path):
    kararlar = {"kararlar": {d["id"]: {"karar": "onay", "risk_onay": True} for d in plan["degisiklikler"]}}
    dz.uygula(plan, kararlar, a, tmp_path / "yedek", tmp_path / "g.jsonl")
    return a.oku("index.html").decode("utf-8")


def test_kullanici_baglantisina_ugc_nofollow_eklenir_noopener_cakismaz(tmp_path):
    html = _sayfa('<section id="yorum-listesi"><a href="https://a.example/" target="_blank">a</a> '
                  '<a href="https://b.example/" rel="external">b</a></section>'
                  '<a href="https://c.example/" target="_blank">c</a>')
    a = _site(tmp_path, html)
    plan = dz.plan_uret([_kayit("kullanici_baglantisi_isaretsiz", "blank_noopener_yok")], [], a, TEMEL, esik=1.01)
    kodlar = sorted(d["bulgu"] for d in plan["degisiklikler"])
    assert kodlar == ["blank_noopener_yok", "kullanici_baglantisi_isaretsiz", "kullanici_baglantisi_isaretsiz"]
    assert {d["kategori"] for d in plan["degisiklikler"] if d["bulgu"] == "kullanici_baglantisi_isaretsiz"} == {"kural"}
    metin = _uygula(plan, a, tmp_path)
    assert '<a href="https://a.example/" target="_blank" rel="ugc nofollow noopener">' in metin
    assert '<a href="https://b.example/" rel="external ugc nofollow">' in metin
    assert '<a href="https://c.example/" target="_blank" rel="noopener">' in metin     # yorum disi: yalnizca noopener
    assert all(d["durum"] == "uygulandi" for d in plan["degisiklikler"])


def test_anlamsiz_alt_metni_mevcut_degerin_yerine_yazilir(tmp_path):
    html = _sayfa('<figure><img src="/a/IMG_2041.jpg" alt="IMG_2041.jpg" width="10"><figcaption>Kareli A4 defter</figcaption></figure>'
                  '<img src="/a/d.png" alt="Kırmızı defter">')
    a = _site(tmp_path, html)
    yz = SahteYZ("Kareli A4 defter")
    plan = dz.plan_uret([_kayit("alt_metni_anlamsiz")], [], a, TEMEL, yz=yz, esik=1.01)
    d = next(x for x in plan["degisiklikler"] if x["bulgu"] == "alt_metni_anlamsiz")
    assert d["kategori"] == "yz" and d["eski"] == "IMG_2041.jpg"
    assert yz.gorevler and "mevcut_alt" in json.dumps(yz.gorevler[0][2], ensure_ascii=False)
    metin = _uygula(plan, a, tmp_path)
    assert '<img src="/a/IMG_2041.jpg" alt="Kareli A4 defter" width="10">' in metin
    assert 'alt="Kırmızı defter"' in metin and metin.count("alt=") == 2   # anlamli alt korunur, nitelik tek


# ------------------------------------------------------------------ getirme, bilgi tabani, ornekler
def test_getirme_bilgi_alanlari_model_alanlarini_degistirmez():
    assert ogretme.beklenen_alanlar([{"sorun": "icerik_tekrar"}]) == ["canonical"]
    assert ogretme.beklenen_alanlar([{"sorun": "genel_baglanti_metni"}, {"sorun": "url_aciklayici_degil"}]) == ["url", "baglanti"]
    # Mod 2'de modele giden sorunlarin alanlari onceki gibi
    assert ogretme.beklenen_alanlar([{"sorun": "title_kisa"}, {"sorun": "img_alt_eksik"}]) == ["title", "img_alt"]


def test_rehber_parcalari_bolum_capali_iki_dilli_ve_lisansli():
    kb = json.loads((KOK / "ogretme" / "bilgi_tabani.json").read_text(encoding="utf-8"))
    rehber = [p for p in kb if p["kaynak"].startswith(REHBER + "?hl=tr#")]
    assert len(rehber) >= 20
    for p in rehber:
        capa = p["kaynak"].split("#")[1]
        assert p["kaynak_en"] == f"{REHBER}#{capa}" and p["lisans"] == "CC BY 4.0"
        assert "SEO Başlangıç Rehberi — " in p["kaynak_basligi"] and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p["erisim_tarihi"])
        assert len(p["icerik"]) <= 400                              # ozet; uzun alinti yok


def test_ornek_bankasi_rehber_etiketli_ve_test_sitesinden_bagimsiz():
    ornekler = json.loads((KOK / "ogretme" / "ornekler.json").read_text(encoding="utf-8"))
    rehber = [o for o in ornekler if (o.get("kaynak") or {}).get("etiket") == "google-starter-guide"]
    assert len(rehber) >= 5 and len(ornekler) - len(rehber) == 5       # mevcut 5 ornek yerinde
    ayri = json.loads((KOK / "ogretme" / "rehber_ornekleri.json").read_text(encoding="utf-8"))
    for o in ayri:
        assert o["kaynak"] == "google-starter-guide" and o["kaynak_url"].startswith(REHBER + "?hl=tr#")
        assert o["tavsiye"] and o["sorunlu"] and o["duzeltilmis"]
    metin = (json.dumps(rehber, ensure_ascii=False) + json.dumps(ayri, ensure_ascii=False)).lower()
    for iz in ("çaylıbahçe", "caylibahce", "127.0.0.1", "rize-filiz", "ihlamur", "semaver"):
        assert iz not in metin, iz
