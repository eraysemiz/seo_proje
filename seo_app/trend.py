"""Bir sitenin taramalari arasindaki egilim (trend) ve gerileme uyarisi.

sonuclar/<site>/sonuc_*/rapor.json dosyalari (salt okunur ya da yonetici modu baslangic taramasi) zamana
gore siralanir; her tarama icin ortalama sayfa/site puani, toplam ve yuksek ciddiyetli sorun sayisi cikarilir.
Son iki tarama karsilastirilir: ortalama sayfa puani PUAN_DUSUSU kadar duserse, yuksek ciddiyetli sorun artarsa
ya da onceki taramada olmayan bir sorun kodu birden fazla sayfada cikarsa gerileme uyarisi verilir.
Deney klasorleri (deney.py) karsilastirmaya girmez: tek bir taramayi temsil etmezler.
"""
import html
import json
import re
from pathlib import Path

PUAN_DUSUSU = 3.0
YUKSEK = ("yuksek", "kritik")


def _ortalama(degerler):
    degerler = [x for x in degerler if isinstance(x, (int, float))]
    return round(sum(degerler) / len(degerler), 1) if degerler else None


def tarama_ozeti(klasor):
    rapor = json.loads((Path(klasor) / "rapor.json").read_text(encoding="utf-8"))
    gecerli = [k for k in rapor if not k.get("hata") and not k.get("atlandi")]
    kodlar = {}
    for k in gecerli:
        for s in k.get("sorunlar") or []:
            kodlar.setdefault(s["sorun"], set()).add(k.get("url") or k["ad"])
    return {
        "tarama": Path(klasor).name,
        "zaman": re.sub(r"^sonuc_", "", Path(klasor).name).replace("_", " ", 1),
        "sayfa": len(gecerli),
        "ort_sayfa_puani": _ortalama([(k.get("once_puanlar") or {}).get("sayfa") for k in gecerli]),
        "ort_site_puani": _ortalama([(k.get("once_puanlar") or {}).get("site") for k in gecerli]),
        "toplam_sorun": sum(len(k.get("sorunlar") or []) for k in gecerli),
        "yuksek_sorun": sum(1 for k in gecerli for s in k.get("sorunlar") or [] if s.get("ciddiyet") in YUKSEK),
        "kodlar": {kod: sorted(s) for kod, s in kodlar.items()},
    }


def taramalar(site_klasoru):
    """Zamana gore sirali tarama ozetleri (eskiden yeniye)."""
    return [tarama_ozeti(k) for k in sorted(Path(site_klasoru).glob("sonuc_*")) if (k / "rapor.json").exists()]


def karsilastir(onceki, son):
    """Gerileme uyarilari (bos liste: gerileme yok)."""
    uyarilar = []
    if onceki["ort_sayfa_puani"] is not None and son["ort_sayfa_puani"] is not None and \
            onceki["ort_sayfa_puani"] - son["ort_sayfa_puani"] >= PUAN_DUSUSU:
        uyarilar.append(f"ortalama sayfa puanı {onceki['ort_sayfa_puani']} → {son['ort_sayfa_puani']} düştü")
    if son["yuksek_sorun"] > onceki["yuksek_sorun"]:
        uyarilar.append(f"yüksek ciddiyetli sorun {onceki['yuksek_sorun']} → {son['yuksek_sorun']} arttı")
    for kod, sayfalar in sorted(son["kodlar"].items()):
        if kod not in onceki["kodlar"] and len(sayfalar) > 1:
            uyarilar.append(f"yeni sorun: {kod} ({len(sayfalar)} sayfada)")
    return uyarilar


def trend(site_klasoru):
    liste = taramalar(site_klasoru)
    uyarilar = karsilastir(liste[-2], liste[-1]) if len(liste) >= 2 else []
    return {"site": Path(site_klasoru).name, "taramalar": liste, "uyarilar": uyarilar}


SUTUNLAR = ("tarama", "sayfa", "ort_sayfa_puani", "ort_site_puani", "toplam_sorun", "yuksek_sorun")


def csv_metni(t):
    satirlar = [";".join(SUTUNLAR)]
    satirlar += [";".join("" if x[s] is None else str(x[s]) for s in SUTUNLAR) for x in t["taramalar"]]
    return "\n".join(satirlar) + "\n"


def html_metni(t, oncelik=None):
    e = html.escape
    govde = "".join("<tr>" + "".join(f"<td>{e(str(x[s] if x[s] is not None else '—'))}</td>" for s in SUTUNLAR) +
                    "</tr>" for x in reversed(t["taramalar"]))
    uyari = ("<div class='uyari'><strong>Gerileme:</strong><ul>" + "".join(f"<li>{e(u)}</li>" for u in t["uyarilar"]) +
             "</ul></div>") if t["uyarilar"] else "<p class='iyi'>Son iki tarama arasında gerileme yok.</p>"
    ek = ""
    if oncelik:
        ek = ("<h2>Search Console trafiğine göre öncelik</h2><table><tr><th>Sayfa</th><th>Gösterim</th><th>Tıklama</th>"
              "<th>Sorun ağırlığı</th><th>Öncelik</th><th>En ciddi sorunlar</th></tr>" +
              "".join(f"<tr><td>{e(o['url'])}</td><td>{o['gosterim']:.0f}</td><td>{o['tiklama']:.0f}</td>"
                      f"<td>{o['sorun_agirligi']}</td><td>{o['oncelik_puani']}</td>"
                      f"<td>{e(', '.join(o['en_ciddi_sorunlar']))}</td></tr>" for o in oncelik[:30]) + "</table>")
    return (f"<!doctype html><html lang='tr'><head><meta charset='utf-8'><title>Trend · {e(t['site'])}</title>"
            "<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:1100px}table{border-collapse:collapse;"
            "width:100%;margin:1rem 0}td,th{border-bottom:1px solid #ddd;padding:.35rem .5rem;text-align:left;"
            "font-variant-numeric:tabular-nums}.uyari{background:#fdecea;border-left:4px solid #c62828;padding:.5rem 1rem}"
            ".iyi{color:#2e7d32}</style></head><body>"
            f"<h1>Tarama eğilimi · {e(t['site'])}</h1>{uyari}<table><tr>" +
            "".join(f"<th>{s.replace('_', ' ')}</th>" for s in SUTUNLAR) + f"</tr>{govde}</table>{ek}</body></html>")
