"""Ogrenme dongusu: yonetici modunda kullanicinin model onerileri hakkindaki kararlari.

Onayli asamadan sonra her model onerisi (title, meta, H1, alt metni, JSON-LD, paragraf) icin bir satir
ogretme/geri_bildirim.jsonl dosyasina eklenir:
  karar "onay"     : oneri oldugu gibi onaylandi
  karar "duzenle"  : kullanici degeri degistirip onayladi (son_deger kullanicinin yazdigi)
  karar "ret"      : reddedildi; ret_nedeni varsa birlikte
  karar "otomatik" : esigi gecip kullanici gormeden uygulandi ve reddedilmedi (kalibrasyonda sayilmaz)
Bu kayitlar iki yerde kullanilir:
  - few-shot: onaylanan/duzenlenen oneriler baska sitelerin sayfalarina ornek olur (ogretme.geri_bildirim_ornekleri)
  - kalibrasyon: alan basina olculmus dogruluk (kalibrasyon.py; etiketle.py kalibre)
Ince ayar (fine-tuning) yapilmaz; ogrenme istem ve guven tabani uzerindendir.
"""
import json
import re
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

DOSYA = "geri_bildirim.jsonl"
RET_NEDENLERI = ("uydurma bilgi", "yanlış konu", "dil/üslup", "uzunluk", "marka/biçim", "gereksiz değişiklik", "diğer")


def _alan(d):
    return (d.get("duzenleme") or {}).get("alan")


def _sayfa_bilgisi(rapor, url):
    k = next((x for x in rapor if x.get("url") == url or x.get("ad") == url), None) or {}
    return {"title": k.get("title"), "meta_description": k.get("meta_description"), "h1": k.get("h1") or []}


SRC = re.compile(r"""src\s*=\s*["']([^"']+)""", re.I)


def _gorsel(d):
    """Alt metni onerisinin gorseli (few-shot orneginde gorunsun diye): dosya adi ve mevcut alt."""
    metinler = [d.get("eski") or ""] + [p.get("eski") or "" for p in d.get("parcalar") or []]
    src = next((m.group(1) for t in metinler for m in [SRC.search(t)] if m), "")
    g = {"id": "g1", "dosya_adi": PurePosixPath(urlsplit(src).path).name if src else "", "baglam": ""}
    if d.get("bulgu") == "alt_metni_anlamsiz" and d.get("eski") and "<" not in d["eski"]:
        g["mevcut_alt"] = d["eski"]
    return g


def kayitlar(plan, kararlar, rapor=()):
    """Plan ve kararlardan geri bildirim kayitlari (yazmadan)."""
    tek = (kararlar or {}).get("kararlar") or {}
    plan_kimligi = (plan.get("tarama") or {}).get("zaman") or plan.get("zaman") or ""
    sonuc = []
    for d in plan.get("degisiklikler", []):
        if d.get("uretici") != "model" or not _alan(d):
            continue
        k = tek.get(d["id"]) or {}
        onerilen = (d.get("duzenleme") or {}).get("deger", d.get("yeni"))
        if k.get("karar") == "ret":
            karar, son = "ret", None
        elif k.get("karar") == "onay" and k.get("deger") is not None and k["deger"] != onerilen:
            karar, son = "duzenle", k["deger"]
        elif k.get("karar") == "onay":
            karar, son = "onay", onerilen
        elif d.get("durum") == "uygulandi" and d.get("onay_kaynagi") == "otomatik":
            karar, son = "otomatik", onerilen
        else:
            continue
        sayfa = _sayfa_bilgisi(rapor, d.get("url"))
        if _alan(d) == "img_alt":
            sayfa["gorsel"] = _gorsel(d)
        sonuc.append({"zaman": time.strftime("%Y-%m-%d %H:%M:%S"), "plan": plan_kimligi, "degisiklik": d["id"],
                      "site": (plan.get("hedef") or {}).get("temel_url") or d.get("url"), "url": d.get("url"),
                      "bulgu": d["bulgu"], "alan": _alan(d), "eski": d.get("eski"), "onerilen": onerilen,
                      "son_deger": son, "karar": karar, "ret_nedeni": k.get("neden") if karar == "ret" else None,
                      "guven": d.get("guven"), "kaynaklar": [x.get("id") for x in d.get("kaynaklar") or []
                                                             if isinstance(x, dict)],
                      "sayfa": sayfa})
    return sonuc


def kaydet(plan, kararlar, ogretme_klasoru, rapor=()):
    """Kayitlari ogretme klasorundeki dosyaya ekler; ayni plan + degisiklik ikinci kez yazilmaz.
    Yazilan kayit sayisini dondurur. ogretme_klasoru bos ise hicbir sey yazilmaz."""
    if not ogretme_klasoru:
        return 0
    yol = Path(ogretme_klasoru) / DOSYA
    gorulen = set()
    if yol.exists():
        for satir in yol.read_text(encoding="utf-8").splitlines():
            try:
                g = json.loads(satir)
            except ValueError:
                continue
            gorulen.add((g.get("plan"), g.get("site"), g.get("degisiklik")))
    yeni = [g for g in kayitlar(plan, kararlar, rapor) if (g["plan"], g["site"], g["degisiklik"]) not in gorulen]
    if yeni:
        with yol.open("a", encoding="utf-8") as f:
            for g in yeni:
                f.write(json.dumps(g, ensure_ascii=False) + "\n")
    return len(yeni)


def oku(ogretme_klasoru):
    yol = Path(ogretme_klasoru) / DOSYA
    if not yol.exists():
        return []
    sonuc = []
    for satir in yol.read_text(encoding="utf-8").splitlines():
        try:
            sonuc.append(json.loads(satir))
        except ValueError:
            continue
    return sonuc


def ret_ozeti(kayitlar_):
    """En sik ret nedenleri ve alanlari: hangi dogrulama kuralinin eksik oldugunu gormek icin."""
    sayac = {}
    for g in kayitlar_:
        if g.get("karar") == "ret":
            anahtar = (g.get("alan"), g.get("ret_nedeni") or "belirtilmedi")
            sayac[anahtar] = sayac.get(anahtar, 0) + 1
    return [{"alan": a, "neden": n, "sayi": s} for (a, n), s in sorted(sayac.items(), key=lambda x: -x[1])]
