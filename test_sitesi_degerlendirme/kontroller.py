"""sorunlar.json'daki kontrollerin canli site uzerinde calistirilmasi.

Her sorunun "kontrol" listesi, sorunun sitede HALA VAR olup olmadigini soyler. Varsayilan
birlestirme "ve"dir (tum kontroller dogruysa sorun vardir); "kontrol_birlesimi": "veya" ile
herhangi biri yeterli olur. Ayni kontrol motoru hem sorunlarin varligini dogrulamak (dogrula.py)
hem de duzeltme sonrasi "duzeldi mi" sorusunu yanitlamak (degerlendir.py) icin kullanilir.
Yalnizca standart kutuphane kullanir.
"""
import gzip
import json
import re
import urllib.error
import urllib.request
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from ortak import TABAN


class _Yonlendirmesiz(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_acici = urllib.request.build_opener(_Yonlendirmesiz)


def getir(yol):
    """(durum, govde_metni, basliklar) — yonlendirme izlenmez."""
    url = urljoin(TABAN + "/", yol)
    istek = urllib.request.Request(url, headers={"User-Agent": "TestDegerlendirici/1.0", "Accept-Encoding": "gzip"})
    try:
        yanit = _acici.open(istek, timeout=10)
        durum, ham, basliklar = yanit.status, yanit.read(), dict(yanit.headers)
    except urllib.error.HTTPError as e:
        durum, ham, basliklar = e.code, e.read(), dict(e.headers)
    if basliklar.get("Content-Encoding") == "gzip":
        ham = gzip.decompress(ham)
    basliklar["_bayt"] = len(ham)
    return durum, ham.decode("utf-8", "replace"), basliklar


class _Ayristirici(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.etiketler, self.yigin, self.main_metin, self.govde_metin = [], [], [], []
        self.title, self._title_ici = None, False
        self._main, self._body, self._atla = 0, 0, 0

    def handle_starttag(self, tag, attrs):
        self.etiketler.append((tag, dict(attrs)))
        if tag == "main":
            self._main += 1
        if tag == "body":
            self._body += 1
        if tag in ("script", "style", "noscript", "template"):
            self._atla += 1
        if tag == "title":
            self._title_ici, self.title = True, ""

    def handle_endtag(self, tag):
        if tag == "main":
            self._main -= 1
        if tag in ("script", "style", "noscript", "template"):
            self._atla = max(0, self._atla - 1)
        if tag == "title":
            self._title_ici = False

    def handle_data(self, veri):
        if self._title_ici:
            self.title += veri
        if self._atla:
            return
        if self._main:
            self.main_metin.append(veri)
        if self._body:
            self.govde_metin.append(veri)


def ayristir(html):
    a = _Ayristirici()
    a.feed(html)
    return a


def _meta(a, ad):
    for tag, ozn in a.etiketler:
        if tag == "meta" and (ozn.get("name") or "").lower() == ad:
            return ozn.get("content") or ""
    return None


def _jsonld(html):
    bloklar = re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I)
    nesneler, hatali = [], 0
    for b in bloklar:
        try:
            veri = json.loads(b)
        except json.JSONDecodeError:
            hatali += 1
            continue
        yigin = [veri]
        while yigin:
            x = yigin.pop()
            if isinstance(x, list):
                yigin += x
            elif isinstance(x, dict):
                nesneler.append(x)
                yigin += list(x.get("@graph") or [])
    return nesneler, hatali


def _turler(nesne):
    t = nesne.get("@type")
    return set(t) if isinstance(t, list) else {t}


def _sitemap_adresleri():
    durum, metin, _ = getir("/sitemap.xml")
    if durum != 200:
        return set()
    return {urlsplit(x.strip()).path + ("?" + urlsplit(x.strip()).query if urlsplit(x.strip()).query else "")
            for x in re.findall(r"<loc>(.*?)</loc>", metin)}


def _shingle(metin, n=5):
    k = re.findall(r"\w+", metin.lower())
    return {" ".join(k[i:i + n]) for i in range(max(0, len(k) - n + 1))}


_baglanti_grafi = {}


def baglanti_grafi():
    """Ham HTML baglantilariyla / adresinden genislik oncelikli tarama: {yol: derinlik}, {yol: gelen kaynaklar}.
    JavaScript calistirilmaz (arama motorunun ilk taramasi gibi)."""
    if _baglanti_grafi:
        return _baglanti_grafi["derinlik"], _baglanti_grafi["gelen"]
    derinlik, gelen, kuyruk = {"/": 0}, {}, deque(["/"])
    while kuyruk:
        yol = kuyruk.popleft()
        durum, html, basliklar = getir(yol)
        if durum in (301, 302, 303, 307, 308):
            hedef = urlsplit(urljoin(TABAN + yol, basliklar.get("Location", ""))).path
            if hedef and hedef not in derinlik:
                derinlik[hedef] = derinlik[yol]
                kuyruk.append(hedef)
            continue
        if durum != 200 or "text/html" not in (basliklar.get("Content-Type") or ""):
            continue
        for tag, ozn in ayristir(html).etiketler:
            if tag != "a" or not ozn.get("href"):
                continue
            p = urlsplit(urljoin(TABAN + yol, ozn["href"]))
            if p.netloc != urlsplit(TABAN).netloc:
                continue
            hedef = p.path + ("?" + p.query if p.query else "")
            if hedef != yol:
                gelen.setdefault(hedef, set()).add(yol)
            if hedef not in derinlik:
                derinlik[hedef] = derinlik[yol] + 1
                kuyruk.append(hedef)
    _baglanti_grafi.update(derinlik=derinlik, gelen=gelen)
    return derinlik, gelen


def onbellegi_temizle():
    _baglanti_grafi.clear()


def kontrol_et(k):
    """Tek bir kontrol. True: sorun (bu kontrole gore) var."""
    tur = k["tur"]
    if tur in ("yetim", "derinlik_en_az"):
        derinlik, gelen = baglanti_grafi()
        if tur == "yetim":
            return not gelen.get(k["url"])
        return derinlik.get(k["url"], 999) >= k["en_az"]
    if tur in ("sitemap_icerir", "sitemap_icermez"):
        var = k["url"] in _sitemap_adresleri()
        return var if tur == "sitemap_icerir" else not var
    if tur == "robots_engel":
        _, robots, _ = getir("/robots.txt")
        engelli = any(k["url"].startswith(s.split(":", 1)[1].strip()) for s in robots.splitlines()
                      if s.lower().startswith("disallow:") and s.split(":", 1)[1].strip())
        return engelli and k["url"] in _sitemap_adresleri()
    if tur == "yonlendirme_adim":
        yol, adim = k["url"], 0
        for _ in range(10):
            durum, _, basliklar = getir(yol)
            if durum not in (301, 302, 303, 307, 308):
                break
            adim += 1
            yol = urlsplit(urljoin(TABAN + yol, basliklar.get("Location", ""))).path
        return adim >= k["en_az"]
    if tur == "benzerlik_en_az":
        a = _shingle(" ".join(ayristir(getir(k["url"])[1]).main_metin))
        b = _shingle(" ".join(ayristir(getir(k["diger"])[1]).main_metin))
        return bool(a | b) and len(a & b) / len(a | b) >= k["oran"]
    if tur in ("ayni_title", "ayni_meta"):
        a, b = ayristir(getir(k["url"])[1]), ayristir(getir(k["diger"])[1])
        if tur == "ayni_title":
            return bool(a.title) and (a.title or "").strip() == (b.title or "").strip()
        ma, mb = _meta(a, "description"), _meta(b, "description")
        return bool(ma) and ma.strip() == (mb or "").strip()
    durum, html, basliklar = getir(k["url"])
    if tur == "durum":
        return durum == k["kod"]
    if tur == "yonlendirme_kodu":
        return durum == k["kod"]
    if tur == "boyut_en_az":
        return durum == 200 and basliklar["_bayt"] >= k["bayt"]
    if durum != 200:
        return False                              # sayfa yoksa icerige dair sorun da yoktur
    bayrak = re.S | (0 if k.get("harf_duyarli") else re.I)
    if tur == "desen_var":
        return re.search(k["desen"], html, bayrak) is not None
    if tur == "desen_yok":
        return re.search(k["desen"], html, bayrak) is None
    if tur == "desen_sayisi":
        return len(re.findall(k["desen"], html, bayrak)) >= k["en_az"]
    a = ayristir(html)
    if tur == "title_uzunluk":
        n = len((a.title or "").strip())
        return a.title is not None and not (k.get("en_az", 0) <= n <= k.get("en_cok", 10 ** 6))
    if tur == "meta_uzunluk":
        m = _meta(a, "description")
        return m is not None and not (k.get("en_az", 0) <= len(m) <= k.get("en_cok", 10 ** 6))
    if tur == "kelime_az":
        metin = " ".join(a.govde_metin if k.get("bolge") == "body" else a.main_metin)
        return len(metin.split()) < k["en_az"]
    if tur == "img_altsiz":
        return any(t == "img" and "alt" not in o for t, o in a.etiketler)
    if tur == "img_boyutsuz":
        return any(t == "img" and not ("width" in o and "height" in o) for t, o in a.etiketler)
    if tur == "link_kirik":
        hrefler = {o.get("href") for t, o in a.etiketler if t == "a"}
        return k["href"] in hrefler and getir(k["href"])[0] >= 400
    if tur == "jsonld_gecersiz":
        return _jsonld(html)[1] > 0
    if tur == "jsonld_eksik":
        nesneler = [n for n in _jsonld(html)[0] if k["tip"] in _turler(n)]
        return any(not any(n.get(alan) for alan in k["alanlar"]) for n in nesneler)
    if tur == "jsonld_tur_yok":
        return not any(_turler(n) & set(k["turler"]) for n in _jsonld(html)[0])
    raise ValueError("bilinmeyen kontrol türü: " + tur)


def sorun_var_mi(sorun):
    """(var_mi, [her kontrolun sonucu]) dondurur."""
    sonuclar = []
    for k in sorun["kontrol"]:
        try:
            sonuclar.append(bool(kontrol_et(k)))
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"Test sitesine ulaşılamadı ({TABAN}); sunucu çalışıyor mu? {e}") from e
    birlesim = any if sorun.get("kontrol_birlesimi") == "veya" else all
    return birlesim(sonuclar), sonuclar
