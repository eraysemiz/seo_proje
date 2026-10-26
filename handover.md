# HANDOVER: Yerel Dil Modeli ile SEO Denetimi ve İyileştirme

Son güncelleme: **26 Ekim 2026** · Aktif dal: `seo-kurallari` (`main`'den bir commit ileride,
yalnızca yerelde; push edilmedi, birleştirilmedi).
Ayrıntılı kullanım: [README.md](README.md). Bu belgenin önceki sürümü (ödev bağlamı, Düzce birim
siteleri bulguları, 20–23 Ekim notları) git geçmişinde: `git show 14d2142:handover.md`.

## 0. Yeni sohbete başlarken (çalışma kuralları)

Kullanıcının bu projede koyduğu ve her oturumda geçerli kurallar:

- **Commit mesajlarına `Co-Authored-By` satırı (ya da başka bir yapay zekâ/ortak yazar ibaresi)
  eklenmez.** Araç bu satırı varsayılan olarak öneriyor olsa bile yazılmaz. Geçmişteki bu satırlar
  kullanıcının isteğiyle silindi (bkz. §8 "Dallar").
- **Commit ve push yalnızca kullanıcı isteyince** yapılır. `main` üzerindeyken önce dal açılır.
- Yeni bağımlılık eklemeden önce sorulur.
- Analiz aracı `sorunlar.json`'u okumaz; bu dosya yalnızca değerlendirme betiklerinindir.
- Araç iyi görünsün diye test sitesi değiştirilmez.
- Yedek, diff günlüğü ve geri alma her değişiklikte çalışır kalmalı.
- Salt okunur mod (Mod 2) bozulmaz; iki modu birden etkileyen değişiklikler ayrıca belirtilir.
- Çok adımlı işlerde her adım sonunda: `✅ [Adım] — değişen dosyalar — doğrulama sonucu`.
  Bir adım iki denemede çalışmazsa durulur ve raporlanır.
- Kullanıcının açık `SEO_Denetim.exe`'si kapatılmaz/öldürülmez. Exe açıkken `dist/` kilitli olduğu
  için derleme beklenir.
