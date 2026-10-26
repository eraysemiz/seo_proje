"""Yonetici modu planinin (degisiklikler.json) onay ekrani icin okunmasi ve kararlarin
`yonet.py onayla` argumanlarina cevrilmesi. Kararlar yalnizca yonet.py uzerinden kaydedilir;
bu modul onaylar.json'a dogrudan yazmaz.
"""
import json
import re
from pathlib import Path

# seo_app.kategoriler.KATEGORI_ADI ve seo_app.yonetici.DURUM_ADI ile ayni; arayuz sureci seo_app'i
# ice aktarmaz (.exe icinde gomulu degildir), bu yuzden gosterim adlari burada da tutulur.
KATEGORI_ADI = {"kural": "Kural çözer", "yz": "YZ önerir", "elle": "Elle düzeltilir"}
DURUM_ADI = {"uygulandi": "Uygulandı", "reddedildi": "Reddedildi", "basarisiz": "Başarısız",
             "onay_bekliyor": "Onay verilmedi", "gecersiz": "Doğrulamadan geçmedi", "oneriliyor": "Önerildi",
             "geri_alindi": "Geri alındı"}
ASAMA_KISA = {"otomatik": "otomatik", "onayli": "onaylı"}
# seo_app.yonetici.BULGU_DURUM_ADI ile ayni
BULGU_DURUM_ADI = {"cozuldu_otomatik": "Çözüldü (otomatik)", "cozuldu_onayli": "Çözüldü (onaylı)",
                   "onay_bekliyor": "Onay bekliyor", "reddedildi": "Reddedildi", "basarisiz": "Başarısız",
                   "dogrulanmadi": "Uygulandı, yeniden kontrol yapılmadı", "elle": "Elle düzeltilir"}
_BLOK_BASI = re.compile(r"^# (D\d+) \[")


def plani_oku(klasor):
    return json.loads((Path(klasor) / "degisiklikler.json").read_text(encoding="utf-8"))


def asamalar(plan):
    return [a["ad"] for a in plan.get("asamalar") or []]


def kilitli_mi(plan):
    """Onayli asama tamamlandiysa ya da uygulama geri alindiysa kararlar degistirilemez."""
    return bool(plan.get("geri_alindi")) or "onayli" in asamalar(plan)


def durum_metni(d):
    metin = DURUM_ADI.get(d["durum"], d["durum"])
    if d["durum"] == "uygulandi" and d.get("asama"):
        metin += " (" + ASAMA_KISA.get(d["asama"], d["asama"]) + ")"
    return metin


