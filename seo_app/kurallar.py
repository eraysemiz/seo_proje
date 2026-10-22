"""Kural tabanli (modelsiz) SEO denetimi ve puanlama.

Sorunlar iki katmanda toplanir:
  katman="sayfa" -> sayfanin HTML'inden gorulebilir
  katman="site"  -> yalnizca canli erisimde olculebilir (robots.txt, sitemap, HTTPS, hiz...)
Model yalnizca sayfa katmanindaki belirli alanlar icin oneri uretir; site katmani
kural tabanli duzeltme veya elle mudahale gerektirir.
"""
import re
from collections import defaultdict
from urllib.parse import urljoin, urlparse

from .cikarma import (GENEL_BAGLANTI_METINLERI, GENEL_KOKLER, SERP_GENISLIK, baslik_piksel, imza_benzerligi,
                      kokler, tr_lower, url_anahtari)

# modelin degistirmesine izin verilen alanlar
IZINLI_ALANLAR = ("title", "meta_description", "h1", "img_alt")
# modelsiz, belirli (deterministik) olarak duzeltilebilen sorunlar
KURAL_SORUNLARI = ("canonical_yok", "html_lang_yok", "h1_birden_fazla", "viewport_yok", "og_etiketleri_yok")
# her alan hangi kural sorunlariyla iliskili (gereksiz degisikligi yakalamak icin)
ALAN_SORUN = {"title": ("title_yok", "title_kisa", "title_uzun", "title_genis"),
              "meta_description": ("meta_description_yok", "meta_description_kisa", "meta_description_uzun"),
              "h1": ("h1_yok",), "img_alt": ("img_alt_eksik",)}

CIDDIYET_AGIRLIK = {"yuksek": 15, "orta": 8, "dusuk": 3}

ACIKLAMA = {
    "title_yok": "Sayfa başlığı (title) yok",
    "title_kisa": "Sayfa başlığı çok kısa (30 karakterden az)",
    "title_uzun": "Sayfa başlığı çok uzun (60 karakterden fazla)",
    "meta_description_yok": "Meta açıklama yok",
    "meta_description_kisa": "Meta açıklama çok kısa (70 karakterden az)",
    "meta_description_uzun": "Meta açıklama çok uzun (160 karakterden fazla)",
    "h1_yok": "Sayfada H1 başlığı yok",
    "h1_birden_fazla": "Sayfada birden fazla H1 var",
    "h1_bos": "Metni olmayan H1 var (boş ya da yalnızca görsel içeriyor)",
    "img_alt_eksik": "Bazı görsellerde alt metni yok",
    "canonical_yok": "Canonical (asıl adres) etiketi yok",
    "html_lang_yok": "html etiketinde dil (lang) bilgisi yok",
    "icerik_az": "Metin içeriği az (300 kelimeden az)",
    # --- site katmani ---
    "robots_yok": "robots.txt dosyası bulunamadı",
    "robots_okunamadi": "robots.txt okunamadı veya hatalı",
    "robots_tum_siteyi_engelliyor": "robots.txt tüm siteyi aramaya kapatıyor",
    "robots_sayfayi_engelliyor": "robots.txt bu sayfanın taranmasını engelliyor",
    "robots_sitemap_bildirilmemis": "robots.txt içinde Sitemap satırı yok",
    "sitemap_yok": "sitemap.xml bulunamadı",
    "sitemap_gecersiz": "sitemap.xml okunamıyor veya geçerli XML değil",
    "sitemap_bos": "sitemap.xml içinde adres yok",
    "sayfa_sitemapte_yok": "Bu sayfa sitemap içinde listelenmemiş",
    "https_yok": "Site HTTPS kullanmıyor",
    "https_yonlendirme_yok": "http adresi https adresine yönlendirilmiyor",
    "sertifika_suresi_dolmus": "SSL sertifikasının süresi dolmuş",
    "sertifika_zinciri_eksik": "Sunucu eksik/yanlış ara sertifika gönderiyor (katı istemciler bağlanamaz)",
    "sertifika_dogrulanamadi": "SSL sertifikası doğrulanamadı",
    "erisilemedi": "Sayfaya canlı olarak erişilemedi",
    "sertifika_yakinda_bitiyor": "SSL sertifikasının süresinin dolmasına 30 günden az kaldı",
    "uzun_yonlendirme_zinciri": "Adres birden fazla yönlendirmeden geçiyor",
    "hata_durum_kodu": "Sunucu başarılı olmayan bir durum kodu döndürdü",
    "hsts_yok": "HSTS (Strict-Transport-Security) başlığı yok",
    "yavas_yanit": "Sunucu yanıt süresi yüksek (TTFB 1 saniyeden fazla)",
    "cok_yavas_yanit": "Sunucu yanıt süresi çok yüksek (TTFB 2,5 saniyeden fazla)",
    # brotli paketi kuruluysa gzip/deflate/br, degilse gzip/deflate istenir (canli._kodlamalar)
    "sikistirma_yok": "Yanıt sıkıştırılmamış (gzip/deflate/br ile istendi, sıkıştırılmadı)",
    "html_cok_buyuk": "HTML belgesi çok büyük (500 KB üstü)",
    "cok_fazla_kaynak": "Sayfa çok sayıda dış kaynak yüklüyor (100 üstü)",
    "viewport_yok": "Mobil uyum için viewport meta etiketi yok",
    "yapisal_veri_yok": "Yapısal veri (schema.org/JSON-LD) yok",
    "yapisal_veri_gecersiz": "JSON-LD yapısal verisi okunamıyor",
    "og_etiketleri_yok": "Open Graph (og:) paylaşım etiketleri yok",
    "twitter_card_yok": "Twitter Card etiketi yok",
    "favicon_yok": "Favicon (site simgesi) tanımlanmamış",
    "noindex": "Sayfa noindex ile aramaya kapatılmış",
    # --- baslik yapisi, uluslararasilastirma, yapisal veri turu, guvenlik ---
    "baslik_atlamasi": "Başlık hiyerarşisinde seviye atlanıyor (örneğin H1'den H3'e)",
    "hreflang_gecersiz": "hreflang değeri geçerli bir dil/bölge kodu değil",
    "hreflang_x_default_yok": "hreflang kullanılıyor ama x-default tanımlı değil",
    "schema_kurum_turu_yok": "Ana sayfanın yapısal verisinde kuruluş türü (Organization veya alt türü) yok",
    "karisik_icerik": "HTTPS sayfa http:// üzerinden kaynak yüklüyor (karışık içerik)",
    # --- odak terim tutarliligi ---
    "title_h1_uyumsuz": "Sayfa başlığı (title) ile H1 ortak hiçbir anahtar terim içermiyor",
    "title_icerikle_uyumsuz": "Sayfa başlığındaki terimler sayfa içeriğinde geçmiyor",
    # --- sayfalar arasi (tarama geneli) ---
    "title_tekrar": "Aynı sayfa başlığı (title) başka sayfalarda da kullanılıyor",
    "meta_tekrar": "Aynı meta açıklama başka sayfalarda da kullanılıyor",
    "h1_tekrar": "Aynı H1 başlığı başka sayfalarda da kullanılıyor",
    "icerik_tekrar": "Sayfa metni başka sayfalarla birebir aynı (kopya içerik)",
    "icerik_benzer": "Sayfa metni başka sayfalarla büyük ölçüde aynı (%90 üstü benzerlik)",
    "yetim_sayfa": "Sitemap'te olan ama taranan hiçbir sayfadan bağlantı almayan sayfa (yetim)",
    "derin_sayfa": "Sayfaya başlangıç sayfasından 3'ten fazla tıklamayla ulaşılıyor",
    "hreflang_donus_yok": "hreflang ile gösterilen sayfa bu sayfaya geri bağlantı vermiyor",
    # --- ek sayfa denetimleri ---
    "title_genis": "Sayfa başlığı arama sonucuna sığmayacak kadar geniş (yaklaşık 580 pikselden fazla)",
    "sayfa_nofollow": "Sayfa nofollow ile işaretli; sayfadaki bağlantılar izlenmiyor",
    "canonical_coklu": "Sayfada birbirinden farklı birden fazla canonical var",
    "canonical_bos": "Canonical etiketinin adresi (href) boş",
    "canonical_head_disi": "Canonical etiketi <head> dışında (arama motorları yok sayar)",
    "canonical_capraz": "Canonical başka bir adresi gösteriyor (sayfa asıl adres değil)",
    "canonical_goreli": "Canonical göreli adres kullanıyor (tam adres önerilir)",
    "canonical_baslik_catismasi": "HTTP Link başlığındaki canonical ile HTML'deki canonical farklı",
    "noindex_canonical_catismasi": "Sayfa noindex ama canonical başka bir adresi gösteriyor (çelişkili sinyal)",
    "meta_refresh": "Sayfa meta refresh veya Refresh başlığıyla yönlendiriyor",
    "js_yonlendirme": "Sayfada JavaScript ile yönlendirme var",
    "js_bagimli_icerik": "Sayfa içeriği JavaScript ile oluşuyor; ham HTML'de neredeyse metin yok",
    "bos_baslik": "Metni olmayan H2-H6 başlığı var",
    "viewport_sorunlu": "Viewport yakınlaştırmayı engelliyor ya da sabit genişlik veriyor",
    "og_gorsel_yok": "Open Graph etiketleri var ama og:image yok",
    "yapisal_veri_eksik_alan": "Yapısal veride zorunlu alanlar eksik",
    "hreflang_kendine_referans_yok": "hreflang listesinde sayfanın kendisi yok",
    "bos_baglanti_metni": "Metni olmayan bağlantılar var (anchor metni boş)",
    "genel_baglanti_metni": "Bağlantı metni anlamsız (\"tıklayın\", \"devamı\" gibi)",
    "ic_nofollow": "Site içi bağlantılarda nofollow kullanılmış",
    "ic_baglanti_yok": "Sayfada başka bir site içi sayfaya bağlantı yok (çıkmaz sayfa)",
    "gorsel_boyut_yok": "Görsellerde width/height boyutu belirtilmemiş (düzen kayması riski)",
    "gorsel_eski_format": "Görseller eski biçimde (JPEG/PNG/GIF); WebP veya AVIF daha küçüktür",
    "gorsel_lazy_yok": "Sayfanın altındaki görseller tembel yüklenmiyor (loading=\"lazy\" yok)",
    "ilk_gorsel_lazy": "Sayfanın ilk görseli tembel yükleniyor; ana görselin (LCP) gelişini geciktirir",
    # --- ek site (canli) denetimleri ---
    "yonlendirme_dongusu": "Adres yönlendirme döngüsüne giriyor",
    "cok_fazla_yonlendirme": "Adres 10'dan fazla yönlendirmeden geçiyor",
    "gecersiz_yonlendirme": "Sunucu yönlendirme kodu döndürüyor ama hedef adres (Location) yok",
    "gecici_yonlendirme": "Adres geçici yönlendirme (302/303/307) kullanıyor",
    "sitemap_hatali_adres": "robots.txt'de bildirilen bazı sitemap adresleri açılamıyor",
    "sitemap_cok_buyuk": "Sitemap 50 MB veya 50.000 adres sınırını aşıyor",
    "noindex_sitemapte": "noindex olan sayfa sitemap'te listelenmiş (çelişkili sinyal)",
    "kirik_ic_link": "Sayfada kırık site içi bağlantılar var (4xx/5xx)",
    "kirik_dis_link": "Sayfada kırık dış bağlantılar var (4xx/5xx)",
    "ic_link_yonlendirme": "Site içi bağlantılar yönlendirilen adreslere gidiyor",
    "kirik_gorsel": "Bazı görseller yüklenemiyor (4xx/5xx)",
    "gorsel_buyuk": "Bazı görsellerin dosya boyutu büyük (200 KB üstü)",
    "cwv_lcp_yavas": "Ana içeriğin yüklenmesi (LCP) yavaş",
    "cwv_inp_yavas": "Etkileşime yanıt süresi (INP) yavaş",
    "cwv_cls_yuksek": "Görsel düzen kayması (CLS) yüksek",
    "sayfa_agir": "Sayfanın toplam indirme boyutu büyük (3 MB üstü)",
}

