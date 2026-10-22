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

### 21 Ekim 2026 sadeleştirmesi (kullanıcı kararı)

- **Kaydedilmiş HTML analizi kaldırıldı;** araç yalnızca canlı adres tarıyor. `snapshots/` klasörü
  yalnızca testlerde örnek sayfa olarak duruyor.
- **Her tarama dil modeliyle yapılıyor;** "yalnızca kural denetimi" seçeneği yok. Tarama başlamadan
  önce LM Studio'ya ulaşılabildiği ve seçilen sohbet/gömme modellerinin yüklü olduğu denetleniyor;
  değilse tarama başlamıyor. Gömme modeli seçilip ulaşılamazsa anahtar kelimeye sessizce geçilmiyor.
- **Deney koşulu sabit: `ornek+bilgi`.** Arayüzde ve `deney.py`'de koşul seçeneği yok; `deney.py`
  artık model × retry matrisini çalıştırıyor. Koşul karşılaştırması (sıfır/örnek/bilgi) yapılacaksa
  bu kararın geri alınması gerekir.
- **Sonuç klasörü:** `sonuclar/<site adı>/sonuc_<YYYY-MM-DD_HH-MM-SS>/`.
- **Arayüz ve mesaj metinleri** Türkçe karakterlerle yazıldı (önceden kaynakta ASCII'ydi).

### Eklenen yetenekler

1. **Canlı erişim** — siteleri Chrome'dan tek tek kaydetmeye gerek yok, adres listesi yeterli.
2. **Site katmanı denetimleri:** robots.txt, sitemap.xml, HTTPS/sertifika/HSTS, http→https yönlendirmesi, durum kodu, yönlendirme zinciri, TTFB, indirme süresi, HTML boyutu, sıkıştırma.
3. **Sayfa katmanına eklenenler:** viewport (mobil uyum), JSON-LD/mikroveri, Open Graph, Twitter Card, favicon, meta robots/noindex, dış kaynak sayısı.
4. **Çözüm yolu sınıflandırması** — her sorun `model` / `kural` / `elle` olarak etiketlenir. Bu, "modelin başarısı" ile "aracın toplam başarısı" ölçümlerini ayırır (hocanın sorabileceği bir soruyu baştan kapatır).
5. **Alt site keşfi** — bir adresteki bağlantılardan kurumun alt sitelerini otomatik çıkarır; test seti bununla oluşturuldu.
6. **Kural tabanlı düzeltmelere eklenenler:** viewport meta etiketi, Open Graph etiketleri (mevcut title/meta'dan türetilir, yeni bilgi uydurulmaz).
7. **robots.txt'ye uyum** — araç varsayılan olarak izin verilmeyen adresi taramaz, istekler arasında bekler, kendini tanıtan User-Agent kullanır. Yöntem bölümünde etik gerekçe olarak yazılabilir.

### Önemli tasarım kararı (yöntem bölümünde açıklanmalı)

Dil modeline **yalnızca** çözüm yolu `model` olan sorunlar gönderilir: title, meta description, H1, alt metni. Canonical, lang, içerik azlığı, yapısal veri ve site katmanı sorunları modele hiç gitmez (21 Ekim 2026 kararı, "temiz ayrım"). Bu yüzden bu tarihten önceki LLM'li sonuçlar yeni çalıştırmalarla doğrudan karşılaştırılamaz; deneyler yeniden çalıştırılmalı. Yeniden denemede modelin zaten kabul edilmiş alanları tekrar göndermesi ret sayılmaz, raporda `yok_sayilan` listesine yazılır.

### Dosya karmaşası uyarısı

Kök dizindeki `seo_pipeline.py`, `seo_pipelineg.py`, `seo_pipeline_ogretmeli.py`, `seo_pipeline_ogretmeli2.py` dosyaları **eski sürümlerdir**. Güncel motor `seo_app/` paketidir. Bunları bir `eski/` klasörüne taşımak karışıklığı önler (yapılmadı, kullanıcının kararı).

## 3. Ortam

- Windows, PowerShell. Python `py` komutuyla çalışıyor (Python 3.15).
- Kurulu paketler: flask, requests, beautifulsoup4, lxml.
- **LM Studio şu an kapalı.** Port oturumdan oturuma değişti (1234/1235) — arayüzdeki "Modelleri getir" düğmesi bağlantıyı sınar.
- Modeller: sohbet `qwen/qwen3.5-9b`, gömme `qwen3-embedding-0.6b`. GPU offload düzeltildi, ~30 token/sn.

## 4. ÇÖZÜLDÜ: RAG/embedding doğrulandı

Önceki handover'ın "doğrulanması gerekiyor" maddesi kapandı. `sonuclar/sonuc_rag/rapor.json` içinde (21 Ekim'de silindi; `git checkout 7b527d1 -- sonuclar/sonuc_rag` ile geri getirilebilir) her iki sayfada da `ogretme_yontemi: "anlamsal"` — yani gömme modeline gerçekten ulaşılmış, anahtar kelime yöntemine düşülmemiş. Anlamsal RAG çalışıyor.

## 4b. 22 Ekim 2026: RAG iyileştirmesi (`rag-iyilestirme` dalı)

Ayrıntı README'nin "Modele verilen ek bağlam" ve "Bilgi getirme (RAG) ölçümü" bölümlerinde.

- Hibrit getirme: metadata filtresi → Türkçe sorgu (+ Qwen3 talimat öneki) → kosinüs ve BM25'in
  ağırlıklı RRF'si → her sorunlu alanı kapsayan seçim (k=5) → 1 600 karakter bütçe.
  İsteğe bağlı rerank istemcisi (`/rerank`, llama.cpp) var; gerçek bir rerank sunucusuyla denenmedi.
- Kaynak atfı: parçalar `[t02]` kimlikleriyle isteme girer, öneride `kaynaklar` alanı, arayüzde bağlantı.
- Sayfa verisi: site adı, H3, menü ve bağlantı listeleri ayıklanmış içerik özeti.
- `localhost` → `127.0.0.1`: Windows'ta her LM Studio isteğine eklenen ~2 sn gecikme kalktı.
- `deney.py --kosullar` geri geldi (yalnızca deneyde; arayüzde koşul sabit).
- Getirme ölçümü (60 sayfa): kapsama 0,457 → 1,000; sorun isabeti 0,939; getirme 2 257 → 39 ms.
  Set 43 farklı siteden 73 canlı sayfayla 133 sayfaya genişletildi (9 grup): eski hat kapsama 0,487 /
  isabet 0,514, yeni hat 1,000 / 1,000, sorun isabeti 0,935. En zayıf sorun `title_kisa` (29/45).
  Eşit ağırlıklı hibrit (0,707) yalnız vektörden (0,931) kötüydü; BM25 bu yüzden 0,1 ağırlıkta.
  qwen3-embedding-0.6b (0,939) nomic-embed-text-v1.5'ten (0,889) iyi.
- Uçtan uca (4 sayfa, qwen3.5-9b, tek çalıştırma; küçük örnek): kabul edilen öneri eski 9 / yeni 9,
  istem ortalaması 7 294 → 6 722 karakter (%8 kısa; hedef %25'ti, tutmadı), son çalıştırmada
  sadakat reddi 0, yeni önerilerin hepsi geçerli kaynak kimliğine dayanıyor. Title'ın 60 karakteri
  aşması (62-65) eski ve yeni hatta sürüyor.

## 5. Test seti ve ilk gerçek sonuçlar

**Test seti:** `test_setleri/duzce_birimleri.txt` — 58 Düzce Üniversitesi birim sitesi, aracın keşif özelliğiyle anasayfadan otomatik çıkarıldı.

**Temel (baseline) tarama:** `sonuclar/sonuc_taban_canli/` (`rapor.json` + `ozet.csv`), 20 Ekim 2026, LLM kullanılmadan, yalnızca kural + canlı denetim. Bu klasör 21 Ekim'de silindi (yerine v2 geldi); `git checkout 7b527d1 -- sonuclar/sonuc_taban_canli` ile geri getirilebilir.

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

### Güncel temel tarama (21 Ekim 2026, Aşama 1-2 sonrası)

**Bundan sonra başvurulacak temel tarama:** `sonuclar/sonuc_taban_canli_v2/`. Yukarıdaki ilk tarama (`sonuc_taban_canli`) tarihsel kayıt olarak duruyor. v2 güncel kurallarla alındı; farklar açıklanabilir:
- `cdn.duzce.edu.tr` 404 dönüyor; hata sayfasının HTML'i artık denetlenmiyor (16 → 7 bulgu).
- `hastane` sitesinin "15/15 alt metni eksik" bulgusu yanlış pozitifmiş (görsellerin hepsi dekoratif, `alt=""`); kalktı.
- Yeni puan ölçeği (sayfa/site ayrı, 0-100 normalleştirilmiş): sayfa medyan 60, site medyan 67. Eski tek puanın medyanı 7 idi ve siteleri ayırt edemiyordu.
- **Yeni bulgu:** 58 sitenin **38'inde meta açıklama birebir aynı** ("Düzce Üniversitesi"), `site_geneli.json`.

**Bağımsız ölçüm (Lighthouse, PageSpeed Insights):** `sonuclar/adim9_lighthouse/`, 10 site. 8 site 75, `adayogrenci` 91, `hastane` 92. Aracın bulgularıyla karşılaştırma: alt metni 10/10 uyumlu (hastane'de Lighthouse da sorun görmüyor; dekoratif görsel düzeltmesinin bağımsız teyidi), robots.txt 9/10 uyumlu (`adayogrenci`'de ayrışma, nedeni belirsiz). Lighthouse puanı kaba bir ölçek (10 sitenin 8'i aynı puan); aracın sayfa/site puanları siteleri daha ince ayırıyor. Düzeltilmiş sayfa yerel olduğu için "sonra" puanı bu yöntemle ölçülemiyor. API anahtarı `PSI_API_ANAHTARI` ortam değişkeninden okunur, depoya yazılmaz.

## 6. Hâlâ eksik olanlar

| Eksik | Durum | Öncelik |
|---|---|---|
| Konu onayı | **Alınmadı** | Kritik |
| Deney matrisi | Koşucu hazır (`deney.py`), henüz tam çalıştırılmadı. İkinci sohbet modeli (4B) yalnızca model karşılaştırması yapılacaksa gerekir | Yüksek |
| LLM'li tam tarama | 58 sitede henüz model çalıştırılmadı | Yüksek |
| Bağımsız ölçüm | "Önce" Lighthouse puanı 10 sitede alındı; "sonra" puanı yerel dosya için ölçülemiyor | Orta |
| Elle değerlendirme | Sadakat/Türkçe kalitesi için en az 2 kişilik kör puanlama tablosu | Yüksek |
| Literatür | Başlanmadı; kişi başı 10-12 kaynak, %50 yabancı | Yüksek, zaman alıcı |
| Metin yazımı | Başlanmadı | Yüksek |
| Bilgi tabanı kaynakları | 22 Ekim 2026'da `bilgi_tabani.json` Google Arama Merkezi ve W3C WAI belgelerine atıflı, Türkçe 28 parça olarak yeniden yazıldı (yine YZ yazımı; 17 kaynak bağlantısı açılıyor, temel iddialar kaynak metinle karşılaştırıldı). Ödevde kullanılacaksa öğrencilerin kaynakları okuyup kendi cümleleriyle gözden geçirmesi gerekir. `seo_kurallari.json` (gömme modeli seçilmediğinde kullanılır) hâlâ atıfsız | Yüksek (Turnitin + akademik dürüstlük) |

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
