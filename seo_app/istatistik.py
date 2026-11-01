"""Olcum icin kucuk istatistik yardimcilari (bagimliliksiz).

wilson_alt   : bir oranin %95 guven araliginin alt siniri; az ornekle olculen dogrulugu iyimser okumamak icin
cohen_kappa  : iki etiketcinin sansla duzeltilmis uyumu
bootstrap_fark: eslestirilmis iki kosulun ortalama farki ve %95 guven araligi (sayfa basina yeniden ornekleme)
"""
import math
import random
from collections import Counter


def wilson_alt(basari, n, z=1.96):
    """Wilson skor araliginin alt siniri; n == 0 ise 0."""
    if n <= 0:
        return 0.0
    p = basari / n
    pay = p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, pay / (1 + z * z / n))


def cohen_kappa(a, b):
    """Iki etiket dizisinin Cohen kappa degeri. Etiketler ayni sirada ayni ogelere aittir. Tanimsizsa None."""
    ciftler = [(x, y) for x, y in zip(a, b) if x not in (None, "") and y not in (None, "")]
    n = len(ciftler)
    if not n:
        return None
    gozlenen = sum(x == y for x, y in ciftler) / n
    ca, cb = Counter(x for x, _ in ciftler), Counter(y for _, y in ciftler)
    beklenen = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if beklenen == 1:
        return 1.0 if gozlenen == 1 else None
    return (gozlenen - beklenen) / (1 - beklenen)


def bootstrap_fark(a, b, tekrar=2000, tohum=0):
    """Eslestirilmis olcumler (ayni sayfalar) icin ortalama(a - b) ve %95 bootstrap guven araligi.
    {"fark", "alt", "ust", "n"} dondurur; eslesen olcum yoksa None."""
    ciftler = [(x, y) for x, y in zip(a, b) if isinstance(x, (int, float)) and isinstance(y, (int, float))]
    if not ciftler:
        return None
    farklar = [x - y for x, y in ciftler]
    n = len(farklar)
    r = random.Random(tohum)
    ortalamalar = sorted(sum(farklar[r.randrange(n)] for _ in range(n)) / n for _ in range(tekrar))
    return {"fark": round(sum(farklar) / n, 4), "alt": round(ortalamalar[int(0.025 * tekrar)], 4),
            "ust": round(ortalamalar[int(0.975 * tekrar) - 1], 4), "n": n}
