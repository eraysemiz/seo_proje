"""Model cevabinin ayiklanmasi ve onerilerin dogrulanmasi testleri (ag gerektirmez)."""
from seo_app.llm import dogrula, json_ayikla

KODLAR = ["title_kisa", "meta_description_kisa", "h1_yok", "img_alt_eksik"]


def oneri(alan, deger, hedef=""):
    return {"alan": alan, "hedef": hedef, "yeni_deger": deger, "gerekce": ""}


def test_json_ayikla_dusunme_blogunu_temizler():
    metin = '<think>once dusunuyorum {"yanlis": 1}</think> {"fixes": []}'
    assert json_ayikla(metin) == {"fixes": []}


def test_json_ayikla_kapanmamis_dusunme_ve_bozuk_json():
    assert json_ayikla('<think>bitmeyen dusunme {"fixes": []}') is None
    assert json_ayikla("cevap yok") is None
    assert json_ayikla("{bozuk json") is None


def test_dogrula_gecerli_title(ornek_sayfa):
    ok, neden = dogrula(oneri("title", "Duzce Universitesi Bilgisayar Muhendisligi"), ornek_sayfa, KODLAR, set(), {})
    assert ok and neden == ""


def test_dogrula_uzunluk_ve_html(ornek_sayfa):
    assert dogrula(oneri("title", "Kisa"), ornek_sayfa, KODLAR, set(), {})[1].startswith("title_uzunluk_")
    assert dogrula(oneri("meta_description", "kisa"), ornek_sayfa, KODLAR, set(), {})[1].startswith("meta_uzunluk_")
    assert dogrula(oneri("h1", "<b>Bilgisayar Muhendisligi</b>"), ornek_sayfa, KODLAR, set(), {})[1] == "html_etiketi_iceriyor"


def test_dogrula_gecersiz_alan_ve_gereksiz_degisiklik(ornek_sayfa):
    assert dogrula(oneri("canonical", "https://x"), ornek_sayfa, KODLAR, set(), {})[1] == "gecersiz_alan"
    ok, neden = dogrula(oneri("title", "Duzce Universitesi Bilgisayar Muhendisligi"), ornek_sayfa, ["h1_yok"], set(), {})
    assert not ok and neden == "sorun_yok_gereksiz_degisiklik"


def test_dogrula_sayfada_olmayan_ifade(ornek_sayfa):
    ok, neden = dogrula(oneri("title", "Duzce Kuantum Hesaplama Uzay Madenciligi"), ornek_sayfa, KODLAR, set(), {})
    assert not ok and neden.startswith("sayfada_olmayan_ifade")


def test_dogrula_gorsel_hedefi_ve_tekrar(ornek_sayfa):
    gorsel = {"g1": "logo.png"}
    assert dogrula(oneri("img_alt", "Logo", "g9"), ornek_sayfa, KODLAR, set(), gorsel)[1] == "hedef_gorsel_listede_yok"
    assert dogrula(oneri("img_alt", "Logo", "g1"), ornek_sayfa, KODLAR, set(), gorsel)[0]
    kabul = {("img_alt", "g1")}
    assert dogrula(oneri("img_alt", "Logo", "g1"), ornek_sayfa, KODLAR, kabul, gorsel)[1] == "ayni_alan_tekrar"
