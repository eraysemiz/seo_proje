# HANDOVER: Yerel Dil Modeli ile SEO Denetimi ve İyileştirme

Son güncelleme: **23 Ekim 2026** · Aktif dal: `yonetici-modu` (son commit `14d2142`).
Ayrıntılı kullanım: [README.md](README.md). Bu belgenin önceki sürümü (ödev bağlamı, Düzce birim
siteleri bulguları, 20–23 Ekim notları) git geçmişinde: `git show 14d2142:handover.md`.

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
py yonet.py onayla <klasör> --kural-hepsi --onay D020 D029 --riski-kabul D029 --ret D050
py yonet.py uygula <klasör>
py yonet.py geri-al sonuclar/127.0.0.1
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
| `seo_app/kurallar.py` | Kural denetimi, `cozum_yolu`, puanlama, `DUZELTME` önerileri |
| `seo_app/ogretme.py`, `llm.py` | RAG (hibrit getirme) ve LM Studio istemcisi + öneri doğrulama |
| `seo_app/uygula.py` | Standart modda önerileri ve kural düzeltmelerini düzeltilmiş HTML kopyasına işler |
| `seo_app/boru.py` | Sayfa analiz akışı ve toplu/site taraması (`topluca_analiz`) |
| `seo_app/kategoriler.py` | Kural çözer / YZ önerir / Elle düzeltilir + risk + olası etki |
| `seo_app/yonetici.py`, `duzeltme.py`, `yz_oneri.py`, `yazma.py`, `html_konum.py` | Yönetici modu: akış, değişiklik planı, YZ önerisi doğrulama, yazma adaptörü, HTML konumları |
| `seo_app/rapor.py`, `web.py`, `sablonlar/`, `statik/` | HTML raporlar ve arayüz |

**Veri akışı:**
1. **Tarama:** `boru.topluca_analiz` → `canli.sayfa_getir` (+ site modunda `tarama.Kuyruk`).
2. **Analiz:** `cikarma.extract` + `kurallar.rule_checks`/`ek_html_denetimi` + canlı denetimler → bulgular.
3. **RAG:** yalnızca `cozum_yolu == "model"` bulgular için `ogretme.ogretme_metni` → `llm.llm_fixes`.
4. **Sınıflandırma:** `kategoriler.kategori()` yalnızca gösterim ve yönetici modunda kullanılır.
5. **Rapor:** `sonuclar/<site>/sonuc_<tarih_saat>/` altına `rapor.json`, `site_ozeti.json`, `rapor.html`, `ozet.csv`.
6. **Yazma (yalnızca yönetici modu):** `duzeltme.plan_uret` → onay → `duzeltme.uygula` (adaptör) → tekrar tarama.

## 4. Temel kavramlar

- **Standart mod (Mod 2):** salt okunur. Düzeltilmiş HTML yalnızca sonuç klasörüne
  (`duzeltilmis_*.html`) yazılır, siteye dokunulmaz.
- **Yönetici modu (Mod 1):**
  - Site kök klasörü ve temel adres açıkça verilir.
  - Taramada model çağrılmaz; YZ önerileri plan aşamasında üretilir.
  - Plan sırasında siteye yazılmaz.
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
- **Onay → yedek → uygulama:**
  - Yazmadan önce tam yedek alınır (`yedek/`).
  - Plandan sonra değişmiş dosyaya, çakışan değişikliğe, HTML/XML/JSON-LD'yi bozan değişikliğe ve
    doldurulmamış `[doğrulanmalı: …]` yer tutucusuna yazılmaz.
  - Model önerileri uygulama anında yeniden doğrulanır.
- **Rollback:** `py yonet.py geri-al sonuclar/<site>`. `sonuclar/<site>/son_uygulama.json`
  üzerinden çalışır ve dosya hash'leriyle doğrular.
- **Yönetici modu sonuç klasörü** (`sonuclar/<site>/sonuc_<tarih_saat>/`): standart çıktılar +
  `degisiklikler.json`, `onizleme.diff`, `onaylar.json`, `yedek/`, `uygulama_gunlugu.jsonl`,
  `uygulanan.diff`, `uygulama.json`, `sonra/`, `yonetici_raporu.json/.html`.

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

## 8. Mevcut durum

