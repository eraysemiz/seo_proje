import glob
import json
import os
import re
import sys
from bs4 import BeautifulSoup

try:
    from openai import OpenAI, BadRequestError
except ImportError:
    print(
        "❌ HATA: 'openai' kütüphanesi yüklü değil!\n"
        "Lütfen terminalde şu komutu çalıştırıp tekrar deneyin:\n"
        "python -m pip install openai beautifulsoup4"
    )
    sys.exit(1)

# ---------------------------------------------------------
# KLASÖR VE LM STUDIO KONFİGÜRASYONU
# ---------------------------------------------------------
INPUT_DIR = "snapshots"
OUTPUT_DIR = "sonuc"

client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"
)

# LM Studio üzerindeki modelinizin tam adı/ID'si
MODEL_NAME = "qwen3.5-9b"


def extract_json_from_text(text: str) -> str:
    """Modelden dönen yanıt içerisindeki JSON bloğunu temizler ve ayıklar."""
    text = text.strip()
    
    # Markdown kod bloklarını temizle
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # En dıştaki { ve } parantezlerinin arasını al
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]

    return text


def clean_html_for_llm(raw_html: str) -> str:
    """
    HTML içindeki ağır script, style ve svg kodlarını temizleyerek
    LLM'e sadece SEO'yu ilgilendiren yapıyı gönderir.
    """
    soup = BeautifulSoup(raw_html, "html.parser")

    for element in soup(["script", "style", "svg", "noscript", "iframe"]):
        element.decompose()

    return str(soup)


