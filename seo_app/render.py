"""JavaScript ile olusan icerigin islenmesi (render).

Yeni bir Python bagimliligi eklememek icin bilgisayarda kurulu Chrome, Edge ya da Chromium
basliksiz (headless) calistirilir ve sayfanin betikler calistiktan sonraki DOM'u alinir
(--dump-dom). Arama motorlari da sayfayi benzer bicimde render eder; ham HTML ile render
sonrasi arasindaki fark, icerigin JavaScript'e bagimli olup olmadigini gosterir.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ADAY_YOLLAR = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
KOMUT_ADLARI = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge")


def tarayici_bul():
    """Kurulu bir Chromium tabanli tarayicinin yolu; CHROME_YOLU ortam degiskeni oncelikli. Yoksa None."""
    ozel = os.environ.get("CHROME_YOLU")
    if ozel and Path(ozel).exists():
        return ozel
    for aday in ADAY_YOLLAR:
        yol = os.path.expandvars(aday)
        if Path(yol).exists():
            return yol
    for ad in KOMUT_ADLARI:
        yol = shutil.which(ad)
        if yol:
            return yol
    return None


def render_et(url, kullanici_ajani, zaman_asimi=40, bekleme_ms=8000):
    """Sayfayi basliksiz tarayicida acip betikler calistiktan sonraki HTML'i dondurur.
    (html, hata) dondurur; tarayici yoksa ya da basarisizsa html None olur."""
    yol = tarayici_bul()
    if not yol:
        return None, "Chrome/Edge bulunamadı (CHROME_YOLU ortam değişkeniyle yol verilebilir)"
    with tempfile.TemporaryDirectory(prefix="seo_render_") as profil:
        komut = [yol, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                 "--disable-extensions", "--mute-audio", "--hide-scrollbars",
                 "--user-data-dir=" + profil, "--user-agent=" + kullanici_ajani,
                 "--virtual-time-budget=" + str(bekleme_ms), "--dump-dom", url]
        try:
            p = subprocess.run(komut, capture_output=True, timeout=zaman_asimi)
        except (subprocess.TimeoutExpired, OSError) as e:
            return None, type(e).__name__ + ": render zaman aşımı ya da başlatılamadı"
    html = p.stdout.decode("utf-8", errors="replace")
    if p.returncode != 0 or "<html" not in html[:2000].lower():
        return None, "render başarısız (çıkış kodu " + str(p.returncode) + ")"
    return html, None
