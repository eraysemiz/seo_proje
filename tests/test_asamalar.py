"""Yonetici modu asamalari: otomatik uygulama, onayli asama, geri cekme, bulgu durumlari, asama metrikleri
ve tum asamalari kapsayan geri alma. Ag ve dil modeli kullanilmaz; yeniden taramalar elle yazilan
rapor.json dosyalariyla benzetilir."""
import json

import pytest

from seo_app import duzeltme as dz
from seo_app import yonetici
from seo_app.yazma import YerelDosyaAdaptoru

TEMEL = "http://site.test/"
SAYFA = ('<!DOCTYPE html>\n<html>\n<head>\n<title>Çay Demleme Rehberi ve Öneriler | Örnek</title>\n'
         '<meta name="robots" content="noindex, follow">\n</head>\n<body>\n<main>\n<h1>Çay demleme</h1>\n'
         '<p>Demlik ısıtılır, çay 185 TL değerindeki pakettendir.</p>\n<h1>Servis</h1>\n</main>\n</body>\n</html>\n')
KODLAR = ("html_lang_yok", "viewport_yok", "h1_birden_fazla", "noindex", "https_yok")
ESIK = 0.9   # kurallar (0.95) otomatik; noindex kaldirma (sezgisel 0.82) onay ister


def _kayit(kodlar, puan=60):
    return {"ad": TEMEL, "site_url": TEMEL, "durum_kodu": 200, "once_puanlar": {"sayfa": puan, "site": 50},
            "sonra_puanlar": {"sayfa": puan, "site": 50},
            "sorunlar": [{"sorun": k, "katman": "site" if k == "https_yok" else "sayfa"} for k in kodlar]}


