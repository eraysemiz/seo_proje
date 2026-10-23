"""HTML kaynak metninde etiketlerin karakter konumlari.

Yonetici modu duzeltmeleri dosyayi BeautifulSoup ile yeniden yazmaz (bu, tum belgenin bicimini
degistirir ve diff'i okunmaz kilar); bunun yerine degistirilecek parcanin kaynak metindeki tam
konumunu bulur ve yalnizca o parcayi degistirir. Bu modul standart kutuphanedeki HTMLParser ile
her ogenin acilis ve kapanis etiketinin konumlarini cikarir.
"""
import re
from html.parser import HTMLParser

BOS_ETIKETLER = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
                 "track", "wbr"}
# kapanis etiketi yazilmasa da HTML'de gecerli olan ogeler (yapi denetiminde eksik sayilmaz)
ISTEGE_BAGLI_KAPANIS = {"p", "li", "td", "th", "tr", "thead", "tbody", "tfoot", "option", "dt", "dd", "html",
                        "head", "body", "colgroup", "caption", "optgroup", "rb", "rt", "rp"}
_NITELIK = re.compile(r"""\s+([^\s=/>"']+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>"']+))?""")


class Oge:
    __slots__ = ("etiket", "bas", "bas_son", "kap_bas", "kap_son", "nitelikler", "ham", "ust")

    def __init__(self, etiket, bas, ham, nitelikler, ust):
        self.etiket, self.bas, self.ham, self.nitelikler, self.ust = etiket, bas, ham, nitelikler, ust
        self.bas_son = bas + len(ham)
        self.kap_bas = self.kap_son = None

    def nitelik(self, ad, varsayilan=None):
        for k, v in self.nitelikler:
            if k == ad:
                return v if v is not None else ""
        return varsayilan

    def __repr__(self):
        return f"<Oge {self.etiket} {self.bas}:{self.bas_son}>"


class _Tarayici(HTMLParser):
    def __init__(self, metin):
        super().__init__(convert_charrefs=False)
        self.metin = metin
        self.satir_baslari = [0] + [m.end() for m in re.finditer("\n", metin)]
        self.ogeler, self.yigin, self.basibos_kapanis = [], [], []

    def _konum(self):
        satir, sutun = self.getpos()
        return self.satir_baslari[satir - 1] + sutun

    def handle_starttag(self, tag, attrs):
        bas = self._konum()
        ham = self.get_starttag_text() or ""
        oge = Oge(tag, bas, ham, attrs, self.yigin[-1] if self.yigin else None)
        self.ogeler.append(oge)
        if tag not in BOS_ETIKETLER:
            self.yigin.append(oge)

    def handle_startendtag(self, tag, attrs):
        bas = self._konum()
        ham = self.get_starttag_text() or ""
        self.ogeler.append(Oge(tag, bas, ham, attrs, self.yigin[-1] if self.yigin else None))

    def handle_endtag(self, tag):
        bas = self._konum()
        son = self.metin.find(">", bas)
        son = len(self.metin) if son == -1 else son + 1
        for i in range(len(self.yigin) - 1, -1, -1):
            if self.yigin[i].etiket == tag:
                self.yigin[i].kap_bas, self.yigin[i].kap_son = bas, son
                del self.yigin[i:]
                return
        self.basibos_kapanis.append((tag, bas))


def tara(metin):
    """Belgedeki ogeler (belge sirasiyla). Her ogenin bas/bas_son (acilis etiketi) ve
    kap_bas/kap_son (kapanis etiketi, yoksa None) konumlari vardir."""
    t = _Tarayici(metin)
    t.feed(metin)
    t.close()
    return t.ogeler


def yapi_hatalari(metin):
    """Kapanmamis zorunlu ogeler + eslesmeyen kapanis etiketleri sayisi. Bir degisikligin
    belgeyi bozup bozmadigini anlamak icin degisiklik oncesi ve sonrasi karsilastirilir."""
    t = _Tarayici(metin)
    t.feed(metin)
    t.close()
    kapanmamis = [o for o in t.ogeler if o.etiket not in BOS_ETIKETLER and o.etiket not in ISTEGE_BAGLI_KAPANIS
                  and o.kap_bas is None and not o.ham.rstrip().endswith("/>")]
    return len(kapanmamis) + len(t.basibos_kapanis)


def bul(ogeler, etiket, kosul=None):
    return [o for o in ogeler if o.etiket == etiket and (kosul is None or kosul(o))]


def ilk(ogeler, etiket, kosul=None):
    sonuc = bul(ogeler, etiket, kosul)
    return sonuc[0] if sonuc else None


def ic_metin(metin, oge):
    if oge.kap_bas is None:
        return ""
    return metin[oge.bas_son:oge.kap_bas]


def nitelik_ekleme_konumu(oge):
    """Acilis etiketinde yeni nitelik eklenecek konum: '>' ya da '/>' hemen oncesi."""
    ham = oge.ham
    son = len(ham) - 1
    if ham.endswith("/>"):
        son = len(ham) - 2
        while son > 0 and ham[son - 1].isspace():
            son -= 1
    return oge.bas + son


def nitelik_konumlari(oge):
    """{ad: (tam_bas, tam_son, deger_bas, deger_son, tirnaksiz_deger)} — konumlar belgeye gore.
    tam_*: nitelik bastaki bosluk dahil butunuyle (silmek icin); deger_*: tirnak icindeki deger."""
    sonuc = {}
    ham = oge.ham
    m0 = re.match(r"<[^\s/>]+", ham)
    for m in _NITELIK.finditer(ham, m0.end() if m0 else 0):
        ad = m.group(1).lower()
        if ad in sonuc:
            continue
        if m.group(2) is None:
            sonuc[ad] = (oge.bas + m.start(), oge.bas + m.end(), oge.bas + m.end(), oge.bas + m.end(), "")
            continue
        deger_bas, deger_son = m.start(2), m.end(2)
        deger = m.group(2)
        if deger[:1] in "\"'":
            deger_bas, deger_son, deger = deger_bas + 1, deger_son - 1, deger[1:-1]
        sonuc[ad] = (oge.bas + m.start(), oge.bas + m.end(), oge.bas + deger_bas, oge.bas + deger_son, deger)
    return sonuc


def etiket_adi_konumlari(oge):
    """Acilis ve kapanis etiketindeki etiket adinin konumlari (ornegin h1 -> h2 yeniden adlandirma)."""
    parcalar = [(oge.bas + 1, oge.bas + 1 + len(oge.etiket))]
    if oge.kap_bas is not None:
        parcalar.append((oge.kap_bas + 2, oge.kap_bas + 2 + len(oge.etiket)))
    return parcalar


def satir_sutun(metin, konum):
    satir = metin.count("\n", 0, konum) + 1
    sutun = konum - (metin.rfind("\n", 0, konum) + 1) + 1
    return satir, sutun
