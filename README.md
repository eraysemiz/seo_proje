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

Her tarama dil modeliyle yapılır; bunun için LM Studio'nun açık ve sunucusunun çalışır durumda
olması gerekir (Developer sekmesi → Running). Arayüzdeki **Modelleri getir** düğmesi bağlantıyı
sınar ve yüklü modelleri listeler. Tarama başlamadan önce LM Studio'ya ulaşılıp ulaşılamadığı ve
seçilen sohbet/gömme modellerinin yüklü olup olmadığı denetlenir; sorun varsa tarama başlamaz ve
hangi modelin eksik olduğunu ve LM Studio adresini yazan bir hata gösterilir.

Araç, verilen adresleri canlı olarak tarar.

## Denetim katmanları

**Sayfa katmanı** (sayfanın HTML'inden görülebilir)

- title, meta description, H1 varlığı ve uzunlukları
- görsellerde alt metni, canonical, `html lang`, içerik uzunluğu
- viewport (mobil uyum), JSON-LD/mikroveri, Open Graph, Twitter Card, favicon, meta robots

**Site katmanı**

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

## Modele verilen ek bağlam

Deney koşulu sabittir: **`ornek+bilgi`**. Modele her taramada few-shot örnekler
(`ogretme/ornekler.json`) ve SEO bilgi tabanından ilgili parçalar (`ogretme/bilgi_tabani.json`)
verilir; arayüzde koşul seçeneği yoktur.

Bir **gömme (embedding) modeli** seçilirse bilgi parçaları anlamsal getirmeyle (RAG) seçilir:
sorgu ve parçalar vektöre çevrilip kosinüs benzerliğiyle en alakalı olanlar alınır. Gömme modeli
seçilmezse anahtar kelime eşleştirmesi kullanılır. Gömme modeli seçildiği hâlde ulaşılamazsa
anahtar kelimeye sessizce geçilmez, hata verilir. Kullanılan yöntem raporda `ogretme_yontemi`
alanında yazar (`anlamsal` / `anahtar_kelime`).

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

Her taramanın çıktısı `sonuclar/<site adı>/sonuc_<YYYY-MM-DD_HH-MM-SS>/` klasörüne yazılır.
Site adı adresin alan adından türetilir (`https://www.ornek.com.tr/x` → `ornek.com.tr`).
Bir taramada birden fazla site varsa her site kendi klasörüne, aynı zaman damgasıyla yazılır:

- `rapor.json` — sayfa başına tüm bulgular, öneriler, reddedilenler, ölçümler
- `ozet.csv` — karşılaştırma tablosu (tarama bitince kendiliğinden yazılır)
- `site_geneli.json` — sayfalar arasında tekrar eden title / meta açıklama / H1 grupları
  (tekrarlar tüm tarama üzerinden bulunur; farklı sitelerde aynı meta açıklama da yakalanır)
- `duzeltilmis_*.html` — düzeltmelerin uygulandığı sayfalar

## Deney matrisi

Model × retry kombinasyonlarını tek komutla çalıştırır (koşul sabit: `ornek+bilgi`). Her
kombinasyon `sonuclar/<site>/sonuc_<tarih_saat>/<model>__ornek_bilgi__r<retry>/` klasörüne,
her sitenin karşılaştırması `sonuclar/<site>/sonuc_<tarih_saat>/karsilastirma.csv` dosyasına yazılır.
Başlamadan önce tüm modeller denetlenir; biri eksikse deney hiç başlamaz.

```
py deney.py --adresler test_setleri/duzce_birimleri.txt --modeller qwen/qwen3.5-9b ^
            --retry 0,1 --embed-model text-embedding-qwen3-embedding-0.6b
```

## Bağımsız ölçüm (isteğe bağlı)

Arayüzdeki "Lighthouse SEO puanını da al" seçeneği, Google PageSpeed Insights
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
Böylece birkaç sorun ölçeği 0'a indirmez. Hata sayfasında (4xx/5xx) sayfa katmanı denetlenmez ve
"ölçülmedi" olarak gösterilir. Eski tek puan (`once_puan` /
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