# Sorun basina somut duzeltme onerisi (raporda "Nasil duzeltilir" olarak gosterilir).
DUZELTME = {
    "title_yok": "<head> içine sayfanın konusunu anlatan, 30-60 karakterlik bir <title> ekleyin.",
    "title_kisa": "Başlığı sayfanın konusu ve site adıyla 30-60 karaktere tamamlayın.",
    "title_uzun": "Başlığı 60 karakterin altına indirin; en önemli kelimeleri başa alın.",
    "title_genis": "Geniş harfleri (M, W, büyük harf) azaltın ya da başlığı kısaltın; Google yaklaşık 580 pikselden sonrasını keser.",
    "meta_description_yok": "Sayfanın içeriğini özetleyen 70-160 karakterlik bir meta açıklama ekleyin.",
    "meta_description_kisa": "Meta açıklamayı sayfanın sunduğu bilgiyle 70-160 karaktere genişletin.",
    "meta_description_uzun": "Meta açıklamayı 160 karakterin altına kısaltın; kesilen kısım arama sonucunda görünmez.",
    "h1_yok": "Sayfanın ana konusunu anlatan bir <h1> başlığı ekleyin.",
    "h1_birden_fazla": "Tek bir <h1> bırakın; diğer ana başlıkları <h2> yapın.",
    "h1_bos": "Metinsiz <h1>'e metin ekleyin ya da logoysa <h1> yerine başka bir etiket kullanın.",
    "img_alt_eksik": "Her içerik görseline ne gösterdiğini anlatan alt metni ekleyin; süs görsellerine alt=\"\" yazın.",
    "canonical_yok": "<head> içine sayfanın asıl adresini gösteren <link rel=\"canonical\" href=\"...\"> ekleyin.",
    "html_lang_yok": "<html> etiketine sayfanın dilini ekleyin, örneğin <html lang=\"tr\">.",
    "icerik_az": "Ana içerik bölümüne kullanıcının sorusunu yanıtlayan özgün metin ekleyin (300+ kelime iyi bir hedeftir).",
    "robots_yok": "Site köküne en azından 'User-agent: *' ve 'Sitemap:' satırlarını içeren bir robots.txt koyun.",
    "robots_okunamadi": "robots.txt'nin 200 durum koduyla ve text/plain türüyle döndüğünü kontrol edin.",
    "robots_tum_siteyi_engelliyor": "robots.txt'deki 'Disallow: /' satırını kaldırın ya da yalnızca gizli dizinlerle sınırlayın.",
    "robots_sayfayi_engelliyor": "Bu sayfanın aranmasını istiyorsanız robots.txt'deki ilgili Disallow kuralını kaldırın.",
    "robots_sitemap_bildirilmemis": "robots.txt'ye 'Sitemap: https://alanadi/sitemap.xml' satırı ekleyin.",
    "sitemap_yok": "Sitenin indekslenmesini istediğiniz adreslerini içeren bir sitemap.xml oluşturup robots.txt'de bildirin.",
    "sitemap_gecersiz": "Sitemap'i sitemaps.org şemasına uygun, geçerli bir XML olarak yeniden üretin.",
    "sitemap_bos": "Sitemap'e indekslenecek sayfaların <loc> adreslerini ekleyin.",
    "sayfa_sitemapte_yok": "İndekslenmesini istiyorsanız bu sayfayı sitemap'e ekleyin.",
    "https_yok": "Siteye TLS sertifikası kurup tüm adresleri https:// üzerinden sunun.",
    "https_yonlendirme_yok": "Sunucuda http:// isteklerini 301 ile https:// adresine yönlendirin.",
    "sertifika_suresi_dolmus": "Sertifikayı hemen yenileyin; otomatik yenileme (ör. Let's Encrypt/certbot) kurun.",
    "sertifika_zinciri_eksik": "Sunucu yapılandırmasına ara sertifikaları da ekleyin (tam zincir / fullchain dosyası).",
    "sertifika_dogrulanamadi": "Sertifikanın alan adıyla eşleştiğini ve güvenilir bir kuruluşça verildiğini kontrol edin.",
    "erisilemedi": "Sunucunun ayakta olduğunu, DNS kaydını ve güvenlik duvarı kurallarını kontrol edin.",
    "sertifika_yakinda_bitiyor": "Sertifikayı süresi dolmadan yenileyin.",
    "uzun_yonlendirme_zinciri": "Bağlantıları ve yönlendirmeleri doğrudan son adrese gidecek şekilde güncelleyin.",
    "hata_durum_kodu": "Sayfa kaldırıldıysa ona verilen bağlantıları düzeltin ya da 301 ile en yakın sayfaya yönlendirin.",
    "hsts_yok": "Yanıtlara 'Strict-Transport-Security: max-age=31536000; includeSubDomains' başlığını ekleyin.",
    "yavas_yanit": "Sunucu tarafı önbellek, veritabanı sorgu iyileştirmesi veya CDN ile yanıt süresini düşürün.",
    "cok_yavas_yanit": "Sunucu tarafı önbellek ve daha güçlü barındırma ile TTFB'yi 1 saniyenin altına indirin.",
    "sikistirma_yok": "Sunucuda HTML, CSS ve JS için gzip veya brotli sıkıştırmasını açın.",
    "html_cok_buyuk": "HTML'deki satır içi betik/stil ve gereksiz işaretlemeyi dış dosyalara taşıyın ya da azaltın.",
    "cok_fazla_kaynak": "Betik ve stil dosyalarını birleştirin, kullanılmayanları kaldırın.",
    "viewport_yok": "<head> içine <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> ekleyin.",
    "yapisal_veri_yok": "Sayfa türüne uygun schema.org yapısal verisini JSON-LD olarak ekleyin (Organization, Article, Product…).",
    "yapisal_veri_gecersiz": "JSON-LD bloğunu bir JSON doğrulayıcıyla düzeltin (eksik virgül, tırnak).",
    "og_etiketleri_yok": "og:title, og:description, og:image ve og:url etiketlerini ekleyin.",
    "twitter_card_yok": "<meta name=\"twitter:card\" content=\"summary_large_image\"> ekleyin.",
    "favicon_yok": "<link rel=\"icon\" href=\"/favicon.ico\"> ile bir site simgesi tanımlayın.",
    "noindex": "Sayfanın aranmasını istiyorsanız meta robots'tan veya X-Robots-Tag başlığından noindex'i kaldırın.",
    "baslik_atlamasi": "Başlıkları sırayla kullanın: H1'in altında H2, H2'nin altında H3.",
    "hreflang_gecersiz": "hreflang değerlerini ISO 639-1 dil ve ISO 3166-1 bölge koduyla yazın (ör. tr, en-GB).",
    "hreflang_x_default_yok": "Dil seçimi sayfanız için hreflang=\"x-default\" bağlantısı ekleyin.",
    "schema_kurum_turu_yok": "Ana sayfaya Organization (veya uygun alt türü) yapısal verisini ad, logo ve adresle ekleyin.",
    "karisik_icerik": "Sayfadaki http:// kaynak adreslerini https:// yapın.",
    "title_h1_uyumsuz": "Başlık ve H1'i aynı ana konuyu anlatacak şekilde ortak bir anahtar terimle yazın.",
    "title_icerikle_uyumsuz": "Başlıktaki terimlerin sayfa metninde de geçtiğinden emin olun ya da başlığı içeriğe göre değiştirin.",
    "title_tekrar": "Her sayfaya kendi konusunu anlatan benzersiz bir başlık verin.",
    "meta_tekrar": "Her sayfaya kendi içeriğini özetleyen benzersiz bir meta açıklama yazın.",
    "h1_tekrar": "Her sayfanın H1'ini o sayfanın konusuna özgü yazın.",
    "icerik_tekrar": "Kopya sayfalardan birini asıl sayfa seçip diğerlerine canonical verin ya da 301 ile yönlendirin.",
    "icerik_benzer": "Benzer sayfaları birleştirin ya da her birine özgün içerik ekleyin; gerekirse canonical kullanın.",
    "yetim_sayfa": "Sayfaya ilgili kategori veya içerik sayfalarından site içi bağlantı verin; gereksizse sitemap'ten çıkarın.",
    "derin_sayfa": "Önemli sayfalara ana sayfa, menü veya kategori sayfalarından daha kısa bir yol açın.",
    "hreflang_donus_yok": "hreflang ilişkisini her iki sayfada da karşılıklı tanımlayın.",
    "sayfa_nofollow": "Sayfadaki bağlantıların izlenmesini istiyorsanız robots meta veya X-Robots-Tag'den nofollow'u kaldırın.",
    "canonical_coklu": "Tek bir canonical bırakın; eklentilerin ya da temanın ikinci bir canonical eklemediğini kontrol edin.",
    "canonical_bos": "Canonical etiketine sayfanın tam adresini yazın ya da etiketi kaldırın.",
    "canonical_head_disi": "Canonical etiketini <body> yerine <head> içine taşıyın.",
    "canonical_capraz": "Bu sayfa asıl sayfaysa canonical'ı sayfanın kendi adresine çevirin; kopyaysa bu bir sorun değildir.",
    "canonical_goreli": "Canonical'da göreli yol yerine https:// ile başlayan tam adres kullanın.",
    "canonical_baslik_catismasi": "HTTP Link başlığı ile HTML'deki canonical'ı aynı adrese ayarlayın ya da birini kaldırın.",
    "noindex_canonical_catismasi": "Ya noindex'i ya da başka adrese işaret eden canonical'ı kaldırın; ikisi birlikte çelişir.",
    "meta_refresh": "Meta refresh yerine sunucu tarafında 301 yönlendirmesi kullanın.",
    "js_yonlendirme": "JavaScript yönlendirmesi yerine sunucu tarafında 301 yönlendirmesi kullanın.",
    "js_bagimli_icerik": "Önemli içeriği sunucu tarafında üretin (SSR veya ön üretim); arama motoru render sırasında içeriği kaçırabilir.",
    "bos_baslik": "Boş başlık etiketlerini kaldırın ya da metin ekleyin.",
    "viewport_sorunlu": "Viewport'u 'width=device-width, initial-scale=1' yapın; user-scalable=no ve maximum-scale'i kaldırın.",
    "og_gorsel_yok": "Paylaşımlarda görünmesi için en az 1200×630 px bir og:image ekleyin.",
    "yapisal_veri_eksik_alan": "Ayrıntıda listelenen zorunlu alanları JSON-LD'ye ekleyin; Google Zengin Sonuç Testi ile doğrulayın.",
    "hreflang_kendine_referans_yok": "hreflang listesine sayfanın kendi dil kodu ve adresiyle bir satır ekleyin.",
    "bos_baglanti_metni": "Metinsiz bağlantılara görünür metin, görsel bağlantılara alt metni ya da aria-label ekleyin.",
    "genel_baglanti_metni": "Bağlantı metninde gidilen sayfanın konusunu yazın (ör. \"burada\" yerine \"başvuru koşulları\").",
    "ic_nofollow": "Site içi bağlantılardan rel=\"nofollow\" niteliğini kaldırın.",
    "ic_baglanti_yok": "Sayfaya ilgili diğer sayfalara giden site içi bağlantılar ekleyin.",
    "gorsel_boyut_yok": "<img> etiketlerine width ve height niteliklerini ekleyin.",
    "gorsel_eski_format": "Görselleri WebP/AVIF'e dönüştürün ya da <picture> ile modern biçimi önerin.",
    "gorsel_lazy_yok": "Sayfanın ilk ekranı dışındaki görsellere loading=\"lazy\" ekleyin.",
    "ilk_gorsel_lazy": "İlk ekrandaki ana görselden loading=\"lazy\" niteliğini kaldırın (fetchpriority=\"high\" ekleyebilirsiniz).",
    "yonlendirme_dongusu": "Yönlendirme kurallarını (sunucu, .htaccess, CMS eklentisi) döngü oluşturmayacak şekilde düzeltin.",
    "cok_fazla_yonlendirme": "Yönlendirmeleri doğrudan son adrese giden tek bir 301'e indirin.",
    "gecersiz_yonlendirme": "3xx yanıtına hedef adresi gösteren bir Location başlığı ekleyin.",
    "gecici_yonlendirme": "Yönlendirme kalıcıysa 302/307 yerine 301/308 kullanın.",
    "sitemap_hatali_adres": "robots.txt'deki açılmayan Sitemap satırlarını düzeltin ya da kaldırın.",
    "sitemap_cok_buyuk": "Sitemap'i 50.000 adresin ve 50 MB'ın altındaki dosyalara bölüp bir sitemap dizini kullanın.",
    "noindex_sitemapte": "noindex sayfaları sitemap'ten çıkarın ya da noindex'i kaldırın.",
    "kirik_ic_link": "Kırık bağlantıları doğru adresle güncelleyin ya da kaldırın; ayrıntıda örnekler var.",
    "kirik_dis_link": "Artık açılmayan dış bağlantıları güncelleyin ya da kaldırın.",
    "ic_link_yonlendirme": "Site içi bağlantıları yönlendirmenin son adresine doğrudan verin.",
    "kirik_gorsel": "Açılmayan görsellerin adresini düzeltin ya da görseli yeniden yükleyin.",
    "gorsel_buyuk": "Görselleri sıkıştırın, gösterilen boyuta küçültün ve WebP/AVIF kullanın.",
    "cwv_lcp_yavas": "Ana görseli/metni öne alın: sunucu yanıtını hızlandırın, ana görseli önceden yükleyin, engelleyici CSS/JS'i azaltın.",
    "cwv_inp_yavas": "Uzun JavaScript görevlerini bölün, gereksiz üçüncü taraf betikleri kaldırın.",
    "cwv_cls_yuksek": "Görsel, reklam ve gömülü öğelere sabit boyut verin; içerik üstüne sonradan öğe eklemeyin.",
    "sayfa_agir": "Görselleri sıkıştırın, kullanılmayan JS/CSS'i kaldırın, yazı tiplerini alt kümeye indirin.",
}

