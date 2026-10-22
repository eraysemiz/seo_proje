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

Dil modeliyle tarama için LM Studio'nun açık ve sunucusunun çalışır durumda
olması gerekir (Developer sekmesi → Running). Arayüzdeki **Modelleri getir** düğmesi bağlantıyı
sınar ve yüklü modelleri listeler. Tarama başlamadan önce LM Studio'ya ulaşılıp ulaşılamadığı ve
seçilen sohbet/gömme modellerinin yüklü olup olmadığı denetlenir; sorun varsa tarama başlamaz ve
hangi modelin eksik olduğunu ve LM Studio adresini yazan bir hata gösterilir.

Dil modeli olmadan çalışmak için **Dil modeli kullanma, yalnızca denetle** seçeneği açıkça
işaretlenmelidir. Bu durumda LM Studio gerekmez, tüm denetimler ve kural tabanlı düzeltmeler
çalışır, yalnızca title/meta/H1/alt metni önerisi üretilmez. Model seçilmemişse ve bu seçenek
kapalıysa tarama sessizce modelsiz devam etmez, hata verir.

**Tarama kapsamı:**

- *Yalnızca listedeki adresler* — her satırdaki adres ayrı ayrı denetlenir.
- *Siteyi tara* — adresler başlangıç kabul edilir; site içi bağlantılar genişlik öncelikli (BFS)
  izlenir (varsayılan en fazla 50 sayfa, 3 tıklama derinliği). Sitemap adresleri ikincil kuyruğa
  girer ve yalnızca bağlantıyla ulaşılacak sayfa kalmayınca taranır; böylece hiçbir sayfadan
  bağlantı almayan (yetim) sayfalar ayırt edilir. nofollow bağlantılar ve nofollow sayfaların
  bağlantıları izlenmez; PDF, görsel gibi HTML olmayan adresler kuyruğa alınmaz.

## Denetim katmanları

