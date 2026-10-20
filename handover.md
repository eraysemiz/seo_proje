# Handover: Yerel YZ ile SEO Analizi Ödevi

Bu dosya, oturumlar arasında bağlamın kaybolmaması için tutulur. Son güncelleme: **20 Ekim 2026**.

## 1. Proje / ödev bağlamı

- **Ders:** YBS317 SEO I (Düzce Üniversitesi, YBS Bölümü, Doç. Dr. Remzi Başar)
- **Ödev türü:** Vize yerine geçen "Bilimsel Araştırma Ödevi", not ağırlığı %40
- **Ekip:** 3 kişilik
- **Konu başlığı:** *"Yerel Büyük Dil Modeli ile Web Sitelerinin Otomatik SEO Denetimi ve İyileştirilmesi: Düzce Üniversitesi Birim Siteleri Örneği"*
- **Teslim:** 11. ders haftası, KLASÖR halinde, MS Word formatında (PDF kabul edilmiyor). 7. haftada yarı bitmiş hâli sunulacak.
- **Kritik kurallar:**
  - Anket kullanımı **yasak** (uzman mülakatı serbest).
  - Kişi başı en az 5 sayfa (kapak/özet/kaynakça hariç), kişi başı 10-12 kaynak, en az %50'si yabancı.
  - Turnitin benzerlik oranı %25'i geçerse ödev geçersiz.
  - Metni öğrenciler kendisi yazmalı. **Kod/araç geliştirmede YZ kullanımı ayrı, metni YZ'ye yazdırmak ayrı** — bu ayrım hocaya açıkça belirtilmeli.
  - Konu onayı 2. hafta sonuna kadar; haftalık görüşme Salı 14:10-16:10.
  - **Hoca bu spesifik kapsamı henüz onaylamadı.** Hâlâ bir sonraki kritik adım.

## 2. Teknik durum: artık bir web uygulaması

**Önceki durum:** tek dosyalık komut satırı betiği (`seo_pipeline_ogretmeli2.py`), yalnızca kaydedilmiş HTML dosyalarını tarıyordu.

**Şimdiki durum:** `seo_app/` paketi + yerel web arayüzü. Çalıştırma:

```
pip install -r requirements.txt
py calistir.py          # http://127.0.0.1:5000 açılır
```

Ayrıntılı kullanım, denetim listesi ve mimari için **`README.md`** dosyasına bakın.

### Eklenen yetenekler