KURUM_SCHEMA_TURLERI = {"Organization", "EducationalOrganization", "CollegeOrUniversity",
                        "GovernmentOrganization", "School", "Hospital", "MedicalOrganization", "Corporation",
                        "LocalBusiness", "NGO", "OnlineStore", "Person"}
HREFLANG_DESENI = re.compile(r"^(x-default|[a-z]{2,3}(-[a-z]{4})?(-([a-z]{2}|\d{3}))?)$", re.I)
# ISO 639-1 dil kodlari; hreflang bu kodlardan biriyle baslamalidir
ISO_DILLER = set("""aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy
da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii
ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr
ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl
sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh
zu""".split())
GECERSIZ_BOLGELER = {"uk", "en", "eu"}      # sik yapilan hata: en-UK (dogrusu en-GB)


def hreflang_gecerli_mi(kod):
    k = (kod or "").strip().lower()
    if not HREFLANG_DESENI.match(k):
        return False
    if k == "x-default":
        return True
    parcalar = k.split("-")
    return parcalar[0] in ISO_DILLER and not (len(parcalar) > 1 and parcalar[-1] in GECERSIZ_BOLGELER)


def cozum_yolu(kod: str) -> str:
    """Sorunun nasil cozulebilecegi: model (dil modeli metin uretir),
    kural (kod ile belirli bicimde duzeltilir) veya elle (insan/sunucu mudahalesi)."""
    if any(kod in kodlar for kodlar in ALAN_SORUN.values()):
        return "model"
    if kod in KURAL_SORUNLARI:
        return "kural"
    return "elle"