**Sayfa katmanı** (sayfanın HTML'inden görülebilir)

- title (eksik, kısa, uzun, **piksel genişliği**), meta description (`name` büyük/küçük harf
  duyarsız), H1 varlığı ve uzunlukları, boş H2-H6, başlık sırası
- görsellerde alt metni, width/height, eski biçim (JPEG/PNG/GIF), tembel yükleme (ilk görsel
  tembel mi, alttakiler değil mi)
- `html lang`, ince içerik (menü/alt bilgi dışındaki ana içerik bölümünün kelime sayısı)
- **indekslenebilirlik:** tüm `robots` ve `googlebot` meta etiketleri birlikte (`noindex`, `none`,
  `nofollow`); **canonical** çoklu, boş, `<head>` dışı, göreli, başka adrese işaret eden (çapraz),
  noindex ile çelişen, HTTP `Link` başlığıyla çelişen
- **yönlendirme:** meta refresh, JavaScript yönlendirmesi
- viewport (yakınlaştırmayı engelliyor mu, sabit genişlik mi), JSON-LD/mikroveri (`@graph` dahil,
  türe göre zorunlu alanlar), kuruluş türü (yalnızca ana sayfada), Open Graph (`og:image` dahil),
  Twitter Card, favicon, hreflang (ISO 639-1 dil kodu, `en-UK` gibi hatalı bölge, x-default,
  kendine referans), karışık içerik (`srcset` ve CSS `url()` dahil)
- **bağlantılar:** boş ve anlamsız bağlantı metni ("tıklayın", "devamı"), site içi nofollow,
  çıkmaz sayfa; içeriği JavaScript'e bağlı sayfa iskeleti (tahmin)

**Site katmanı** (canlı erişimle)

- robots.txt: var mı, geçerli mi, sitemap bildiriyor mu, sayfayı engelliyor mu
- sitemap.xml: erişilebilir mi, geçerli XML mi, kaç adres içeriyor, sayfa listede mi, açılmayan
  sitemap adresleri, 50 MB / 50.000 adres sınırı, noindex sayfa sitemap'te mi
- HTTPS: şema, http→https yönlendirmesi, sertifika süresi ve **zincir bütünlüğü**, HSTS
- durum kodu, yönlendirme zinciri, **yönlendirme döngüsü**, 10'dan uzun zincir, Location'sız
  3xx, geçici (302/303/307) yönlendirme, `Refresh` başlığı, `X-Robots-Tag` (bota özel satırlar dahil)
- **bağlantı ve görsel denetimi:** kırık site içi ve dış bağlantılar, yönlendirilen site içi
  bağlantılar, kırık ve 200 KB'tan büyük görseller (HEAD, gerekirse GET; farklı host'lar paralel,
  aynı host'a sırayla ve beklemeli)
- Hız/boyut: TTFB, indirme süresi, HTML boyutu, sıkıştırma (gzip/br), dış kaynak sayısı;
  PageSpeed açıksa **Core Web Vitals** (LCP, INP, CLS) ve toplam sayfa ağırlığı

**Tarama geneli** (puana katılmaz; site özetinde gösterilir)

- tekrar eden title / meta açıklama / H1
- birebir aynı ve %90 üstü benzer ana içerik (5 kelimelik parçaların MinHash imzası)
- yetim sayfa, 3'ten fazla tıklama derinliği, karşılıklı olmayan hreflang
- her sayfa için tıklama derinliği ve kaç taranan sayfadan site içi bağlantı aldığı

**JavaScript render (isteğe bağlı):** bilgisayarda kurulu Chrome/Edge başlıksız çalıştırılır
(yeni bağımlılık yoktur; yol `CHROME_YOLU` ortam değişkeniyle de verilebilir). Sayfa render
sonrası DOM üzerinden denetlenir; ham HTML'e göre metin belirgin artıyorsa içerik JavaScript'e
bağlı sayılır.

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

Bilgi tabanı (`ogretme/bilgi_tabani.json`) Google Arama Merkezi ve W3C WAI belgelerine dayanan,
Türkçe yazılmış 28 parçadır. Her parçada `alan` (title, meta_description, h1, img_alt, genel…),
`baslik`, `etiketler`, `kaynak` (bağlantı), `kaynak_basligi` ve `erisim_tarihi` bulunur.

Bir **gömme (embedding) modeli** seçilirse parçalar hibrit getirmeyle (RAG) seçilir
(`seo_app/ogretme.py: bilgi_getir`):

1. **Metadata filtresi:** yalnızca sayfanın sorunlu alanlarına ve genel yönergelere ait parçalar aday olur.
2. **Sorgu:** sorun kodları yerine Türkçe açıklamaları, sayfa başlığı, site adı ve menüden ayıklanmış
   içerik özeti; gömme modeline uygun sorgu öneki (Qwen3 `Instruct:`, e5 `query:`, nomic `search_query:`).
3. **Sıralama:** kosinüs (anlamsal) ve BM25 (sözcüksel) sıralamaları ağırlıklı RRF ile birleştirilir
   (vektör 1,0, BM25 0,1). İsteğe bağlı bir yeniden sıralama (rerank) modeli son sırayı belirler.
4. **Seçim:** her sorunlu alandan en az bir parça, kalan yer en yüksek puanlılarla (`bilgi_sayisi`, varsayılan 5);
   toplam 1 600 karakteri aşarsa önce dolgu parçaları çıkarılır.

Parçalar isteme kimlikleriyle (`[t02] …`) eklenir; model her önerinin dayandığı parçaları `kaynaklar`
alanına yazar, verilmemiş kimlikler ayıklanır (`gecersiz_kaynak`). Raporda `ogretme_parcalar`
(kimlik, kaynak, puan), `getirme_ms` ve `kb_surum` (bilgi tabanı özeti) yer alır; arayüz her
önerinin yanında dayandığı yönergeyi kaynağına bağlantıyla gösterir. Parça vektörleri
`bilgi_tabani_gomme_cache.json` dosyasında model başına saklanır; bilgi tabanı değişince yalnızca
değişen parçalar yeniden gömülür ve artık olmayanlar önbellekten silinir.

Gömme modeli seçilmezse `seo_kurallari.json` içinden sorunlu alanlara ait kurallar eklenir
(`anahtar_kelime`). Gömme ya da yeniden sıralama modeli seçildiği hâlde ulaşılamazsa sessizce başka
yönteme geçilmez, hata verilir.

**Yeniden sıralama (isteğe bağlı):** LM Studio bir `/rerank` ucu sunmaz; `bge-reranker-v2-m3` gibi
bir model llama.cpp sunucusunda (`llama-server --reranking`) çalıştırılıp `deney.py --rerank-url
http://127.0.0.1:8012/v1 --rerank-model bge-reranker-v2-m3` ile kullanılabilir.

**Not (Windows):** `localhost` önce IPv6 adresine çözüldüğü için LM Studio'ya giden her istek
yaklaşık 2 saniye gecikiyordu; istekler artık doğrudan `127.0.0.1` adresine gider.

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
- `site_geneli.json` — tarama geneli bulgu grupları: tekrar eden title / meta / H1, kopya ve
  benzer içerik, yetim ve derin sayfalar, karşılıklı olmayan hreflang
- `site_ozeti.json` — site bazlı özet: her sorun için önem, etkilenen sayfa sayısı, örnek sayfalar
  ve düzeltme önerisi (en çok puan kaybettiren üstte)
- `rapor.html` — tek dosyalık, internetsiz açılan, yazdırılabilir rapor (site özeti, sayfa tablosu,
  sorun başına açıklama ve "nasıl düzeltilir")
- `duzeltilmis_*.html` — düzeltmelerin uygulandığı sayfalar

Arayüzden `rapor.html`, `rapor.json` ve `ozet.csv` indirilebilir. Her sorunun yanında somut bir
düzeltme önerisi gösterilir (`kurallar.DUZELTME`).

## Deney matrisi

Model × koşul × retry kombinasyonlarını tek komutla çalıştırır. Arayüzde koşul sabittir
(`ornek+bilgi`); burada `--kosullar sifir,ornek,bilgi,ornek+bilgi` ile bilgi tabanının ve örneklerin
katkısı ölçülebilir (varsayılan `ornek+bilgi`). Her
kombinasyon `sonuclar/<site>/sonuc_<tarih_saat>/<model>__<kosul>__r<retry>/` klasörüne,
her sitenin karşılaştırması `sonuclar/<site>/sonuc_<tarih_saat>/karsilastirma.csv` dosyasına yazılır.
Başlamadan önce tüm modeller denetlenir; biri eksikse deney hiç başlamaz.

```
py deney.py --adresler test_setleri/duzce_birimleri.txt --modeller qwen/qwen3.5-9b ^
            --retry 0,1 --embed-model text-embedding-qwen3-embedding-0.6b
py deney.py --adresler test_setleri/duzce_birimleri.txt --modeller qwen/qwen3.5-9b --retry 1 ^
            --kosullar sifir,bilgi,ornek+bilgi --embed-model text-embedding-qwen3-embedding-0.6b
```

## Bilgi getirme (RAG) ölçümü

`rag_degerlendir.py` dil modeli çalıştırmadan, yalnızca gömme modeliyle getirme kalitesini ölçer.
Ölçüm seti `tests/veri/rag_degerlendirme.json`, 133 sayfa ve 9 gruptan oluşur:

- 60 sayfa kayıtlı HTML'lerden (`--veri-olustur`; 58 Düzce Üniversitesi birim sitesi, 2 üniversite anasayfası)
- 73 sayfa `test_setleri/rag_ek_siteler.txt` listesindeki 43 siteden canlı indirildi (`--veri-ekle`):
  üniversite, kamu, belediye, haber, e-ticaret, sağlık, blog/medya, STK/kültür. Her sitenin anasayfası ve
  bir iç sayfası alınır, robots.txt'ye uyulur. Depoya HTML değil, yalnızca çıkarılmış alanlar yazılır.

Altın etiketler sorun kodlarından türetilir:

- **kapsama:** sayfanın sorunlu alanlarından en az bir parçayla kapsananların oranı
- **isabet:** getirilen parçalardan ilgili olanların oranı (sorunlu alan ya da genel yönerge)
- **MRR:** sorunlu alana ait ilk parçanın sırasının tersi
- **sorun isabeti:** her sorun için tanımlı altın parçalardan (örneğin `title_uzun` → t02/t04/t05)
  en az biri seçilmiş mi

```
py rag_degerlendir.py --embed-model text-embedding-qwen3-embedding-0.6b
py rag_degerlendir.py --embed-model a,b,c --siralama vektor      # modelleri / sıralamaları karşılaştır
py rag_degerlendir.py --veri-ekle test_setleri/rag_ek_siteler.txt
```

Sonuçlar grup kırılımıyla birlikte `sonuclar/rag_degerlendirme/` altına yazılır.
22 Ekim 2026 ölçümü, 133 sayfa, qwen3-embedding-0.6b:

| | Kapsama | İsabet | MRR | Sorun isabeti | Getirme |
|---|---|---|---|---|---|
| Eski hat (k=3) | 0,487 | 0,514 | – | – | 44 ms* |
| Yeni hat, yalnız BM25 (k=5) | 1,000 | 1,000 | 0,937 | 0,796 | <1 ms |
| Yeni hat, yalnız vektör (k=5) | 1,000 | 1,000 | 0,969 | 0,905 | 38 ms |
| Yeni hat, ağırlıklı hibrit (k=5) | 1,000 | 1,000 | 0,969 | 0,909 | 39 ms |
| **+ t02 parçası tamamlandı (varsayılan)** | 1,000 | 1,000 | 0,969 | **0,935** | 36 ms |

\* Eski hat `localhost` ile sayfa başına 2 257 ms sürüyordu; tablodaki değer 127.0.0.1 ile ölçüldü.

Eski hattın isabeti Düzce dışındaki sitelerde çok daha düşüktür (haber 0,30, e-ticaret 0,30,
blog/medya 0,11). Kapsama ve isabet yeni hatta tasarım gereği tavandadır; sıralama kalitesini sorun
isabeti ayırt eder. En zayıf sorun `title_kisa`'dır (29/45). Her sorun için ayrı alt sorgu denendi
ancak sorun isabetini 0,815'e düşürdüğü için alınmadı. t02 düzeltmesi aynı setteki sonuçlar görülerek
yapıldı; kazanç biraz iyimser olabilir, yeni sitelerle doğrulanması önerilir.

## Bağımsız ölçüm (isteğe bağlı)

Arayüzdeki "PageSpeed: Lighthouse SEO ve Core Web Vitals" seçeneği, Google PageSpeed Insights
üzerinden Lighthouse SEO ve performans puanını, Core Web Vitals değerlerini rapora ve CSV'ye ekler.
Gerçek kullanıcı (CrUX saha) verisi varsa LCP, INP ve CLS ondan (75. yüzdelik), yoksa laboratuvar
ölçümünden alınır; laboratuvarda INP olmadığı için yerine Total Blocking Time kullanılır ve bu
raporda belirtilir. Eşikler web.dev'deki iyi/kötü sınırlarıdır. Anahtarsız kullanımın günlük kotası
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
  Yönlendirmeler tek tek izlenir ve her ara adres de robots.txt'ye sorulur; yasaklı bir ara adres
  istenmez. Bağlantı denetimi de yasaklı adresleri istemez.
- İstekler arasında bekleme uygular ve kendini tanıtan bir User-Agent kullanır. Bağlantı
  denetiminde aynı host'a istekler sırayla ve beklemeyle gider; sayfa başına denetlenen adres
  sayısı sınırlıdır (varsayılan 60 site içi bağlantı, 20 dış bağlantı, 15 görsel).
- Sertifika doğrulaması başarısız olursa varsayılan olarak tarama durmaz: sayfa doğrulamasız
  indirilir ve durum yüksek önemli bir bulgu olarak raporlanır. "Sertifika doğrulanamazsa sayfayı
  indirme" seçeneğiyle bu kapatılabilir.

## Dosya düzeni

```
calistir.py              uygulamayı başlatır
deney.py                 deney matrisi koşucusu (komut satırı)
rag_degerlendir.py       bilgi getirme (RAG) ölçümü
tests/                   pytest testleri (tests/veri/: RAG ölçüm seti)
seo_app/
  bagimsiz.py            PageSpeed (Lighthouse) SEO puanı ve Core Web Vitals
  cikarma.py             HTML'den veri çıkarma
  kurallar.py            kural denetimi, çözüm yolu sınıflandırması, puanlama
  canli.py               canlı erişim denetimleri (robots, sitemap, HTTPS, hız)
  ogretme.py             few-shot ve bilgi tabanı (hibrit RAG)
  rag_olcum.py           getirme ölçütleri (kapsama, isabet, MRR, sorun isabeti)
  llm.py                 LM Studio istemcisi, öneri doğrulama
  uygula.py              önerilerin HTML'e işlenmesi, kural tabanlı düzeltmeler
  boru.py                tek sayfa analiz akışı, toplu/site taraması, bağlantı denetimi, alt site keşfi
  tarama.py              site taraması kuyruğu (BFS + sitemap), bağlantı grafiği bulguları
  render.py              Chrome/Edge ile JavaScript render
  rapor.py               tek dosyalık HTML rapor (sablonlar/rapor_cikti.html)
  web.py                 Flask arayüzü
  sablonlar/ statik/     arayüz dosyaları
ogretme/                 örnekler, bilgi tabanı, gömme önbelleği
test_setleri/            tarama adres listeleri
sonuclar/                tüm tarama çıktıları
```

Eski komut satırı sürümleri `outdated/` klasöründe geliştirme geçmişi olarak durmaktadır;
güncel motor `seo_app/` paketidir.
