# Yerel Dil Modeli ile Otomatik SEO Denetimi ve İyileştirme

YBS317 SEO I dersi bilimsel araştırma ödevi kapsamında geliştirilen araç.
Web sayfalarını kural tabanlı olarak denetler, tespit edilen eksikler için **yerel** bir
büyük dil modelinden (LM Studio) metin önerisi alır, önerileri doğrulayıp HTML'e uygular
ve öncesi/sonrası karşılaştırmalı bir rapor üretir.

## Kurulum

```
pip install flask requests beautifulsoup4 lxml
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
- **sadakat denetimi:** sayfada geçmeyen en az iki içerik kelimesi varsa reddedilir
  (modelin bilgi uydurmasına karşı)
- görsel hedefi gerçekten listede var mı, aynı alan için tekrar öneri verilmiş mi

## Çıktılar

Her tarama `sonuclar/` altında kendi klasörüne yazar (ad verilmezse `sonuc_<tarih>`):

- `rapor.json` — sayfa başına tüm bulgular, öneriler, reddedilenler, ölçümler
- `ozet.csv` — karşılaştırma tablosu (arayüzden indirilir)
- `duzeltilmis_*.html` — düzeltmelerin uygulandığı sayfalar

## Test seti

`test_setleri/duzce_birimleri.txt` — Düzce Üniversitesi birim siteleri. Liste, aracın
**Alt siteleri keşfet** özelliğiyle anasayfadaki bağlantılardan otomatik üretilmiştir.

## Puanlama hakkında uyarı

Arayüzdeki 0-100 puan, bu aracın kendi ağırlıklandırmasıdır (yüksek 15, orta 8, düşük 3 ceza
puanı). Lighthouse gibi **bağımsız bir ölçüm değildir**; aracın kendi kurallarıyla kendi
başarısını ölçmek döngüsel olacağından, ödevde bağımsız bir doğrulama ayrıca yapılmalıdır.

## Etik ve sınırlar

- Araç varsayılan olarak **robots.txt kurallarına uyar**; izin verilmeyen adresi taramaz.
- İstekler arasında bekleme uygular ve kendini tanıtan bir User-Agent kullanır.
- Sertifika doğrulaması başarısız olursa tarama durmaz: sayfa doğrulamasız indirilir ve
  durum yüksek önemli bir bulgu olarak raporlanır.

## Dosya düzeni

```
calistir.py              uygulamayı başlatır
seo_app/
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
