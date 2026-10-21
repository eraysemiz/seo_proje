# Yerel Dil Modeli ile Otomatik SEO Denetimi ve İyileştirme

YBS317 SEO I dersi bilimsel araştırma ödevi kapsamında geliştirilen araç.
Web sayfalarını kural tabanlı olarak denetler, tespit edilen eksikler için **yerel** bir
büyük dil modelinden (LM Studio) metin önerisi alır, önerileri doğrulayıp HTML'e uygular
ve öncesi/sonrası karşılaştırmalı bir rapor üretir.

## Kurulum

```
pip install -r requirements.txt
```

## Çalıştırma

```
py calistir.py
```

Tarayıcıda `http://127.0.0.1:5000` açılır. Sunucu yalnızca bu bilgisayardan erişilebilir.

Dil modeli önerisi isteniyorsa LM Studio'nun açık ve sunucusunun çalışır durumda olması
gerekir (Developer sekmesi → Running). Arayüzdeki **Modelleri getir** düğmesi bağlantıyı
sınar ve yüklü modelleri listeler. Model yoksa **"Dil modeli ile öneri üret"** kutusunun
işaretini kaldırarak yalnızca kural denetimi (baseline) çalıştırılabilir.

## İki tarama modu

| Mod | Girdi | Yapılabilen denetimler |
|---|---|---|
| **Canlı adresler** | URL listesi | Sayfa içi denetimlerin tamamı **+ site katmanı**: robots.txt, sitemap.xml, HTTPS/sertifika, yanıt süresi ve boyut |
| **Kaydedilmiş HTML** | `.htm`/`.html` klasörü | Yalnızca sayfa içi denetimler (site katmanı ölçülemez) |

Kaydedilmiş HTML modu, sayfaların zaman içinde değişmesinden etkilenmeyen tekrarlanabilir
deneyler için kullanışlıdır; canlı mod ise gerçek bir denetimin tüm kapsamını sunar.

## Denetim katmanları

