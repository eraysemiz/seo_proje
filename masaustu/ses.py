"""Is bitince, hata olunca ve onay sorulurken Windows sistem sesleri (winsound, standart kutuphane)."""
try:
    import winsound
except ImportError:                          # Windows disi: sessiz
    winsound = None

_SESLER = {"bitti": "SystemAsterisk", "hata": "SystemHand", "onay": "SystemExclamation"}


def cal(tur, acik=True):
    if not (acik and winsound):
        return
    try:
        winsound.PlaySound(_SESLER[tur], winsound.SND_ALIAS | winsound.SND_ASYNC)
    except RuntimeError:
        pass
