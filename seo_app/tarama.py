"""Site taramasi: baglantilari izleyerek sayfa kesfi ve baglanti grafigi bulgulari.

Kesif genislik oncelikli (BFS) yapilir; her sayfanin baslangic sayfasina tiklama uzakligi
(derinlik) boylece dogru olculur. Sitemap adresleri ikincil kuyruktadir: yalnizca baglanti
izleyerek ulasilacak sayfa kalmadiginda taranir. Bu sayede sitemap'te olup hicbir sayfadan
baglanti almayan (yetim) sayfalar ayirt edilebilir.
"""
import re
from collections import defaultdict, deque
from urllib.parse import urlparse

from .cikarma import ayni_site, url_anahtari
from .kurallar import cozum_yolu

HTML_DISI = re.compile(r"\.(pdf|jpe?g|png|gif|webp|avif|svg|ico|bmp|tiff?|zip|rar|7z|gz|tar|docx?|xlsx?|pptx?|odt|"
                       r"mp[34]|avi|mov|wmv|webm|exe|msi|dmg|apk|css|js|mjs|xml|json|txt|csv|ics|woff2?|ttf|eot)$", re.I)
DERIN_ESIK = 3


def taranabilir(adres, kok_host):
    """Ayni sitede, http(s) ve HTML olmasi beklenen bir adres mi."""
    p = urlparse(adres)
    return p.scheme in ("http", "https") and ayni_site(p.hostname, kok_host) and not HTML_DISI.search(p.path)


class Kuyruk:
    """Iki oncelikli tarama kuyrugu. Adresler url_anahtari ile tekillestirilir; ana kuyruk
    (baslangic + baglantilar) bitmeden yedek kuyruga (sitemap) gecilmez."""

    def __init__(self):
        self.ana, self.yedek, self.gorulen = deque(), deque(), set()

    def ekle(self, adres, derinlik, kaynak, yedek=False):
        anahtar = url_anahtari(adres)
        if anahtar in self.gorulen:
            return False
        if yedek:
            self.yedek.append((adres, derinlik, kaynak))
            return True
        self.gorulen.add(anahtar)
        self.ana.append((adres, derinlik, kaynak))
        return True

    def goruldu(self, adres):
        """Yonlendirme hedefi gibi baska yoldan ziyaret edilen adresi isaretler."""
        if adres:
            self.gorulen.add(url_anahtari(adres))

    def al(self):
        if self.ana:
            return self.ana.popleft()
        while self.yedek:
            adres, derinlik, kaynak = self.yedek.popleft()
            if url_anahtari(adres) not in self.gorulen:
                self.gorulen.add(url_anahtari(adres))
                return adres, derinlik, kaynak
        return None

    def __len__(self):
        return len(self.ana) + len(self.yedek)


def _grup(kod, deger, sayfalar):
    return {"sorun": kod, "cozum_yolu": cozum_yolu(kod), "deger": deger, "sayfalar": sayfalar}


def baglanti_bulgulari(rapor, sitemap_adresleri=(), site_modu=True):
    """Taranan sayfalar arasindaki baglanti grafiginden tarama geneli bulgular. Her kayda
    'gelen_baglanti' (kac taranan sayfadan site ici baglanti aldigi) yazilir.
    site_modu=False iken (yalnizca liste) yetim ve derinlik bulgulari uretilmez; bunlar ancak
    site baglanti izlenerek tarandiginda anlamlidir."""
    gecerli = [k for k in rapor if not (k.get("hata") or k.get("atlandi"))]
    gelen = defaultdict(set)
    for k in gecerli:
        kendi = url_anahtari(k.get("site_url") or k.get("ad"))
        for hedef in (k.get("ic_baglantilar") or []) + (k.get("ic_nofollow_baglantilar") or []):
            a = url_anahtari(hedef)
            if a != kendi:
                gelen[a].add(kendi)
    for k in gecerli:
        anahtarlar = {url_anahtari(k.get("ad")), url_anahtari(k.get("site_url") or k.get("ad"))}
        k["gelen_baglanti"] = len(set().union(*(gelen.get(a, set()) for a in anahtarlar)))
    bulgular = []
    # sitemap'te listelenen ama hata kodu donen (ya da acilmayan) adres; liste modunda da gecerlidir
    olu = {}
    sitemap_k = {url_anahtari(a) for a in sitemap_adresleri}
    for k in rapor:
        a = url_anahtari(k.get("ad"))
        if a in sitemap_k and not k.get("atlandi") and (k.get("hata") or (k.get("durum_kodu") or 0) >= 400):
            olu[a] = k["ad"]
    if olu:
        bulgular.append(_grup("sitemap_olu_adres", f"{len(olu)} sitemap adresi hata döndürüyor", list(olu.values())))
    if site_modu:
        baglanti_alan = set(gelen)
        baslangic = {url_anahtari(k.get("ad")) for k in gecerli if k.get("derinlik") == 0}
        # sitemap'te listelenen ama baska adrese yonlenen adres yetim degildir: sitemap'in son adresi
        # listelemesi gerekir (sitemap_yonlendirme). Son adres baglanti aliyorsa sayfa da yetim degildir.
        yonlenen = {url_anahtari(k["ad"]): k["site_url"] for k in gecerli
                    if k.get("site_url") and url_anahtari(k["site_url"]) != url_anahtari(k["ad"])}
        yetimler, yonlendirmeler = [], []
        for adres in dict.fromkeys(sitemap_adresleri):
            a = url_anahtari(adres)
            if a in olu:
                continue                      # hata donen adres yetim degil, sitemap'ten cikmali (sitemap_olu_adres)
            if a in yonlenen:
                yonlendirmeler.append(adres)
            elif a not in baglanti_alan and a not in baslangic:
                yetimler.append(adres)
        if yetimler:
            bulgular.append(_grup("yetim_sayfa", f"{len(yetimler)} sitemap adresi, {len(gecerli)} taranan sayfaya göre",
                                  yetimler[:500]))
        if yonlendirmeler:
            bulgular.append(_grup("sitemap_yonlendirme", f"{len(yonlendirmeler)} sitemap adresi yönlendiriliyor",
                                  yonlendirmeler[:500]))
        derinler = [k["ad"] for k in gecerli if (k.get("derinlik") or 0) > DERIN_ESIK]
        if derinler:
            bulgular.append(_grup("derin_sayfa", f"{len(derinler)} sayfa {DERIN_ESIK}+ tıklama derinliğinde", derinler))
    # hreflang karsilikliligi: A, B'yi gosteriyorsa ve B tarandiysa B de A'yi gostermeli
    hreflang = {}
    for k in gecerli:
        hrefler = {url_anahtari(h["href"]) for h in k.get("hreflang_baglantilari") or [] if h.get("href")}
        hreflang[url_anahtari(k.get("site_url") or k["ad"])] = (k, hrefler)
    donussuz = []
    for anahtar, (k, hrefler) in hreflang.items():
        for hedef in hrefler - {anahtar}:
            if hedef in hreflang and anahtar not in hreflang[hedef][1]:
                donussuz.append(k["ad"])
                break
    if donussuz:
        bulgular.append(_grup("hreflang_donus_yok", f"{len(donussuz)} sayfa", donussuz))
    return bulgular
