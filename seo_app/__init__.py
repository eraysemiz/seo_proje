"""Yerel LLM destekli SEO denetim uygulamasi.

Paket yapisi:
  cikarma.py  - HTML'den SEO verisi cikarma
  kurallar.py - sayfa ici kural denetimi ve puanlama
  canli.py    - canli erisim denetimleri (robots, sitemap, HTTPS, hiz, yapisal veri)
  ogretme.py  - few-shot ornekler ve bilgi tabani (RAG)
  llm.py      - LM Studio istemcisi, oneri uretme ve dogrulama
  uygula.py   - onerilerin HTML'e islenmesi, kural tabanli duzeltmeler
  boru.py     - tek sayfalik tam analiz akisi
  web.py      - Flask arayuzu
"""
__version__ = "3.0"