def rule_checks(d: dict) -> list:
    """Sayfa katmani temel denetimi. Modele yalnizca bu listedeki sorunlar gonderilir."""
    issues = []
    def add(kod, ciddiyet, ayrinti=""):
        issues.append({"sorun": kod, "ciddiyet": ciddiyet, "ayrinti": ayrinti,
                       "katman": "sayfa", "cozum_yolu": cozum_yolu(kod)})
    t = d["title"]
    if not t: add("title_yok", "yuksek")
    elif len(t) < 30: add("title_kisa", "orta", f"{len(t)} karakter")
    elif len(t) > 60: add("title_uzun", "orta", f"{len(t)} karakter")
    elif baslik_piksel(t) > SERP_GENISLIK: add("title_genis", "dusuk", f"yaklaşık {baslik_piksel(t)} px")
    m = d["meta_description"]
    if not m: add("meta_description_yok", "yuksek")
    elif len(m) < 70: add("meta_description_kisa", "orta", f"{len(m)} karakter")
    elif len(m) > 160: add("meta_description_uzun", "orta", f"{len(m)} karakter")
    if len(d["h1"]) == 0: add("h1_yok", "yuksek")
    elif len(d["h1"]) > 1: add("h1_birden_fazla", "orta", f"{len(d['h1'])} adet")
    if d.get("h1_bos_sayisi"): add("h1_bos", "dusuk", f"{d['h1_bos_sayisi']} adet metinsiz H1")
    if d["img_no_alt"]: add("img_alt_eksik", "orta", f"{len(d['img_no_alt'])}/{d['img_total']} görsel")
    if not d["canonical"]: add("canonical_yok", "dusuk")
    if not d["lang"]: add("html_lang_yok", "dusuk")
    # ince icerik: menu ve alt bilgi disindaki ana icerik bolgesinin kelime sayisi
    kelime = d.get("icerik_kelime_sayisi", d["word_count"])
    if kelime < 300: add("icerik_az", "dusuk", f"ana içerikte {kelime} kelime")
    return issues