- Kullanıcıyla Türkçe yazışılır.
- **graphify:** proje kökündeki `CLAUDE.md` (git'te izlenmiyor) kod soruları için önce
  `graphify query/explain/path` kullanılmasını ister. Grafik 26 Ekim'de `seo-kurallari` dalında
  baştan kuruldu (`graphify-out/`, git dışında; 1820 düğüm, 63 topluluk). Kod değişince
  `graphify update .` ile güncellenir.

## 1. Proje amacı

- YBS317 SEO I dersi için bilimsel araştırma ödevinin aracı: *"Yerel Büyük Dil Modeli ile Web
  Sitelerinin Otomatik SEO Denetimi ve İyileştirilmesi"* (Düzce Üniversitesi birim siteleri örneği).
- Araç canlı siteleri tarar, kural tabanlı SEO denetimi yapar, LM Studio'daki yerel model ve RAG ile
  düzeltme önerileri üretir, önce/sonra raporlar.
- Erişimimiz olan sitelerde (yönetici modu) onaylanan düzeltmeleri siteye yazar ve geri alınabilir tutar.

## 2. Hızlı başlangıç

- **Python:** geliştirme `Python 3.15.0` ile yapıldı (`py` komutu). Daha eski sürümlerde çalışıp
  çalışmadığı denenmedi `[doğrulanmalı]`.
- **Bağımlılıklar:** `requirements.txt` (flask, requests, beautifulsoup4, lxml, brotlicffi);
  testler için `requirements-dev.txt` (+pytest).
- **LM Studio:** sunucu açık olmalı (Developer → Running), varsayılan adres `http://127.0.0.1:1234/v1`.
  Kullanılan modeller: sohbet `qwen/qwen3.5-9b`, gömme `text-embedding-qwen3-embedding-0.6b`.
- **İsteğe bağlı ortam değişkenleri:** `PSI_API_ANAHTARI` (PageSpeed), `CHROME_YOLU` (JS render).
- **Model gerekmeyen kullanım:** arayüzde "yalnızca denetle" seçeneği; yönetici modunda `--model` vermeden.

```
pip install -r requirements-dev.txt
py calistir.py                 # arayüz: http://127.0.0.1:5000  (--port, --host, --acma)
py -m pytest -q                # testler
```

**Standart mod (salt okunur):** arayüzde "Standart mod" seçili tarama. Toplu deney için:
```
py deney.py --adresler test_setleri/duzce_birimleri.txt --modeller qwen/qwen3.5-9b --embed-model text-embedding-qwen3-embedding-0.6b
```

**Yönetici modu (siteye yazar):**
```
py yonet.py tara --kok test_sitesi/site --url http://127.0.0.1:8080/ --model qwen/qwen3.5-9b --embed-model text-embedding-qwen3-embedding-0.6b
py yonet.py onizle sonuclar/127.0.0.1/sonuc_<tarih_saat> --diff
py yonet.py tara ... --esik 0.8 --oto-uygula      # eşiği geçenleri onaysız uygula + tekrar tara
py yonet.py onayla <klasör> --kural-hepsi --onay D020 D029 --riski-kabul D029 --ret D050
py yonet.py uygula <klasör>                    # onaylar.json yoksa yalnızca otomatik onaylılar
py yonet.py geri-al sonuclar/127.0.0.1
```

**Masaüstü uygulaması (Windows):** yukarıdaki işlemlerin hepsi tek pencereden yürütülür (README →
"Masaüstü uygulaması").
```
py masaustu/baslat.py                         # kaynaktan
py build_exe.py   (ya da build_exe.bat)       # → dist/SEO_Denetim/SEO_Denetim.exe (onedir)
dist/SEO_Denetim/SEO_Denetim.exe --oto-test rapor.json   # tam döngüyü arayüz üzerinden sına
```

## 3. Mimari

| Dosya | Sorumluluk |
|---|---|
| `calistir.py` | Flask arayüzünü başlatır |
| `yonet.py` | Yönetici modu komut satırı (tara, onizle, onayla, uygula, geri-al) |
| `deney.py`, `rag_degerlendir.py` | Deney matrisi (model × koşul × retry); RAG getirme ölçümü |
| `seo_app/canli.py` | HTTP getirme, yönlendirme zinciri, robots.txt, sitemap, HTTPS, bağlantı denetimi |
| `seo_app/tarama.py` | Site taraması (BFS + sitemap kuyruğu), yetim/derin sayfa, hreflang dönüşü |
| `seo_app/cikarma.py` | HTML'den veri çıkarma (title, meta, H1, görseller, JSON-LD, içerik imzası) |
| `seo_app/kurallar.py` | Kural denetimi, `cozum_yolu`, `DUZELTME` önerileri, sayfa kimliği (yönlendirme/parametre/canonical birleştirme), yumuşak 404 şüphesi |
| `seo_app/puanlama.py` | Puan ağırlıkları, kritik tavanlar, tarama geneli bulguların ciddiyeti: tek yapılandırma |
| `seo_app/guven.py` | Değişiklik güven puanı (0–1), zorunlu onay kuralları, otomatik onay eşiği: tek yapılandırma |
| `seo_app/ogretme.py`, `llm.py` | RAG (hibrit getirme) ve LM Studio istemcisi + öneri doğrulama |
| `seo_app/uygula.py` | Standart modda önerileri ve kural düzeltmelerini düzeltilmiş HTML kopyasına işler |
| `seo_app/boru.py` | Sayfa analiz akışı ve toplu/site taraması (`topluca_analiz`) |
| `seo_app/kategoriler.py` | Kural çözer / YZ önerir / Elle düzeltilir + risk + olası etki |
| `seo_app/yonetici.py`, `duzeltme.py`, `yz_oneri.py`, `yazma.py`, `html_konum.py` | Yönetici modu: akış, değişiklik planı, YZ önerisi doğrulama, yazma adaptörü, HTML konumları |
| `seo_app/rapor.py`, `web.py`, `sablonlar/`, `statik/` | HTML raporlar ve arayüz |
| `masaustu/` | Masaüstü başlatıcı (Tkinter): betikleri alt süreç olarak çalıştırır; onay ekranı, durum çubuğu, oto-test |
| `masaustu/salt_okunur.py` | Salt okunur taramanın komut satırı karşılığı (`web.ayarlari_dogrula` + `boru.topluca_analiz`) |
| `build_exe.py`, `masaustu/seo_masaustu.spec` | uv + Python 3.13 ortamında PyInstaller derlemesi |

**Veri akışı:**
1. **Tarama:** `boru.topluca_analiz` → `canli.sayfa_getir` (+ site modunda `tarama.Kuyruk`).
2. **Analiz:** `cikarma.extract` + `kurallar.rule_checks`/`ek_html_denetimi` + canlı denetimler → bulgular.
3. **RAG:** yalnızca `cozum_yolu == "model"` bulgular için `ogretme.ogretme_metni` → `llm.llm_fixes`.
4. **Sınıflandırma:** `kategoriler.kategori()` yalnızca gösterim ve yönetici modunda kullanılır.
5. **Rapor:** `sonuclar/<site>/sonuc_<tarih_saat>/` altına `rapor.json`, `site_ozeti.json`, `rapor.html`, `ozet.csv`.
6. **Yazma (yalnızca yönetici modu), üç aşama:** `duzeltme.plan_uret` → otomatik aşama
   (`yonetici.asama_uygula(..., "otomatik")`, tarama sonunda) → tekrar tarama `sonra_otomatik/` → onay →
   onaylı aşama (`uygula_ve_dogrula`) → tekrar tarama `sonra/` → `yonetici.rapor_uret`
   (`bulgu_durumlari.json`, `yonetici_raporu`, durumlu `rapor.html`).

## 4. Temel kavramlar

- **Standart mod (Mod 2):** salt okunur. Düzeltilmiş HTML yalnızca sonuç klasörüne
  (`duzeltilmis_*.html`) yazılır, siteye dokunulmaz.
- **Yönetici modu (Mod 1):**
  - Site kök klasörü ve temel adres açıkça verilir.
  - Taramada model çağrılmaz; YZ önerileri plan aşamasında üretilir.
  - Plan sırasında siteye yazılmaz; plandan hemen sonra otomatik aşama eşiği geçenleri yazar
    (`ayarlar["oto_uygula"]`, CLI `--oto-uygulama-yok` ile kapatılır).
- **Kategoriler** (`seo_app/kategoriler.py`):
  - **Kural çözer:** toplu onaylanabilir.
  - **YZ önerir:** tek tek onaylanır, düzenlenebilir. Canonical, noindex, hreflang ve robots
    kararları *yüksek risk*tir ve ayrıca risk onayı ister.
  - **Elle düzeltilir:** yalnızca raporda kalır.
- **`cozum_yolu` ≠ kategori:** `kurallar.cozum_yolu` (model/kural/elle) analiz akışını yönetir ve
  değiştirilmedi. Kategori ayrı bir gösterim katmanıdır.
- **Yazma adaptörü** (`seo_app/yazma.py`):
  - `SiteAdaptoru` arayüzü: oku, yaz, listele, yedekle, geri_al.
  - Tek uygulama `YerelDosyaAdaptoru`. FTP/SFTP/CMS adaptörleri henüz uygulanmadı.
  - `..`, mutlak yol, symlink ve junction reddedilir. Aracın klasörü ve `sonuclar/` hedef olamaz.
- **Aşamalı uygulama** (`duzeltme.uygula(..., asama)`):
  - İlk yazmadan önce tam yedek alınır (`yedek/`); onaylı aşama aynı yedeği kullanır.
  - Değişiklik konumları planın gördüğü özgün dosyaya göredir. Bu yüzden her aşamada dosya yedekteki
    özgün halinden yeniden kurulur: önceki aşamada uygulananlar + yeni onaylananlar; reddedilen
    otomatik değişiklik dışarıda bırakılır (geri çekilir). `plan["dosya_guncel"]` son yazılan hash'i
    tutar; dosya aşamalar arasında elle değiştiyse yazılmaz.
  - Plandan sonra değişmiş dosyaya, çakışan değişikliğe, HTML/XML/JSON-LD'yi bozan değişikliğe ve
    doldurulmamış `[doğrulanmalı: …]` yer tutucusuna yazılmaz ("Başarısız").
  - Model önerileri uygulama anında yeniden doğrulanır.
  - Aşama kaydı `plan["asamalar"]`: ad, zaman, yazılan dosyalar, ölçüldüğü tarama klasörü
    (`None` = yazıldı ama taranmadı; dosya yazılmadıysa önceki ölçüm geçerli).
- **Bulgu durumları** (`yonetici.bulgu_durumlari`): başlangıç taramasındaki her (sorun, sayfa) için
  `cozuldu_otomatik` / `cozuldu_onayli` / `onay_bekliyor` / `reddedildi` / `basarisiz` /
  `dogrulanmadi` / `elle`. "Çözüldü" yalnızca yeniden taramaya dayanır. Bulgu → değişiklik eşlemesi:
  önce (bulgu, url) birebir; site katmanındaki sayfaya özgü olmayan bulgular (robots.txt, sitemap adresi)
  ve tekrar grupları (title/meta/H1/içerik tekrarı) aynı kodun başka adresteki düzeltmesine bağlanır.
  Çözüm oranı = çözülen çözülebilir / çözülebilir (önerisi olan bulgular); "Elle" ayrı sayılır.
- **Güven puanı ve otomatik onay** (`seo_app/guven.py`):
  - Her değişikliğe 0–1 `guven` ve `guven_nedenleri` yazılır. Kural: kural başına sabit; sezgisel:
    kanıta göre; model: alan tabanı − yeniden deneme cezası (0.12) − kaynakta geçmeyen kelime cezası.
  - `guven ≥ oto_esik` (varsayılan 0.8; arayüz, `--esik`, masaüstü) olanlar otomatik onaylı gelir.
  - Güvenden bağımsız hep onay: `[doğrulanmalı]` yer tutucusu, canonical ile başka sayfaya bağlama,
    noindex/nofollow/Disallow ekleyen, 2000+ karakter silen değişiklikler (`zorunlu_onay`).
  - `onaylar.json` / `uygulama.json` her değişikliğin onay kaynağını (kullanıcı/otomatik/toplu) tutar.
- **Rollback:** `py yonet.py geri-al sonuclar/<site> [--tekrar-tara]`. `sonuclar/<site>/son_uygulama.json`
  üzerinden çalışır, tüm aşamaları birlikte geri alır ve dosya hash'leriyle doğrular. Uygulanmış
  değişiklikler `geri_alindi` olur, bulgu durumları başlangıca döner; geçmiş aşamaların ölçümleri
  raporda kalır, "Geri alma sonrası" sütunu eklenir.
- **Yönetici modu sonuç klasörü** (`sonuclar/<site>/sonuc_<tarih_saat>/`): standart çıktılar +
  `degisiklikler.json`, `onizleme.diff`, `onaylar.json`, `yedek/`, `uygulama_gunlugu.jsonl`,
  `uygulanan.diff` (aşama başlıklı), `uygulama.json`, `sonra_otomatik/`, `sonra/`, `geri_alma/`,
  `bulgu_durumlari.json`, `yonetici_raporu.json/.html`.
- **Puanlama** (`seo_app/puanlama.py`): her grup için `100 × Π(1 − ağırlık)`, ağırlıklar yüksek 0.20 /
  orta 0.09 / düşük 0.035; kritik bulgular tavan koyar (erişilemez 0, robots tüm site 20, 4xx/5xx 30,
  yumuşak 404 40, noindex 60, kopya içerik 70…). Sayfaya özgü site bulguları ve tarama geneli bulgular
  (title tekrarı, yetim, derin…) sayfa puanına girer. **İki modu da etkiler.**

## 5. Test ortamı

- **Test sitesi:** `test_sitesi/` — kurgusal "Çaylıbahçe" çay mağazası, 25 sayfa.
  - Belge kökü `test_sitesi/site/`.
  - Sunucu ayarları (yönlendirmeler, yumuşak 404) `test_sitesi/sunucu_ayarlari.json` içinde.
  - Sunucu yalnızca 127.0.0.1'de çalışır, harf duyarlıdır.
- **`sorunlar.json`** (`test_sitesi_degerlendirme/`): 47 kasıtlı sorun (18 kolay, 16 orta, 13 zor),
  analiz aracının erişemediği yerde. Her kayıtta kategori, zorluk, URL/dosya, doğru düzeltme, beklenen
  çözüm, aracın tespit kodları (`tespit`/`yan`) ve sorunun hâlâ var olup olmadığını denetleyen
  `kontrol` listesi bulunur.
- **Kontrol motoru:** `test_sitesi_degerlendirme/kontroller.py`. Hem `dogrula.py` (sorunlar var mı)
  hem `degerlendir.py` (düzeldi mi) kullanır.
- **Sıfırlama:** `sifirla.py`, `orijinal_site/` kopyasını geri yükler ve `orijinal_hashler.json`
  ile doğrular. Yalnızca `test_sitesi/site/` değişir.
- **Orijinal kopyayı yeniden üretme:** `site_uret.py`. Sayfa içeriği bu betikte yazılıdır.

```
py test_sitesi/sunucu.py                                    # 1. ayrı terminalde açık kalsın
py test_sitesi_degerlendirme/sifirla.py                     # 2. sıfırla (+ --kontrol: yalnızca karşılaştır)
py test_sitesi_degerlendirme/dogrula.py                     #    47/47 sorun sitede mi
py yonet.py tara --kok test_sitesi/site --url http://127.0.0.1:8080/ --model qwen/qwen3.5-9b
py yonet.py onayla <klasör> --kural-hepsi --onay ... ; py yonet.py uygula <klasör>   # 3-4. uygula + tekrar tara
py test_sitesi_degerlendirme/degerlendir.py --sonuc <klasör> # 5. değerlendir → <klasör>/degerlendirme.md
py yonet.py geri-al sonuclar/127.0.0.1                      # 6. geri al (ya da sifirla.py)
```

## 6. RAG ve bilgi tabanı

- **Kaynaklar** (`ogretme/`):
  - `bilgi_tabani.json`: 28 Türkçe parça. 23'ü Google Arama Merkezi (developers.google.com/search),
    4'ü W3C WAI, 1'i Google blog kaynaklı. Her parçada `kaynak`, `kaynak_basligi`, `erisim_tarihi` var.
  - `ornekler.json`: few-shot örnekler.
  - `seo_kurallari.json`: gömme modeli yokken kullanılır ve atıfsızdır.
- **Getirme** (`seo_app/ogretme.py`): sırasıyla alan filtresi, BM25 + kosinüs (ağırlıklı RRF),
  her sorunlu alanı kapsayan seçim (`bilgi_sayisi` = 5), bağlam bütçesi. İsteğe bağlı `/rerank`
  istemcisi var; gerçek bir rerank sunucusuyla denenmedi.
- **Embedding önbelleği:** `ogretme/bilgi_tabani_gomme_cache.json`. Ayrı bir indeks dosyası yok.
- **Güncelleme komutu yok:** `bilgi_tabani.json` düzenlenince bir sonraki kullanımda yalnızca
  değişen parçaların gömmesi hesaplanır (içerik hash'i ile). Bilgi tabanı sürümü rapora yazılır
  (`kb_surum`).
- **Getirme ölçümü:** `py rag_degerlendir.py --embed-model text-embedding-qwen3-embedding-0.6b`.
  Ölçüm seti `tests/veri/rag_degerlendirme.json` (133 sayfa), sonuçlar `sonuclar/rag_degerlendirme/`.
- **Yönetici modunda YZ önerileri:** `yz_oneri.YZIstemcisi` aynı `bilgi_getir`'i kullanır. Modelin
  yazdığı kaynak kimlikleri verilen parçalarla sınırlanır.

## 7. Son değişiklikler (tarih sırasıyla)

- **20 Ekim:** komut satırı betiklerinden `seo_app/` paketine ve web arayüzüne geçiş. Eski betikler
  `outdated/` içinde.
- **21 Ekim (Adım 1–10, `asama-1-2`):**
  - pytest iskeleti;
  - yerel sunucuyu siteler arası istekten (CSRF) koruma;
  - modele yalnızca `model` sınıfı sorunlar;
  - sadakat denetimi;
  - TTFB, deney koşucusu;
  - PageSpeed;
  - normalleştirilmiş kategori puanları;
  - Türkçe karakterli arayüz.
- **22 Ekim (arayüz):** form üstte / rapor altta tasarım, puan ve etiketlere bilgi balonu.
- **22 Ekim (`rag-iyilestirme`):** RAG ölçüm altyapısı, bilgi tabanının kaynaklı Türkçe yeniden
  yazımı, hibrit getirme + kaynak atfı, ölçüm seti 133 sayfa. Amaç RAG'ın gerçekten doğru parçayı
  getirdiğini ölçmekti.
- **22 Ekim (`denetim-gelistirme`, `5ed04c4`):** Screaming Frog/Sitebulb karşılaştırmasıyla site
  taraması, bağlantı/görsel, indekslenebilirlik, yönlendirme, CWV, JS render ve `rapor.html` eklendi.
- **23 Ekim (`9ba6301`):** `graphify-out/` `.gitignore`'a eklendi. `main` bu commit'e kadar
  güncellendi.
- **23 Ekim (`yonetici-modu`, `c677d96`):** iki modlu yapı, üç kategori, yazma adaptörü,
  onay/yedek/geri alma, test sitesi ve değerlendirme betikleri.
- **23 Ekim (`14d2142`):** `.gitattributes` ile test sitesi dosyaları bayt bayt saklanıyor; hash
  manifesti başka makinelerde de eşleşsin diye.
- **23 Ekim:** `yonetici-modu` `main`'e fast-forward birleştirildi (`102f83f`).
- **23 Ekim (`masaustu-uygulama`):** Tkinter masaüstü başlatıcı ve PyInstaller ile `.exe` derlemesi.
  Mevcut kod değişmedi; yeni olanlar `masaustu/`, `build_exe.py/.bat` ve `tests/test_masaustu.py`.
  `2ff300d`: PageSpeed yerel/özel ağ adreslerinde çağrılmaz.
- **23 Ekim (`dogruluk-iyilestirme`, `489189d`):**
  - Yeni denetimler: yumuşak 404 (başlık/H1 hata kalıbı + rastgele kardeş adres yoklaması),
    render'ı engelleyen betik, URL'de büyük harf, charset (her iki mod), sitemap'te yönlendiren adres.
  - Sayfa kimliği: yönlendirme takma adları, parametre canonical'ları ve %90+ benzer canonical
    birleştirmeleri tek sayfa sayılır (sahte `canonical_capraz`/tekrar bulguları kalktı).
  - Yeni düzelticiler: JSON-LD sözdizimi onarımı, fiyat/para birimi normalleştirme, isteğe bağlı yer
    tutucu alanları atma, doğrulama geri bildirimiyle bir kez yeniden deneme, uzunluk kırpma,
    `defer` ekleme, sitemap yönlendirme hedefini yazma.
  - Güven puanı + otomatik onay eşiği (web, masaüstü, CLI, yönetici raporu).
  - Yeni puanlama (`puanlama.py`); README güncellendi; `tests/test_dogruluk.py`.
  - `sorunlar.json`'a yalnızca değerlendirme etiketi eklendi (O14/Z06/Z10 tespit kodları, O03/O04 `yan`).
- **25 Ekim (`asamali-uygulama`, `98a4534`): üç aşamalı uygulama ve doğrulanmış durumlar.**
  - Kök neden: otomatik onay yalnızca bir etiketti (`onay_turu`); siteye yazan tek fonksiyon
    (`uygula_ve_dogrula`) kullanıcı "Uygula"ya basınca çalışıyordu ve plan başına bir kez
    çalışabiliyordu. Rapor yalnızca önce/sonra ortalama puanı gösteriyordu; web tablosu ve analiz
    raporu yönetici modunda da "sonra" değerini düzeltilmiş HTML kopyasından alıyordu.
  - Otomatik aşama tarama sonunda yazıyor; onaylı aşama üstüne yazıyor/geri çekiyor; her aşamadan
    sonra tam yeniden tarama (önce `canli.onbellek_temizle()`: aynı süreçteki robots/sitemap önbelleği
    yazılan dosyaları gizliyordu).
  - Bulgu durumları + üç aşamalı metrikler: `bulgu_durumlari.json`, yönetici raporu, durumlu `rapor.html`,
    web paneli/tablosu, masaüstü plan özeti ve onay penceresi, CLI tablosu.
  - Geri alma tüm aşamaları kapsıyor; durumlar ve metrikler başlangıca dönüyor (`--tekrar-tara`).
  - `degerlendir.py`: `sonra_otomatik/` desteği ve araç "Çözüldü" ↔ canlı kontrol tutarlılığı.
  - Yeni testler `tests/test_asamalar.py` (13).

- **25 Ekim (`seo-kurallari`, `819510f`): SEO kural listesinden 12 kural eklendi.**
  - Yeni kodlar: `canonical_kirik`, `sitemap_olu_adres` (artık iki modda, tarama geneli),
    `blank_noopener_yok`, `guvenlik_basligi_eksik`, `onbellek_basligi_yok`, `schema_kurum_logo_yok`,
    `schema_sosyal_profil_yok`, `breadcrumb_yok`, `yapisal_veri_onerilen_alan`,
    `robots_bilinmeyen_yonerge`, `robots_kaynak_engelliyor`, `tarih_bilgisi_yok`, `icerik_eski`,
    `anahtar_kelime_doldurma`, `form_etiketi_yok`, `buton_adi_yok`, `aria_gecersiz_referans`.
  - Düzelticiler: noopener, kuruluş logo/sameAs (sayfadaki logo görseli ve sosyal bağlantılardan),
    BreadcrumbList (adres yolu + üst sayfa H1'i), kırık canonical (mevcut canonical düzelticisi),
    robots yönerge adı ve `Allow` satırı (YZ önerir, yüksek risk; toplu kural onayına girmesin diye).
    Diğerleri elle.
  - Puanı etkiler (iki mod): test sitesinde başlangıç ortalama sayfa puanı 79 → 72, bulgu 187 → 287.
    `sorunlar.json`'a dokunulmadı; yeni bulgular değerlendirmede "plansız" (92) görünür.
  - Testler `tests/test_yeni_kurallar.py` (15).
- **26 Ekim:** graphify bilgi grafiği baştan kuruldu (kod değişmedi). Devir belgesi yeni sohbet
  için güncellendi (§0 çalışma kuralları, §8 dal ve çalışma ağacı durumu).
- **26 Ekim (`seo-kurallari`, commit'lenmedi): iki açık soru kullanıcının onayıyla kapatıldı.**
  - `anahtar_kelime_doldurma` eşiği %2,5 → %3 (`kurallar.DOLDURMA_ESIGI`; %4 üstü "orta" aynı).
    Test sitesinde 14 → 8 bulgu (son taramanın oranlarıyla hesaplandı). **İki modun puanını etkiler.**
  - Toplu onay (`--kural-hepsi`, masaüstü "tümünü onayla", web "Kural çözer grubunun tamamını
    onayla") artık `zorunlu_onay`'lı kural değişikliklerini kapsamaz; bunlar tek tek onaylanır.
    Değişen yerler: `duzeltme.kararlari_coz`, `masaustu/plan.py` (`toplu_onayli`, `onaylanan_sayisi`,
    `onay_argumanlari`), `masaustu/uygulama.py` gösterimi, `statik/uygulama.js` (zorunlu kutular
    işaretsiz gelir, toplu işarete girmez, işaretsiz kalırsa ret değil "onay bekliyor").
    Robots düzelticileri hâlâ "YZ önerir · yüksek risk"; artık kural kategorisine alınabilirler (karar bekliyor).
  - README, `yonet.py` yardım metni ve testler güncellendi (`test_toplu_kural_onayi_zorunlu_onayli_degisikligi_kapsamaz`).
- **26 Ekim:** .exe `seo-kurallari` ile yeniden derlendi (11:33); oto-test 13/13, temiz kapanış.
- **26 Ekim (commit'lenmedi): sayaçlar bulgu durumlarından (tek doğruluk kaynağı).**
  - Kök neden: durumlar doğruydu ama rapor sayaçları üç ayrı kaynaktan geliyordu (başlangıç
    `once_sorun_sayisi`/`site_ozeti`, yeniden taramanın ham `bulgu_sayisi`, durum çipi); çözülenler
    "aktif" listede kalıyordu; web `/api/html` yönetici modunda durumsuz rapor üretiyordu.
  - `yonetici.bulgu_durumlari` artık `ozet` (aktif/çözülen otomatik/onaylı), aşama başına aynı sayaçlar,
    `sayfalar` (sayfa sayaçları + başlangıç/güncel puan + çözüm oranı) ve çözülen bulgu için `cozum`
    (değişiklik özeti, güven, onay kaynağı) üretir; `rapor.html`, `yonetici_raporu`, web, CLI ve .exe özeti
    bunu okur. Tespit/puanlama/düzeltme ve Mod 2 raporu değişmedi.
  - Test sitesinde (modelsiz): otomatik 187 aktif + 94 çözülen = 281; D003/D004 onay + D049 ret →
    186 + 94 + 1; geri alma → 281 + 0. Dört yüzey aynı sayıyı verdi. Testler 293 geçti.
  - Ardından sayaç birimi: site geneli ayarlar (HTTPS, HTTPS yönlendirmesi, güvenlik başlıkları,
    `sitemap_hatali_adres`, ayrıca puanlamada sayfaya özgü olan `onbellek_basligi_yok` —
    `yonetici.SUNUCU_AYARI_KODLARI`) bir kez sayılır; sayfa sayaçlarına girmez, "Site geneli ayarlar"
    bölümünde gösterilir. Test sitesinde 281 bulgu → 133 birim; otomatik: 69 aktif (65 sayfa + 4 ayar) +
    64 çözülen; 2 onay + 1 ret: 68 + 64 + 1; geri alma: 133 + 0.
  - Takma adres bulguları (`yonetici.asil_adresler`, `takma_adresleri_bagla`): yönlendirme/parametreli
    adresteki bulgu asıl sayfadaki aynı koda, geçersiz sayfanın (yumuşak 404, hata kodu) içerik bulguları o
    sorunun kendisine bağlanır; durum asıldan gelir, sayaca bir kez girer. Test sitesinde 133 → 102 birim
    (31 bağlı); otomatik: 50 aktif (46 sayfa + 4 ayar) + 52 çözülen; 2 onay + 1 ret: 49 + 52 + 1;
    geri alma: 102 + 0. Testler 294 geçti.

- **26 Ekim (commit'lenmedi): Google SEO Başlangıç Rehberi.**
  - Çekme modülü/güncelleme komutu yoktu (görev bunu varsayıyordu); kullanıcı kararıyla mevcut yöntem:
    rehberin 18 bölümü kendi cümlelerimizle 23 Türkçe parça olarak `bilgi_tabani.json`'a eklendi
    (28 → 51; `kaynak` = TR bölüm çapası, ek alanlar `kaynak_en`, `lisans` CC BY 4.0). Mevcut kayıtlar
    bayt düzeyinde aynı (yalnızca sona ekleme).
  - `ornekler.json` +5 rehber örneği (`kaynak.etiket = "google-starter-guide"`, isteme girmez);
    `ogretme/rehber_ornekleri.json` (19 sorunlu → tavsiye → düzeltilmiş HTML örneği, isteme girmez).
  - Getirme: `ogretme.BILGI_ALANI_SORUN` model dışı bulguları (canonical, kopya, adres, bağlantı…) bilgi
    alanına bağlar; önceden bu bulgularda yalnızca 'genel' parçalar geliyordu. Mod 2 istemi değişmez.
  - Yeni kontroller: `url_aciklayici_degil`, `alt_metni_anlamsiz` (YZ, model alanı img_alt),
    `kullanici_baglantisi_isaretsiz` (kural, rel="ugc nofollow"), `uzun_metin_ara_baslik_yok`,
    `video_baslik_yok`. Rehberle çelişenler (onaylı): `h1_birden_fazla` düşük + güven 0.6 (otomatik
    değil), `icerik_az` metninde kelime hedefi yok, `baslik_atlamasi` erişilebilirlik olarak etiketli,
    `sitemap_yok` düşük, `icerik_tekrar` orta ve puan tavanı yok. **İki modun puanını etkiler.**
  - Ölçüm (qwen3.5-9b, otomatik aşama): düzeldi 36/47 → 35/47 (fark K08: fazla H1 artık onay bekliyor);
    sayfa puanı 72 → 73 (başlangıç); yeni kontroller test sitesinde bulgu üretmedi; kurgusal 5 sayfada
    5/5 doğru, 0 yanlış alarm. RAG (133 sayfa): kapsama 1.0, MRR 0.969 → 0.972, altın listeye göre sorun
    isabeti 0.935 → 0.833 (rehber parçaları altın listede değil; konuya göre ~0.92).
  - Ardından (kullanıcı kararıyla): RAG altın listesine t06/m06/g06/g07 eklendi (`rag_olcum.ALTIN_SURUM`,
    `ozet.json`'a yazılır); aynı listeyle 0.935 (eski taban) → 0.929 (yeni). Kopya içerik (`icerik_tekrar`):
    sitede `.htaccess`/`_redirects` varsa kopya adres için 301 satırı (`duzeltme.yz_yonlendirme`, zorunlu onay),
    yoksa canonical + "301 tercih edin" gerekçesi. `sorunlar.json` K08: `"onay_gerekir": true` (yalnızca
    değerlendirme); `degerlendir.py` onay bekleyen beklenen düzeltmeleri ayrıca gösterir.

## 8. Mevcut durum

- **Testler:** `py -m pytest -q` → 290 geçti, 1 atlandı (Windows'ta sembolik bağlantı yetkisi yok).
  Python 3.13 derleme ortamında 289'luk sürümde denendi; 290'lık sürüm 3.13'te koşulmadı `[doğrulanmalı]`.
- **.exe oto-testi (26 Ekim, `seo-kurallari` = `819510f`, eşik/toplu onay değişikliklerinden önce):**
  13/13 adım, temiz kapanış (süreç kalmadı, 8080/5000 kapalı). Tespit 47/47, düzeldi 37/47
  (kural 13/13, YZ 23/27, elle 1/7); sayfa puanı 72 → 88 (otomatik) → 88 (onaylı), bulgu 287 → 163 → 156.
  Rapor: oturumun geçici klasöründe (`oto_rapor.json`), çıktılar `sonuclar/127.0.0.1/sonuc_2026-10-26_11-34-22/`.
- **Düzelticinin yarattığı yeni bulgular (incelendi, 25 Ekim 23:37 taraması):** otomatik aşamadan sonra
  9 yeni bulgu. 6'sı `urunler/beyaz-cay.html`'de (düzeltmeyle taramaya giren sayfa; site geneli başlık/
  HTTPS bulguları). `yapisal_veri_onerilen_alan` (rize-filiz): D025 bozuk JSON-LD'yi onarınca görünür oldu.
  `anahtar_kelime_doldurma` (hakkımızda, %2,6): yeni eşikle kalktı. **Açık:** `schema_sosyal_profil_yok`
  (ana sayfa): `yz_jsonld` (`schema_kurum_turu_yok`) Organization bloğuna logoyu sayfadan veriyor ama
  sosyal profilleri vermiyor; çözüm `kural_sosyal_profil`'deki bağlantı toplama yardımcıya alınıp
  profiller modele + kaynak metne verilmeli, model yazmazsa `sameAs` eklenmeli (henüz yapılmadı).
- **.exe tam döngüsü (23 Ekim, `--oto-test`, qwen3.5-9b):**
  - .exe proje dışında, Türkçe karakterli bir klasörden çalıştırıldı; 13/13 adım başarılı.
  - Döngü: test sitesi → doğrula → modelli tarama (399 sn) → onay → uygula → değerlendir → geri al
    → iptal → sıfırla → doğrula → web arayüzü.
  - Arayüz en fazla 112 ms takıldı.
  - Kapanışta geride süreç kalmadı, 8080 ve 5000 portları kapandı.
  - Doğrula ve hash karşılaştırma çıktıları doğrudan CLI ile satır satır aynı.
  - "LM Studio kapalı" durumu, LM adresi kullanılmayan bir porta çevrilerek denendi.
- **Mod 2 eşdeğerliği:** `main` ile `yonetici-modu` aynı test sitesini taradığında `rapor.json`,
  `site_geneli.json`, `site_ozeti.json` ve puanlar aynı çıktı. Fark yalnızca HTML rapordaki
  kategori etiketlerinde.
- **Yönetici modu tam döngüsü (23 Ekim, qwen3.5-9b):**
  - Plan: 20 kural, 32 YZ önerisi (13 yüksek risk), 9 elle iş.
  - 47 değişiklik uygulandı, 4 öneri doğrulamada elendi.
  - Sorunlar: tespit 44/47, düzeldi 35/47 (kural 13/13, YZ 22/27, elle 0/7).
  - Geri alma sonrası 48 dosyanın hash'i eşleşti.
  - Çıktılar `sonuclar/127.0.0.1/sonuc_2026-10-23_12-48-02/` (git'te değil, yerel).
- **Güven eşikli tam döngü (`dogruluk-iyilestirme`, qwen3.5-9b, hiç elle onay yok):**
  - Plan: 25 kural, 31 YZ, 11 elle; 50 değişiklik eşiği (0.80) geçti, 5 onay bekledi, 1 geçersiz.
  - Tespit 47/47; düzeldi 36/47 (kolay 17/18, orta 10/16, zor 9/13; kural 13/13, YZ 23/27, elle 0/7).
  - Yeni çıkan bulgu 0. Geri alma + `sifirla.py` sonrası 48 dosyanın hash'i eşleşti.
  - Çıktılar `sonuclar/127.0.0.1/sonuc_2026-10-23_18-56-35/`.
- **Üç aşamalı tam döngü (25 Ekim, qwen3.5-9b, CLI):**
  - Otomatik aşama: onaysız 50 değişiklik / 19 dosya; sayfa puanı 79 → 95, sorun 187 → 81,
    çözüm oranı %91 (73/80 çözülebilir); 5 onay bekledi, D048 doğrulamadan geçmedi (Başarısız).
  - Onaylı aşama: D004/D005 (`defer`) ve D038 onaylandı; D050, D029 reddedildi; otomatik yazılmış
    D024 (iletişim title) geri çekildi. D038 uygulandı ama ince içerik hâlâ bulunuyor → "Başarısız –
    düzeltme etkisiz". Durumlar: Çözüldü (otomatik) 89, Çözüldü (onaylı) 1, Reddedildi 4, Başarısız 3, Elle 90.
  - `degerlendir.py`: düzeldi 36/47; araç 34 sorunu "Çözüldü" dedi, 34'ü canlı kontrolde de düzelmiş
    (yanlış "Çözüldü" yok); eksik: O07 (sayfa sitemap'ten çıkınca taranmadığı için doğrulanamıyor).
  - Geri alma (`--tekrar-tara`): 19 dosya geri yazıldı, 48 hash eşleşti; ölçüm başlangıçla aynı
    (79 / 187), durumlar başlangıçtaki gibi (78 onay bekliyor, 2 başarısız, 107 elle).
  - Çıktılar `sonuclar/127.0.0.1/sonuc_2026-10-25_22-28-42/`.
- **Kısmen çalışan:**
  - İnce içerik (`O10`, `O11`): paragraf önerileri düşük güvenli (0.44/0.58), onay bekliyor.
  - `K05`: model tek uzun cümle yazıyor (186 karakter); kırpma yalnızca son cümle/marka eki atar.
  - Kopya içerik (`Z08`) canonical birleştirme olarak önerilir, her zaman onay ister.
  - `defer` (`Z10`) güveni 0.6: satır içi betik bağımlılığı denetlenmiyor.
- **Henüz uygulanmadı:**
  - FTP/SFTP/CMS adaptörleri.
  - Rerank sunucusuyla gerçek deneme.
  - 58 Düzce sitesinde modelli tam tarama (önceki notlara göre) `[doğrulanmalı]`.
- **Dallar (26 Ekim):**
  - `main` = `asamali-uygulama` = `aa2cc57`, ikisi de GitHub'da (`origin`). Önceki dallar
    (`yonetici-modu`, `dogruluk-iyilestirme` = `489189d` vb.) `main`'e birleştirilmiş durumda.
  - `seo-kurallari` = `819510f` (12 yeni kural), `main`'in bir commit önünde. **Yalnızca yerelde**;
    push ve birleştirme kullanıcının kararını bekliyor (`git push -u origin seo-kurallari`).
  - Commit mesajlarından `Co-Authored-By` satırları silindi (geçmiş yeniden yazıldı, GitHub'a
    zorla gönderildi). Eski hâli yerel `yedek/coauthor-oncesi-main` ve `yedek/coauthor-oncesi-masaustu`
    etiketlerinde; kullanıcı isterse silinebilir. Yeni commit'lerde de bu satır yazılmaz (§0).
- **Çalışma ağacı (26 Ekim):** test sitesi geri alındı ve oto-test sonunda sıfırlandı; 48 dosyanın
  hash'i orijinalle eşleşiyor, `test_sitesi/` git'te temiz. Commit'lenmemiş değişiklikler: `handover.md`,
  `README.md`, `yonet.py`, `seo_app/kurallar.py`, `seo_app/duzeltme.py`, `seo_app/statik/uygulama.js`,
  `masaustu/plan.py`, `masaustu/uygulama.py`, üç test dosyası. İzlenmeyen `CLAUDE.md` ve `.claude/`
  graphify/Claude Code ayarlarıdır.
- **.exe:** son derleme 26 Ekim 11:33 (`seo-kurallari` = `819510f`). `seo_app` ve `masaustu/*.py`
  .exe'ye gömülmez, proje klasöründen okunur; eşik/toplu onay değişiklikleri için yeniden derleme
  gerekmez. Değişikliklerden sonra oto-test tekrarlanmadı `[doğrulanmalı]`.
- **Tarama çıktıları git dışında:** `sonuclar/` tamamen `.gitignore`'da (`3bad90d`). Önceden
  izlenen 114 dosya (örn. `adim9_lighthouse/`) depodan çıkarıldı, diskte duruyor; eski sürümleri
  git geçmişinde (`git show 0261537:sonuclar/...`).

## 9. Alınan kararlar

- **Fine-tuning yerine RAG + few-shot:** kodda ve belgelerde açık bir gerekçe kaydı bulunamadı
  `[doğrulanmalı]`. Uygulamada model değiştirilmeden bilgi tabanı ve örneklerle yönlendiriliyor.
- **Deney koşulu sabit `ornek+bilgi`** (`boru.VARSAYILAN_AYARLAR["kosul"]`): arayüzde seçilmez.
  Koşul karşılaştırması yalnızca `deney.py --kosullar` ile yapılır.
- **Kaydedilmiş HTML analizi kaldırıldı (21 Ekim):** yalnızca canlı adres taranır. `snapshots/`
  yalnızca testlerde örnek sayfa olarak duruyor.
- **Modele yalnızca `model` sorunları gider** (title, meta, H1, alt metni): "model başarısı" ile
  "araç başarısı" ölçümleri karışmasın diye.
- **Sessiz geri dönüş yok:** LM Studio ya da model yoksa tarama hata verir. Modelsiz çalışmak için
  "yalnızca denetle" açıkça seçilmelidir.
- **Kategori ayrı katman:** `cozum_yolu` değiştirilmedi ki Mod 2 analizi ve puanları değişmesin.
  Başta yönetici moduna özgü olan `charset_yok` (23 Ekim) ve `sitemap_olu_adres` (25 Ekim) artık
  iki modda da çalışıyor.
- **Parça değişimi:** dosyalar BeautifulSoup ile yeniden yazılmaz; diff okunur kalır ve dosyanın
  plan sonrası değiştiği algılanabilir.
- **Uydurmaya karşı yer tutucu:** model sitede olmayan bilgiyi `[doğrulanmalı: …]` ile yazar;
  doldurulmadan uygulanamaz.
- **Puan aracın kendi ölçeğidir**, bağımsız bir ölçüm değildir. Ağırlıklar test sitesinin gerçek
  sorun listesine göre ayarlandı: ≥2 gerçek sorunlu 14 sayfadan 90+ alan 13 → 2; kritik sorunsuz
  sayfalarda Spearman(puan, gerçek sorun) −0.41 → −0.57. Tüm sayfalarda Spearman −0.2 civarında kalır,
  çünkü tek kritik sorun (noindex, 404) birçok küçük sorundan ağır basar; bu bilinçli.
- **Otomatik onay sınırı:** yüksek riskli kararlar (canonical, hreflang, robots) güvene göre
  otomatik onaylanabilir; indekslemeyi kapatan ve sayfayı dizinden düşüren değişiklikler hiçbir
  eşikte otomatik değildir. Pillow eklenmedi; büyük görsel elle düzeltilir.
- **Masaüstü uygulaması yalnızca arayüz katmanıdır:**
  - Her işlem mevcut betiği alt süreç olarak çalıştırır. Onaylar `yonet.py onayla` argümanlarına
    çevrilir; `onaylar.json` dosyasına doğrudan yazılmaz.
  - Salt okunur taramanın CLI'ı yoktu. `masaustu/salt_okunur.py` web arayüzüyle aynı fonksiyonları
    çağırır.
  - `seo_app` .exe'ye gömülmez, proje klasöründen okunur.
- **.exe kararları:**
  - Paketleme uv ile ayrı bir Python 3.13 ortamında, PyInstaller ile *onedir* olarak yapılır.
  - Arayüzde "Bilgi tabanı" sekmesi şimdilik yok: Google'dan içerik çeken bir güncelleme betiği yok.
  - Uygula, geri al, sıfırla ve onay kaydı yarıda kesilemez (yazma işlemleri).

## 10. Bilinen tuzaklar

- **LM Studio kapalı:** tarama başlamaz ("LM Studio sunucusuna ulaşılamadı"). Arayüzdeki
  "Modelleri getir" ile sınayın. Port daha önce 1234/1235 arasında değişti.
- **`localhost` gecikmesi:** Windows'ta `localhost` önce IPv6'ya çözülür ve her isteğe ~2 sn ekler.
  Kod `127.0.0.1` kullanır (`llm.istek_adresi`).
- **Türkçe karakter:**
  - Dosyalar UTF-8 okunur/yazılır; JSON yanıtlarında `ensure_ascii=False`.
  - Konsolda bozuk görünürse `PYTHONIOENCODING=utf-8` kullanılabilir.
  - Bash heredoc'larında Türkçe/JSON kaçışları sorun çıkardı; betikleri dosyaya yazıp çalıştırmak
    daha güvenli.
- **Satır sonları:** Python Windows'ta CRLF yazar, `core.autocrlf=true`. Test sitesi bu yüzden
  `.gitattributes` ile `-text`. Yeni test dosyası eklerken manifesti `site_uret.py` ile yeniden üretin.
- **Harf duyarlılığı:** Windows'ta `HANDOVER.md` ile `handover.md` aynı dosyadır. Test sunucusu
  Linux gibi harf duyarlı davranacak şekilde yazıldı.
- **PATH:** Python için `py` kullanın. Node PATH'te değil; gerekirse fnm altındaki
  `node.exe` tam yoluyla çalıştırılır `[doğrulanmalı: makineye özgü]`.
- **Python 3.15:** proje bağımlılıkları kurulu ve çalışıyor (lxml 6.1.3, brotlicffi 1.2.0.2,
  Flask 3.1.3). Yardımcı araç graphify'ın `tree-sitter` bağımlılığının 3.15 tekerleği yoktu; uv ile
  ayrı Python 3.13 ortamına kuruldu.
- **Git worktree:** bu yolda (`Düzce Üniversitesi`, uzun geçici yol) `git worktree add`
  başarısız oldu. Karşılaştırma için `git archive main | tar -x` kullanıldı.
- **PageSpeed localhost'u ölçemez:** yerel/özel ağ adreslerinde hiç çağrılmaz ("atlandı"); önceden
  modelli döngüyü ~9 dk'ya uzatıyordu.
- **Eski testler ve otomatik onay:** yönetici modu testleri `esik=1.01` ile (otomatik onay kapalı)
  çalışır. Sahte YZ yeniden denemede son yanıtını tekrarlar.
- **Masaüstü / .exe:**
  - .exe projenin kodunu gömülü **Python 3.13** ile çalıştırır. Kaynaktan çalışmada 3.15 kullanılır.
    Testler iki sürümde de geçiyor; yeni kod 3.13 ile uyumlu kalmalı.
  - .exe'nin kullandığı modüller, `seo_masaustu.spec` derleme sırasında proje dosyalarının import
    satırları taranarak eklenir. `seo_app`'e yeni bir dış kütüphane eklenince yeniden derlemek gerekir.
  - Pencereli .exe'nin stdout'u cp1252'dir. `baslat.akislari_hazirla` her modda UTF-8'e çevirir.
  - Windows'ta kapalı bir porta bağlanmak zaman aşımına kadar sürer. Port ve LM denetimleri arayüz
    iş parçacığında yapılmaz (`Uygulama.arka_planda`).
  - Ayarlar `%APPDATA%\SEO Denetim Aracı\ayarlar.json` dosyasındadır. Oto-test için `--ayar` ile ayrı
    bir dosya verin.

## 11. Sonraki adımlar (öncelik sırasıyla)

1. Hocadan konu ve kapsam onayı. Önceki notlarda "alınmadı" olarak duruyordu `[doğrulanmalı]`.
2. 58 Düzce sitesinde (`test_setleri/duzce_birimleri.txt`) modelli tarama ve `deney.py` ile deney
   matrisi (model × `sifir`/`ornek`/`bilgi`/`ornek+bilgi` × retry).
3. Elle değerlendirme tablosu: sadakat ve Türkçe kalitesi, en az 2 kişi, model adı gizli.
4. Literatür taraması ve ödev metni. Metin öğrencilerce yazılmalı; kodda YZ yardımı yöntem
   bölümünde belirtilmeli.
5. Açık sorular (yönetici modu):
   - `canonical_yok` Kural çözer mi kalmalı, YZ önerir · yüksek risk mi?
   - Kopya içerik için özgünleştirme görevi eklensin mi?
6. `seo-kurallari` dalı: 26 Ekim değişikliklerini commit'lemek (kullanıcı isteyince), push edip
   `main`'e birleştirmek. Değişikliklerden sonra oto-testi bir kez daha koşmak. Puanlama ve yeni
   denetimler Mod 2 puanlarını da değiştirir; Düzce sitelerindeki eski sonuçlarla karşılaştırma
   yeniden yapılmalı.
   - Yapılacak: `yz_jsonld` Organization önerisine sayfadaki sosyal profillerden `sameAs` (§8).
   - Kapandı (26 Ekim): doldurma eşiği %3; toplu onay `zorunlu_onay`'a uyuyor.
   - Yeni soru: robots düzelticileri (`robots_bilinmeyen_yonerge`, `robots_kaynak_engelliyor`)
     artık "Kural çözer"e alınsın mı? Toplu onay açığı kapandığı için engel kalmadı.
7. Açık sorular (güven): K05 için kelime sınırında kırpma eklensin mi? `defer` güveni satır içi
   betik bağımlılığı denetlenerek yükseltilsin mi? Eşik 0.8 başka sitelerde ölçülmeli.
8. Diğer kararlar:
   - `test_sitesi/site/` git'te kalsın mı, `.gitignore`'a alınıp `sifirla.py` ile mi üretilsin?
9. `seo_kurallari.json` atıfsız. Ödevde kullanılacaksa kaynaklandırılmalı.