**Sayfa katmanı** (HTML'den görülebilir, her iki modda da çalışır)

- title, meta description, H1 varlığı ve uzunlukları
- görsellerde alt metni, canonical, `html lang`, içerik uzunluğu
- viewport (mobil uyum), JSON-LD/mikroveri, Open Graph, Twitter Card, favicon, meta robots

**Site katmanı** (yalnızca canlı erişimde)

- robots.txt: var mı, geçerli mi, sitemap bildiriyor mu, sayfayı engelliyor mu
- sitemap.xml: erişilebilir mi, geçerli XML mi, kaç adres içeriyor, sayfa listede mi
- HTTPS: şema, http→https yönlendirmesi, sertifika süresi ve **zincir bütünlüğü**, HSTS
- Hız/boyut: TTFB, indirme süresi, HTML boyutu, sıkıştırma (gzip/br), dış kaynak sayısı

## Her sorunun bir çözüm yolu vardır

Rapordaki her bulgu üç sınıftan birine düşer:

- `model` — dil modelinin metin üretmesi gerekir (title, meta description, H1, alt metni)
- `kural` — kod ile kesin biçimde düzeltilir (canonical, lang, fazla H1, viewport, og etiketleri)
- `elle` — sunucu/yönetici müdahalesi gerekir (robots.txt, sertifika, yanıt süresi...)

Dil modeline **yalnızca** `model` sınıfındaki sorunlar gönderilir. Bu ayrım, "modelin başarısı"
ile "aracın toplam başarısı" ölçümlerinin karışmasını önler.

## Deney koşulları

| Koşul | Modele verilen ek bağlam |
|---|---|
| `sifir` | yok (temel karşılaştırma koşulu) |
| `ornek` | few-shot örnekler (`ogretme/ornekler.json`) |
| `bilgi` | SEO bilgi tabanından ilgili parçalar (`ogretme/bilgi_tabani.json`) |
| `ornek+bilgi` | ikisi birden |

`bilgi` koşulunda bir **gömme (embedding) modeli** seçilirse gerçek anlamsal getirme (RAG)
yapılır: sorgu ve bilgi parçaları vektöre çevrilip kosinüs benzerliğiyle en alakalı parçalar
seçilir. Model seçilmezse veya ulaşılamazsa anahtar kelime eşleştirmesine düşülür — hangisinin
kullanıldığı raporda `ogretme_yontemi` alanında yazar (`anlamsal` / `anahtar_kelime`).

## Önerilerin doğrulanması

Modelden gelen her öneri uygulanmadan önce denetlenir; geçmeyen öneri reddedilir ve
gerekçesiyle rapora yazılır:

- izin verilen alanlardan biri mi, boş mu, HTML etiketi içeriyor mu
- alanın uzunluk kuralına uyuyor mu (title 30-60, meta 70-160, H1 5-70 karakter)
- **sadakat denetimi:** sayfanın içerik bölgesinde (menü, üst ve alt bilgi hariç) geçmeyen en az
  iki içerik kelimesi varsa reddedilir (modelin bilgi uydurmasına karşı)
- **doğrulanamayan nitelemeler:** "uzmanlaşmış", "başarılı", "lider", "öncü" gibi ifadeler, sayfanın
  kendi title/meta/H1 metninde geçmiyorsa reddedilir
- yeniden denemede modelin zaten kabul edilmiş alanları tekrar göndermesi ret sayılmaz;
  raporda ayrı bir `yok_sayilan` listesine yazılır
- görsel hedefi gerçekten listede var mı, aynı alan için tekrar öneri verilmiş mi

## Çıktılar

Her tarama `sonuclar/` altında kendi klasörüne yazar (ad verilmezse `sonuc_<tarih>`):

- `rapor.json` — sayfa başına tüm bulgular, öneriler, reddedilenler, ölçümler
- `ozet.csv` — karşılaştırma tablosu (tarama bitince kendiliğinden yazılır)
- `site_geneli.json` — sayfalar arasında tekrar eden title / meta açıklama / H1 grupları
- `duzeltilmis_*.html` — düzeltmelerin uygulandığı sayfalar

## Deney matrisi

Model × koşul × retry kombinasyonlarını tek komutla çalıştırır; her kombinasyon ayrı klasöre,
karşılaştırması `sonuclar/<ad>/karsilastirma.csv` dosyasına yazılır:

```
py deney.py --klasor snapshots --modeller qwen/qwen3.5-9b,qwen3.8-4b-distill --ad deney1
py deney.py --adresler test_setleri/duzce_birimleri.txt --modeller qwen/qwen3.5-9b ^
            --kosullar sifir,bilgi --retry 0,1 --embed-model text-embedding-qwen3-embedding-0.6b
```

## Bağımsız ölçüm (isteğe bağlı)

Arayüzdeki "Lighthouse SEO puanını da al" seçeneği, canlı modda Google PageSpeed Insights
üzerinden Lighthouse SEO puanını rapora ve CSV'ye ekler. Anahtarsız kullanımın günlük kotası
çabuk dolar; ücretsiz bir API anahtarı `PSI_API_ANAHTARI` ortam değişkenine yazılabilir.
Düzeltilmiş sayfa yerel bir dosya olduğu için "sonra" puanı bu yöntemle ölçülemez.

## Testler

```
pip install -r requirements-dev.txt
py -m pytest tests
```

## Test seti

`test_setleri/duzce_birimleri.txt` — Düzce Üniversitesi birim siteleri. Liste, aracın
**Alt siteleri keşfet** özelliğiyle anasayfadaki bağlantılardan otomatik üretilmiştir.

## Puanlama hakkında uyarı

Arayüz **sayfa** ve **site** puanlarını ayrı gösterir; ayrıntı panelinde ayrıca içerik, teknik,
güvenlik ve performans kategori puanları vardır. Her puan 0-100 arasıdır ve o kapsamda görülebilecek
en kötü durumun cezasına bölünerek hesaplanır (ceza ağırlıkları: yüksek 15, orta 8, düşük 3).
Böylece birkaç sorun ölçeği 0'a indirmez. Ölçülemeyen kapsam (çevrimdışı modda site katmanı,
hata sayfasında sayfa katmanı) "ölçülmedi" olarak gösterilir. Eski tek puan (`once_puan` /
`sonra_puan`) deney karşılaştırılabilirliği için raporda korunur.

Bu puanlar aracın kendi ölçeğidir, Lighthouse gibi **bağımsız bir ölçüm değildir**. Aracın kendi
kurallarıyla kendi başarısını ölçmek döngüsel olacağından, ödevde bağımsız bir doğrulama ayrıca
yapılmalıdır.

## Etik ve sınırlar

- Araç varsayılan olarak **robots.txt kurallarına uyar**; izin verilmeyen adresi taramaz.
- İstekler arasında bekleme uygular ve kendini tanıtan bir User-Agent kullanır.
- Sertifika doğrulaması başarısız olursa tarama durmaz: sayfa doğrulamasız indirilir ve
  durum yüksek önemli bir bulgu olarak raporlanır.

## Dosya düzeni

```
calistir.py              uygulamayı başlatır
deney.py                 deney matrisi koşucusu (komut satırı)
tests/                   pytest testleri
seo_app/
  bagimsiz.py            PageSpeed (Lighthouse) SEO puanı
  cikarma.py             HTML'den veri çıkarma
  kurallar.py            kural denetimi, çözüm yolu sınıflandırması, puanlama
  canli.py               canlı erişim denetimleri (robots, sitemap, HTTPS, hız)
  ogretme.py             few-shot ve bilgi tabanı (RAG)
  llm.py                 LM Studio istemcisi, öneri doğrulama
  uygula.py              önerilerin HTML'e işlenmesi, kural tabanlı düzeltmeler
  boru.py                tek sayfa analiz akışı, toplu tarama, alt site keşfi
  web.py                 Flask arayüzü
  sablonlar/ statik/     arayüz dosyaları
ogretme/                 örnekler, bilgi tabanı, gömme önbelleği
test_setleri/            tarama adres listeleri
sonuclar/                tüm tarama çıktıları
```

Eski komut satırı sürümleri `outdated/` klasöründe geliştirme geçmişi olarak durmaktadır;
güncel motor `seo_app/` paketidir.