def _viewport_sorunu(icerik):
    v = (icerik or "").lower().replace(" ", "")
    nedenler = []
    if re.search(r"user-scalable=(no|0)(,|$)", v):
        nedenler.append("user-scalable=no")
    m = re.search(r"maximum-scale=([\d.]+)", v)
    if m:
        try:
            if float(m.group(1)) < 2:
                nedenler.append("maximum-scale=" + m.group(1))
        except ValueError:
            pass
    if re.search(r"(^|,)width=\d+", v):
        nedenler.append("sabit genişlik")
    return ", ".join(nedenler)


def _ana_sayfa_mi(url):
    return url is None or urlparse(url).path in ("", "/") and not urlparse(url).query


def canonical_denetimi(yv, sayfa_url, add):
    """Canonical etiketinin yapisi ve hedefi. noindex ile birlikte celiski de burada denetlenir."""
    hepsi = yv.get("canonicallar") or []
    html_c = [c for c in hepsi if c.get("kaynak", "html") == "html"]
    http_c = [c for c in hepsi if c.get("kaynak") == "http"]
    if len({c["href"] for c in html_c}) > 1:
        add("canonical_coklu", "orta", " | ".join(c["href"] or "(boş)" for c in html_c)[:160])
    if any(not c["href"] for c in html_c):
        add("canonical_bos", "orta")
    if any(not c["head"] for c in html_c):
        add("canonical_head_disi", "orta")
    if not sayfa_url:
        return
    asil = next((c["href"] for c in html_c + http_c if c["href"]), None)
    if not asil:
        return
    if html_c and html_c[0]["href"] and not re.match(r"^https?://", html_c[0]["href"], re.I):
        add("canonical_goreli", "dusuk", html_c[0]["href"][:100])
    hedef = urljoin(sayfa_url, asil)
    noindex = bool({"noindex", "none"} & set(yv.get("robots_yonergeleri") or []))
    if url_anahtari(hedef) != url_anahtari(sayfa_url):
        add("canonical_capraz", "dusuk", hedef[:160])
        if noindex:
            add("noindex_canonical_catismasi", "orta", hedef[:160])
    elif sayfa_url.lower().startswith("https://") and hedef.lower().startswith("http://"):
        add("canonical_capraz", "dusuk", "http sürümünü gösteriyor: " + hedef[:140])
    html_hedef = next((urljoin(sayfa_url, c["href"]) for c in html_c if c["href"]), None)
    http_hedef = next((urljoin(sayfa_url, c["href"]) for c in http_c if c["href"]), None)
    if html_hedef and http_hedef and url_anahtari(html_hedef) != url_anahtari(http_hedef):
        add("canonical_baslik_catismasi", "orta", "başlık: " + http_hedef[:70] + " | html: " + html_hedef[:70],
            katman="site")


def baglanti_denetimi(baglantilar, add):
    """Sayfa ici baglanti kalitesi: bos ve anlamsiz anchor metni, site ici nofollow, cikmaz sayfa."""
    if not baglantilar:
        return
    bos = [b for b in baglantilar if not b["metin"]]
    if bos:
        add("bos_baglanti_metni", "dusuk", f"{len(bos)} bağlantı, ör. {bos[0]['adres'][:80]}")
    genel = [b for b in baglantilar if tr_lower(b["metin"]).strip(" .…>»→!") in GENEL_BAGLANTI_METINLERI]
    if genel:
        add("genel_baglanti_metni", "dusuk", f"{len(genel)} bağlantı, ör. \"{genel[0]['metin']}\"")
    ic_nofollow = [b for b in baglantilar if b["ic"] and b["nofollow"]]
    if ic_nofollow:
        add("ic_nofollow", "dusuk", f"{len(ic_nofollow)} bağlantı, ör. {ic_nofollow[0]['adres'][:80]}")
    if not any(b["ic"] for b in baglantilar):
        add("ic_baglanti_yok", "dusuk")


def gorsel_denetimi(gorseller, add):
    """Gorsel performansi: boyut nitelikleri, bicim ve tembel yukleme (HTML'den gorulebilenler)."""
    g = [x for x in gorseller or [] if x.get("src") and not x.get("veri_uri")]
    if not g:
        return
    boyutsuz = [x for x in g if not x["boyut_var"]]
    if boyutsuz:
        add("gorsel_boyut_yok", "dusuk", f"{len(boyutsuz)}/{len(g)} görsel")
    eski = [x for x in g if x["eski_format"]]
    if eski:
        add("gorsel_eski_format", "dusuk", f"{len(eski)}/{len(g)} görsel")
    # ilk ekran tahmini: ilk 3 gorsel; sonrasindakiler tembel yuklenmeli
    alttakiler = [x for x in g[3:] if not x["lazy"]]
    if alttakiler:
        add("gorsel_lazy_yok", "dusuk", f"{len(alttakiler)} görsel")
    if g[0]["lazy"]:
        add("ilk_gorsel_lazy", "dusuk", g[0]["src"][:100])


def ek_html_denetimi(yv: dict, sayfa_url=None) -> list:
    """Yapisal veri, mobil uyum, paylasim etiketleri, baslik yapisi ve karisik icerik denetimi.
    Tamami sayfanin HTML'inden gorulebilir; modele gonderilmez.
    sayfa_url verilirse ve https ise karisik icerik denetimi de yapilir."""
    issues = []
    def add(kod, ciddiyet, ayrinti="", katman="sayfa"):
        issues.append({"sorun": kod, "ciddiyet": ciddiyet, "ayrinti": ayrinti,
                       "katman": katman, "cozum_yolu": cozum_yolu(kod)})
    if not yv["viewport"]:
        add("viewport_yok", "orta")
    elif _viewport_sorunu(yv["viewport"]):
        add("viewport_sorunlu", "dusuk", _viewport_sorunu(yv["viewport"]))
    if yv["jsonld_sayisi"] == 0 and not yv["mikroveri"]:
        add("yapisal_veri_yok", "dusuk")
    elif yv["jsonld_hatali"]:
        add("yapisal_veri_gecersiz", "dusuk", str(yv["jsonld_hatali"]) + " blok")
    if yv.get("schema_eksikleri"):
        add("yapisal_veri_eksik_alan", "dusuk", ", ".join(yv["schema_eksikleri"][:4]))
    if not yv["og_etiketleri"]:
        add("og_etiketleri_yok", "dusuk")
    elif "og:image" not in yv["og_etiketleri"]:
        add("og_gorsel_yok", "dusuk")
    if not yv["twitter_etiketleri"]:
        add("twitter_card_yok", "dusuk")
    if not yv["favicon"]:
        add("favicon_yok", "dusuk")
    if yv["dis_kaynak_sayisi"] > 100:
        add("cok_fazla_kaynak", "dusuk", str(yv["dis_kaynak_sayisi"]) + " kaynak")
    # robots ve googlebot meta etiketlerinin tamami birlikte degerlendirilir; "none" = noindex, nofollow
    yonergeler = set(yv.get("robots_yonergeleri") or
                     [x.strip().lower() for x in (yv.get("robots_meta") or "").split(",") if x.strip()])
    if yonergeler & {"noindex", "none"}:
        add("noindex", "yuksek", "meta robots: " + str(yv["robots_meta"]))
    if yonergeler & {"nofollow", "none"}:
        add("sayfa_nofollow", "orta", "meta robots: " + str(yv["robots_meta"]))
    canonical_denetimi(yv, sayfa_url, add)
    if yv.get("meta_refresh"):
        r = yv["meta_refresh"]
        add("meta_refresh", "orta", f"{r['sure']:g} sn sonra → {r['hedef'][:120]}")
    if yv.get("js_yonlendirme"):
        add("js_yonlendirme", "dusuk", "satır içi betikte location ataması")
    if yv.get("js_iskelet"):
        add("js_bagimli_icerik", "orta", "ham HTML'de 50'den az kelime; uygulama iskeleti (tahmin)")
    seviyeler = yv.get("baslik_seviyeleri") or []
    atlamalar = [f"H{a}->H{b}" for a, b in zip(seviyeler, seviyeler[1:]) if b > a + 1]
    if atlamalar:
        add("baslik_atlamasi", "dusuk", ", ".join(sorted(set(atlamalar))[:3]))
    if yv.get("bos_baslik_sayisi"):
        add("bos_baslik", "dusuk", str(yv["bos_baslik_sayisi"]) + " adet")
    hreflang = [h for h in (yv.get("hreflang") or []) if h is not None]
    if hreflang:
        gecersiz = [h for h in hreflang if not hreflang_gecerli_mi(h)]
        if gecersiz:
            add("hreflang_gecersiz", "dusuk", ", ".join(gecersiz[:3]))
        if not any(h.strip().lower() == "x-default" for h in hreflang):
            add("hreflang_x_default_yok", "dusuk")
        baglar = yv.get("hreflang_baglantilari") or []
        if sayfa_url and baglar and not any(url_anahtari(b["href"]) == url_anahtari(sayfa_url) for b in baglar):
            add("hreflang_kendine_referans_yok", "dusuk")
    # kurulus turu yalnizca ana sayfada beklenir; urun/haber sayfasinda Organization olmamasi sorun degildir
    if yv["jsonld_sayisi"] and _ana_sayfa_mi(sayfa_url) and \
            not (set(yv.get("schema_turleri") or []) & KURUM_SCHEMA_TURLERI):
        add("schema_kurum_turu_yok", "dusuk", ", ".join(yv.get("schema_turleri") or []) or "tür yok")
    if sayfa_url and sayfa_url.lower().startswith("https://") and yv.get("http_kaynak_sayisi"):
        add("karisik_icerik", "orta", str(yv["http_kaynak_sayisi"]) + " kaynak")
    baglanti_denetimi(yv.get("baglantilar"), add)
    gorsel_denetimi(yv.get("gorseller"), add)
    return issues


