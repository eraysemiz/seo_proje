# Handover: Yerel YZ ile SEO Analizi Ödevi

Bu dosya, Claude ile Claude.ai'de yürütülen bir sohbetin devamı olarak Claude Code'a aktarılmak üzere hazırlandı. Amaç: yeni oturumun sıfırdan bağlam kurmasına gerek kalmadan kaldığı yerden devam edebilmesi.

## 1. Proje / ödev bağlamı

- **Ders:** YBS317 SEO I (Düzce Üniversitesi, YBS Bölümü, Doç. Dr. Remzi Başar)
- **Ödev türü:** Vize yerine geçen "Bilimsel Araştırma Ödevi", not ağırlığı %40
- **Ekip:** 3 kişilik
- **Konu başlığı:** *"Yerel Büyük Dil Modeli ile Web Sitelerinin Otomatik SEO Denetimi ve İyileştirilmesi"* (kesin değil, örnek adres eklenerek spesifikleştirilebilir, örn. "...: Düzce Üniversitesi Birim Siteleri Örneği")
- **Teslim:** 11. ders haftası, KLASÖR halinde, MS Word formatında (PDF kabul edilmiyor). Ara sınav haftasında (7. hafta) ödevin yarı bitmiş hâli sunulacak.
- **Kritik kurallar (ödev hazırlama kılavuzundan):**
  - Anket kullanımı **yasak**.
  - Kişi başı en az 5 sayfa (kapak/özet/kaynakça hariç), kişi başı 10-12 kaynak, en az %50'si yabancı.
  - Turnitin benzerlik oranı %25'i geçerse ödev geçersiz.
  - Metni öğrenciler kendisi yazmalı; ağırlıklı YZ ile yazdırılmış metin geçersiz sayılır (kod/araç geliştirmede YZ kullanımı ayrı, metni YZ'ye yazdırmak ayrı — bu ayrım hocaya açıkça belirtilmeli).
  - Konu onayı 2. hafta sonuna kadar alınmalı; bir sayfalık özetle (konu, yöntem, veri seti, beklenen sonuç) haftalık görüşme saatine (Salı 14:10-16:10) gidilmesi öneriliyor.
  - **Hoca henüz bu spesifik kapsamı (yerel LLM pipeline + RAG + few-shot deneyleri) onaylamadı.** Bir sonraki adım bu olmalı.

## 2. Teknik yapı: ne inşa edildi

Bir Python betiği (`seo_pipeline.py`), yerel bir LLM'i (LM Studio üzerinden) kullanarak web sayfalarının SEO sorunlarını tespit edip (kural tabanlı) düzeltme önerisi üretiyor (LLM tabanlı), önerileri doğrulayıp uyguluyor ve ayrıntılı bir rapor çıkarıyor.

### Dosya dizini (kullanıcının bilgisayarında)

```
Desktop/Düzce Üniversitesi/seo_proje/      ← klasör adı zaman içinde değişti, şu an bu
  seo_pipeline.py
  ogretme/
    ornekler.json                  ← few-shot örnekleri (5 adet, sahte/örnek sitelerden)
    seo_kurallari.json             ← anahtar-kelime eşleştirmeli RAG'ın kullandığı 14 kısa kural
    bilgi_tabani.json              ← anlamsal (embedding) RAG'ın kullandığı 20 parçalık geniş bilgi tabanı
    bilgi_tabani_gomme_cache.json  ← betik otomatik oluşturur, parça vektörlerini önbellekler
  snapshots/                       ← kullanıcının Chrome'dan "Web Sayfası, Yalnızca HTML" olarak kaydettiği sayfalar
  sonuc_*/                         ← her --out ile farklı bir çıktı klasörü
    fixed_<dosya>.html
    rapor.json
```

Bu projenin tüm dosyaları şu an Claude.ai tarafının `/mnt/user-data/outputs/` klasöründe duruyor (bu oturumda erişilebilir, kullanıcının bilgisayarında değil):
- `/mnt/user-data/outputs/seo_pipeline.py`
- `/mnt/user-data/outputs/ogretme/ornekler.json`
- `/mnt/user-data/outputs/ogretme/seo_kurallari.json`
- `/mnt/user-data/outputs/ogretme/bilgi_tabani.json`
- `/mnt/user-data/outputs/ogretme/bilgi_tabani_gomme_cache.json`

### Ortam (kullanıcının bilgisayarı)

- **İşletim sistemi:** Windows, PowerShell kullanıyor
- **Python:** `py` komutuyla çalıştırılıyor (PATH sorunu `python` komutunda vardı, `py` çalışıyor)
- **LLM sunucusu:** LM Studio, sürüm 1.1.8, OpenAI uyumlu API (`http://localhost:1234/v1` veya `1235`, port oturumdan oturuma değişti — **kesin port kullanıcıdan teyit edilmeli**)
- **GPU sorunu çözüldü:** Başta CPU kullanıyordu (~6-7 token/sn), GPU offload düzeltildi, şu an ~30 token/sn.
- **Kullanılan modeller:**
  - Sohbet modeli: `qwen/qwen3.5-9b` (ve denemelerde `qwen3.8-4b-distill`)
  - Gömme (embedding) modeli: Qwen3-Embedding-0.6B (kullanıcı yeni yükledi, test edilmedi)

### Betiğin akışı (özet)

1. `extract()` — HTML'den title, meta açıklama, H1, görseller, metin örneği, kelime kökleri çıkarır.
2. `rule_checks()` — kod tabanlı, modelsiz SEO denetimi (title/meta uzunluğu, H1 var mı, canonical, lang, alt metin, içerik uzunluğu).
3. Sorun yoksa dur.
4. `ogretme_metni()` — **`--kosul` deney koşuluna göre** modele ek bağlam hazırlar (bkz. aşağıdaki RAG/öğretme bölümü).
5. `llm_fixes()` — LM Studio'ya akışlı (streaming) istek gönderir, JSON öneri alır, think-block temizler.
6. `dogrula()` — her öneriyi kontrol eder: izinli alan mı, HTML sızıntısı var mı, uzunluk kuralına uyuyor mu, **sayfada olmayan kelime var mı (sadakat/uydurma kontrolü)**, görsel hedefi gerçek mi.
7. Eksik alan kaldıysa `--retry` ile bir kez daha (yalnızca eksik alanlar + ret nedenleriyle) sorulur.
8. `apply_fixes()` — kabul edilen öneriler HTML'e yazılır.
9. `kural_duzelt()` — modelsiz, kod tabanlı düzeltmeler: canonical (sayfanın "saved from url" yorumundan), eksik `lang`, fazla H1→H2.
10. Yeniden denetim, `rapor.json`'a yaz: çözülen/kalan/yeni çıkan sorunlar, çözüm oranları, reddedilenler, süre/hız metrikleri.

### Deney koşulları (`--kosul`)

| Koşul | Ne yapar |
|---|---|
| `sifir` | Ek bağlam yok |
| `ornek` | İsteme 3 few-shot örneği eklenir (`ornekler.json`'dan, sorunlarla en çok örtüşenler seçilir) |
| `bilgi` | SEO bilgi tabanından ilgili parçalar eklenir (RAG) |
| `ornek+bilgi` | İkisi birden |

`bilgi` koşulunun iki alt yöntemi var:
- `--embed-model` **verilmezse** → anahtar kelime eşleştirmesi (`seo_kurallari.json`, sorun kodu → alan etiketi eşleşmesi)
- `--embed-model` **verilirse** → gerçek anlamsal RAG: sorgu + 20 parça embedding'e çevrilir, kosinüs benzerliğiyle en alakalı 4 parça seçilir (eşik 0.2). Gömme modeline ulaşılamazsa otomatik anahtar kelime yöntemine döner, uyarı basar.

### Komut örneği (son doğru format)

```
py seo_pipeline.py snapshots --out sonuc_rag --url http://localhost:1234/v1 --kosul bilgi --embed-model qwen3-embedding-0.6b
```

Diğer faydalı parametreler: `--model`, `--retry` (varsayılan 1), `--max-tokens` (varsayılan 3000), `--site-url`, `--dil`, `--ornek-sayisi`, `--no-llm` (yalnızca baseline/kural denetimi).

## 3. Bu oturumda çözülen hatalar (kronolojik, tekrar düşmemek için)

1. Python PATH sorunu → `py` komutuyla çözüldü.
2. LM Studio sunucusu kapalıydı → Developer sekmesinde Running yapıldı.
3. `.htm` uzantılı dosyalar `.html` aranan betik tarafından bulunamıyordu → betik hem `.htm` hem `.html` okuyacak şekilde düzeltildi.
4. İlk denemelerde düşünme (thinking) modu kapanmadığı için `max_tokens` düşünmeye harcanıp cevap boş kalıyordu (`bitis_nedeni: length`, `ham: ""`) → betik akışlı (streaming) hale getirildi, zaman aşımı sorunu ortadan kalktı; düşünme metni ayrı sayılıp cevaptan ayıklanıyor.
5. Model önerileri yanlış alanlara yazılıyordu (örn. H1 önerisi title alanına, canonical linki meta açıklamasına) → her öneri `dogrula()` ile kontrol edilip reddediliyor, H1 için ayrı alan eklendi, canonical modelden tamamen çıkarılıp koda (`kural_duzelt`) verildi.
6. Görsel `src` yolları uzun/Türkçe karakterli olduğu için model birebir yazamıyor, eşleşme başarısız oluyordu → kısa kimlikler (`g1`, `g2`...) + görsel bağlamı (dosya adı, bağlantı metni, title/aria-label) eklendi.
7. Model sayfada olmayan bilgi uyduruyordu (örn. "çevre ve sağlık alanında ihtisaslaşmış") → kelime kökü tabanlı sadakat kontrolü eklendi, sayfada geçmeyen ≥2 içerik kelimesi varsa öneri reddediliyor.
8. GPU kullanılmıyordu (CPU'da ~6-7 token/sn) → kullanıcı GPU offload ayarlarını düzeltti, şu an ~30 token/sn.
9. Eski dosya sürümleri kullanılarak yeni parametrelerin (`--kosul`, `--embed-model`) tanınmadığı hatalar alındı → **kullanıcıya her güncellemede dosyanın üzerine yazması hatırlatılmalı**, `py seo_pipeline.py --help` ile sürüm kontrolü öneriliyor.

## 4. RAG/embedding kısmı — şu an test edilmedi, DOĞRULANMASI GEREKİYOR

Kullanıcı Qwen3-Embedding-0.6B'yi LM Studio'ya yeni yükledi ama:
- İki modelin (sohbet + gömme) aynı anda `http://localhost:1234/v1/models` (veya 1235) listesinde göründüğü **henüz teyit edilmedi**.
- `--kosul bilgi --embed-model qwen3-embedding-0.6b` ile gerçek bir çalıştırma **henüz yapılmadı/rapor paylaşılmadı**.
- Beklenen doğru çalışma işareti: konsolda uyarı olmaması + `rapor.json` içinde `"ogretme_yontemi": "anlamsal"` (eğer `"anahtar_kelime"` çıkarsa embedding modeline ulaşılamamış demektir).

**Bir sonraki oturumun ilk işi:** kullanıcıdan `/v1/models` çıktısını ve ilk `--kosul bilgi --embed-model ...` çalıştırmasının `rapor.json` çıktısını almak, `ogretme_yontemi` alanını kontrol etmek.

## 5. Ödevde hâlâ eksik olanlar (hocaya "zor" dedirten kısımlar)

| Eksik | Durum | Öncelik |
|---|---|---|
| Test seti | Şu an yalnızca 1 site (Düzce Üniversitesi anasayfası) | Yüksek — 20-30 siteye çıkarılmalı |
| Bağımsız ölçüm | Yok — başarı şu an betiğin kendi kurallarıyla ölçülüyor (döngüsel) | Yüksek — Lighthouse SEO skoru önce/sonra eklenmeli |
| Model karşılaştırması | Kısmen var (9B vs 4B denendi) ama sistematik değil | Orta |
| Deney matrisi | `--kosul` × model × `--retry` kombinasyonları henüz toplu çalıştırılmadı | Orta |
| Elle değerlendirme | Yapılmadı — sadakat/Türkçe kalitesi için en az 2 kişilik kör puanlama tablosu gerekiyor | Yüksek |
| Literatür | Henüz başlanmadı — kişi başı 10-12 kaynak, %50 yabancı | Yüksek, zaman alıcı |
| Metin yazımı | Henüz başlanmadı | Yüksek |
| Konu onayı | **Alınmadı** | Kritik — her şeyden önce yapılmalı |
| SEO kapsamı sınırlı | robots.txt, sitemap, sayfa hızı, URL yapısı, schema, mobil uyum, HTTPS gibi kontroller YOK (yalnızca title/meta/H1/alt/canonical/lang/içerik uzunluğu var) | Yöntem bölümünde açıkça "kapsam dışı" olarak yazılmalı; istenirse viewport/HTTPS/schema kontrolleri kolayca eklenebilir |

## 6. Önerilen sıradaki adımlar

1. Embedding/RAG çalıştırmasını doğrula (bkz. madde 4).
2. Hocadan konu ve kapsam onayı al (tek sayfalık özetle, Salı 14:10-16:10).
3. Test setini 20-30 siteye çıkar (Chrome'dan "Web Sayfası, Yalnızca HTML" ile kaydet).
4. Baseline çalıştır: `py seo_pipeline.py snapshots --out sonuc_baseline --no-llm`
5. Deney matrisini çalıştır: en az 2 model × `sifir/ornek/bilgi/ornek+bilgi` × `--retry 0/1`
6. Lighthouse ile önce/sonra SEO skorlarını ölç (ayrı, betikten bağımsız bir doğrulama).
7. Elle değerlendirme tablosu: site/alan/öneri/sadakat(E-H)/Türkçe kalitesi(1-5), en az 2 kişi, model adı gizli.
8. Literatür taraması + yazım, paralel yürüt.
9. `ogretme/bilgi_tabani.json` ve `seo_kurallari.json` içeriğini kullanıcı kendi cümleleriyle yeniden yazıp kaynak göstermeli (şu an Claude'un yazdığı özgün ama atıfsız bir taslak, Turnitin ve akademik dürüstlük için düzeltilmeli).

## 7. Önemli uyarılar / hatırlatmalar

- Betik kodunu yazan/geliştiren Claude oldu — bu, **Yöntem bölümünde açıkça belirtilmeli** ("kodun geliştirilmesinde YZ yardımı alınmıştır"), ama ödev metninin kendisi öğrenciler tarafından yazılmalı.
- `seo_kurallari.json` ve `bilgi_tabani.json` içerikleri Claude tarafından yazılmış özgün ama kaynaksız taslaklardır — ödeve konmadan önce gerçek kaynaklarla (Google SEO başlangıç kılavuzu vb.) karşılaştırılıp öğrenciler tarafından yeniden yazılmalı.
- Anket kullanımı yasak — SEO uzmanlarıyla kısa mülakat kılavuzda izin veriliyor, anket değil.
- Kaynakça klasörüne kullanılan makale/web sayfalarının PDF'leri konulmalı.