def extract_html_metadata(raw_html: str) -> dict:
    """HTML içeriğini ayrıştırarak metadata özetini çıkarır."""
    soup = BeautifulSoup(raw_html, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else None

    meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    desc_content = meta_desc.get("content") if meta_desc else None

    meta_viewport = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
    canonical = soup.find("link", attrs={"rel": re.compile(r"^canonical$", re.I)})

    images_missing_alt = [
        {"src": img.get("src", "bilinmiyor"), "context": img.parent.text[:50].strip()}
        for img in soup.find_all("img")
        if not img.get("alt")
    ]

    h1_tags = [h1.get_text(strip=True) for h1 in soup.find_all("h1")]
    h2_tags = [h2.get_text(strip=True) for h2 in soup.find_all("h2")]

    og_tags = [
        str(tag) for tag in soup.find_all("meta", property=re.compile(r"^og:", re.I))
    ]

    return {
        "title": title,
        "meta_description": desc_content,
        "has_viewport": bool(meta_viewport),
        "canonical_url": canonical.get("href") if canonical else None,
        "h1_count": len(h1_tags),
        "h1_contents": h1_tags,
        "h2_contents": h2_tags,
        "open_graph_tags_count": len(og_tags),
        "images_without_alt_count": len(images_missing_alt),
        "images_without_alt_details": images_missing_alt[:10],
        "has_schema_json_ld": bool(soup.find("script", type="application/ld+json")),
    }


def step_1_generate_seo_report(cleaned_html: str, metadata: dict) -> str:
    """Aşama 1: HTML ve metadata LM Studio üzerinden Qwen modeline gönderilerek JSON SEO raporu alınır."""
    system_prompt = (
        "Sen kıdemli bir Technical SEO Uzmanısın. Verilen HTML kodunu ve çıkarılmış metadata özetini inceleyerek "
        "tüm SEO aksaklıklarını, eksikliklerini ve optimizasyon fırsatlarını tespit et. "
        "Yanıtını SADECE geçerli bir JSON nesnesi olarak ver, açıklama metni ekleme."
    )

    user_prompt = f"""Aşağıdaki verileri incele ve SADECE JSON formatında bir SEO Denetim Raporu döndür.

--- METADATA ÖZETİ ---
{json.dumps(metadata, ensure_ascii=False, indent=2)}

--- HTML KODU (Temizlenmiş) ---
{cleaned_html[:15000]}

Lütfen raporunu tam olarak aşağıdaki JSON şemasına uygun yaz:
{{
  "critical_errors": ["Sorun 1", "Sorun 2"],
  "warnings": ["Uyarı 1"],
  "action_items": [
    {{"element": "meta title", "issue": "Eksik", "fix_suggestion": "İçeriğe uygun başlık oluştur"}},
    {{"element": "img alt", "issue": "Görselde alt metin yok", "fix_suggestion": "İlgili alt tag ekle"}}
  ]
}}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    raw_response = response.choices[0].message.content
    return extract_json_from_text(raw_response)


def step_2_fix_html_code(raw_html: str, seo_report_json: str) -> str:
    """Aşama 2: Üretilen SEO Raporuna göre HTML kodu onarılır."""
    system_prompt = (
        "Sen uzman bir Frontend ve SEO Geliştiricisisin. Görevin, sana verilen SEO raporundaki tüm "
        "sorunları çözerek mükemmel derecede optimize edilmiş yeni HTML kodunu üretmektir."
    )

    user_prompt = f"""Aşağıda tespit edilen SEO Hataları ve Orijinal HTML Kodu yer almaktadır.

--- SEO DENETİM RAPORU ---
{seo_report_json}

--- ORİJİNAL HTML ---
{raw_html[:15000]}

TALİMATLAR:
1. SEO Raporunda belirtilen TÜM kritik hataları ve uyarıları düzelt.
2. Eksik ise <title>, <meta description>, Open Graph ve canonical etiketlerini ekle.
3. Eksik `alt` etiketi olan tüm görsellere içeriğe uygun açıklayıcı alt metinler tanımla.
4. Sayfadaki H1 hiyerarşisini düzelt (Sadece 1 adet H1 olmalı).
5. Head bölümüne uygun bir Schema.org (JSON-LD) yapılandırılmış veri bloğu ekle.
6. Orijinal sayfa yapısını ve içeriğini kesinlikle bozma.
7. ÇIKTI FORMATI: SADECE temizlenmiş tam HTML kodunu ver.
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    fixed_code = response.choices[0].message.content

    if "```html" in fixed_code:
        fixed_code = fixed_code.split("```html")[1].split("```")[0].strip()
    elif "```" in fixed_code:
        fixed_code = fixed_code.split("```")[1].split("```")[0].strip()

    return fixed_code


def process_single_file(file_path: str):
    """Tek bir HTML/HTM dosyasını işler."""
    if not os.path.isfile(file_path):
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    filename = os.path.basename(file_path)
    base_name, ext = os.path.splitext(filename)

    output_report = os.path.join(OUTPUT_DIR, f"{base_name}_seo_report.json")
    output_fixed_html = os.path.join(OUTPUT_DIR, f"{base_name}_fixed{ext}")

    print(f"\n==================================================")
    print(f"📄 İŞLENİYOR: {file_path}")
    print(f"==================================================")

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        raw_html = f.read()

    cleaned_html = clean_html_for_llm(raw_html)
    metadata = extract_html_metadata(raw_html)

    try:
        # 1. Raporlama
        print("🔍 [Aşama 1/2] LM Studio ile SEO Hataları Analiz Ediliyor...")
        report_json_str = step_1_generate_seo_report(cleaned_html, metadata)

        with open(output_report, "w", encoding="utf-8") as f:
            f.write(report_json_str)
        print(f"✅ SEO Raporu Kaydedildi: {output_report}")

        # 2. Kod İyileştirme
        print("🛠️ [Aşama 2/2] LM Studio ile Kod Yeniden Yapılandırılıyor...")
        fixed_html = step_2_fix_html_code(raw_html, report_json_str)

        with open(output_fixed_html, "w", encoding="utf-8") as f:
            f.write(fixed_html)
        print(f"✅ Onarılan HTML Kaydedildi: {output_fixed_html}")

    except BadRequestError as e:
        if "No models loaded" in str(e):
            print(
                "\n❌ LM STUDIO HATASI: LM Studio uygulamasında model yüklü değil!\n"
                "👉 Lütfen LM Studio'yu açıp Qwen modelini RAM'e yükleyin ve sunucuyu başlatın."
            )
            sys.exit(1)
        else:
            print(f"\n❌ API Hatası: {e}")


def get_target_files() -> list:
    """snapshots klasöründeki dosyaları filtreler."""
    if len(sys.argv) > 1:
        return [f for f in sys.argv[1:] if os.path.isfile(f)]

    if not os.path.exists(INPUT_DIR):
        print(f"❌ Hata: '{INPUT_DIR}' klasörü bulunamadı.")
        return []

    all_paths = glob.glob(os.path.join(INPUT_DIR, "*.html")) + glob.glob(os.path.join(INPUT_DIR, "*.htm"))
    return [p for p in all_paths if os.path.isfile(p)]


def main():
    target_files = get_target_files()

    if not target_files:
        print(f"⚠️ '{INPUT_DIR}' klasöründe işlenecek geçerli .html veya .htm dosyası bulunamadı!")
        return

    print(f"🎯 Bulunan Geçerli Dosya Sayısı: {len(target_files)}")
    for file_path in target_files:
        process_single_file(file_path)

    print(f"\n🎉 İşlem tamamlandı. Çıktılar '{OUTPUT_DIR}/' klasöründe!")


if __name__ == "__main__":
    main()