def odak_terim_denetimi(d: dict) -> list:
    """Title, H1 ve icerik arasinda ortak anahtar terim olup olmadigini denetler.
    Kokler 5 harfe kisaltildigi icin Turkce ek farklari tolere edilir; kurumlarin her sayfada
    gecen genel sozcukleri (GENEL_KOKLER) sayilmaz."""
    issues = []
    def add(kod, ayrinti=""):
        issues.append({"sorun": kod, "ciddiyet": "dusuk", "ayrinti": ayrinti,
                       "katman": "sayfa", "cozum_yolu": cozum_yolu(kod)})
    title_k = kokler(d.get("title") or "") - GENEL_KOKLER
    h1_k = kokler(" ".join(d.get("h1") or [])) - GENEL_KOKLER
    if title_k and h1_k and not (title_k & h1_k):
        add("title_h1_uyumsuz", "title: " + (d.get("title") or "")[:40] + " | h1: " + " / ".join(d["h1"])[:40])
    if title_k and d.get("icerik_kokleri") and not (title_k & d["icerik_kokleri"]):
        add("title_icerikle_uyumsuz", (d.get("title") or "")[:60])
    return issues


def _normal(metin):
    return " ".join((metin or "").lower().split())


def site_geneli(rapor: list) -> list:
    """Taramadaki sayfalar arasinda tekrar eden title / meta / H1 degerlerini bulur.
    Her kayit icin tek tek bakilarak gorulemeyen, tarama geneline ait bir denetimdir.
    Grup listesi dondurur: [{"sorun", "deger", "sayfalar"}]."""
    gruplar = {"title_tekrar": defaultdict(list), "meta_tekrar": defaultdict(list), "h1_tekrar": defaultdict(list)}
    for k in rapor:
        if k.get("hata") or k.get("atlandi") or k.get("hata_sayfasi"):
            continue
        if _normal(k.get("title")):
            gruplar["title_tekrar"][_normal(k["title"])].append(k["ad"])
        if _normal(k.get("meta_description")):
            gruplar["meta_tekrar"][_normal(k["meta_description"])].append(k["ad"])
        for h in set(_normal(h) for h in (k.get("h1") or []) if _normal(h)):
            gruplar["h1_tekrar"][h].append(k["ad"])
    sonuc = [{"sorun": kod, "cozum_yolu": cozum_yolu(kod), "deger": deger, "sayfalar": sayfalar}
             for kod, g in gruplar.items() for deger, sayfalar in g.items() if len(sayfalar) > 1]
    return sonuc + icerik_tekrarlari(rapor)


BENZERLIK_ESIGI = 0.9
EN_AZ_KELIME_TEKRAR = 50          # cok kisa sayfalarin (giris, hata) benzerligi anlamli degildir


def icerik_tekrarlari(rapor):
    """Ana icerik metni birebir ayni (icerik_tekrar) ya da %90 ustu benzer (icerik_benzer) sayfa
    gruplari. Imzalar cikarma.icerik_imzasi ile uretilir; benzer gruplar birlesim-bul ile toplanir."""
    adaylar = [k for k in rapor if k.get("icerik_imzasi") and not (k.get("hata") or k.get("atlandi") or
               k.get("hata_sayfasi")) and (k.get("icerik_kelime_sayisi") or 0) >= EN_AZ_KELIME_TEKRAR]
    birebir = defaultdict(list)
    for k in adaylar:
        birebir[tuple(k["icerik_imzasi"])].append(k["ad"])
    sonuc = [{"sorun": "icerik_tekrar", "cozum_yolu": cozum_yolu("icerik_tekrar"),
              "deger": f"{len(s)} sayfa aynı metni taşıyor", "sayfalar": s} for s in birebir.values() if len(s) > 1]
    # her birebir gruptan bir temsilci; benzerlik temsilciler arasinda olculur
    temsilci = [next(k for k in adaylar if k["ad"] == s[0]) for s in birebir.values()]
    ebeveyn = list(range(len(temsilci)))

    def bul(i):
        while ebeveyn[i] != i:
            ebeveyn[i] = ebeveyn[ebeveyn[i]]
            i = ebeveyn[i]
        return i
    en_yuksek = {}
    for i in range(len(temsilci)):
        for j in range(i + 1, len(temsilci)):
            b = imza_benzerligi(temsilci[i]["icerik_imzasi"], temsilci[j]["icerik_imzasi"])
            if b >= BENZERLIK_ESIGI:
                ebeveyn[bul(i)] = bul(j)
                en_yuksek[bul(j)] = max(en_yuksek.get(bul(j), 0), b)
    kumeler = defaultdict(list)
    for i, k in enumerate(temsilci):
        kumeler[bul(i)].extend(birebir[tuple(k["icerik_imzasi"])])
    for kok, sayfalar in kumeler.items():
        if len({tuple(next(x for x in adaylar if x["ad"] == a)["icerik_imzasi"]) for a in sayfalar}) > 1:
            sonuc.append({"sorun": "icerik_benzer", "cozum_yolu": cozum_yolu("icerik_benzer"),
                          "deger": f"{len(sayfalar)} sayfa, benzerlik %{round(100 * en_yuksek.get(kok, BENZERLIK_ESIGI))}",
                          "sayfalar": sayfalar})
    return sonuc