- **Testler:** `py -m pytest -q` → 226 geçti, 1 atlandı (Windows'ta sembolik bağlantı yetkisi yok).
- **Mod 2 eşdeğerliği:** `main` ile `yonetici-modu` aynı test sitesini taradığında `rapor.json`,
  `site_geneli.json`, `site_ozeti.json` ve puanlar aynı çıktı. Fark yalnızca HTML rapordaki
  kategori etiketlerinde.
- **Yönetici modu tam döngüsü (23 Ekim, qwen3.5-9b):**
  - Plan: 20 kural, 32 YZ önerisi (13 yüksek risk), 9 elle iş.
  - 47 değişiklik uygulandı, 4 öneri doğrulamada elendi.
  - Sorunlar: tespit 44/47, düzeldi 35/47 (kural 13/13, YZ 22/27, elle 0/7).
  - Geri alma sonrası 48 dosyanın hash'i eşleşti.
  - Çıktılar `sonuclar/127.0.0.1/sonuc_2026-10-23_12-48-02/` (git'te değil, yerel).
- **Araçta denetimi olmayan sorunlar:** yumuşak 404, render'ı engelleyen kaynak, URL'de büyük harf;
  standart modda charset eksikliği.
- **Kısmen çalışan:**
  - İnce içerik genişletme: ıhlamur sayfasında eklenen paragraf yeterli olmadı (`O11`).
  - Kopya içerik için yalnızca canonical öneriliyor; özgünleştirme önerisi üretilmiyor.
  - Kısa alanlardaki "sayfada olmayan kelime" kuralı bazı geçerli önerileri eliyor (örnek: bitki
    çayları meta açıklaması).
- **Henüz uygulanmadı:**
  - FTP/SFTP/CMS adaptörleri.
  - Rerank sunucusuyla gerçek deneme.
  - 58 Düzce sitesinde modelli tam tarama (önceki notlara göre) `[doğrulanmalı]`.
- **Merge edilmemiş dal:** `yonetici-modu` henüz `main`'e birleştirilmedi ve push edilmedi.
- **Git dışındaki tarama çıktıları:** `sonuclar/127.0.0.1/`, `books.toscrape.com/`,
  `crawler-test.com/`, `ogrenciportali9.wordpress.com/`, `pierrecardin.com.tr/`.

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
  Yönetici moduna özgü denetimler (`charset_yok`, `sitemap_olu_adres`) Mod 2'ye eklenmedi.
- **Parça değişimi:** dosyalar BeautifulSoup ile yeniden yazılmaz; diff okunur kalır ve dosyanın
  plan sonrası değiştiği algılanabilir.
- **Uydurmaya karşı yer tutucu:** model sitede olmayan bilgiyi `[doğrulanmalı: …]` ile yazar;
  doldurulmadan uygulanamaz.
- **Puan aracın kendi ölçeğidir** (yüksek 15 / orta 8 / düşük 3 ceza), bağımsız bir ölçüm değildir.

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
- **PageSpeed localhost'u ölçemez:** düzeltilmiş ya da yerel sayfa için "sonra" Lighthouse puanı alınamaz.

## 11. Sonraki adımlar (öncelik sırasıyla)

1. `yonetici-modu` dalını gözden geçirip `main`'e birleştirmek ve push etmek (kullanıcı kararı).
2. Hocadan konu ve kapsam onayı. Önceki notlarda "alınmadı" olarak duruyordu `[doğrulanmalı]`.
3. 58 Düzce sitesinde (`test_setleri/duzce_birimleri.txt`) modelli tarama ve `deney.py` ile deney
   matrisi (model × `sifir`/`ornek`/`bilgi`/`ornek+bilgi` × retry).
4. Elle değerlendirme tablosu: sadakat ve Türkçe kalitesi, en az 2 kişi, model adı gizli.
5. Literatür taraması ve ödev metni. Metin öğrencilerce yazılmalı; kodda YZ yardımı yöntem
   bölümünde belirtilmeli.
6. Açık sorular (yönetici modu):
   - `canonical_yok` Kural çözer mi kalmalı, YZ önerir · yüksek risk mi?
   - Kısa alanlardaki "sayfada olmayan kelime" kuralı gevşetilsin mi?
   - Kopya içerik için özgünleştirme görevi eklensin mi?
7. Araçta denetimi olmayan sorunları (yumuşak 404, render'ı engelleyen kaynak, URL büyük harf,
   charset) eklemek. Mod 2 sonuçlarını değiştirir, ayrı karar ister.
8. Diğer kararlar:
   - `test_sitesi/site/` git'te kalsın mı, `.gitignore`'a alınıp `sifirla.py` ile mi üretilsin?
   - `sonuclar/` altındaki deneme çıktıları ne olacak?
9. `seo_kurallari.json` atıfsız. Ödevde kullanılacaksa kaynaklandırılmalı.
