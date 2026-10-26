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
  çıkmaz sayfa, `target="_blank"` dış bağlantıda `noopener` eksikliği; içeriği JavaScript'e bağlı
  sayfa iskeleti (tahmin)
- **yapısal veri (ek):** ana sayfadaki kuruluş verisinde `logo` ve `sameAs`; iki düzey derinlikteki
  sayfalarda BreadcrumbList; türe göre önerilen alanlar; yazılarda tarih bilgisi ve 2 yıldan eski
  `dateModified`/`datePublished`
- **içerik:** anahtar kelime doldurma (title'daki bir terimin ana içerikte %3'ten sık geçmesi,
  150+ kelimelik sayfalarda; %4 üstü "orta" önemde)
- **SEO Başlangıç Rehberi'ne göre:** yalnızca kimlikten oluşan adres (`url_aciklayici_degil`;
  anahtar kelime aranmaz), dosya adı ya da "resim" gibi genel sözcük olan alt metni
  (`alt_metni_anlamsiz`, model yeniden yazar), yorum/forum bölümündeki `ugc`/`nofollow`'suz dış
  bağlantı (`kullanici_baglantisi_isaretsiz`, kural `rel="ugc nofollow"` ekler), ara başlıksız 700+
  kelimelik metin (`uzun_metin_ara_baslik_yok`), başlıksız gömülü video (`video_baslik_yok`).
  Rehberin "odaklanmayın" dediği konulara göre: fazla H1 düşük önemde ve onay ister (yalnızca
  erişilebilirlik), başlık sırası erişilebilirlik bulgusudur, kelime sayısı hedef verilmez, kopya
  içerik puana tavan koymaz (ceza değil), sitemap yokluğu düşük önemdedir; meta keywords denetlenmez.