def puan(issues) -> int:
    """Sorunlarin ciddiyetine gore 0-100 arasi saydam bir SEO puani.
    Lighthouse gibi bagimsiz bir olcum degildir; bu uygulamanin kendi olcegidir."""
    ceza = sum(CIDDIYET_AGIRLIK.get(i.get("ciddiyet"), 5) for i in issues)
    return max(0, 100 - ceza)


# ------------------------------------------------------------ kategori bazli puan
# kod: (kategori, grup, en yuksek ciddiyet, gorulebildigi katmanlar)
# Ayni gruptaki kodlar birbirini dislar (ornegin title_yok / title_kisa / title_uzun);
# bir grubun en fazla cezasi o gruptaki en yuksek ciddiyetin agirligidir.
SORUN_TANIMI = {
    "title_yok": ("icerik", "title", "yuksek", "sayfa"), "title_kisa": ("icerik", "title", "orta", "sayfa"),
    "title_uzun": ("icerik", "title", "orta", "sayfa"),
    "meta_description_yok": ("icerik", "meta", "yuksek", "sayfa"),
    "meta_description_kisa": ("icerik", "meta", "orta", "sayfa"),
    "meta_description_uzun": ("icerik", "meta", "orta", "sayfa"),
    "h1_yok": ("icerik", "h1", "yuksek", "sayfa"), "h1_birden_fazla": ("icerik", "h1", "orta", "sayfa"),
    "h1_bos": ("icerik", "h1_bos", "dusuk", "sayfa"),
    "img_alt_eksik": ("icerik", "img_alt", "orta", "sayfa"),
    "icerik_az": ("icerik", "icerik_az", "dusuk", "sayfa"),
    "title_h1_uyumsuz": ("icerik", "title_h1", "dusuk", "sayfa"),
    "title_icerikle_uyumsuz": ("icerik", "title_icerik", "dusuk", "sayfa"),
    "baslik_atlamasi": ("icerik", "baslik", "dusuk", "sayfa"),
    "canonical_yok": ("teknik", "canonical", "dusuk", "sayfa"),
    "html_lang_yok": ("teknik", "lang", "dusuk", "sayfa"),
    "viewport_yok": ("teknik", "viewport", "orta", "sayfa"),
    "yapisal_veri_yok": ("teknik", "yapisal", "dusuk", "sayfa"),
    "yapisal_veri_gecersiz": ("teknik", "yapisal", "dusuk", "sayfa"),
    "schema_kurum_turu_yok": ("teknik", "schema_tur", "dusuk", "sayfa"),
    "og_etiketleri_yok": ("teknik", "og", "dusuk", "sayfa"),
    "twitter_card_yok": ("teknik", "twitter", "dusuk", "sayfa"),
    "favicon_yok": ("teknik", "favicon", "dusuk", "sayfa"),
    "hreflang_gecersiz": ("teknik", "hreflang_gecersiz", "dusuk", "sayfa"),
    "hreflang_x_default_yok": ("teknik", "hreflang_x", "dusuk", "sayfa"),
    "noindex": ("teknik", "noindex", "yuksek", "sayfa site"),
    "cok_fazla_kaynak": ("performans", "kaynak", "dusuk", "sayfa"),
    "karisik_icerik": ("guvenlik", "karisik", "orta", "sayfa"),
    "erisilemedi": ("teknik", "erisim", "yuksek", "site"),
    "hata_durum_kodu": ("teknik", "erisim", "yuksek", "site"),
    "uzun_yonlendirme_zinciri": ("teknik", "yonlendirme", "dusuk", "site"),
    "robots_yok": ("teknik", "robots", "orta", "site"), "robots_okunamadi": ("teknik", "robots", "orta", "site"),
    "robots_tum_siteyi_engelliyor": ("teknik", "robots", "yuksek", "site"),
    "robots_sayfayi_engelliyor": ("teknik", "robots", "yuksek", "site"),
    "robots_sitemap_bildirilmemis": ("teknik", "robots_sitemap", "dusuk", "site"),
    "sitemap_yok": ("teknik", "sitemap", "orta", "site"), "sitemap_gecersiz": ("teknik", "sitemap", "orta", "site"),
    "sitemap_bos": ("teknik", "sitemap", "orta", "site"),
    "sayfa_sitemapte_yok": ("teknik", "sitemap", "dusuk", "site"),
    "https_yok": ("guvenlik", "https", "yuksek", "site"),
    "https_yonlendirme_yok": ("guvenlik", "https_yon", "orta", "site"),
    "sertifika_suresi_dolmus": ("guvenlik", "sertifika_sure", "yuksek", "site"),
    "sertifika_yakinda_bitiyor": ("guvenlik", "sertifika_sure", "orta", "site"),
    "sertifika_zinciri_eksik": ("guvenlik", "sertifika_zincir", "yuksek", "site"),
    "sertifika_dogrulanamadi": ("guvenlik", "sertifika_zincir", "yuksek", "site"),
    "hsts_yok": ("guvenlik", "hsts", "dusuk", "site"),
    "yavas_yanit": ("performans", "hiz", "dusuk", "site"), "cok_yavas_yanit": ("performans", "hiz", "orta", "site"),
    "sikistirma_yok": ("performans", "sikistirma", "dusuk", "site"),
    "html_cok_buyuk": ("performans", "boyut", "dusuk", "site"),
    # --- ek sayfa denetimleri ---
    "title_genis": ("icerik", "title", "dusuk", "sayfa"),
    "sayfa_nofollow": ("teknik", "nofollow", "orta", "sayfa site"),
    "canonical_coklu": ("teknik", "canonical_coklu", "orta", "sayfa"),
    "canonical_bos": ("teknik", "canonical_bos", "orta", "sayfa"),
    "canonical_head_disi": ("teknik", "canonical_head", "orta", "sayfa"),
    "canonical_capraz": ("teknik", "canonical_hedef", "dusuk", "sayfa"),
    "canonical_goreli": ("teknik", "canonical_goreli", "dusuk", "sayfa"),
    "canonical_baslik_catismasi": ("teknik", "canonical_baslik", "orta", "site"),
    "noindex_canonical_catismasi": ("teknik", "noindex_canonical", "orta", "sayfa"),
    "meta_refresh": ("teknik", "meta_refresh", "orta", "sayfa site"),
    "js_yonlendirme": ("teknik", "js_yon", "dusuk", "sayfa"),
    "js_bagimli_icerik": ("teknik", "js_icerik", "orta", "sayfa"),
    "bos_baslik": ("icerik", "bos_baslik", "dusuk", "sayfa"),
    "viewport_sorunlu": ("teknik", "viewport", "dusuk", "sayfa"),
    "og_gorsel_yok": ("teknik", "og", "dusuk", "sayfa"),
    "yapisal_veri_eksik_alan": ("teknik", "yapisal_alan", "dusuk", "sayfa"),
    "hreflang_kendine_referans_yok": ("teknik", "hreflang_kendi", "dusuk", "sayfa"),
    "bos_baglanti_metni": ("icerik", "bag_bos", "dusuk", "sayfa"),
    "genel_baglanti_metni": ("icerik", "bag_genel", "dusuk", "sayfa"),
    "ic_nofollow": ("teknik", "ic_nofollow", "dusuk", "sayfa"),
    "ic_baglanti_yok": ("teknik", "ic_bag_yok", "dusuk", "sayfa"),
    "gorsel_boyut_yok": ("performans", "gorsel_boyut", "dusuk", "sayfa"),
    "gorsel_eski_format": ("performans", "gorsel_format", "dusuk", "sayfa"),
    "gorsel_lazy_yok": ("performans", "gorsel_lazy", "dusuk", "sayfa"),
    "ilk_gorsel_lazy": ("performans", "gorsel_lcp", "dusuk", "sayfa"),
    # --- ek site (canli) denetimleri ---
    "yonlendirme_dongusu": ("teknik", "erisim", "yuksek", "site"),
    "cok_fazla_yonlendirme": ("teknik", "erisim", "yuksek", "site"),
    "gecersiz_yonlendirme": ("teknik", "erisim", "yuksek", "site"),
    "gecici_yonlendirme": ("teknik", "yonlendirme_tur", "dusuk", "site"),
    "sitemap_hatali_adres": ("teknik", "sitemap_adres", "dusuk", "site"),
    "sitemap_cok_buyuk": ("teknik", "sitemap_boyut", "orta", "site"),
    "noindex_sitemapte": ("teknik", "noindex_sitemap", "orta", "site"),
    "kirik_ic_link": ("teknik", "kirik_ic", "orta", "site"),
    "kirik_dis_link": ("teknik", "kirik_dis", "dusuk", "site"),
    "ic_link_yonlendirme": ("teknik", "ic_yon", "dusuk", "site"),
    "kirik_gorsel": ("teknik", "kirik_gorsel", "orta", "site"),
    "gorsel_buyuk": ("performans", "gorsel_buyuk", "dusuk", "site"),
    "cwv_lcp_yavas": ("performans", "lcp", "orta", "site"),
    "cwv_inp_yavas": ("performans", "inp", "orta", "site"),
    "cwv_cls_yuksek": ("performans", "cls", "orta", "site"),
    "sayfa_agir": ("performans", "agirlik", "dusuk", "site"),
}
KATEGORILER = ("icerik", "teknik", "guvenlik", "performans")
# tarama geneline ait bulgular (site_geneli, tarama.baglanti_bulgulari); sayfa kaydinin sorunlarina
# girmez, puanlanmaz
TARAMA_GENELI_KODLARI = ("title_tekrar", "meta_tekrar", "h1_tekrar", "icerik_tekrar", "icerik_benzer",
                         "yetim_sayfa", "derin_sayfa", "hreflang_donus_yok")