1. **Canlı erişim modu** — artık siteleri Chrome'dan tek tek kaydetmeye gerek yok, adres listesi yeterli.
2. **Site katmanı denetimleri** (yalnızca canlı modda): robots.txt, sitemap.xml, HTTPS/sertifika/HSTS, http→https yönlendirmesi, durum kodu, yönlendirme zinciri, TTFB, indirme süresi, HTML boyutu, sıkıştırma.
3. **Sayfa katmanına eklenenler** (çevrimdışı modda da çalışır): viewport (mobil uyum), JSON-LD/mikroveri, Open Graph, Twitter Card, favicon, meta robots/noindex, dış kaynak sayısı.
4. **Çözüm yolu sınıflandırması** — her sorun `model` / `kural` / `elle` olarak etiketlenir. Bu, "modelin başarısı" ile "aracın toplam başarısı" ölçümlerini ayırır (hocanın sorabileceği bir soruyu baştan kapatır).
5. **Alt site keşfi** — bir adresteki bağlantılardan kurumun alt sitelerini otomatik çıkarır; test seti bununla oluşturuldu.
6. **Kural tabanlı düzeltmelere eklenenler:** viewport meta etiketi, Open Graph etiketleri (mevcut title/meta'dan türetilir, yeni bilgi uydurulmaz).
7. **robots.txt'ye uyum** — araç varsayılan olarak izin verilmeyen adresi taramaz, istekler arasında bekler, kendini tanıtan User-Agent kullanır. Yöntem bölümünde etik gerekçe olarak yazılabilir.

### Önemli tasarım kararı (yöntem bölümünde açıklanmalı)

Dil modeline **yalnızca** temel sayfa denetiminin (`rule_checks`) çıktısı gönderilir — yani title, meta description, H1, alt metni. Yeni eklenen yapısal veri / site katmanı sorunları modele hiç gitmez. Böylece canlı mod eklenmeden önce yapılan deney koşullarıyla karşılaştırılabilirlik korunur ve modelden çözemeyeceği şeyler istenmez.

### Dosya karmaşası uyarısı

Kök dizindeki `seo_pipeline.py`, `seo_pipelineg.py`, `seo_pipeline_ogretmeli.py`, `seo_pipeline_ogretmeli2.py` dosyaları **eski sürümlerdir**. Güncel motor `seo_app/` paketidir. Bunları bir `eski/` klasörüne taşımak karışıklığı önler (yapılmadı, kullanıcının kararı).

## 3. Ortam

- Windows, PowerShell. Python `py` komutuyla çalışıyor (Python 3.15).
- Kurulu paketler: flask, requests, beautifulsoup4, lxml.
- **LM Studio şu an kapalı.** Port oturumdan oturuma değişti (1234/1235) — arayüzdeki "Modelleri getir" düğmesi bağlantıyı sınar.
- Modeller: sohbet `qwen/qwen3.5-9b`, gömme `qwen3-embedding-0.6b`. GPU offload düzeltildi, ~30 token/sn.

## 4. ÇÖZÜLDÜ: RAG/embedding doğrulandı

Önceki handover'ın "doğrulanması gerekiyor" maddesi kapandı. `sonuclar/sonuc_rag/rapor.json` içinde her iki sayfada da `ogretme_yontemi: "anlamsal"` — yani gömme modeline gerçekten ulaşılmış, anahtar kelime yöntemine düşülmemiş. Anlamsal RAG çalışıyor.

## 5. Test seti ve ilk gerçek sonuçlar

**Test seti:** `test_setleri/duzce_birimleri.txt` — 58 Düzce Üniversitesi birim sitesi, aracın keşif özelliğiyle anasayfadan otomatik çıkarıldı.

**Temel (baseline) tarama:** `sonuclar/sonuc_taban_canli/` (`rapor.json` + `ozet.csv`), 20 Ekim 2026, LLM kullanılmadan, yalnızca kural + canlı denetim.

- 58/58 site başarıyla tarandı, hata yok, robots nedeniyle atlanan yok
- Ortalama 13,5 sorun/site; ortalama puan 10,6/100 (yalnızca kural düzeltmeleriyle 16,9'a çıkıyor)

**Kurumsal düzeyde bulgular (ödevin en güçlü verisi):**

| Bulgu | Kaç sitede |
|---|---|
| Canonical etiketi yok | 58/58 |
| Yapısal veri (schema.org) yok | 58/58 |
| Open Graph etiketleri yok | 58/58 |
| sitemap.xml yok | 56/58 (yalnızca kaliteyonetim ve rimer'de var) |
| robots.txt yok | 55/58 (yalnızca hastane'de var) |
| Sertifika 30 günden az kaldı | 54/58 |
| H1 başlığı yok | 51/58 |
| Görsellerde alt metni eksik | 49/58 |
| **Sunucu eksik/yanlış ara sertifika gönderiyor** | 41/58 |

**Tek kök neden tespitleri** (yazımda bunları ayrı ayrı 54 sorun gibi saymayın):

- 54 site aynı `*.duzce.edu.tr` joker sertifikasını kullanıyor, **18 Kasım 2026**'da doluyor.
- Sertifika zinciri hatası: sunucular yaprak sertifikanın vereni olan *"Sectigo Public Server Authentication CA DV R36"* ara sertifikasını göndermiyor, onun yerine farklı bir ara sertifika (*"Sectigo RSA Domain Validation Secure Server CA"*) gönderiyor. Tarayıcılar eksik halkayı kendileri tamamladığı için kullanıcılar fark etmiyor; **katı doğrulama yapan istemciler (Python `requests`/certifi, bazı tarayıcı botları) bağlanamıyor.** Bu, SEO açısından gerçek bir risk ve ödevin özgün bulgusu olabilir.
- En yavaş siteler: hukuk (2132 ms TTFB), uabs (2051 ms), kurulkararlari (2045 ms).

## 6. Hâlâ eksik olanlar

| Eksik | Durum | Öncelik |
|---|---|---|
| Konu onayı | **Alınmadı** | Kritik |
| Deney matrisi | `--kosul` × model × retry kombinasyonları toplu çalıştırılmadı. Arayüz tek koşul çalıştırıyor; toplu deney için bir betik gerekir | Yüksek |
| LLM'li tam tarama | 58 sitede henüz model çalıştırılmadı (LM Studio kapalıydı) | Yüksek |
| Bağımsız ölçüm | Lighthouse önce/sonra ölçümü yok. Aracın kendi puanı döngüsel | Yüksek |
| Elle değerlendirme | Sadakat/Türkçe kalitesi için en az 2 kişilik kör puanlama tablosu | Yüksek |
| Literatür | Başlanmadı; kişi başı 10-12 kaynak, %50 yabancı | Yüksek, zaman alıcı |
| Metin yazımı | Başlanmadı | Yüksek |
| Bilgi tabanı kaynakları | `bilgi_tabani.json` ve `seo_kurallari.json` YZ tarafından yazılmış, atıfsız taslaklar. Gerçek kaynaklarla (Google SEO Başlangıç Kılavuzu vb.) karşılaştırılıp öğrenciler tarafından yeniden yazılmalı | Yüksek (Turnitin + akademik dürüstlük) |

## 7. Önerilen sıradaki adımlar

1. Hocadan konu ve kapsam onayı al (tek sayfalık özet: konu, yöntem, veri seti, beklenen sonuç).
2. LM Studio'yu aç, arayüzden küçük bir alt küme (5-10 site) üzerinde LLM'li tarama yap, çıktıyı gözle doğrula.
3. Deney matrisini çalıştır: en az 2 model × `sifir`/`ornek`/`bilgi`/`ornek+bilgi` × `retry 0/1`. Bunun için `seo_app` motorunu döngüye sokan küçük bir betik yazılmalı.
4. Lighthouse ile bağımsız önce/sonra SEO skoru ölç.
5. Elle değerlendirme tablosu: site / alan / öneri / sadakat (E-H) / Türkçe kalitesi (1-5), en az 2 kişi, model adı gizli.
6. Literatür taraması + yazım, paralel yürüt.
7. Bilgi tabanı metinlerini kaynak göstererek yeniden yaz.

## 8. Önemli uyarılar

- Kodun geliştirilmesinde YZ yardımı alındı — **Yöntem bölümünde açıkça belirtilmeli**. Ödev metninin kendisi öğrenciler tarafından yazılmalı.
- Arayüzdeki 0-100 puan aracın kendi ölçeğidir (yüksek 15 / orta 8 / düşük 3 ceza puanı). Bağımsız bir ölçüm değildir; ödevde bu sınır açıkça yazılmalı.
- Kapsam dışı kalan SEO konuları yöntem bölümünde belirtilmeli: içerik kalitesi/anahtar kelime stratejisi, backlink profili, Core Web Vitals (gerçek tarayıcı ölçümü), JavaScript ile oluşturulan içerik (araç yalnızca sunucudan gelen HTML'i görür), çok dilli yapı.
- Kaynakça klasörüne kullanılan makale/web sayfalarının PDF'leri konulmalı.