- **erişilebilirlik (HTML'den görülebilen):** etiketsiz form alanı, erişilebilir adı olmayan düğme,
  olmayan id'yi gösteren `aria-labelledby`/`aria-describedby`. Kontrast ve klavye gezintisi gerçek
  tarayıcı ister, denetlenmez.

**Site katmanı** (canlı erişimle)

- robots.txt: var mı, geçerli mi, sitemap bildiriyor mu, sayfayı engelliyor mu, tanınmayan ya da
  yazım hatalı yönerge var mı, sayfanın CSS/JS dosyalarını engelliyor mu
- canonical'ın gösterdiği adres hata kodu döndürüyor mu (kırık canonical)
- sitemap.xml: erişilebilir mi, geçerli XML mi, kaç adres içeriyor, sayfa listede mi, açılmayan
  sitemap adresleri, 50 MB / 50.000 adres sınırı, noindex sayfa sitemap'te mi
- HTTPS: şema, http→https yönlendirmesi, sertifika süresi ve **zincir bütünlüğü**, HSTS;
  güvenlik başlıkları (X-Content-Type-Options, X-Frame-Options ya da CSP frame-ancestors, CSP)
- durum kodu, yönlendirme zinciri, **yönlendirme döngüsü**, 10'dan uzun zincir, Location'sız
  3xx, geçici (302/303/307) yönlendirme, `Refresh` başlığı, `X-Robots-Tag` (bota özel satırlar dahil)
- **bağlantı ve görsel denetimi:** kırık site içi ve dış bağlantılar, yönlendirilen site içi
  bağlantılar, kırık ve 200 KB'tan büyük görseller (HEAD, gerekirse GET; farklı host'lar paralel,
  aynı host'a sırayla ve beklemeli); site içi CSS/JS ve görsellerde önbellek başlığı
  (Cache-Control max-age ya da Expires)
- Hız/boyut: TTFB, indirme süresi, HTML boyutu, sıkıştırma (gzip/br), dış kaynak sayısı;
  PageSpeed açıksa **Core Web Vitals** (LCP, INP, CLS) ve toplam sayfa ağırlığı

**Tarama geneli** (puana katılmaz; site özetinde gösterilir)

- tekrar eden title / meta açıklama / H1
- birebir aynı ve %90 üstü benzer ana içerik (5 kelimelik parçaların MinHash imzası)
- yetim sayfa, 3'ten fazla tıklama derinliği, karşılıklı olmayan hreflang, sitemap'te hata kodu
  döndüren adres (iki modda da)
- her sayfa için tıklama derinliği ve kaç taranan sayfadan site içi bağlantı aldığı

**JavaScript render (isteğe bağlı):** bilgisayarda kurulu Chrome/Edge başlıksız çalıştırılır
(yeni bağımlılık yoktur; yol `CHROME_YOLU` ortam değişkeniyle de verilebilir). Sayfa render
sonrası DOM üzerinden denetlenir; ham HTML'e göre metin belirgin artıyorsa içerik JavaScript'e
bağlı sayılır.

## Her sorunun bir çözüm kategorisi vardır

Rapordaki her bulgu üç kategoriden birine düşer. Kategoriler tek bir yapılandırmada tanımlıdır
(`seo_app/kategoriler.py`); arayüzdeki etiketler ve bilgi balonları buradan gelir:

- **Kural çözer**: deterministik bir kuralla güvenle düzeltilir. Örnekler: eksik lang, charset ya
  da viewport; fazla H1; kırık iç bağlantı; görsellere width/height; robots.txt ve sitemap
  düzeltmeleri. Yönetici modunda grup olarak toplu onaylanabilir; her zaman onay isteyen
  değişiklikler (ör. `Disallow` ekleyen robots.txt düzeltmesi) toplu onaya girmez, tek tek onaylanır.
- **YZ önerir**: yerel model ya da sezgisel bir yöntem öneri üretir ve insan onayı gerekir.
  Örnekler: title/meta/H1 yeniden yazımı, alt metni, ince içeriği genişletme, JSON-LD, yetim ya da
  derin sayfalara iç bağlantı. Canonical, noindex, yönlendirme, hreflang ve robots kararları
  **yüksek risklidir**; öneriyle birlikte olası etkisi gösterilir.
- **Elle düzeltilir**: yapay zekânın kapsamı dışındadır ve yalnızca raporda öneri olarak kalır.
  Örnekler: sunucu/barındırma ayarı, HTTPS, önbellek, gerçek görsel üretimi, firmaya özgü
  doğrulanmış bilgi, site dışı SEO.

Bu kategori gösterim ve yönetici modu içindir. Analiz akışında modele hangi sorunların gideceğini
`kurallar.cozum_yolu` belirler (`model` / `kural` / `elle`) ve bu değişmemiştir. Dil modeline
standart modda **yalnızca** `model` sorunları gönderilir.

## İki mod: standart ve yönetici

**Standart mod (Mod 2)** erişimimiz olmayan siteler içindir. Site indirilir, analiz edilir ve
raporlanır; siteye hiçbir şey yazılmaz. Yönetici moduyla aynı analizi ve aynı puanlamayı kullanır.
Doğruluk iyileştirmesinden (`dogruluk-iyilestirme` dalı) sonra standart modda da yeni denetimler
(charset, render'ı engelleyen betik, URL'de büyük harf, yumuşak 404, sitemap'te yönlendirme) ve yeni
puanlama geçerlidir. Önceki taramalarla puanlar doğrudan karşılaştırılamaz.

**Yönetici modu (Mod 1)** admin erişimimiz olan siteler içindir. Akış üç aşamalıdır:

1. **Başlangıç:** analiz → değişiklik planı.
2. **Otomatik düzeltmeler:** güven eşiğini geçen ve her zaman onay isteyen kurallara girmeyen
   değişiklikler tarama biter bitmez, onay beklemeden yazılır (önce tam yedek); site yeniden taranır.
3. **Onaylı düzeltmeler:** onay ekranında onaylanan, düzenlenen ya da reddedilen değişiklikler
   uygulanır; otomatik yazılmış bir değişiklik reddedilirse geri çekilir; site yeniden taranır.

Rapor üç aşamayı yan yana gösterir. Geri alma tüm aşamaları birlikte geri alır.

- **Hedef:** Site kök klasörü ve temel adres açıkça verilir. Yazma yalnızca bu klasöre yapılır.
  `..`, mutlak yol, sembolik bağlantı ve junction ile dışarı çıkış reddedilir. Aracın kendi
  klasörü ve `sonuclar/` hedef olamaz.
- **Yazma katmanı:** Siteye yazma `seo_app/yazma.py` içindeki adaptör arayüzünden geçer (oku, yaz,
  listele, yedekle, geri al). Şimdilik yalnızca yerel dosya sistemi adaptörü vardır.
  FTP/SFTP/CMS adaptörleri aynı arayüzle eklenebilir.
- **Değişiklik kaydı:** Her değişiklik yapılandırılmıştır: kategori, risk, dosya, satır/sütun,
  eski ve yeni değer, ilgili bulgu, gerekçe ve RAG kaynağı. Dosya yeniden yazılmaz; yalnızca ilgili
  parça değiştirilir, bu yüzden diff'ler okunur kalır.
- **YZ önerilerinin doğrulanması:** Model yalnızca sitedeki içerikten ve bilgi tabanından
  yararlanır. Sitede olmayan bir olgu gerekiyorsa `[doğrulanmalı: …]` yer tutucusu yazar; böyle bir
  öneri, değer elle doldurulmadan uygulanamaz. Her öneri şunlardan geçer: uzunluk, dil, bozuk
  karakter ve harfleri düşürülmüş Türkçe (cay/çay) denetimi; sayfada olmayan sayı, özel ad ve
  doğrulanamayan övgü denetimi; JSON-LD şeması. Geçemeyen öneri, ret nedeniyle birlikte modele bir
  kez daha sorulur; yine geçemezse uygulanmaz ve nedeniyle raporlanır. Bozuk JSON-LD sözdizimi ve
  fiyat/para birimi yazımı (`1.250` → `1250`, `TL` → `TRY`) modele gitmeden deterministik düzeltilir.
- **Güvenli uygulama:**
  - İlk yazmadan önce sitenin tam yedeği alınır; sonraki aşama aynı yedeği kullanır.
  - Her aşamada dosya, yedekteki özgün halinden yeniden kurulur: önceki aşamada uygulananlar ve yeni
    onaylananlar birlikte, her biri belge geçerliliği denetlenerek.
  - Plandan ya da önceki aşamadan sonra elle değişmiş dosyaya yazılmaz.
  - HTML, XML ya da JSON-LD geçerliliğini bozacak değişiklik uygulanmaz ve "Başarısız" raporlanır.
  - Her sonuç aşamasıyla birlikte günlüğe (`uygulama_gunlugu.jsonl`) ve diff'e (`uygulanan.diff`) yazılır.
  - Son uygulama (tüm aşamalar) tek komutla geri alınır ve dosya hash'leriyle doğrulanır; durumlar ve
    metrikler başlangıç haline döner.
- **Güven puanı ve onay** (`seo_app/guven.py`): Her değişikliğin 0–1 arası bir güven puanı ve düşük
  güven nedeni vardır. Puan şuna göre belirlenir:
  - Kural düzeltmeleri: kural başına sabit değer. Örneğin görsel boyutu 0,98; `defer` ekleme 0,60.
  - Sezgisel yapısal kararlar: kanıta göre. Örneğin canonical'ın gösterdiği sayfa 404 dönüyor ya da
    içerik ondan açıkça farklıysa güven yüksek; içerikler benzerse sayfa gerçekten kopya olabilir,
    güven düşük.
  - Dil modeli önerileri: alan tabanı (title/meta/H1 0,92, paragraf 0,70). Yeniden deneme ve önerideki
    kelimelerin kaynakta geçmeme oranı puanı düşürür.

  **Eşiği** (`oto_esik`, varsayılan 0,8; `--esik`, web formu, masaüstü) geçen değişiklikler otomatik
  aşamada onaysız yazılır ve onay ekranında reddedilebilir (geri çekilir); altındakiler onay ister. Şunlar güven ne olursa olsun her zaman
  onaya düşer: `[doğrulanmalı]` yer tutuculu içerik, sayfayı canonical ile başka sayfaya bağlayıp
  dizinden düşüren birleştirme, noindex/nofollow/Disallow ekleyen ve büyük bir içerik bloğunu silen
  değişiklikler. Onay ekranı güven puanını ve nedenini gösterir. Eşiğin altındaki yüksek riskli
  öneriler ayrıca risk onayı ister. Otomatik uygulananlar da aynı yedek, günlük, diff ve geri alma
  yolundan geçer.

- **Sorun durumları:** Başlangıç taramasındaki her (sorun, sayfa) bulgusunun bir durumu vardır:
  `Çözüldü (otomatik)`, `Çözüldü (onaylı)`, `Onay bekliyor`, `Reddedildi`, `Başarısız` (nedeniyle),
  `Elle düzeltilir`. "Çözüldü" yalnızca düzeltmeden sonraki yeniden taramada bulgu artık tespit
  edilmiyorsa verilir; uygulandığı halde hâlâ tespit edilen bulgu "Başarısız – düzeltme etkisiz" olur.
  Sayfa yeniden taramada yoksa (ör. sitemap'ten çıkarıldı) durum "Uygulandı, yeniden kontrol yapılmadı"
  olarak kalır. Durumlar `bulgu_durumlari.json`'a, yönetici raporuna, analiz raporuna (`rapor.html`,
  her sorunun yanında), web arayüzüne ve masaüstü özetine yazılır.
- **Sayaçlar tek kaynaktan:** genel, aşama başına ve sayfa başına bütün sayaçlar bulgu durumlarından
  hesaplanır (`yonetici.durum_sayaclari`, `sayfa_sayaclari`). **Aktif** = Onay bekliyor + Reddedildi +
  Başarısız + Elle düzeltilir (+ uygulanmış ama yeniden kontrolle doğrulanmamış); **Çözülen** = Çözüldü
  (otomatik) + Çözüldü (onaylı). Sayaç birimi sayfa bulgusu ya da **site geneli ayardır**: HTTPS,
  HTTPS yönlendirmesi, güvenlik/önbellek başlıkları, robots.txt'deki sitemap adresi gibi tek seferde
  düzelen bulgular her sayfada değil bir kez sayılır (tüm sayfalarda giderildiyse çözülmüş, bir sayfada
  bile sürüyorsa aktif) ve raporda "Site geneli ayarlar" bölümünde gösterilir. Tespit ve puanlama sayfa
  × sorun olarak kalır; ham sayı `sayaclar.ham_toplam`'dadır. **Takma adres bulguları** da ayrıca
  sayılmaz: aynı dosyayı açan yönlendirme ya da parametreli adresteki bulgu, asıl sayfada aynı kod varsa
  ona bağlanır ve durumunu ondan alır (asıl bulgu yeniden kontrole dayanır); yumuşak 404 / hata kodlu
  sayfanın içerik bulguları o tek sorunun altında sayılır (sitemap bulguları ve kendi düzeltmesi olanlar
  ayrı kalır). Asıl bulgunun yanında "ayrıca görüldüğü adresler" listelenir. Aktif + çözülen her zaman başlangıçtaki
  birim sayısına eşittir; düzeltmeyle yeni çıkan bulgular ayrı sayılır. Yönetici modunun `rapor.html`'inde her sayfa "Aktif
  sorunlar" ve "Çözülen sorunlar" (nasıl çözüldüğü, değişiklik özeti, güven puanı) olarak ayrılır; rapor
  her aşamadan ve geri almadan sonra yeniden üretilir ve önbelleğe alınmaz. Web arayüzü aynı sayıları
  sayfa yenilenmeden gösterir. Salt okunur modun raporu değişmez.
- **Çözüm oranı** = çözülen çözülebilir bulgu / çözülebilir bulgu. Çözülebilir: araçta bir düzeltme
  önerisi olan bulgu (onaylanmış, bekleyen, reddedilen ya da doğrulamadan geçemeyen). Önerisi olmayan
  "Elle düzeltilir" bulgular orana girmez, ayrı sayılır (başka bir düzeltmeyle dolaylı giderilenler de
  gösterilir). Her aşamanın değerleri o aşamadan sonraki yeniden taramadan ölçülür.
- **Yeniden kontrol tam taramadır:** Tekrar eden başlık, yetim sayfa, sitemap ve robots.txt gibi site
  geneli bulgular tüm sayfalara bağlı olduğu için yalnızca değişen sayfaları taramak (artımlı tarama)
  bunları yanlış ölçer. Her aşamadan sonra site baştan taranır (modelsiz; test sitesinde birkaç saniye).

Arayüzde mod formun ilk adımında seçilir; yönetici modunda kök klasör, temel adres ve güven eşiği
istenir. Komut satırından:

```
py yonet.py tara --kok test_sitesi/site --url http://127.0.0.1:8080/ --model qwen/qwen3.5-9b [--esik 0.8] [--oto-uygulama-yok]
                                   # plan + otomatik aşama (eşiği geçenler yazılır, site yeniden taranır)
py yonet.py onizle sonuclar/127.0.0.1/sonuc_<tarih_saat> [--diff]   # güven puanları ve onay bekleyenler
py yonet.py onayla <klasör> --onay D021 D030 --riski-kabul D030 --ret D033 --duzenle "D021=Yeni başlık | Site" [--esik 0.9]
py yonet.py uygula <klasör>        # onaylı aşama + yeniden tarama + üç aşamalı rapor
py yonet.py geri-al sonuclar/127.0.0.1 [--tekrar-tara]   # tüm aşamaları geri al
```

Yönetici modu klasöründe standart taramanın çıktılarına ek olarak şu dosyalar bulunur:
`degisiklikler.json` (plan ve aşamalar), `onizleme.diff`, `onaylar.json`, `yedek/`,
`uygulama_gunlugu.jsonl`, `uygulanan.diff`, `uygulama.json`, `sonra_otomatik/` ve `sonra/` (aşama
sonrası taramalar), `geri_alma/` (isteğe bağlı), `bulgu_durumlari.json` ve `yonetici_raporu.html`.

## Test sitesi

`test_sitesi/` altında yerelde çalışan, kurgusal bir çay mağazası sitesi var (Çaylıbahçe, 25 sayfa).
Sitede 47 kasıtlı SEO sorunu bulunur: 18 kolay, 16 orta, 13 zor. Sorunların kaydı ve değerlendirme
betikleri sitenin dışında, `test_sitesi_degerlendirme/` altındadır; analiz aracı bunlara erişemez.

```
py test_sitesi/sunucu.py                         # 1. siteyi başlat (yalnızca http://127.0.0.1:8080)
py test_sitesi_degerlendirme/dogrula.py          #    kayıtlı 47 sorunun sitede var olduğunu doğrula
py yonet.py tara --kok test_sitesi/site --url http://127.0.0.1:8080/ --model <model>   # 2. tara + otomatik aşama
py yonet.py onayla <klasör> --onay ... --ret ... # 3. (isteğe bağlı) eşiğin altındakileri onayla / reddet
py yonet.py uygula <klasör>                      # 4. onaylı aşama + tekrar tara
py test_sitesi_degerlendirme/degerlendir.py --sonuc <klasör>   # 5. değerlendir
py test_sitesi_degerlendirme/sifirla.py          # 6. sıfırla (hash doğrulamalı)
```

`degerlendir.py` her sorun için şunları raporlar ve `degerlendirme.md` dosyasına yazar:

- önce taramasında tespit edildi mi;
- canlı sitede düzeldi mi;
- araç sonra taramasında (`sonra/`, yoksa `sonra_otomatik/`) hâlâ buluyor mu;
- aracın "Çözüldü" dediği sorunlar canlı kontrolde de düzelmiş mi (tutarlılık; yanlış ve eksik
  "Çözüldü" ayrı listelenir). Analiz aracı `sorunlar.json`'u okumaz; bu karşılaştırma yalnızca
  değerlendirme betiğindedir.

Sonuçlar zorluğa, SEO alanına ve beklenen çözüm kategorisine göre özetlenir. Düzeltme sırasında
yeni çıkan bulgular ve kayıt dışında kalan bulgular da listelenir. Sıfırlama yalnızca
`test_sitesi/site/` klasörünü değiştirir.

## Masaüstü uygulaması (Windows)

Yukarıdaki komutların hepsi tek bir pencereden de çalıştırılabilir. Uygulama yalnızca bir arayüz
katmanıdır (`masaustu/`): her işlem mevcut betiği alt süreç olarak çalıştırır, çıktısı alttaki
panelde canlı görünür. Komut satırı kullanımı aynen geçerlidir.

```
py masaustu/baslat.py            # kaynaktan çalıştır (Tkinter, ek bağımlılık yok)
build_exe.bat                    # ya da: py build_exe.py  → dist/SEO_Denetim/SEO_Denetim.exe
```

| Sekme | İşlemler |
|---|---|
| Analiz | Mod (Yönetici / Salt okunur), site adresi, kök klasör, model seçimi, taramayı başlat; yönetici modunda tarama otomatik aşamayı da yürütür; ardından **önizle ve onayla** (kategoriye göre gruplu diff, YZ önerilerine tek tek onay/ret, otomatik yazılmış değişikliği geri çekme, yüksek risk onayı, değer düzenleme) ve **onaylı aşamayı uygula**; plan alanında üç aşamalı metrikler (sayfa puanı, sorun sayısı, çözüm oranı) ve sorun durumları görünür; tarayıcı arayüzünü (`calistir.py`) başlat/durdur |
| Test sitesi | Başlat / durdur / tarayıcıda aç, doğrula, sıfırla, hash karşılaştır, değerlendir |
| Sonuçlar | `sonuclar/` altındaki taramalar; rapor ve klasör açma, son uygulamayı geri alma |
| Ayarlar | Proje klasörü, LM Studio adresi, varsayılan modeller, portlar, ses |

- Alttaki durum çubuğu LM Studio'ya ulaşılıp ulaşılamadığını, seçilen modellerin yüklü olup
  olmadığını, test sitesi ve web arayüzünün çalışıp çalışmadığını gösterir.
- Aynı anda tek iş çalışır. Tarama ve doğrulama gibi işler **İptal** ile durdurulabilir.
  Uygulama, geri alma, sıfırlama ve onay kaydı siteye ya da sonuç klasörüne yazdığı için yarıda
  kesilmez. Siteye yazan işlemler önce onay penceresi gösterir.
- Her alt süreç bir Windows Job Object'e bağlıdır. Uygulama kapanınca, beklenmedik biçimde
  kapansa bile, başlattığı sunucular ve alt süreçler kapanır.
- Ayarlar `%APPDATA%\SEO Denetim Aracı\ayarlar.json` dosyasında tutulur (`--ayar` ile başka dosya).
  Proje klasörü ayarda yoksa .exe'nin bulunduğu klasörden yukarı doğru `yonet.py` aranır.
  .exe proje dışına taşındıysa klasör Ayarlar sekmesinden seçilir.
- `--oto-test rapor.json` tam döngüyü arayüz üzerinden kendiliğinden çalıştırır: test sitesi →
  doğrula → tarama → onay → uygula → değerlendir → geri al → iptal → sıfırla. Sonunda geride
  süreç kalmadığını denetleyip raporu JSON olarak yazar. `SEO_OTO_MODELSIZ=1` ile tarama modelsiz
  yapılır.

**Derleme.** `build_exe.py`, uv ile `build/venv313` altında ayrı bir Python 3.13 ortamı kurar.
PyInstaller yalnızca bu ortama yüklenir, projenin bağımlılıklarına eklenmez. Varsayılan çıktı
*onedir* biçimindedir: hızlı açılır ve antivirüs yazılımlarına daha az takılır.
`--onefile` tek dosya üretir, ama her açılışta kendini geçici klasöre açtığı için birkaç saniye geç
başlar ve yanlış alarma daha sık takılır. .exe yalnızca Python çalışma ortamını, arayüzü ve
kütüphaneleri içerir. `seo_app/`, betikler, `ogretme/` (gömme önbelleği dahil), `sonuclar/` ve
test sitesi gömülmez, proje klasöründen okunur. Bu yüzden kod değişikliği için yeniden derlemek
gerekmez. İkon `masaustu/ikon.ico` dosyasıdır; `masaustu/ikon_uret.py` ile yeniden üretilir ya da
aynı adla başka bir ikon konabilir.

## Modele verilen ek bağlam

Deney koşulu sabittir: **`ornek+bilgi`**. Modele her taramada few-shot örnekler
(`ogretme/ornekler.json`) ve SEO bilgi tabanından ilgili parçalar (`ogretme/bilgi_tabani.json`)
verilir; arayüzde koşul seçeneği yoktur.

Bilgi tabanı (`ogretme/bilgi_tabani.json`) Google Arama Merkezi ve W3C WAI belgelerine dayanan,
Türkçe yazılmış 51 parçadır. Her parçada `alan` (title, meta_description, h1, img_alt, genel…),
`baslik`, `etiketler`, `kaynak` (bağlantı), `kaynak_basligi` ve `erisim_tarihi` bulunur.
23 parça Google'ın [SEO Başlangıç Rehberi](https://developers.google.com/search/docs/fundamentals/seo-starter-guide?hl=tr)'nin
bölümlerinin kendi cümlelerimizle özetidir (alıntı değil; içerik CC BY 4.0, atıf: Google Arama Merkezi).
Bunlarda `kaynak` bölüm çapalı Türkçe sayfayı, `kaynak_en` aynı bölümün İngilizcesini gösterir ve
`lisans` alanı bulunur. Bilgi tabanı elle güncellenir; bir çekme/güncelleme komutu yoktur.
Değişen parçaların gömmesi bir sonraki kullanımda içerik hash'iyle yeniden hesaplanır.

Few-shot örneklerin 5'i rehbere dayanır (`kaynak.etiket = "google-starter-guide"`; `kaynak` alanı
isteme girmez). Model alanları dışındaki tavsiyeler için sorunlu → tavsiye → düzeltilmiş HTML
örnekleri `ogretme/rehber_ornekleri.json`'dadır; bu dosya isteme girmez, belge ve test içindir.

Bir **gömme (embedding) modeli** seçilirse parçalar hibrit getirmeyle (RAG) seçilir
(`seo_app/ogretme.py: bilgi_getir`):

1. **Metadata filtresi:** yalnızca sayfanın sorunlu alanlarına ve genel yönergelere ait parçalar aday olur.
   Modelin metin yazmadığı bulgular (canonical, kopya içerik, adres, bağlantı metni, robots/sitemap…)
   yalnızca getirme için `BILGI_ALANI_SORUN` ile kendi alanlarına bağlanır; yönetici modunun YZ
   önerileri böylece ilgili parçaları alır. Mod 2'de modele giden alanlar değişmez.
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
güvenlik ve performans kategori puanları vardır. Hesap ve ağırlıklar tek yapılandırmadadır
(`seo_app/puanlama.py`):

- Her sorun puanı kendi ağırlığı oranında düşürür: yüksek %20, orta %9, düşük %3,5. Aynı gruptaki
  sorunlar bir kez sayılır. Puan = 100 × Π(1 − ağırlık).
- Kritik sorunlarda üst sınır vardır: noindex 60, robots engeli 50, yumuşak 404 40, kopya içerik 70,
  title yok 75.
- Sayfa puanına o sayfaya ait site bulguları (kırık bağlantı, yönlendirme, sitemap…) ve sayfayı
  içeren tarama geneli bulgular (tekrar eden title/meta/H1, kopya içerik, yetim sayfa) da girer.
  HTTPS gibi site geneli sorunlar site puanında görünür. Yönlendirme ile aynı sayfaya düşen adresler
  ve doğru canonical'lar kopya sayılmaz.

Önceki hesap cezayı "olabilecek tüm sorunların cezasına" (227) bölüyordu. Bu yüzden yüksek önemli bir
sorun sayfa puanını yalnızca 6,6 puan düşürüyor, 47 kasıtlı sorunlu test sitesinde sayfaların 26/29'u
90'ın üzerinde çıkıyordu. Yeni hesapla ortalama 95,3'ten 78,8'e indi. En az iki gerçek sorunu olan 14
sayfanın 90 ve üstü alanı 13'ten 2'ye düştü. Hata sayfasında (4xx/5xx) sayfa katmanı denetlenmez ve
"ölçülmedi" olarak gösterilir. Eski tek puan (`once_puan` / `sonra_puan`) deney karşılaştırılabilirliği
için raporda korunur.

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
yonet.py                 yönetici modu komut satırı (tara, onizle, onayla, uygula, geri-al)
deney.py                 deney matrisi koşucusu (komut satırı)
rag_degerlendir.py       bilgi getirme (RAG) ölçümü
build_exe.py / .bat      masaüstü uygulamasını derler (dist/SEO_Denetim/)
masaustu/                masaüstü başlatıcı (Tkinter): baslat.py, uygulama.py, onay ekranı, salt_okunur.py, oto_test.py
tests/                   pytest testleri (tests/veri/: RAG ölçüm seti)
seo_app/
  bagimsiz.py            PageSpeed (Lighthouse) SEO puanı ve Core Web Vitals
  cikarma.py             HTML'den veri çıkarma
  kurallar.py            kural denetimi, çözüm yolu sınıflandırması, puanlar, tekrar/takma ad denetimi
  puanlama.py            puan ağırlıkları, kritik sorun tavanları, bulguların sayfaya atanması (tek yapılandırma)
  guven.py               düzeltme güven puanı, otomatik onay eşiği, her zaman onay isteyen durumlar
  canli.py               canlı erişim denetimleri (robots, sitemap, HTTPS, hız)
  ogretme.py             few-shot ve bilgi tabanı (hibrit RAG)
  rag_olcum.py           getirme ölçütleri (kapsama, isabet, MRR, sorun isabeti)
  llm.py                 LM Studio istemcisi, öneri doğrulama
  uygula.py              önerilerin HTML'e işlenmesi, kural tabanlı düzeltmeler
  boru.py                tek sayfa analiz akışı, toplu/site taraması, bağlantı denetimi, alt site keşfi
  tarama.py              site taraması kuyruğu (BFS + sitemap), bağlantı grafiği bulguları
  render.py              Chrome/Edge ile JavaScript render
  rapor.py               tek dosyalık HTML rapor (sablonlar/rapor_cikti.html)
  kategoriler.py         bulgu kategorileri (Kural çözer / YZ önerir / Elle düzeltilir), risk ve olası etki
  yazma.py               yönetici modu yazma katmanı (adaptör arayüzü, yerel dosya adaptörü, yol güvenliği)
  html_konum.py          HTML etiketlerinin kaynak metindeki konumları
  duzeltme.py            değişiklik planı, önizleme diff'i, güvenli uygulama
  yz_oneri.py            YZ önerileri: model + RAG + uydurma/dil/JSON-LD doğrulaması
  yonetici.py            yönetici modu akışı, geri alma, önce/sonra raporu (sablonlar/yonetici_rapor.html)
  web.py                 Flask arayüzü
  sablonlar/ statik/     arayüz dosyaları
ogretme/                 örnekler, bilgi tabanı, gömme önbelleği
test_setleri/            tarama adres listeleri
test_sitesi/             yerel test sitesi (sunucu.py, sunucu_ayarlari.json, site/)
test_sitesi_degerlendirme/  sorunlar.json, dogrula.py, degerlendir.py, sifirla.py, orijinal_site/
sonuclar/                tüm tarama çıktıları
```

Eski komut satırı sürümleri `outdated/` klasöründe geliştirme geçmişi olarak durmaktadır;
güncel motor `seo_app/` paketidir.