def _azami_ceza(katmanlar, kategori=None):
    """Verilen katmanlarda gorulebilen tum gruplarin en yuksek cezalarinin toplami."""
    gruplar = {}
    for kat, grup, ciddiyet, kod_katmanlari in SORUN_TANIMI.values():
        if (kategori is None or kat == kategori) and set(kod_katmanlari.split()) & set(katmanlar):
            gruplar[grup] = max(gruplar.get(grup, 0), CIDDIYET_AGIRLIK[ciddiyet])
    return sum(gruplar.values())


def _normal_puan(issues, katmanlar, kategori=None):
    secili = [i for i in issues if i.get("katman") in katmanlar and
              (kategori is None or SORUN_TANIMI.get(i["sorun"], ("",))[0] == kategori)]
    azami = _azami_ceza(katmanlar, kategori)
    if not azami:
        return None
    ceza = sum(CIDDIYET_AGIRLIK.get(i.get("ciddiyet"), 5) for i in secili)
    return max(0, round(100 * (1 - ceza / azami)))


def puanlar(issues, sayfa_olculdu=True) -> dict:
    """Katman ve kategori bazli, 0-100 arasina normallestirilmis puanlar.
    Her puan, o kapsamda gorulebilecek en kotu durumun cezasina bolunur; boylece birkac
    sorun olcegi 0'a indirmez ve siteler birbirinden ayirt edilebilir. Sayfa katmani
    olculmediyse (hata sayfasi) sayfa puani None olur, kategoriler site katmanindan hesaplanir."""
    # hata sayfasinda (4xx/5xx) sayfa katmani denetlenmez; bulgu olmamasi "kusursuz" demek degildir
    katmanlar = ("sayfa", "site") if sayfa_olculdu else ("site",)
    sonuc = {"sayfa": _normal_puan(issues, ("sayfa",)) if sayfa_olculdu else None,
             "site": _normal_puan(issues, ("site",))}
    for kat in KATEGORILER:
        sonuc[kat] = _normal_puan(issues, katmanlar, kat)
    return sonuc


def acikla(kod: str) -> str:
    return ACIKLAMA.get(kod, kod)


def tekillestir(issues):
    """Ayni kodlu bulgulari bire indirir (ornegin noindex hem meta etiketinde hem X-Robots-Tag
    basliginda): ilk bulgu kalir, ayrintilar birlestirilir. Boylece ayni sorun iki kez cezalanmaz."""
    sonuc, gorulen = [], {}
    for i in issues:
        if i["sorun"] in gorulen:
            ilk = gorulen[i["sorun"]]
            if i.get("ayrinti") and i["ayrinti"] not in (ilk.get("ayrinti") or ""):
                ilk["ayrinti"] = ((ilk.get("ayrinti") or "") + " · " + i["ayrinti"]).strip(" ·")
            continue
        i = dict(i)
        gorulen[i["sorun"]] = i
        sonuc.append(i)
    return sonuc


def site_ozeti(rapor, tarama_bulgulari=()):
    """Site bazli ozet: her sorun kodu icin etkilenen sayfa sayisi, ciddiyet ve ornek sayfalar.
    Siralama: once ciddiyet agirligi x sayfa sayisi (en cok puan kaybettiren ustte)."""
    sayac = {}
    for k in rapor:
        for i in k.get("sorunlar") or []:
            s = sayac.setdefault(i["sorun"], {"sorun": i["sorun"], "aciklama": acikla(i["sorun"]),
                                              "duzeltme": DUZELTME.get(i["sorun"], ""), "ciddiyet": i.get("ciddiyet"),
                                              "katman": i.get("katman"), "cozum_yolu": i.get("cozum_yolu"),
                                              "sayfa_sayisi": 0, "ornek_sayfalar": []})
            s["sayfa_sayisi"] += 1
            if CIDDIYET_AGIRLIK.get(i.get("ciddiyet"), 0) > CIDDIYET_AGIRLIK.get(s["ciddiyet"], 0):
                s["ciddiyet"] = i["ciddiyet"]
            if len(s["ornek_sayfalar"]) < 5:
                s["ornek_sayfalar"].append(k.get("ad"))
    for g in tarama_bulgulari:
        s = sayac.setdefault(g["sorun"], {"sorun": g["sorun"], "aciklama": acikla(g["sorun"]),
                                          "duzeltme": DUZELTME.get(g["sorun"], ""), "ciddiyet": "bilgi",
                                          "katman": "tarama", "cozum_yolu": g.get("cozum_yolu"),
                                          "sayfa_sayisi": 0, "ornek_sayfalar": []})
        yeni = [a for a in g["sayfalar"] if a not in s["ornek_sayfalar"]]
        s["sayfa_sayisi"] += len(yeni)
        s["ornek_sayfalar"] = (s["ornek_sayfalar"] + yeni)[:5]
    return sorted(sayac.values(), key=lambda s: (-CIDDIYET_AGIRLIK.get(s["ciddiyet"], 0) * s["sayfa_sayisi"],
                                                 -s["sayfa_sayisi"], s["sorun"]))