@pytest.fixture
def ortam(tmp_path):
    kok = tmp_path / "site"
    kok.mkdir()
    (kok / "index.html").write_text(SAYFA, encoding="utf-8")
    a = YerelDosyaAdaptoru(kok)
    plan = dz.plan_uret([_kayit(KODLAR)], [], a, TEMEL, esik=ESIK)
    klasor = tmp_path / "sonuclar" / "site.test" / "sonuc_1"
    klasor.mkdir(parents=True)
    plan["tarama"] = {"hedefler": [{"url": TEMEL}], "ayarlar": {}, "ogretme_klasoru": "", "zaman": "sonuc_1"}
    (klasor / "rapor.json").write_text(json.dumps([_kayit(KODLAR + ("charset_yok",))]), encoding="utf-8")
    (klasor / "degisiklikler.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return {"a": a, "plan": plan, "klasor": klasor, "sonuc": tmp_path / "sonuclar", "ilk": a.hashler()}


def _bul(plan, bulgu):
    return next(d for d in plan["degisiklikler"] if d["bulgu"] == bulgu)


def _otomatik(o):
    return yonetici.asama_uygula(o["klasor"], o["plan"], {}, "otomatik", o["sonuc"], tekrar_tara=False)


def _tarama_yaz(klasor, alt, kodlar, puan):
    (klasor / alt).mkdir()
    (klasor / alt / "rapor.json").write_text(json.dumps([_kayit(kodlar, puan)]), encoding="utf-8")


def test_otomatik_asama_onaysiz_yazar_ve_esik_altini_bekletir(ortam):
    kayit, _ = _otomatik(ortam)
    metin = ortam["a"].oku("index.html").decode("utf-8")
    assert '<html lang="tr">' in metin and '<meta charset="utf-8">' in metin and "<h2>Servis</h2>" in metin
    assert "noindex" in metin                                   # guven 0.82 < 0.9: onay bekler
    plan = ortam["plan"]
    assert _bul(plan, "html_lang_yok")["durum"] == "uygulandi" and _bul(plan, "html_lang_yok")["asama"] == "otomatik"
    assert _bul(plan, "html_lang_yok")["onay_kaynagi"] == "otomatik"
    assert _bul(plan, "noindex")["durum"] == "onay_bekliyor"
    assert kayit["yeni_uygulanan"] == 4 and (ortam["klasor"] / "yedek" / "manifest.json").exists()
    gunluk = [json.loads(s) for s in (ortam["klasor"] / "uygulama_gunlugu.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {s["asama"] for s in gunluk} == {"otomatik"}
    assert (ortam["klasor"] / "uygulanan.diff").read_text(encoding="utf-8").startswith("# ===== Aşama: Otomatik")
    u = json.loads((ortam["klasor"] / "uygulama.json").read_text(encoding="utf-8"))
    assert [a["ad"] for a in u["asamalar"]] == ["otomatik"] and u["onay_kaynaklari"]["otomatik"] == 4


def test_zorunlu_onay_ve_yer_tutucu_otomatik_yazilmaz(ortam):
    d = _bul(ortam["plan"], "html_lang_yok")
    d["zorunlu_onay"] = "indekslemeyi kapatan bir yönerge ekleniyor"
    v = _bul(ortam["plan"], "viewport_yok")
    v["yer_tutucu"] = True
    _otomatik(ortam)
    metin = ortam["a"].oku("index.html").decode("utf-8")
    assert '<html lang="tr">' not in metin and "viewport" not in metin
    assert d["durum"] == "onay_bekliyor" and "indekslemeyi kapatan" in d["durum_nedeni"]
    assert v["durum"] == "onay_bekliyor"


def test_toplu_kural_onayi_zorunlu_onayli_degisikligi_kapsamaz():
    zorunlu = {"id": "D001", "kategori": "kural", "risk": "dusuk", "durum": "oneriliyor", "guven": 0.95,
               "dogrulama": {"gecti": True}, "zorunlu_onay": "indekslemeyi kapatan bir yönerge ekleniyor"}
    serbest = dict(zorunlu, id="D002", zorunlu_onay=None, guven=0.5)
    plan = {"degisiklikler": [zorunlu, serbest], "esik": ESIK}
    onaylanan, _ = dz.kararlari_coz(plan, {"kural_hepsi": True, "kararlar": {}})
    assert [d["id"] for d in onaylanan] == ["D002"] and serbest["onay_kaynagi"] == "toplu"
    assert zorunlu["durum"] == "onay_bekliyor" and "indekslemeyi kapatan" in zorunlu["durum_nedeni"]
    zorunlu["durum"] = "oneriliyor"
    onaylanan, _ = dz.kararlari_coz(plan, {"kural_hepsi": True, "kararlar": {"D001": {"karar": "onay"}}})
    assert {d["id"] for d in onaylanan} == {"D001", "D002"} and zorunlu["onay_kaynagi"] == "kullanıcı"


def test_otomatik_asamada_belgeyi_bozan_degisiklik_basarisiz(ortam):
    d = _bul(ortam["plan"], "html_lang_yok")
    metin = ortam["a"].oku("index.html").decode("utf-8")
    bas = metin.index("</main>")
    d["parcalar"] = [{"bas": bas, "son": bas + len("</main>"), "eski": "</main>", "yeni": ""}]
    _otomatik(ortam)
    assert d["durum"] == "basarisiz" and "HTML yapısı" in d["durum_nedeni"]
    assert "</main>" in ortam["a"].oku("index.html").decode("utf-8")


def test_onayli_asama_otomatigin_ustune_yazar_ve_reddedileni_geri_ceker(ortam):
    _otomatik(ortam)
    plan = ortam["plan"]
    noindex, h1 = _bul(plan, "noindex")["id"], _bul(plan, "h1_birden_fazla")["id"]
    kararlar = {"kararlar": {noindex: {"karar": "onay", "risk_onay": True}, h1: {"karar": "ret"}}}
    kayit, _ = yonetici.asama_uygula(ortam["klasor"], plan, kararlar, "onayli", ortam["sonuc"], tekrar_tara=False)
    metin = ortam["a"].oku("index.html").decode("utf-8")
    assert 'content="index, follow"' in metin                  # onayli asamada yeni yazildi
    assert '<html lang="tr">' in metin                          # otomatik asamadaki yerinde kaldi
    assert "<h1>Servis</h1>" in metin and "<h2>Servis</h2>" not in metin   # reddedilen geri cekildi
    assert _bul(plan, "noindex")["asama"] == "onayli" and _bul(plan, "noindex")["onay_kaynagi"] == "kullanıcı"
    assert _bul(plan, "h1_birden_fazla")["durum"] == "reddedildi"
    assert "geri çekildi" in _bul(plan, "h1_birden_fazla")["durum_nedeni"]
    assert kayit["yeni_uygulanan"] == 1 and kayit["geri_cekilen"] == 1
    diff = (ortam["klasor"] / "uygulanan.diff").read_text(encoding="utf-8")
    assert "# ===== Aşama: Otomatik" in diff and "# ===== Aşama: Onaylı" in diff


def test_asamalar_arasinda_elle_degisen_dosyaya_yazilmaz(ortam):
    _otomatik(ortam)
    a = ortam["a"]
    a.yaz("index.html", a.oku("index.html").replace("Servis".encode(), "Sunum".encode()))
    plan = ortam["plan"]
    noindex = _bul(plan, "noindex")["id"]
    yonetici.asama_uygula(ortam["klasor"], plan, {"kararlar": {noindex: {"karar": "onay", "risk_onay": True}}},
                          "onayli", ortam["sonuc"], tekrar_tara=False)
    assert _bul(plan, "noindex")["durum"] == "basarisiz" and "elle değişmiş" in _bul(plan, "noindex")["durum_nedeni"]
    assert "Sunum" in a.oku("index.html").decode("utf-8")


def test_onayli_asama_bir_kez_yapilir(ortam):
    _otomatik(ortam)
    yonetici.uygula_ve_dogrula(ortam["klasor"], {}, ortam["sonuc"], tekrar_tara=False)
    with pytest.raises(yonetici.YoneticiHatasi):
        yonetici.uygula_ve_dogrula(ortam["klasor"], {}, ortam["sonuc"], tekrar_tara=False)


def test_bulgu_durumlari_yeniden_taramaya_dayanir(ortam):
    _otomatik(ortam)
    k, plan = ortam["klasor"], ortam["plan"]
    # otomatik asamadan sonra: lang ve charset giderildi; viewport duzeltmesi uygulandi ama hala bulunuyor
    _tarama_yaz(k, "sonra_otomatik", ("viewport_yok", "h1_birden_fazla", "noindex", "https_yok"), 75)
    plan["asamalar"][-1]["tarama"] = "sonra_otomatik"
    noindex, h1 = _bul(plan, "noindex")["id"], _bul(plan, "h1_birden_fazla")["id"]
    yonetici.asama_uygula(k, plan, {"kararlar": {noindex: {"karar": "onay", "risk_onay": True}, h1: {"karar": "ret"}}},
                          "onayli", ortam["sonuc"], tekrar_tara=False)
    _tarama_yaz(k, "sonra", ("viewport_yok", "h1_birden_fazla", "https_yok"), 85)
    plan["asamalar"][-1]["tarama"] = "sonra"
    r = yonetici.rapor_uret(k, plan)
    d = {b["sorun"]: b for b in r["bulgu_durumlari"]}
    assert d["html_lang_yok"]["durum"] == "cozuldu_otomatik"
    assert d["charset_yok"]["durum"] == "cozuldu_otomatik"
    assert d["noindex"]["durum"] == "cozuldu_onayli"
    assert d["viewport_yok"]["durum"] == "basarisiz" and "etkisiz" in d["viewport_yok"]["neden"]
    assert d["h1_birden_fazla"]["durum"] == "reddedildi"
    assert d["https_yok"]["durum"] == "elle"
    a0, a1, a2 = r["asamalar"]
    assert [a["ad"] for a in r["asamalar"]] == ["baslangic", "otomatik", "onayli"]
    assert (a0["puanlar"]["sayfa"], a1["puanlar"]["sayfa"], a2["puanlar"]["sayfa"]) == (60, 75, 85)
    # cozulebilir: duzeltme onerisi olan 5 bulgu (https_yok elle); cozum orani = cozulen / cozulebilir
    assert (a0["cozulen"], a1["cozulen"], a2["cozulen"]) == (0, 2, 3)
    assert a2["cozulebilir"] == 5 and a2["cozum_orani"] == 0.6 and a2["elle"] == 1
    assert r["bulgu_sayilari"]["cozuldu_otomatik"] == 2 and r["bulgu_sayilari"]["basarisiz"] == 1
    html = (k / "yonetici_raporu.html").read_text(encoding="utf-8")
    assert "Otomatik düzeltmeler sonrası" in html and "Onaylı düzeltmeler sonrası" in html and "Çözüm oranı" in html


def test_yeniden_tarama_yoksa_cozuldu_denmez(ortam):
    _otomatik(ortam)                                            # tekrar_tara=False: olcum yok
    r = yonetici.rapor_uret(ortam["klasor"], ortam["plan"])
    d = {b["sorun"]: b["durum"] for b in r["bulgu_durumlari"]}
    assert d["html_lang_yok"] == "dogrulanmadi" and not any(x.startswith("cozuldu") for x in d.values())
    assert r["asamalar"][1]["olculdu"] is False


def test_geri_alma_tum_asamalari_ve_durumlari_geri_dondurur(ortam):
    _otomatik(ortam)
    k, plan = ortam["klasor"], ortam["plan"]
    _tarama_yaz(k, "sonra_otomatik", ("noindex", "https_yok"), 80)
    plan["asamalar"][-1]["tarama"] = "sonra_otomatik"
    (k / "degisiklikler.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    noindex = _bul(plan, "noindex")["id"]
    yonetici.uygula_ve_dogrula(k, {"kararlar": {noindex: {"karar": "onay", "risk_onay": True}}}, ortam["sonuc"],
                               tekrar_tara=False)
    assert ortam["a"].hashler() != ortam["ilk"]
    sonuc = yonetici.geri_al(k.parent)
    assert sonuc["eslesiyor"] and ortam["a"].hashler() == ortam["ilk"]
    plan = json.loads((k / "degisiklikler.json").read_text(encoding="utf-8"))
    assert not any(d["durum"] == "uygulandi" for d in plan["degisiklikler"]) and plan["geri_alindi"]["eslesiyor"]
    r = json.loads((k / "yonetici_raporu.json").read_text(encoding="utf-8"))
    durumlar = {b["durum"] for b in r["bulgu_durumlari"]}
    assert durumlar <= {"onay_bekliyor", "elle"}                 # baslangictaki gibi
    geri = r["asamalar"][-1]
    assert geri["ad"] == "geri_alma" and geri["cozulen"] == 0 and geri["puanlar"] == r["asamalar"][0]["puanlar"]
    assert r["asamalar"][1]["cozulen"] > 0                       # gecmis asamanin olcumu korunur
    with pytest.raises(yonetici.YoneticiHatasi):
        yonetici.uygula_ve_dogrula(k, {}, ortam["sonuc"], tekrar_tara=False)


def test_yonetici_analiz_raporu_durumlari_gosterir(ortam, tmp_path):
    k = ortam["klasor"]
    (k / "site_ozeti.json").write_text("[]", encoding="utf-8")
    (k / "site_geneli.json").write_text("[]", encoding="utf-8")
    _otomatik(ortam)
    html = (k / "rapor.html").read_text(encoding="utf-8")
    assert "Yönetici modu: aşamalara göre metrikler" in html and "Uygulandı, yeniden kontrol yapılmadı" in html


def test_standart_mod_raporu_yonetici_bolumu_icermez():
    from seo_app.rapor import html_rapor
    html = html_rapor([_kayit(("title_yok",))], [])
    assert "aşamalara göre" not in html and "Çözüm oranı ⓘ" not in html


def test_masaustu_plan_yardimcilari_uygulanmislari_ayri_sayar(ortam):
    from masaustu import plan as pl
    from masaustu import sonuclar as sn
    _otomatik(ortam)
    plan = ortam["plan"]
    noindex, lang = _bul(plan, "noindex")["id"], _bul(plan, "html_lang_yok")["id"]
    kararlar = {"kural_hepsi": False, "kararlar": {noindex: {"karar": "onay", "risk_onay": True},
                                                   lang: {"karar": "ret"}}}
    assert pl.onaylanan_sayisi(plan, kararlar) == 1 and pl.geri_cekilecek_sayisi(plan, kararlar) == 1
    assert not pl.kilitli_mi(plan) and pl.durum_metni(_bul(plan, "html_lang_yok")) == "Uygulandı (otomatik)"
    assert sn.klasor_bilgisi(ortam["klasor"])["durum"] == "otomatik uygulandı"
    satirlar = pl.ozet_satirlari(pl.rapor_ozeti(ortam["klasor"]))
    assert satirlar[0].startswith("Başlangıç") and satirlar[-1].startswith("Sorun durumları")
    yonetici.uygula_ve_dogrula(ortam["klasor"], kararlar, ortam["sonuc"], tekrar_tara=False)
    plan = json.loads((ortam["klasor"] / "degisiklikler.json").read_text(encoding="utf-8"))
    assert pl.kilitli_mi(plan) and sn.klasor_bilgisi(ortam["klasor"])["durum"] == "uygulandı"


def test_web_plan_ucu_asama_ozetini_ve_durumlari_dondurur(ortam):
    from seo_app import web
    _otomatik(ortam)
    web.DURUM.update({"calisiyor": False, "mod": "yonetici",
                      "yonetici": {"asama": "plan_hazir", "klasor": str(ortam["klasor"])}})
    try:
        d = web.uygulama.test_client().get("/api/yonetici/plan").get_json()
    finally:
        web.DURUM.update({"mod": "standart", "yonetici": None})
    assert d["sayilar"]["uygulandi"] == 4 and d["sayilar"]["otomatik_uygulandi"] == 4 and d["asamalar"] == ["otomatik"]
    assert [a["ad"] for a in d["ozet"]["asamalar"]] == ["baslangic", "otomatik"]
    assert d["ozet"]["durumlar"]["html_lang_yok|" + TEMEL]["durum"] == "dogrulanmadi"