def rapor_ozeti(klasor):
    """yonetici_raporu.json'dan asama metrikleri ve bulgu durumlari; yoksa None."""
    try:
        r = json.loads((Path(klasor) / "yonetici_raporu.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"asamalar": r.get("asamalar") or [], "sayilar": r.get("bulgu_sayilari") or {},
            "toplam": r.get("bulgu_toplam", 0), "tanim": r.get("cozum_orani_tanimi", ""),
            "geri_alindi": r.get("geri_alindi"), "sayaclar": r.get("sayaclar") or {}}


def ozet_satirlari(oz):
    """Asama metriklerinin kisa metin hali (masaustu plan alani ve gunluk icin)."""
    if not oz or not oz["asamalar"]:
        return []
    satirlar = []
    for a in oz["asamalar"]:
        if not a.get("olculdu"):
            satirlar.append(f"{a['adi']}: ölçülmedi")
            continue
        oran = "—" if a.get("cozum_orani") is None else f"%{round(100 * a['cozum_orani'])}"
        satirlar.append(f"{a['adi']}: sayfa puanı {a['puanlar']['sayfa']} · aktif {a.get('aktif', '—')} · "
                        f"çözülen {a.get('cozuldu_otomatik', '—')} otomatik + {a.get('cozuldu_onayli', '—')} onaylı · "
                        f"çözüm oranı {oran} ({a['cozulen']}/{a['cozulebilir']}) · elle {a['elle']}")
    durumlar = ", ".join(f"{BULGU_DURUM_ADI.get(d, d)} {n}" for d, n in oz["sayilar"].items() if n)
    satirlar.append(f"Sorun durumları ({oz['toplam']}): {durumlar}")
    s = oz.get("sayaclar")
    if s:
        ayrim = f" ({s['sayfa']['aktif']} sayfa sorunu + {s['site_ayari']['aktif']} site geneli ayar)" if "sayfa" in s else ""
        satirlar.append(f"Aktif {s['aktif']}{ayrim} · Çözülen {s['cozulen']} (otomatik {s['cozuldu_otomatik']}, "
                        f"onaylı {s['cozuldu_onayli']}) · toplam {s['toplam']}")
    return satirlar


def kararlari_oku(klasor):
    yol = Path(klasor) / "onaylar.json"
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        veri = {}
    return {"kural_hepsi": bool(veri.get("kural_hepsi")), "kararlar": veri.get("kararlar") or {}}


def diff_bloklari(klasor):
    """onizleme.diff'i degisiklik kimligine gore parcalar: {"D001": "...diff metni..."}."""
    yol = Path(klasor) / "onizleme.diff"
    if not yol.exists():
        return {}
    bloklar, kimlik, satirlar = {}, None, []
    for satir in yol.read_text(encoding="utf-8").splitlines():
        m = _BLOK_BASI.match(satir)
        if m or satir.startswith("####"):
            if kimlik:
                bloklar[kimlik] = "\n".join(satirlar).strip("\n")
            kimlik, satirlar = (m.group(1), [satir]) if m else (None, [])
        elif kimlik:
            satirlar.append(satir)
    if kimlik:
        bloklar[kimlik] = "\n".join(satirlar).strip("\n")
    return bloklar


def baslangic_secimleri(plan, onceki):
    """Onay ekraninin ilk durumu: daha once kaydedilmis kararlar."""
    secimler = {}
    for d in plan["degisiklikler"]:
        k = onceki["kararlar"].get(d["id"]) or {}
        secimler[d["id"]] = {"karar": k.get("karar"), "risk": bool(k.get("risk_onay")),
                             "deger": k.get("deger")}
    return secimler


def esik(plan, kararlar=None):
    e = (kararlar or {}).get("esik")
    return float(e) if e is not None else float(plan.get("esik", 0.8))


def otomatik_mi(d, esik_degeri):
    """seo_app.guven.otomatik_mi ile ayni kosul: dogrulamadan gecmis, zorunlu onay ve yer tutucu yok,
    guven esigi geciyor. Guven puani olmayan (eski) planlarda hicbir degisiklik otomatik degildir."""
    return ("guven" in d and d["dogrulama"]["gecti"] and not d.get("zorunlu_onay") and not d.get("yer_tutucu")
            and d["guven"] >= esik_degeri)


def toplu_onayli(d, kural_hepsi):
    """duzeltme.kararlari_coz ile ayni kosul: 'tumunu onayla' yalnizca zorunlu onayi olmayan kural
    duzeltmelerini kapsar."""
    return bool(kural_hepsi) and d["kategori"] == "kural" and not d.get("zorunlu_onay")


def geri_cekilecek_sayisi(plan, kararlar):
    """Otomatik asamada yazilip onay ekraninda reddedilen (onayli asamada geri cekilecek) degisiklikler."""
    return sum(1 for d in plan["degisiklikler"] if d["durum"] == "uygulandi"
               and (kararlar["kararlar"].get(d["id"]) or {}).get("karar") == "ret")


def onaylanan_sayisi(plan, kararlar):
    """Kaydedilmis kararlara gore onayli asamada yeni yazilacak degisiklik sayisi (duzeltme.kararlari_coz'un
    onay kosullari; duzenlenen degerin dogrulamasi uygulama aninda yapilir). Otomatik asamada zaten
    yazilmis olanlar sayilmaz."""
    sayi, e = 0, esik(plan, kararlar)
    for d in plan["degisiklikler"]:
        k = kararlar["kararlar"].get(d["id"]) or {}
        if d["durum"] in ("gecersiz", "uygulandi") or k.get("karar") == "ret":
            continue
        oto = otomatik_mi(d, e)
        if not (k.get("karar") == "onay" or oto or toplu_onayli(d, kararlar["kural_hepsi"])):
            continue
        if d["risk"] == "yuksek" and not k.get("risk_onay") and not oto:
            continue
        sayi += 1
    return sayi


def onay_argumanlari(plan, onceki, secimler, kural_hepsi):
    """Secimleri `yonet.py onayla <klasor>` argumanlarina cevirir. (argumanlar, uyarilar) dondurur.

    yonet.py onceki kararlarin uzerine ekler; bu yuzden ekranda geri cekilen bir onay (ya da
    kapatilan 'tumunu onayla') ret olarak gonderilir. Verilmis bir risk onayi komut satirindan geri
    alinamaz; boyle bir durumda kullanici uyarilir (oneriyi reddetmek her zaman mumkundur)."""
    onay, ret, risk, duzenle, uyarilar = [], [], [], [], []
    for d in plan["degisiklikler"]:
        if d["durum"] == "gecersiz":
            continue
        i = d["id"]
        s = secimler.get(i) or {}
        k = onceki["kararlar"].get(i) or {}
        karar = s.get("karar")
        if karar == "onay":
            onay.append(i)
            if d["risk"] == "yuksek":
                if s.get("risk"):
                    risk.append(i)
                elif k.get("risk_onay"):
                    uyarilar.append(i + ": daha önce verilen risk onayı geri alınamıyor; uygulanmasın "
                                    "istiyorsanız Ret seçin.")
            deger = s.get("deger")
            if d.get("duzenleme") and deger is not None and deger != d.get("yeni"):
                duzenle.append(i + "=" + deger)
        elif karar == "ret":
            ret.append(i)
        elif k.get("karar") == "onay":
            ret.append(i)                    # ekranda onay geri cekildi
        elif toplu_onayli(d, onceki["kural_hepsi"]) and not kural_hepsi:
            ret.append(i)                    # 'tumunu onayla' kapatildi; yonet.py bu bayragi geri almaz
    argumanlar = ["--kural-hepsi"] if kural_hepsi else []
    for bayrak, liste in (("--onay", onay), ("--ret", ret), ("--riski-kabul", risk), ("--duzenle", duzenle)):
        if liste:
            argumanlar += [bayrak, *liste]
    return argumanlar, uyarilar
