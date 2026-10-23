#!/usr/bin/env python3
"""Test sitesinin sorunlu orijinal halini uretir: test_sitesi_degerlendirme/orijinal_site/

Site kurgusaldir (Çaylıbahçe adli bir cay magazasi). Sorunlar sayfalarin dogal yapisina
gomuludur; hangi sorunun nerede oldugu yalnizca sorunlar.json'da kayitlidir. Bu betik yalnizca
orijinal kopyayi yeniden uretmek icindir; canli site sifirla.py ile bu kopyadan geri yuklenir.

Kullanim: py test_sitesi_degerlendirme/site_uret.py
"""
import json
import random
import shutil
import struct
import zlib
from pathlib import Path

BURASI = Path(__file__).resolve().parent
HEDEF = BURASI / "orijinal_site"
TABAN = "http://127.0.0.1:8080"
SITE = "Çaylıbahçe"


# ------------------------------------------------------------------ gorseller
def png_yaz(yol, genislik, yukseklik, gurultu=False, renk=(46, 125, 50)):
    rastgele = random.Random(7)
    satirlar = bytearray()
    for _ in range(yukseklik):
        satirlar.append(0)
        if gurultu:
            satirlar += bytes(rastgele.getrandbits(8) for _ in range(genislik * 3))
        else:
            satirlar += bytes(renk) * genislik

    def parca(tur, veri):
        return struct.pack(">I", len(veri)) + tur + veri + struct.pack(">I", zlib.crc32(tur + veri) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", genislik, yukseklik, 8, 2, 0, 0, 0)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(b"\x89PNG\r\n\x1a\n" + parca(b"IHDR", ihdr) +
                    parca(b"IDAT", zlib.compress(bytes(satirlar), 9)) + parca(b"IEND", b""))


def svg_yaz(yol, etiket, zemin, vurgu, genislik=400, yukseklik=300):
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{genislik}" height="{yukseklik}" '
        f'viewBox="0 0 {genislik} {yukseklik}">'
        f'<rect width="100%" height="100%" fill="{zemin}"/>'
        f'<ellipse cx="{genislik / 2}" cy="{yukseklik * 0.62}" rx="{genislik * 0.22}" ry="{yukseklik * 0.2}" fill="{vurgu}"/>'
        f'<rect x="{genislik * 0.36}" y="{yukseklik * 0.3}" width="{genislik * 0.28}" height="{yukseklik * 0.3}" '
        f'rx="18" fill="{vurgu}" opacity="0.85"/>'
        f'<text x="50%" y="{yukseklik * 0.16}" text-anchor="middle" font-family="Georgia, serif" '
        f'font-size="{max(14, genislik // 18)}" fill="#1b3a1f">{etiket}</text></svg>\n', encoding="utf-8")


# ------------------------------------------------------------------ sablon
MENU = ('<header class="ust"><a class="logo" href="/"><img src="/img/logo.svg" alt="Çaylıbahçe logosu" '
        'width="160" height="48"></a><nav aria-label="Ana menü"><ul>'
        '<li><a href="/">Ana Sayfa</a></li><li><a href="/urunler/">Ürünler</a></li>'
        '<li><a href="/blog/">Blog</a></li><li><a href="/hakkimizda.html">Hakkımızda</a></li>'
        '<li><a href="/iletisim.html">İletişim</a></li></ul></nav></header>')
ALT = ('<footer class="alt"><ul><li><a href="/sss.html">Sıkça Sorulan Sorular</a></li>'
       '<li><a href="/kargo-ve-iade.html">Kargo ve İade</a></li><li><a href="/gizlilik.html">Gizlilik Politikası</a></li>'
       '<li><a href="/en/">English</a></li></ul><p>© 2026 Çaylıbahçe. Tüm hakları saklıdır.</p></footer>')


# Sayfalara ozgu ek bolumler (her sayfanin ana icerigi kendi konusunu yeterince anlatsin diye)
EK = {
    "index.html": """
<h2>Neden küçük partiler?</h2>
<p>Büyük depolarda aylarca bekleyen çay, kokusunun önemli bir bölümünü kaybeder. Biz ise her hafta yalnızca
o haftanın siparişlerine yetecek kadar çay paketliyoruz. Bu yöntem sayesinde paketi açtığınız anda yaprakların
taze kokusunu fark edebilirsiniz.</p>
""",
    "urunler/index.html": """
<h2>Ürünlerimizi nasıl seçiyoruz?</h2>
<p>Kataloğa eklediğimiz her çayı önce kendi mutfağımızda farklı sürelerle demleyip tadına bakıyoruz. Rengi,
kokusu ve ikinci demlemedeki davranışı beklentimizi karşılamayan ürünleri listeye almıyoruz. Bitki çaylarında
ise yaprakların ne zaman toplandığını ve nasıl kurutulduğunu toplayıcılarımızla birlikte kontrol ediyoruz.
Her ürün kartındaki kısa açıklama, o çayın en belirgin tat notasını özetler; ayrıntılı demleme önerisi için
ürün sayfasına geçebilirsiniz. Sezonu biten ürünler katalogdan kaldırılır ve arşiv bölümüne taşınır.</p>
""",
    "blog/index.html": """
<h2>Hangi yazıdan başlamalı?</h2>
<p>Çay demlemeye yeni başlıyorsanız önce temel demleme adımlarını anlatan yazımızı okuyun. Ardından bitki
çayları rehberiyle kafeinsiz seçenekleri tanıyabilir, kış aylarında baharatlı harman tarifini deneyebilirsiniz.
Her yazının sonunda ilgili ürünleri ve sık yapılan hataları da paylaşıyoruz. Yazıları okurken aklınıza takılan
noktaları bize yazarsanız, sonraki yazılarda bu sorulara da yer veririz. Okurlarımızın en çok merak ettiği
konular demleme süresi, su sıcaklığı ve çayın saklanması oluyor.</p>
""",
    "hakkimizda.html": """
<h2>Bahçeden bardağa</h2>
<p>Bir paket çayın yolculuğu, ilkbaharda yaprakların toplanmasıyla başlar. Toplanan yapraklar aynı gün
atölyeye taşınır, soldurulur, kıvrılır ve kurutulur. Kuruyan çay depomuza geldiğinde elenir, kırık parçalar
ayrılır ve tadım yapılır. Tadımdan geçen çay haftalık siparişlere göre paketlenir ve kargoya verilir. Bu
sürecin her adımında aynı küçük ekip çalışır; böylece bir sorun olduğunda nerede olduğunu hemen bulabilir ve
düzeltebiliriz. Müşterilerimizden gelen her yorum, ekipte herkesle paylaşılır.</p>
""",
    "iletisim.html": """
<h2>Ziyaret ve teslim alma</h2>
<p>Depomuz Of ilçe merkezine yürüme mesafesindedir. Çevredeki çay bahçelerini gezmeye gelen misafirlerimiz
siparişlerini kargo beklemeden depomuzdan teslim alabilir. Teslim almak istediğiniz siparişi verirken sipariş
notuna "depodan teslim" yazmanız yeterlidir; siparişiniz hazır olduğunda size kısa mesajla haber veririz.
Depoya gelirken sipariş numaranızı yanınızda bulundurmanızı rica ederiz. Hafta sonları depoda tadım
etkinlikleri düzenlediğimiz günlerde yoğunluk olabileceği için ziyaret saatinizi önceden bildirmenizi
öneririz.</p>
""",
    "urunler/beyaz-cay.html": """
<h2>Beyaz çayın hasadı</h2>
<p>Beyaz çay tomurcukları yılda yalnızca birkaç gün, ilkbaharın en serin sabahlarında toplanır. Toplayıcılar her
bitkiden yalnızca henüz açılmamış tomurcukları seçer; bir paket beyaz çay için binlerce tomurcuk tek tek elle
koparılır. Toplanan tomurcuklar gölgede, ince bir tabaka halinde yayılarak yavaşça soldurulur ve ardından düşük
ısıda kurutulur. Bu süreçte tomurcuklar hiç kıvrılmadığı için doğal şekillerini ve gümüşi tüylerini korur.
Hasat dönemi kısa ve emek yoğun olduğu için beyaz çay her sezon sınırlı miktarda hazırlanır.</p>
""",
    "urunler/rize-filiz-cayi.html": """
<h2>Filiz çayını farklı kılan nedir?</h2>
<p>Filiz çayı yalnızca sezonun ilk hasadında, birkaç hafta boyunca toplanabilir. Bu dönemde çay bitkisi
kışın biriktirdiği besinleri taze sürgünlerine aktarır; bu yüzden ilk yapraklar daha yumuşak ve aromalıdır.
Sonraki hasatlarda yapraklar kalınlaşır ve tat sertleşir. Filiz çayının sınırlı miktarda üretilmesinin nedeni
budur. Paketlerimizin üzerinde hasat yılını ve toplandığı ayı belirtiyoruz; böylece elinizdeki çayın hangi
sezondan geldiğini her zaman bilebilirsiniz. Açılmamış paketler serin bir dolapta bir yıl boyunca tazeliğini
korur.</p>
""",
    "urunler/Kis-Cayi.html": """
<h2>Baharatları nereden alıyoruz?</h2>
<p>Harmanda kullandığımız tarçın kabuğunu ve karanfili, baharatları bütün olarak satan bir aile işletmesinden
temin ediyoruz. Öğütülmüş baharat yerine kırılmış parçalar kullanmamızın nedeni, kokunun paketin içinde daha
uzun süre korunmasıdır. Portakal kabuklarını ise kış aylarında Akdeniz'den gelen taze portakallardan kendimiz
hazırlıyor, düşük ısıda kurutuyoruz. Harmanın her partisinden küçük bir numuneyi saklıyor ve sonraki partileri
bu numuneyle karşılaştırıyoruz. Böylece harmanın tadı sezon boyunca değişmeden kalır.</p>
""",
    "urunler/demlik-seti.html": """
<h2>Setin parçaları</h2>
<p>Çaydanlık iki litre su alır ve kalın tabanı sayesinde gazlı, elektrikli ve indüksiyonlu ocaklarda
kullanılabilir. Kulpu ısınmayan bakalit kaplamalıdır. Porselen demlik bir litre kapasitelidir ve çaydanlığın
üzerine tam oturacak şekilde tasarlanmıştır. Bardaklar yüz mililitre hacimlidir; ince belli formu çayın
sıcaklığını korurken rengini de en iyi şekilde gösterir. Set, altı kişilik bir çay sofrası için gereken her
şeyi içerir. Yedek bardak ve demlik ihtiyacınız olursa parçaları ayrı ayrı da sipariş edebilirsiniz. Tüm
parçalar gıdayla temasa uygun malzemelerden üretilmiştir ve kutusunda kullanım kılavuzuyla birlikte gelir.</p>
""",
    "urunler/ada-cayi.html": """
<h2>Ada çayı nasıl toplanır?</h2>
<p>Toplayıcılarımız ada çayını sabah erken saatlerde, çiy kurumadan önce toplar. Bitkinin yalnızca üst
kısımlarındaki genç yapraklar kesilir; kök ve alt dallar yerinde bırakılır ki bitki bir sonraki yıl yeniden
sürgün verebilsin. Aynı yamaçtan iki yıl üst üste toplama yapılmaz. Bu kurallar hem doğanın korunmasına hem de
yaprakların kalitesinin her yıl aynı kalmasına yardımcı olur. Kurutma sırasında yapraklar her gün elle
çevrilir ve nem kontrol edilir. Paketlenen ada çayının kokusu, iyi koşullarda saklandığında bir yıl boyunca
belirgin şekilde korunur.</p>
""",
    "urunler/sayfa/2.html": """
<h2>Hediye paketi hazırlarken</h2>
<p>Hediye paketi seçerken hediye edeceğiniz kişinin çay alışkanlığını düşünmek iyi bir başlangıçtır. Koyu ve
demli çay sevenler için siyah çay ağırlıklı kutuları, akşamları kafeinsiz bir şey içmeyi tercih edenler için
bitki çaylarını içeren kutuları öneririz. Kutuların içindeki çaylar, birbirinden farklı tatları tanıtacak
şekilde seçilir. Siparişinize ekleyeceğiniz notu el yazısıyla karta geçiriyor ve kutuyu kurdeleyle
kapatıyoruz. Fatura ve fiyat bilgisi hediye kutusunun içine konulmaz; bu bilgiler yalnızca size e-posta ile
gönderilir. Kutular ayrıca kargo kolisine yerleştirilerek gönderilir.</p>
""",
    "kargo-ve-iade.html": """
<h2>Teslimat adresi değişikliği</h2>
<p>Siparişiniz kargoya verilmeden önce teslimat adresinizi değiştirmek isterseniz bize e-posta ile ya da
telefonla ulaşmanız yeterlidir. Kargoya verilmiş siparişlerde adres değişikliği kargo firmasının şube
işlemleriyle yapılabilir; bu durumda size takip numarasıyla birlikte yol gösteririz.</p>
""",
    "gizlilik.html": """
<h2>Bülten ve bildirimler</h2>
<p>Bültenimize yalnızca açık onay verdiğinizde abone olursunuz. Bültende yeni sezon ürünlerini, blog
yazılarını ve kampanyaları paylaşıyoruz; ayda ikiden fazla e-posta göndermiyoruz. Her e-postanın altındaki
bağlantıyla aboneliğinizi tek adımda sonlandırabilirsiniz. Sipariş durumunuzla ilgili bilgilendirme
e-postaları bülten kapsamında değildir ve siparişinizin teslim edilmesi için gönderilir. Telefon numaranızı
yalnızca kargo bildirimleri için kullanırız; pazarlama amaçlı kısa mesaj göndermeyiz. Bu politikada yapılan
değişiklikleri bu sayfada yayımlar, önemli değişiklikleri ayrıca e-posta ile duyururuz.</p>
""",
    "blog/bitki-caylari.html": """
<h2>Bitki çaylarını ne zaman içmeli?</h2>
<p>Kafein içermedikleri için bitki çayları akşam saatlerinde siyah çayın yerini rahatlıkla alabilir. Ada çayı
ferah kokusuyla öğleden sonralara, ıhlamur ise yumuşak içimiyle kış akşamlarına çok yakışır. Gün içinde farklı
bitkileri denemek, damak zevkinize en uygun olanı bulmanın en kolay yoludur.</p>
""",
    "blog/kis-caylari.html": """
<h2>Harmanla birlikte ne ikram edilir?</h2>
<p>Baharatlı kış çayı, tarçınlı kurabiyeler, cevizli kek ya da kuru meyvelerle çok iyi uyum sağlar. Tatlı
ikramlar baharatın sıcaklığını öne çıkarırken peynirli poğaça gibi tuzlu atıştırmalıklar harmanın burukluğunu
dengeler. Kalabalık bir misafir sofrası hazırlıyorsanız harmanı büyük bir demlikte demleyip ayrı bir çaydanlıkta
sıcak su bulundurmanızı öneririz; böylece herkes çayını istediği koyulukta içebilir. Harmanı demlemeden önce
yaprakları avucunuzda hafifçe ovuşturmak, baharatların kokusunu daha da belirgin hale getirir.</p>
""",
    "urunler/arsiv/index.html": """
<h2>Arşiv ürünleri nasıl saklanıyor?</h2>
<p>Arşive ayırdığımız paketler vakumlu ambalajda, sabit sıcaklıktaki karanlık bir depo bölümünde bekletilir.
Her sezonun sonunda bu paketlerden birini açıp tadım yapıyor, çayın tazeliğini koruyup korumadığını kontrol
ediyoruz. Tadımda beklediğimiz kaliteyi göstermeyen paketler satıştan kaldırılır. Arşiv ürünlerinin
etiketlerinde hasat yılının yanında son tadım tarihini de görebilirsiniz. Bu bilgi, satın aldığınız çayın en
son ne zaman kontrol edildiğini gösterir ve arşiv ürünlerine duyduğunuz güvenin dayanağıdır.</p>
""",
    "urunler/arsiv/2019/index.html": """
<h2>2019 hasadının notları</h2>
<p>O yılın tadım defterimizde sonbahar hasadı için koyu kızıl renk, kuru meyve kokusu ve uzun süren bir
burukluk not edilmiş. Yaz başındaki hasatta ise yapraklar daha küçük ve daha az sayıdaydı; bu nedenle ilkbahar
ürünlerinin bir kısmını o yıl hiç hazırlayamadık. Kurak geçen yıllarda üreticilerimizle birlikte sulama ve
gölgeleme önlemlerini konuştuk; bu deneyim sonraki yıllarda bahçelerin daha dayanıklı olmasını sağladı.
Arşivdeki 2019 paketleri, o dönemin çay karakterini bugün de tadabilmeniz için saklanıyor.</p>
""",
    "urunler/arsiv/2019/ozel-harman.html": """
<h2>Özel Harman'ın bahçeleri</h2>
<p>Harmanın ince yaprakları deniz seviyesinden yaklaşık bin metre yükseklikteki bir bahçeden, kalın yaprakları
ise vadi tabanına yakın bir bahçeden gelir. İki bahçe de yıllardır birlikte çalıştığımız ailelere aittir.
Hasat zamanı her iki bahçede de aynı hafta içinde toplama yapılır; böylece harmana giren yapraklar aynı
dönemin karakterini taşır. Harman oranları her parti için tadımla doğrulanır ve paket üzerindeki parti
numarasıyla kayıt altına alınır.</p>
""",
    "blog/yesil-cay-faydalari.html": """
<h2>Yeşil çay seçerken</h2>
<p>İyi bir yeşil çayın yaprakları canlı yeşil renkte ve bütün olmalıdır. Kahverengiye dönmüş ya da toz halindeki
yapraklar çayın uzun süre beklediğini gösterir. Paket üzerinde hasat ve paketleme tarihini görmek, tazeliği
anlamanın en güvenilir yoludur.</p>
""",
}


EK2 = {
    "urunler/beyaz-cay.html": """Beyaz çayı ilk kez deneyecekseniz küçük bir paketle başlamanızı öneririz. Narin tadı,
        siyah çaya alışkın damaklar için birkaç demlemede tanınır hale gelir; her demlemede tomurcukların suyun içinde
        yavaşça açılmasını izlemek de bu çayın keyfinin bir parçasıdır. Tomurcukları ağzı sıkı kapanan cam bir kavanozda,
        ışıktan ve nemden uzak saklayın.""",
    "blog/index.html": """Blog yazılarımızın tamamını mağaza ekibimiz yazıyor. Her yazıda kendi deneyimlerimizi,
        bahçe ziyaretlerinde öğrendiklerimizi ve müşterilerimizin paylaştığı küçük ipuçlarını bir araya getiriyoruz.
        Yazılardaki fotoğrafları da depomuzda ve mutfağımızda kendimiz çekiyoruz.""",
    "hakkimizda.html": """Gelecek yıllarda çalıştığımız üretici sayısını artırmayı değil, mevcut bahçelerle ilişkimizi
        derinleştirmeyi hedefliyoruz. Her yıl bir bahçede organik tarıma geçiş için üreticimizle birlikte çalışıyor,
        bu süreçte ortaya çıkan maliyetleri paylaşıyoruz.""",
    "iletisim.html": """Sosyal medya hesaplarımızdan gelen mesajları da aynı ekip yanıtlıyor; ancak sipariş
        bilgileriniz gibi kişisel ayrıntıları paylaşmanız gerekiyorsa e-posta kanalını kullanmanızı öneririz.
        Böylece bilgileriniz yalnızca ilgili ekip arkadaşımızla paylaşılır. Bayram ve resmi tatil günlerinde mesajlara
        verdiğimiz yanıtlar gecikebilir; bu dönemlerde verilen siparişler tatilin ardından gelen ilk iş günü sırasıyla
        hazırlanır ve kargoya teslim edilir. Tatil öncesindeki son kargo günlerini ana sayfamızda ayrıca duyuruyoruz.""",
    "urunler/rize-filiz-cayi.html": """Filiz çayını sade içmeyi sevenler için ilk demlemeyi kısa tutmak, çiçeksi
        kokunun bardakta daha belirgin kalmasını sağlar. Demin bir saatten fazla beklememesine özen gösterin ve her
        yeni misafir için demliği tazeleyin.""",
    "urunler/Kis-Cayi.html": """Kış Çayı Harmanı kafein içerir; akşam saatlerinde içecekseniz harmanı ıhlamur ile
        karıştırarak kafein miktarını azaltabilirsiniz. Bu karışım baharat kokusunu korurken daha yumuşak bir içim
        sunar ve özellikle uzun kış gecelerinde tercih edilir.""",
    "urunler/demlik-seti.html": """Demlik setimizi kullanan müşterilerimizin en sık sorduğu soru, çaydanlıktaki suyun
        ne zaman kısık ateşe alınması gerektiğidir. Su kaynadıktan sonra demliği yerleştirip ocağı en kısık
        seviyeye getirmeniz yeterlidir; böylece demleme boyunca su kaynamaya devam etmez.""",
    "kargo-ve-iade.html": """Yurt dışına gönderim şu an için yapılmamaktadır. Yurt içindeki tüm adreslere, kargo
        firmasının hizmet verdiği köy ve mahalleler de dahil olmak üzere gönderim yapıyoruz. Teslimat sırasında
        evde olamayacaksanız kargo firmasının şubesinden teslim alma seçeneğini kullanabilirsiniz.""",
    "gizlilik.html": """Sitemiz, bağlantılarınızın güvenliği için şifreli iletişim kullanmayı hedefler ve kişisel
        bilgilerinize yalnızca bu bilgilere işi gereği ihtiyaç duyan ekip arkadaşlarımız erişebilir. Erişim
        kayıtları düzenli olarak gözden geçirilir.""",
    "urunler/sayfa/2.html": """Sınırlı üretim harmanlarımız tükendiğinde aynı tarifle yeniden üretilmez. Bir
        sonraki sezon, o yılın hasadına göre yeni bir harman hazırlanır ve katalogda yeni adıyla yer alır. Tükenen
        ürünler için stok bildirimi isteyebilirsiniz.""",
    "blog/bitki-caylari.html": """Bitki çaylarını demlerken kullandığınız suyun sertliği de tadı etkiler. Kireçli
        sularda demlenen ıhlamur ve ada çayı daha mat bir renk ve hafif metalik bir tat verebilir; filtrelenmiş su
        kullanmak bu sorunu büyük ölçüde giderir.""",
    "blog/kis-caylari.html": """Hazırladığınız harmanı ağzı kapalı cam kavanozlarda, ışık almayan bir dolapta
        saklayın. Baharatlar zamanla kokusunu kaybettiği için harmanı iki ay içinde tüketmek, ilk günkü tadı korumanın
        en kolay yoludur.""",
    "urunler/arsiv/index.html": """Arşiv koleksiyonlarından sipariş verirken ürün sayfasındaki stok bilgisini kontrol
        edin. Stoğu azalan ürünlerin sayfasında kalan paket sayısını gösteriyoruz; son paketler genellikle sezon
        başlarında hızla tükeniyor.""",
    "urunler/arsiv/2019/index.html": """Bu koleksiyondan aldığınız paketi açtıktan sonra iki ay içinde tüketmenizi
        öneririz. Uzun süre saklanmış yapraklar açıldıktan sonra havayla temas ettikçe kokusunu daha hızlı kaybeder;
        bu yüzden küçük bir kavanoza aktarıp kullanmak en iyisidir.""",
    "blog/yesil-cay-faydalari.html": """Yeşil çayı demlerken cam ya da porselen demlik kullanmak, yaprakların
        açılışını izlemenizi sağlar. Metal demlikler ısıyı uzun süre tuttuğu için yeşil çayın yanmasına ve
        acılaşmasına neden olabilir.""",
}


def sayfa(yol, *, baslik, aciklama, h1, govde, lang="tr", charset=True, viewport=True, canonical="kendi",
          head_ek="", jsonld="webpage", menu=True, govde_yalin=None):
    url = TABAN + "/" + yol.replace("index.html", "")
    parcalar = ["<!DOCTYPE html>", f'<html lang="{lang}">' if lang else "<html>", "<head>"]
    if charset:
        parcalar.append('<meta charset="utf-8">')
    if viewport:
        parcalar.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    if baslik is not None:
        parcalar.append(f"<title>{baslik}</title>")
    if aciklama is not None:
        parcalar.append(f'<meta name="description" content="{aciklama}">')
    if canonical == "kendi":
        parcalar.append(f'<link rel="canonical" href="{url}">')
    elif canonical:
        parcalar.append(f'<link rel="canonical" href="{canonical}">')
    paylasim_basligi = baslik or SITE
    parcalar += ['<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
                 f'<meta property="og:title" content="{paylasim_basligi}">',
                 f'<meta property="og:description" content="{aciklama or SITE}">',
                 f'<meta property="og:image" content="{TABAN}/img/paylasim.png">',
                 f'<meta property="og:url" content="{url}">',
                 '<meta property="og:type" content="website">',
                 '<meta name="twitter:card" content="summary">',
                 '<link rel="stylesheet" href="/css/site.css">']
    if head_ek:
        parcalar.append(head_ek)
    if jsonld == "webpage":
        jsonld = {"@context": "https://schema.org", "@type": "WebPage", "name": paylasim_basligi, "url": url}
    if isinstance(jsonld, dict):
        jsonld = json.dumps(jsonld, ensure_ascii=False, indent=2)
    if jsonld:
        parcalar.append(f'<script type="application/ld+json">\n{jsonld}\n</script>')
    parcalar += ["</head>", "<body>"]
    if govde_yalin is not None:
        parcalar.append(govde_yalin)
    else:
        if menu:
            parcalar.append(MENU)
        parcalar.append("<main>")
        if h1:
            parcalar.append(h1)
        parcalar.append(govde.strip())
        if yol in EK:
            parcalar.append(EK[yol].strip())
        if yol in EK2:
            parcalar.append("<p>" + " ".join(EK2[yol].split()) + "</p>")
        parcalar.append("</main>")
        parcalar.append(ALT)
    parcalar += ["</body>", "</html>", ""]
    hedef = HEDEF / yol
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text("\n".join(parcalar), encoding="utf-8")


def urun_ld(ad, aciklama, fiyat=None, gorsel=None):
    veri = {"@context": "https://schema.org", "@type": "Product", "name": ad, "description": aciklama,
            "brand": {"@type": "Brand", "name": SITE}}
    if gorsel:
        veri["image"] = TABAN + gorsel
    if fiyat:
        veri["offers"] = {"@type": "Offer", "price": fiyat, "priceCurrency": "TRY",
                          "availability": "https://schema.org/InStock"}
    return veri


def makale_ld(baslik, tarih):
    return {"@context": "https://schema.org", "@type": "BlogPosting", "headline": baslik,
            "datePublished": tarih, "author": {"@type": "Organization", "name": SITE}}


def img(src, alt, g=400, y=300, lazy=False, boyut=True):
    parca = f'<img src="{src}"'
    if alt is not None:
        parca += f' alt="{alt}"'
    if boyut:
        parca += f' width="{g}" height="{y}"'
    if lazy:
        parca += ' loading="lazy"'
    return parca + ">"


# ------------------------------------------------------------------ sayfalar
def sayfalari_uret():
    sayfa(
        "index.html",
        baslik="Çaylıbahçe | Doğal Çaylar ve Bitki Çayları Mağazası",
        aciklama="Karadeniz'in yamaçlarından gelen doğal siyah çaylar, bitki çayları ve demlik setleri. "
                 "Çaylıbahçe'de taze çay, özenli paketleme ve hızlı kargo.",
        h1="<h1>Çaylıbahçe'ye Hoş Geldiniz</h1>",
        head_ek='<link rel="alternate" hreflang="en" href="' + TABAN + '/en/">\n'
                '<link rel="stylesheet" href="/css/yazi-tipi.css">\n'
                '<script src="/js/analitik.js"></script>\n<script src="/js/kaydirici.js"></script>',
        jsonld={"@context": "https://schema.org", "@type": "WebSite", "name": SITE, "url": TABAN + "/"},
        govde=f"""
{img("/img/ana-gorsel.svg", "Çay bahçesinde taze toplanmış çay yaprakları", 800, 400)}
<p>Çaylıbahçe, Karadeniz'in sisli yamaçlarında yetişen çayları ve özenle seçilmiş bitki çaylarını sofranıza
getiren küçük bir çay mağazasıdır. Her sezon üreticilerimizle birlikte hasat zamanını takip ediyor, yaprakları
kuruttuktan sonra küçük partiler halinde paketliyoruz. Böylece demliğe giren her çay, raflarda aylarca beklemiş
bir üründen çok daha canlı bir koku ve renk verir.</p>
<p>Mağazamızda ilkbahar hasadından gelen filiz çaylarından kış akşamları için hazırladığımız baharatlı
harmanlara kadar geniş bir seçki bulabilirsiniz. Müşterilerimizin en çok tercih ettiği ürün, yıllardır aynı
tarifle hazırladığımız Özel Harman siyah çayımızdır; koyu rengi ve yumuşak içimiyle kahvaltı sofralarının
vazgeçilmezi olmuştur.</p>
<h1>Doğal Çaylar ve Bitki Çayları</h1>
<p>Siyah çayın yanında ada çayı, ıhlamur ve beyaz çay gibi farklı demleme alışkanlıklarına uygun ürünler de
sunuyoruz. Her ürün sayfasında demleme sıcaklığı, bekleme süresi ve saklama önerilerini ayrıntılı olarak
paylaşıyoruz. Yeni başlayanlar için <a href="/blog/">çay blogumuzdaki</a> rehber yazılar, doğru demleme
için iyi bir başlangıç noktasıdır.</p>
<h2>Öne çıkan ürünler</h2>
<ul>
<li><a href="/urunler/rize-filiz-cayi.html">Rize Filiz Çayı</a>: ilkbahar hasadının ilk yapraklarından hazırlanır.</li>
<li><a href="/urunler/Kis-Cayi.html">Kış Çayı Harmanı</a>: tarçın, karanfil ve portakal kabuğuyla zenginleştirilir.</li>
<li><a href="/urunler/demlik-seti.html">Demlik Seti</a>: çaydanlık, demlik ve altı ince belli bardaktan oluşur.</li>
</ul>
<p><a href="/urunler/">Tüm çay ürünlerimizi</a> kategori sayfasında karşılaştırabilir, geçen sezonlardan
kalan sınırlı stoklara da <a href="/eski-urunler">geçmiş sezon ürünleri</a> bölümünden ulaşabilirsiniz.</p>
<h2>Bu ay mağazada</h2>
{img("/img/kampanya-afisi.svg", None, 800, 200)}
<p>Kış ayları boyunca baharatlı harmanlarımızda paketleme ücreti almıyoruz. Siparişleriniz hafta içi saat
on beşe kadar verildiğinde aynı gün kargoya teslim edilir. Paketlerimizde plastik yerine geri dönüştürülebilir
kâğıt ve karton kullanıyor, her siparişe demleme önerilerini anlatan küçük bir kart ekliyoruz. Sorularınız
için iletişim sayfamızdaki telefon ve e-posta adreslerinden bize her zaman ulaşabilirsiniz.</p>
<p>Çaylıbahçe ailesi olarak amacımız, iyi bir bardak çayın sade keyfini olabildiğince çok eve ulaştırmak.
Çay seçerken kararsız kalırsanız ürün açıklamalarındaki tat notlarına göz atabilir, damak zevkinize en yakın
harmanı kolayca bulabilirsiniz.</p>
""")

    kartlar = [
        ("rize-filiz-cayi.html", "Rize Filiz Çayı", "filiz-cayi.svg",
         "İlkbahar hasadının ilk iki yaprağı ve tomurcuğundan hazırlanan filiz çayı, açık amber rengi ve hafif "
         "çiçeksi kokusuyla güne yumuşak bir başlangıç yapmak isteyenler için hazırlandı. Beş yüz gramlık "
         "paketlerde sunulur."),
        ("ada-cayi.html", "Ada Çayı", "ada-cayi.svg",
         "Ege dağlarından toplanan ada çayı yaprakları gölgede kurutulur. Ferah kokusu ve hafif buruk tadıyla "
         "öğleden sonraları sade ya da bir dilim limonla içilebilir."),
        ("ihlamur.html", "Ihlamur", "ihlamur.svg",
         "Çiçekli ıhlamur dalları elle ayıklanarak paketlenir. Kış akşamlarında bal ile tatlandırılarak içilen "
         "ıhlamur, sıcak ve yumuşak bir içim sunar."),
        ("beyaz-cay.html", "Beyaz Çay", "beyaz-cay.svg",
         "Tomurcukları açılmadan toplanan beyaz çay en az işlem gören çay türüdür. Düşük sıcaklıkta demlenir ve "
         "kavun ile bal notaları taşıyan narin bir tat bırakır."),
        ("Kis-Cayi.html", "Kış Çayı Harmanı", "kis-cayi.svg",
         "Siyah çay tabanına tarçın, karanfil ve kurutulmuş portakal kabuğu eklenerek hazırlanan harman, soğuk "
         "günlerde evinizi baharat kokusuyla doldurur."),
        ("demlik-seti.html", "Demlik Seti", "demlik.svg",
         "Paslanmaz çelik çaydanlık, porselen demlik ve altı adet ince belli bardaktan oluşan set, çayı geleneksel "
         "yöntemle demlemek isteyenler için hazırlandı."),
    ]
    liste = []
    for sira, (dosya, ad, gorsel, metin) in enumerate(kartlar):
        liste.append(f'<article class="kart"><a href="/urunler/{dosya}">'
                     f'{img("/img/urunler/" + gorsel, ad, lazy=sira >= 2, boyut=False)}</a>'
                     f'<h2><a href="/urunler/{dosya}">{ad}</a></h2><p>{metin}</p></article>')
    sayfa(
        "urunler/index.html", canonical=None,
        baslik="Çay Ürünleri ve Harmanlar | Çaylıbahçe",
        aciklama="Siyah çaylar, bitki çayları, beyaz çay ve demlik setleri. Çaylıbahçe ürünlerini fiyat, "
                 "tat notu ve demleme önerileriyle karşılaştırın.",
        h1='<p class="sayfa-basligi">Çay Ürünleri ve Harmanlar</p>',
        govde=f"""
<p>Bu sayfada mağazamızdaki çay ürünlerinin tamamını bulabilirsiniz. Ürünleri yeni eklenenlere veya fiyata göre
sıralayabilir, her ürünün kendi sayfasında demleme önerilerine ulaşabilirsiniz. Harmanlarımızın tamamı küçük
partiler halinde hazırlanır, bu nedenle bazı ürünlerin stoğu sezon içinde tükenebilir.</p>
<p class="siralama">Sırala: <a href="/urunler/?siralama=fiyat&amp;ref=menu">Fiyata göre</a> ·
<a href="/urunler/?siralama=yeni&amp;ref=menu">Yeni eklenenler</a></p>
<div class="izgara">
{chr(10).join(liste)}
</div>
<p>Bitki çaylarımız kafein içermez, akşam saatlerinde rahatlıkla tercih edilebilir. Siyah ve beyaz çaylarımız
ise farklı sıcaklık ve sürelerle demlendiğinde birbirinden çok farklı tatlar verir. Hangi ürünün size uygun
olduğundan emin değilseniz blogumuzdaki demleme rehberine göz atabilirsiniz.</p>
<nav class="sayfalama" aria-label="Sayfalar"><span>1</span> <a href="/urunler/sayfa/2.html">Sonraki sayfa: 2</a></nav>
""")

    sayfa(
        "urunler/sayfa/2.html", canonical=TABAN + "/urunler/",
        baslik="Çay Ürünleri ve Harmanlar – Sayfa 2 | Çaylıbahçe",
        aciklama="Çaylıbahçe ürün kataloğunun ikinci sayfası: hediye paketleri, sınırlı üretim harmanlar ve "
                 "geçmiş sezon koleksiyonları.",
        h1="<h1>Çay Ürünleri ve Harmanlar – Sayfa 2</h1>",
        govde=f"""
<p>Kataloğumuzun ikinci sayfasında hediye paketlerimizi ve sınırlı sayıda üretilen harmanlarımızı listeliyoruz.
Bu ürünler çoğunlukla özel günler için hazırlanır ve her sezon yeniden düzenlenir. Stokları az olduğu için
sipariş vermeden önce ürün sayfasındaki stok bilgisini kontrol etmenizi öneririz.</p>
<article class="kart"><h2><a href="/urunler/hediye-paketleri.html">Hediye Paketleri</a></h2>
<p>Ahşap kutularda sunulan hediye paketlerimiz iki ya da dört farklı çaydan oluşur. Kutunun içine isteğinize
göre kısa bir not ekleyebilir, paketi doğrudan sevdiklerinizin adresine gönderebilirsiniz. Kurumsal siparişler
için toplu paketleme seçeneğimiz de bulunur.</p></article>
<article class="kart"><h2>Sınırlı üretim harmanlar</h2>
<p>Her yıl sonbaharda yalnızca birkaç yüz paket olarak hazırladığımız harmanlar, o yılın hasadından seçilen
yapraklarla hazırlanır. Tat profili her yıl biraz değişir; bu yüzden harman notlarını paket üzerinde ayrıca
belirtiriz. Geçmiş yılların harmanlarına arşiv bölümünden ulaşabilirsiniz.</p></article>
<h2>Geçmiş sezonlar</h2>
<p>Önceki sezonlarda hazırladığımız ve hâlâ az miktarda stoğu bulunan ürünleri
<a href="/urunler/arsiv/">arşiv koleksiyonlarımızda</a> topladık. Arşivdeki ürünler, aynı bahçelerden gelen
yaprakların farklı yıllarda nasıl değiştiğini merak eden çay meraklıları için güzel bir karşılaştırma imkânı
sunar. Arşiv sayfalarında her koleksiyonun hasat yılı, harman oranları ve demleme önerileri ayrı ayrı yer alır.</p>
<p>Katalogdaki tüm ürünler için kargo süresi ve iade koşulları aynıdır. Ayrıntıları kargo ve iade sayfamızda
bulabilir, siparişinizle ilgili sorularınızı iletişim sayfasındaki adreslerden bize iletebilirsiniz. Önceki
sayfaya dönerek tüm ürünleri yeniden görüntüleyebilirsiniz.</p>
<nav class="sayfalama" aria-label="Sayfalar"><a href="/urunler/">Önceki sayfa: 1</a> <span>2</span></nav>
""")

    ortak_demleme = """
<h2>Saklama önerisi</h2>
<p>Çayı ışık almayan, nemsiz ve kokusuz bir dolapta, ağzı sıkıca kapanan bir kapta saklayın. Baharat ve kahve
gibi kokulu ürünlerin yanında bekleyen çay kısa sürede kendi kokusunu kaybeder. Açılan paketi iki ay içinde
tüketmenizi öneririz.</p>
"""
    sayfa(
        "urunler/rize-filiz-cayi.html",
        baslik="Rize Filiz Çayı 500 g | Çaylıbahçe",
        aciklama="Çaylıbahçe'de doğal çaylar, bitki çayları ve demlik setleri uygun fiyatlarla. Siparişleriniz "
                 "aynı gün kargoda.",
        h1="<h1>Rize Filiz Çayı</h1>",
        jsonld='{\n  "@context": "https://schema.org",\n  "@type": "Product",\n  "name": "Rize Filiz Çayı",\n'
               '  "offers": {"@type": "Offer", "price": "185", "priceCurrency": "TRY",},\n}',
        govde=f"""
{img("/img/urunler/filiz-cayi.svg", "Rize Filiz Çayı paketi ve demlenmiş bir bardak çay")}
<p class="fiyat">Fiyat: 185 TL · 500 g</p>
<p>Rize Filiz Çayı, mayıs ayında yapılan ilk hasatta toplanan iki yaprak ve bir tomurcuktan hazırlanır.
Yapraklar toplandıktan sonra aynı gün soldurulur, kıvrılır ve fermente edilir. Kısa fermantasyon süresi
sayesinde çay, açık amber bir renk ve hafif çiçeksi bir koku verir. Sert ve buruk çaylar yerine yumuşak bir
içim arayanlar için hazırladığımız bu çay, sabah kahvaltısında ve gün içinde rahatlıkla içilebilir.</p>
<p>Filiz çayının yaprakları diğer siyah çaylara göre daha ince olduğu için demleme süresine dikkat etmek
gerekir. Uzun beklettiğinizde tadı acılaşabilir; kısa demlediğinizde ise rengi açık kalır. Aşağıdaki öneriler,
çoğu damak zevkine uygun bir başlangıç noktası sunar.</p>
<h2>Demleme önerisi</h2>
<p>Demliğe kişi başına bir tatlı kaşığı çay koyun. Kaynamış suyu bir dakika bekletip demliğe ekleyin ve
çaydanlığın üzerinde on iki ile on beş dakika demlenmeye bırakın. Bardağa önce demi, ardından sıcak suyu
ekleyerek dilediğiniz koyulukta servis edebilirsiniz. Filiz çayı şekersiz içildiğinde aromasını en iyi
şekilde gösterir.</p>
<p>Daha baharatlı bir tat arayanlar, filiz çayını <a href="/urunler/Kis-Cayi.html">Kış Çayı Harmanı</a> ile
yarı yarıya karıştırarak deneyebilir. Bu karışım özellikle soğuk havalarda sevilen bir lezzet ortaya çıkarır.
Demleme adımlarının ayrıntılı anlatımını <a href="/blog/Cay-Nasil-Demlenir.html">çay demleme yazımızda</a>
bulabilirsiniz.</p>
{ortak_demleme}
""")

    sayfa(
        "urunler/ada-cayi.html", canonical=TABAN + "/urunler/ihlamur.html",
        baslik="Doğal Bitki Çayları ve Harmanlar | Çaylıbahçe",
        aciklama="Ege dağlarından toplanan ada çayı yaprakları gölgede kurutulup elle ayıklanır. Ferah koku ve "
                 "hafif buruk tat için Çaylıbahçe ada çayı.",
        h1="<h1>Ada Çayı – Doğal Bitki Çayı</h1>",
        jsonld=urun_ld("Ada Çayı", "Gölgede kurutulmuş Ege ada çayı yaprakları.", "95", "/img/urunler/ada-cayi.svg"),
        govde=f"""
{img("/img/urunler/ada-cayi.svg", "Kurutulmuş ada çayı yaprakları")}
<p class="fiyat">Fiyat: 95 TL · 100 g</p>
<p>Ada çayı, Ege ve Akdeniz kıyılarındaki kayalık yamaçlarda kendiliğinden yetişen bir bitkidir. Yapraklarını
yaz başında, çiçeklenme dönemi bitmeden topluyoruz. Toplanan dallar gölgede ve havadar bir ortamda yavaşça
kurutulur; doğrudan güneşte kurutulan yapraklar hem rengini hem de kokusunu kaybettiği için bu adımı
aceleye getirmiyoruz. Kuruyan dallar elle ayıklanır, kalın saplar ayrılır ve yalnızca yapraklar paketlenir.</p>
<p>Bitki çayımızın kokusu ferah, tadı ise hafif buruktur. Öğleden sonraları sade olarak ya da bir dilim limonla
içilebilir. Kafein içermediği için akşam saatlerinde de tercih edilen ada çayı, bitki çaylarıyla tanışmak
isteyenler için iyi bir başlangıçtır. Daha yumuşak bir içim isteyenler bir tatlı kaşığı bal ekleyebilir.</p>
<h2>Demleme önerisi</h2>
<p>Bir bardak için bir tatlı kaşığı ada çayını demliğe koyun. Kaynayan suyu biraz soğuttuktan sonra yaprakların
üzerine dökün ve kapağını kapatarak beş dakika bekletin. Uzun süre bekleyen ada çayı acılaşır, bu nedenle süreyi
kısa tutmanızı öneririz. Demlenen çayı süzerek servis edin; aynı yapraklarla ikinci bir demleme yapmayın.</p>
<p>Ada çayını tek başına içebileceğiniz gibi ıhlamur ya da kuşburnu ile karıştırarak kendi bitki çayı
harmanınızı da hazırlayabilirsiniz. Karışımlarda ada çayının oranını üçte birin altında tutmak, kokusunun
diğer bitkileri bastırmasını önler.</p>
{ortak_demleme}
""")

    sayfa(
        "urunler/ihlamur.html", viewport=False,
        baslik="Doğal Bitki Çayları ve Harmanlar | Çaylıbahçe",
        aciklama="Elle ayıklanmış çiçekli ıhlamur dalları. Kış akşamları için bal ile tatlandırılan yumuşak "
                 "içimli doğal bitki çayı.",
        h1="<h1>Ihlamur – Doğal Bitki Çayı</h1>",
        jsonld=urun_ld("Ihlamur", "Elle ayıklanmış çiçekli ıhlamur.", "110", "/img/urunler/ihlamur.svg"),
        govde=f"""
{img("/img/urunler/ihlamur.svg", "Çiçekli ıhlamur dalları")}
<p class="fiyat">Fiyat: 110 TL · 80 g</p>
<p>Çiçekli ıhlamur dalları elle ayıklanarak paketlenir. Kaynamış suyla beş dakika demleyip bal ekleyerek
içebilirsiniz. Ihlamur kafein içermez.</p>
""")

    sayfa(
        "urunler/beyaz-cay.html",
        baslik="Beyaz Çay – Tomurcuk Hasadı | Çaylıbahçe",
        aciklama="Tomurcukları açılmadan toplanan, düşük sıcaklıkta demlenen beyaz çay. Kavun ve bal notaları "
                 "taşıyan narin içim.",
        h1="<h1>Beyaz Çay</h1>",
        jsonld=urun_ld("Beyaz Çay", "Açılmamış tomurcuklardan hazırlanan beyaz çay.", "240",
                       "/img/urunler/beyaz-cay.svg"),
        govde=f"""
{img("/img/urunler/beyaz-cay.svg", "Gümüşi tüylü beyaz çay tomurcukları")}
<p class="fiyat">Fiyat: 240 TL · 50 g</p>
<p>Beyaz çay, çay bitkisinin henüz açılmamış tomurcuklarından hazırlanır. Tomurcukların üzerindeki ince gümüşi
tüyler, çayın adını aldığı açık rengin kaynağıdır. Toplanan tomurcuklar kıvırma ve fermantasyon işlemlerinden
geçmeden yalnızca soldurulup kurutulur. Bu nedenle beyaz çay, tüm çay türleri arasında en az işlem gören ve
yaprağın doğal halini en çok koruyan çaydır.</p>
<p>Tadı oldukça narindir. İyi demlenmiş bir bardak beyaz çayda kavun, bal ve taze çiçek notaları hissedilir.
Siyah çaya alışkın olanlar ilk yudumda bu hafifliği şaşırtıcı bulabilir; birkaç denemeden sonra ise beyaz
çayın sade zarafeti kolayca sevilir. Yemeklerden sonra ya da kitap okurken yavaş yavaş içmek için idealdir.</p>
<h2>Demleme önerisi</h2>
<p>Beyaz çay yüksek sıcaklığa dayanmaz. Kaynayan suyu birkaç dakika bekleterek yaklaşık seksen dereceye
düşürün. Bir bardak için iki tatlı kaşığı tomurcuğu cam bir demliğe koyun ve suyu ekleyerek dört ile beş dakika
bekletin. Aynı tomurcuklarla iki ya da üç kez demleme yapabilirsiniz; her demlemede süreyi bir dakika
uzatmanız yeterlidir.</p>
<p>Beyaz çayı şeker ya da limon eklemeden içmenizi öneririz. Narin aroması, eklenen tatlandırıcılarla kolayca
kaybolur. Soğuk demleme için tomurcukları oda sıcaklığındaki suyla buzdolabında sekiz saat bekletebilirsiniz.</p>
{ortak_demleme}
""")

    sayfa(
        "urunler/Kis-Cayi.html",
        baslik="Kış Çayı Harmanı 250 g | Çaylıbahçe",
        aciklama="Siyah çay, tarçın, karanfil ve portakal kabuğuyla hazırlanan Kış Çayı Harmanı. Soğuk günler "
                 "için baharatlı ve sıcak bir içim.",
        h1="<h1>Kış Çayı Harmanı</h1>",
        jsonld=urun_ld("Kış Çayı Harmanı", "Tarçın, karanfil ve portakal kabuklu siyah çay harmanı.", "140",
                       "/img/urunler/kis-cayi.svg"),
        govde=f"""
{img("/img/urunler/kis-cayi.svg", "Tarçın çubukları ve portakal kabuğuyla kış çayı harmanı")}
<p class="fiyat">Fiyat: 140 TL · 250 g</p>
<p>Kış Çayı Harmanı, soğuk aylarda sofranızı ısıtmak için hazırladığımız baharatlı bir siyah çay karışımıdır.
Tabanında Karadeniz siyah çayı bulunur; üzerine tarçın kabuğu parçaları, bütün karanfil ve fırında kurutulmuş
portakal kabuğu eklenir. Baharatları her parti için yeniden tartıyor ve karışımı küçük miktarlarda
hazırlıyoruz; böylece paketi açtığınızda baharat kokusu taze kalır.</p>
<p>Harmanın tadı sıcak ve hafif tatlıdır. Tarçın ve portakal kabuğu çayın burukluğunu yumuşatır, karanfil ise
belirgin ama baskın olmayan bir derinlik katar. Kar yağışlı bir akşamda, sobanın yanında içilen bir bardak kış
çayı, misafirleriniz için de unutulmaz bir ikram olur. Harmanı süt ekleyerek de deneyebilirsiniz.</p>
<h2>Demleme önerisi</h2>
<p>Kişi başına bir tatlı kaşığı harmanı demliğe koyun ve üzerine kaynar su ekleyin. Baharatların aromasını
tam olarak bırakması için çayı çaydanlığın üzerinde on beş dakika demleyin. Servis ederken bardağa bir dilim
portakal ya da bir parça tarçın çubuğu eklemek, harmanın kokusunu daha da belirgin hale getirir. Şekersiz
içmeyi sevmeyenler için bal, beyaz şekerden daha uyumlu bir tatlandırıcıdır.</p>
<p>Harman, filiz çayı ya da sade siyah çayla karıştırılarak yoğunluğu azaltılabilir. Baharat oranını düşük
seven misafirleriniz için bu yöntemi öneririz.</p>
{ortak_demleme}
""")

    sayfa(
        "urunler/demlik-seti.html",
        baslik="Demlik Seti – Çaydanlık ve 6 Bardak | Çaylıbahçe",
        aciklama="Çaylıbahçe'de doğal çaylar, bitki çayları ve demlik setleri uygun fiyatlarla. Siparişleriniz "
                 "aynı gün kargoda.",
        h1="<h1>Demlik Seti</h1>",
        jsonld={"@context": "https://schema.org", "@type": "Product", "name": "Demlik Seti",
                "description": "Paslanmaz çelik çaydanlık, porselen demlik ve altı ince belli bardak."},
        govde=f"""
{img("/img/urunler/demlik-seti-buyuk.png", "Paslanmaz çelik çaydanlık, porselen demlik ve altı bardaktan oluşan demlik seti", 480, 360)}
<p class="fiyat">Fiyat: 1.250 TL · 1 set</p>
<p>Demlik Seti, çayı geleneksel yöntemle demlemek isteyenler için hazırladığımız eksiksiz bir settir. Setin
içinde iki litrelik paslanmaz çelik çaydanlık, bir litrelik porselen demlik ve altı adet ince belli cam bardak
bulunur. Çaydanlığın tabanı her tür ocakta kullanılabilecek şekilde kalın üretilmiştir; ısıyı eşit dağıttığı
için su hızlı kaynar ve demlik üzerinde çay uzun süre sıcak kalır.</p>
<p>Porselen demlik, çayın kokusunu ve rengini bozmadan demlenmesini sağlar. Demliğin ağzındaki ince süzgeç
yaprakların bardağa geçmesini önler. İnce belli bardaklar ise çayın rengini en güzel gösteren klasik formdadır;
tabanları kalın olduğu için masaya konulduklarında devrilmezler. Set, ilk evini kuranlar ya da çay sofrasını
yenilemek isteyenler için de anlamlı bir hediye seçeneğidir.</p>
<h2>Kullanım ve bakım</h2>
<p>İlk kullanımdan önce çaydanlığı bir kez su kaynatıp boşaltın. Porselen demliği bulaşık makinesinde
yıkayabilirsiniz; ancak demliğin içindeki çay lekelerini korumak isteyen çay meraklıları onu yalnızca sıcak
suyla durulamayı tercih eder. Çelik çaydanlıkta kireç oluşursa yarım limonla birlikte su kaynatmanız yeterlidir.
Cam bardakları ani sıcaklık değişimlerinden korumak için önce sıcak suyla ısıtmanızı öneririz.</p>
<p>Setimizi Rize Filiz Çayı ya da Özel Harman siyah çayımızla birlikte sipariş ederek ilk demlemenizi hemen
yapabilirsiniz. Tüm parçalar köpük korumalı kutuda, kırılmaya karşı ayrı ayrı sarılarak gönderilir.</p>
""")

    sayfa(
        "urunler/hediye-paketleri.html",
        baslik="Hediye Paketleri – Ahşap Kutuda Çaylar | Çaylıbahçe",
        aciklama="İki ya da dört farklı çaydan oluşan ahşap kutulu hediye paketleri. Not ekleme ve doğrudan "
                 "adrese gönderim seçeneğiyle.",
        h1=None, govde="",
        govde_yalin='<div id="app"></div>\n<noscript>Bu sayfayı görüntülemek için JavaScript gerekir.</noscript>\n'
                    '<script src="/js/hediye.js"></script>',
    )

    sayfa(
        "urunler/arsiv/index.html",
        baslik="Arşiv Koleksiyonları – Geçmiş Sezonlar | Çaylıbahçe",
        aciklama="Önceki sezonlarda hazırlanan ve az miktarda stoğu kalan çay koleksiyonları. Hasat yılı ve "
                 "harman notlarıyla arşiv ürünleri.",
        h1="<h1>Arşiv Koleksiyonları</h1>",
        govde="""
<p>Arşiv koleksiyonları, geçmiş sezonlarda hazırladığımız ve depomuzda hâlâ az miktarda bulunan çaylardan
oluşur. Çay da tıpkı diğer tarım ürünleri gibi her yıl farklı hava koşullarından etkilenir; yağışlı geçen bir
ilkbahar daha yumuşak yapraklar, kurak bir yaz ise daha keskin bir tat verebilir. Arşiv bölümünü, bu farkları
merak eden çay meraklıları için oluşturduk.</p>
<p>Her koleksiyonun sayfasında hasat yılı, yaprakların toplandığı bahçe, harman oranları ve o yıla özgü tat
notları yer alır. Arşiv ürünleri uygun koşullarda saklandığı için tazeliğini korur; yine de paketin üzerindeki
paketleme tarihini kontrol etmenizi öneririz. Koleksiyonlar sınırlı olduğundan tükenen ürünler yeniden
üretilmez.</p>
<h2>Koleksiyonlar</h2>
<ul>
<li><a href="/urunler/arsiv/2019/">2019 Sonbahar Koleksiyonu</a>: kurak geçen yazın ardından toplanan, koyu
renkli ve güçlü içimli yapraklardan hazırlandı.</li>
</ul>
<p>2019 koleksiyonu, Özel Harman siyah çayımızın ilk kez hazırlandığı sezondur. O yıl denediğimiz harman
oranları müşterilerimizden o kadar olumlu geri dönüş aldı ki tarifi sonraki yıllarda da koruduk. Koleksiyon
sayfasında harmanın ilk halini ve bugünkü tarifle arasındaki küçük farkları anlattık.</p>
<p>Arşiv ürünleri normal kargo ve iade koşullarıyla gönderilir. Sınırlı stok nedeniyle bir siparişte aynı
üründen en fazla üç paket alınabilir. Koleksiyonlarla ilgili sorularınızı iletişim sayfamızdaki e-posta
adresine yazabilirsiniz; hasat ve harman ayrıntılarını memnuniyetle paylaşırız.</p>
<p>Yeni sezon ürünlerine dönmek için ürünler sayfasını kullanabilir, demleme önerilerimizi blogda
okuyabilirsiniz. Arşivi düzenli olarak güncelliyor, yeni sezon kapandığında o sezonun ürünlerini bu bölüme
taşıyoruz.</p>
""")

    sayfa(
        "urunler/arsiv/2019/index.html",
        baslik="2019 Sonbahar Koleksiyonu | Çaylıbahçe",
        aciklama="Kurak bir yazın ardından toplanan koyu renkli yapraklardan hazırlanan 2019 sonbahar "
                 "koleksiyonu ve Özel Harman'ın ilk tarifi.",
        h1="<h1>2019 Sonbahar Koleksiyonu</h1>",
        govde="""
<p>2019 yılının yazı Karadeniz'de alışılmadık derecede kurak geçti. Yağmurların azaldığı bu dönemde çay
bitkileri daha yavaş büyüdü ve yapraklar daha kalın, aroması daha yoğun bir yapı kazandı. Sonbahar hasadında
topladığımız yapraklar, demlendiğinde koyu kızıl bir renk ve belirgin bir burukluk veriyordu. Bu koleksiyonu,
o yılın karakterini korumak için özellikle ayrı paketledik.</p>
<p>Koleksiyonun en önemli ürünü, bugün mağazamızın en çok satan çayı olan Özel Harman'dır. Özel Harman'ı ilk
kez bu sezon, iki farklı bahçeden gelen yaprakları belirli oranlarda karıştırarak hazırladık. Yüksek rakımlı
bahçenin hafif yaprakları harmana zarafet, alçak rakımlı bahçenin kalın yaprakları ise gövde kazandırdı.</p>
<h2>Koleksiyondaki ürünler</h2>
<ul>
<li><a href="/urunler/arsiv/2019/ozel-harman.html">Özel Harman Siyah Çay</a>: iki bahçenin yapraklarından
hazırlanan dengeli ve koyu içimli harman.</li>
</ul>
<p>Koleksiyondaki diğer ürünler kısa sürede tükendi; Özel Harman ise o günden bu yana her sezon yeniden
hazırlanıyor. Arşivdeki 2019 paketleri, harmanın ilk tarifini tatmak isteyenler için saklanan son
stoklardır. Paketler vakumlu ambalajda, ışık almayan bir depoda bekletildi.</p>
<p>Bu koleksiyonu demlerken suyu tam kaynama noktasında kullanmanızı ve demleme süresini on beş dakikanın
üzerine çıkarmamanızı öneririz. Kurak yılın yoğun yaprakları uzun demlendiğinde fazla buruk bir tat verebilir.
Sade içimi sevenler bardağa biraz daha fazla sıcak su ekleyebilir.</p>
<p>Koleksiyonlar arasında gezinmek için arşiv ana sayfasına dönebilirsiniz. Her sezonun notlarını aynı
düzende yazdığımız için yılları birbiriyle kolayca karşılaştırabilirsiniz.</p>
""")

    sayfa(
        "urunler/arsiv/2019/ozel-harman.html",
        baslik="Özel Harman Siyah Çay 1 kg | Çaylıbahçe",
        aciklama="Çaylıbahçe'nin en çok satan çayı Özel Harman: iki bahçenin yapraklarından hazırlanan koyu "
                 "renkli, yumuşak içimli siyah çay.",
        h1="<h1>Özel Harman Siyah Çay</h1>",
        jsonld=urun_ld("Özel Harman Siyah Çay", "İki bahçenin yapraklarından hazırlanan siyah çay harmanı.", "210",
                       "/img/urunler/ozel-harman.svg"),
        govde=f"""
{img("/img/urunler/ozel-harman.svg", "Özel Harman siyah çay paketi")}
<p class="fiyat">Fiyat: 210 TL · 1 kg</p>
<p>Özel Harman, mağazamızın en çok tercih edilen siyah çayıdır. Yüksek rakımlı bir bahçeden gelen ince
yapraklarla alçak rakımlı bir bahçenin kalın yapraklarını belirli bir oranda karıştırarak hazırlanır. İnce
yapraklar harmana hafif ve çiçeksi bir koku katarken kalın yapraklar koyu bir renk ve dolgun bir içim sağlar.
Bu denge sayesinde Özel Harman hem sabah kahvaltısında hem de akşam sohbetlerinde aynı keyifle içilir.</p>
<p>Harmanın tarifini ilk kez 2019 sonbaharında oluşturduk ve o günden bu yana her sezon aynı oranları
korumaya çalışıyoruz. Hasat yılına göre tat profili küçük farklılıklar gösterebilir; bu farkları paket
üzerindeki sezon notunda belirtiriz. Bir kilogramlık ekonomik paket, kalabalık aileler ve çayı gün boyu
demlikte tutan çay severler için hazırlandı.</p>
<h2>Demleme önerisi</h2>
<p>Demliğe kişi başına bir tatlı kaşığı çay koyun ve kaynar suyu ekleyin. Çaydanlığın üzerinde on iki ile on beş
dakika demlendirin. Özel Harman'ın koyu rengi kısa sürede ortaya çıkar; tavşan kanı bir renk için bardağın
üçte birine dem koyup kalanını sıcak suyla tamamlamanız yeterlidir. Uzun süre demlikte bekleyen çayı tazelemek
için demin yarısını dökerek yeni su ekleyebilirsiniz.</p>
<p>Özel Harman şekerli ya da şekersiz içilebilir. Yanında simit, peynir ve zeytinle hazırlanmış bir kahvaltı
sofrası, harmanın en sevilen eşlikçisidir.</p>
{ortak_demleme}
""")

    demleme_metni = """
<p>Çay demlemek ilk bakışta basit görünse de birkaç küçük ayrıntı, bardaktaki tadı tamamen değiştirebilir.
Kullandığınız suyun kalitesi, demliğe koyduğunuz çay miktarı, demleme süresi ve demliğin sıcaklığı birlikte
düşünülmesi gereken unsurlardır. Bu yazıda evde her seferinde aynı lezzeti yakalamanız için adım adım bir
demleme yöntemi anlatıyoruz.</p>
<h2>1. Suyu seçin</h2>
<p>Kireçli musluk suyu çayın rengini bulanıklaştırır ve tadını sertleştirir. Mümkünse filtrelenmiş ya da
kaynak suyu kullanın. Suyu her demlemede yeniden kaynatın; daha önce kaynamış ve soğumuş su, içindeki oksijeni
kaybettiği için çayın aromasını tam olarak açığa çıkarmaz. Çaydanlığı her kullanımdan sonra boşaltmak da
kireç birikmesini azaltır.</p>
<h2>2. Demliği ısıtın</h2>
<p>Soğuk bir demliğe dökülen su hızla ısı kaybeder ve yapraklar yeterince açılmaz. Çayı koymadan önce
demliği bir miktar sıcak suyla çalkalayın ve bu suyu dökün. Isınan demlik, demleme boyunca sıcaklığın sabit
kalmasına yardımcı olur.</p>
<h2>3. Doğru miktarı koyun</h2>
<p>Genel bir ölçü olarak kişi başına bir tatlı kaşığı çay yeterlidir. Kalabalık sofralar için demliğe bir
kaşık da demlik için eklenebilir. Fazla çay koymak demi acılaştırır; az çay koymak ise rengi açık ve tadı
sulu bir çay verir. Kendi damak zevkinize göre bu ölçüyü birkaç denemede ayarlayabilirsiniz.</p>
<h2>4. Suyu ekleyin ve bekleyin</h2>
<p>Kaynayan suyu yaprakların üzerine dökün ve demliği çaydanlığın üzerine yerleştirin. Çaydanlıktaki suyun
kısık ateşte sıcak kalması, demin de sıcak kalmasını sağlar. Siyah çaylar için on iki ile on beş dakika arası
bir demleme süresi çoğu damak zevkine uygundur. Demliği bu süre boyunca karıştırmamaya özen gösterin.</p>
<h2>5. Servis edin</h2>
<p>Bardağa önce demi, ardından sıcak suyu ekleyin. Koyu çay sevenler demi artırabilir, açık çay sevenler
suyu artırabilir. Demlendikten sonra bir saatten fazla bekleyen çay bayatlar ve tadı ekşimeye başlar; bu
durumda demliği boşaltıp yeniden demlemek en iyisidir.</p>
<p>Bu adımları izlediğinizde evde hazırladığınız çay, her seferinde aynı canlı renk ve dengeli tatla
bardağınıza gelir. Farklı çay türleri için önerdiğimiz süre ve sıcaklıkları ürün sayfalarımızda ayrıca
bulabilirsiniz.</p>
"""
    sayfa(
        "blog/index.html",
        baslik="Çay Blogu: Demleme ve Tarifler | Çaylıbahçe",
        aciklama="Çay demleme yöntemleri, bitki çayları ve kış harmanları üzerine Çaylıbahçe blog yazıları. "
                 "Evde daha lezzetli çay için öneriler.",
        h1="<h1>Çay Blogu</h1>",
        govde="""
<p>Çaylıbahçe blogunda çayın bahçeden bardağa uzanan yolculuğunu, farklı çay türlerinin nasıl demleneceğini ve
mevsimlere göre hazırlayabileceğiniz tarifleri paylaşıyoruz. Yazılarımızı mağazamızda en sık duyduğumuz
sorulardan yola çıkarak hazırlıyoruz; amacımız, evde hazırladığınız her bardak çayın biraz daha lezzetli
olmasına katkıda bulunmak.</p>
<h2>Son yazılar</h2>
<article><h3><a href="/blog/cay-nasil-demlenir.html">Çay nasıl demlenir?</a></h3>
<p>Suyun seçiminden demleme süresine kadar, evde her seferinde aynı lezzeti yakalamanız için izlemeniz
gereken beş adımı anlattık. Yeni başlayanlar için en iyi başlangıç noktası bu yazıdır.</p></article>
<article><h3><a href="/blog/cay-demleme-rehberi.html">Çay demleme rehberi</a></h3>
<p>Demlik, çaydanlık ve bardak seçimiyle birlikte demleme adımlarını tek bir rehberde topladık. Sofranızı
hazırlarken yanınızda bulunması gereken pratik bir kaynak.</p></article>
<article><h3><a href="/blog/bitki-caylari.html">Bitki çayları rehberi</a></h3>
<p>Ada çayı, ıhlamur ve diğer bitki çaylarının nasıl demleneceğini, hangi saatlerde içilebileceğini ve
birbirleriyle nasıl harmanlanabileceğini anlattık.</p></article>
<article><h3><a href="/blog/kis-caylari.html">Kış çayı harmanı nasıl hazırlanır?</a></h3>
<p>Tarçın, karanfil ve portakal kabuğuyla evde kendi kış çayı harmanınızı hazırlamanın yollarını ve baharat
oranlarının tada etkisini paylaştık.</p></article>
<article><h3><a href="/blog/semaver-bakimi.html">Semaver bakımı nasıl yapılır?</a></h3>
<p>Semaverde kireç birikmesini önlemenin ve semaveri uzun yıllar sorunsuz kullanmanın püf noktalarını
derledik.</p></article>
<h2>Yazılarımız hakkında</h2>
<p>Bloglardaki tarif ve önerileri kendi mutfağımızda deneyerek yazıyoruz. Demleme süreleri ve ölçüler bir
başlangıç noktasıdır; kullandığınız suyun sertliği ve damak zevkiniz, en iyi sonucu veren ölçüyü
belirleyecektir. Yazılarla ilgili sorularınızı ve kendi tariflerinizi iletişim sayfamızdaki e-posta adresine
gönderebilirsiniz. Okurlarımızdan gelen önerileri zaman zaman yeni yazılarda paylaşıyoruz.</p>
<p>Yeni yazılarımızı her ay düzenli olarak yayımlıyoruz. Mevsim değiştikçe önerdiğimiz çayları ve tarifleri
de güncelliyoruz; sonbaharda baharatlı harmanlara, yazın ise soğuk demleme yöntemlerine ağırlık veriyoruz.</p>
""")

    sayfa(
        "blog/cay-nasil-demlenir.html", viewport=False,
        baslik="Çay Nasıl Demlenir? Adım Adım Anlatım | Çaylıbahçe",
        aciklama="Evde her seferinde aynı lezzette çay için suyun seçiminden servis etmeye kadar beş adımlı "
                 "çay demleme yöntemi.",
        h1="<h1>Çay Nasıl Demlenir?</h1>",
        jsonld=makale_ld("Çay Nasıl Demlenir?", "2025-11-03"),
        govde=demleme_metni)

    sayfa(
        "blog/cay-demleme-rehberi.html",
        baslik="Çay Demleme Rehberi: Adım Adım | Çaylıbahçe",
        aciklama="Demlik, çaydanlık ve bardak seçimiyle birlikte adım adım çay demleme rehberi. Sofranız için "
                 "pratik demleme önerileri.",
        h1="<h1>Çay Demleme Rehberi</h1>",
        jsonld=makale_ld("Çay Demleme Rehberi", "2026-01-15"),
        govde=demleme_metni.replace("Bu yazıda evde", "Bu rehberde evde", 1))

    sayfa(
        "blog/bitki-caylari.html",
        baslik="Bitki Çayları Rehberi: Demleme ve Harmanlar | Çaylıbahçe",
        aciklama="Ada çayı, ıhlamur, kuşburnu ve yasemin gibi bitki çaylarının nasıl demleneceği, hangi saatlerde "
                 "içilebileceği, birbirleriyle nasıl harmanlanabileceği ve evde nasıl saklanması gerektiği "
                 "üzerine kapsamlı bir rehber.",
        h1="<h1>Bitki Çayları Rehberi</h1>",
        jsonld=makale_ld("Bitki Çayları Rehberi", "2025-12-10"),
        govde="""
<p>Bitki çayları, çay bitkisi dışındaki bitkilerin yaprak, çiçek, kök ya da meyvelerinden hazırlanan
içeceklerdir. Kafein içermedikleri için günün her saatinde tercih edilebilirler. Bu rehberde mağazamızda en çok
sorulan bitki çaylarının nasıl demleneceğini ve evde hangi harmanları deneyebileceğinizi anlatıyoruz.</p>
<h2>Ada çayı</h2>
<p>Ada çayının ferah kokusu, kısa demleme süresiyle en iyi şekilde ortaya çıkar. Bir bardak için bir tatlı
kaşığı yaprak yeterlidir. Kaynayan suyu biraz soğutup yaprakların üzerine dökün ve beş dakika bekletin. Uzun
demlenen ada çayı acılaşır. Ürün sayfamızda ada çayının toplanma ve kurutulma sürecini ayrıca anlattık.</p>
<h2>Ihlamur</h2>
<p>Ihlamur, çiçekli dallarıyla birlikte demlenir. Dalları kırmadan demliğe yerleştirip kaynar su ekleyin ve
kapağı kapalı olarak beş ile yedi dakika bekletin. Kış akşamlarında bir kaşık bal ve bir dilim limonla içilen
ıhlamur, sıcak ve yumuşak bir içim sunar.</p>
<h2>Yasemin</h2>
<p>Yasemin çiçekleri çoğunlukla yeşil çayla birlikte harmanlanır; tek başına demlendiğinde ise çok hafif ve
çiçeksi bir tat verir. Yasemin çiçeklerini düşük sıcaklıktaki suyla üç dakika demlemek yeterlidir.
Mağazamızdaki <a href="/urunler/yasemin-cayi.html">yasemin çayını</a> sade ya da yeşil çayla karıştırarak
deneyebilirsiniz.</p>
<h2>Evde harman hazırlamak</h2>
<p>Bitki çaylarını birbirleriyle karıştırarak kendi harmanınızı hazırlayabilirsiniz. Ihlamur ve ada çayı
karışımı kış aylarında sevilen bir seçimdir; kuşburnu eklemek ise harmana hafif ekşi ve meyvemsi bir not katar.
Harman hazırlarken baskın kokulu bitkilerin oranını düşük tutmanızı, her denemenin ölçüsünü not almanızı
öneririz. Böylece beğendiğiniz harmanı bir sonraki sefer kolayca tekrarlayabilirsiniz.</p>
<p>Bitki çaylarını da diğer çaylar gibi ışık almayan, nemsiz bir dolapta ve ağzı kapalı bir kapta saklayın.
Kurutulmuş çiçekler ve yapraklar nemle kolayca bozulur; paketi açtıktan sonra birkaç ay içinde tüketmek
tazelik açısından en iyisidir.</p>
""")

    sayfa(
        "blog/kis-caylari.html", canonical=None,
        baslik="Kış Çayı Harmanı Nasıl Hazırlanır? | Çaylıbahçe",
        aciklama="Tarçın, karanfil ve portakal kabuğuyla evde kış çayı harmanı hazırlamanın yolları ve baharat "
                 "oranlarının tada etkisi.",
        h1="<h1>Kış Çayı Harmanı</h1>",
        jsonld=makale_ld("Kış Çayı Harmanı Nasıl Hazırlanır?", "2026-01-05"),
        govde=f"""
<p>Havalar soğuduğunda baharatlı bir çayın kokusu evin her köşesine sıcaklık taşır. Kış çayı harmanı, siyah
çayın burukluğunu tarçın, karanfil ve portakal kabuğuyla yumuşatan, hazırlaması kolay bir karışımdır. Bu yazıda
evde kendi kış harmanınızı nasıl hazırlayabileceğinizi ve baharat oranlarını nasıl ayarlayabileceğinizi
anlatıyoruz.</p>
{img("/img/blog/baharatlar.svg", None)}
<h2>Malzemeler</h2>
<p>Harmanın tabanı için iyi kalitede bir siyah çay seçin. İki yüz gram çay için yaklaşık on gram kırılmış
tarçın kabuğu, beş gram bütün karanfil ve on beş gram kurutulmuş portakal kabuğu iyi bir başlangıç oranıdır.
Portakal kabuğunu evde kurutmak isterseniz kabukların beyaz kısmını incelterek ayırın ve düşük ısıdaki fırında
birkaç saat bekletin.</p>
<h2>Hazırlanışı</h2>
<p>Baharatları havanda hafifçe kırarak aromalarını açığa çıkarın; toz haline getirmeyin, aksi halde demlik
süzgecinden bardağa geçerler. Kırılan baharatları çayla birlikte geniş bir kapta karıştırın ve ağzı sıkıca
kapanan bir kavanoza aktarın. Harmanı kullanmadan önce iki gün dinlendirmek, baharatların kokusunun çay
yapraklarına geçmesini sağlar.</p>
{img("/img/blog/kis-cayi-bardak.svg", None)}
<h2>Oranları ayarlamak</h2>
<p>Tarçın oranını artırmak harmana tatlımsı bir sıcaklık katar; karanfil ise küçük miktarlarda bile belirgin
olduğu için dikkatli kullanılmalıdır. Portakal kabuğu, harmanın en ferah notasıdır ve çocuklu evlerde sevilen
bir tat verir. Her denemenin ölçülerini not alarak damak zevkinize en uygun oranı birkaç seferde bulabilirsiniz.</p>
<p>Kendi harmanınızı hazırlamaya vakit bulamazsanız mağazamızdaki Kış Çayı Harmanı, aynı malzemelerle küçük
partiler halinde hazırlanır. Kış boyunca yapılan kampanyaları da bu harman için takip edebilirsiniz.</p>
""")

    sayfa(
        "blog/yesil-cay-faydalari.html",
        baslik="Yeşil Çay Hakkında Bilinmesi Gerekenler | Çaylıbahçe",
        aciklama="Yeşil çayın siyah çaydan farkı, doğru demleme sıcaklığı ve saklama koşulları. Yeşil çayla "
                 "tanışmak isteyenler için kısa bir rehber.",
        h1="<h1>Yeşil Çay Hakkında Bilinmesi Gerekenler</h1>",
        jsonld=makale_ld("Yeşil Çay Hakkında Bilinmesi Gerekenler", "2025-10-20"),
        govde="""
<p>Yeşil çay, siyah çayla aynı bitkiden elde edilir; aradaki fark yaprakların işlenme biçimindedir. Siyah
çayda yapraklar kıvrıldıktan sonra uzun süre oksitlenmeye bırakılırken yeşil çayda yapraklar toplandıktan
kısa süre sonra ısıl işlemle sabitlenir. Bu işlem yaprağın yeşil rengini ve taze, otsu kokusunu korur.</p>
<h2>Demleme sıcaklığı</h2>
<p>Yeşil çayın en sık yapılan demleme hatası, kaynar su kullanmaktır. Yüksek sıcaklık yaprakları yakar ve
çaya acı bir tat verir. Suyu kaynattıktan sonra birkaç dakika bekleterek yetmiş ile seksen derece arasına
düşürün. Bir bardak için bir tatlı kaşığı yaprak yeterlidir ve demleme süresi iki ile üç dakikayı geçmemelidir.</p>
<h2>Kaç kez demlenir?</h2>
<p>Kaliteli yeşil çay yaprakları iki ya da üç kez demlenebilir. İlk demleme en hafif ve en kokulu olanıdır;
sonraki demlemelerde süreyi birer dakika artırmanız yeterlidir. Her demlemede çayın tadının nasıl değiştiğini
fark etmek, yeşil çayın keyifli yanlarından biridir.</p>
<h2>Saklama</h2>
<p>Yeşil çay, siyah çaya göre daha çabuk bayatlar. Paketi açtıktan sonra ışık almayan, serin bir yerde ve
hava almayan bir kapta saklayın. Buzdolabında saklamak isterseniz kabın kokuları geçirmediğinden emin olun ve
çayı kullanmadan önce oda sıcaklığına gelmesini bekleyin. Açılmış paketi bir ay içinde tüketmek, yeşil çayın
tazeliğini korumanın en kolay yoludur.</p>
<h2>Hangi saatlerde içilir?</h2>
<p>Yeşil çay da kafein içerir, ancak demleme süresi kısa olduğu için bardağa geçen kafein genellikle siyah
çaydan azdır. Sabahları ya da öğleden sonraları tercih edilebilir. Yemeklerle birlikte içildiğinde hafif ve
ferah tadı, ağır yemeklerin ardından da hoş bir denge kurar.</p>
<p>Yeşil çayla yeni tanışıyorsanız önce sade olarak denemenizi, ardından yasemin ya da nane ile harmanlanmış
çeşitlerine geçmenizi öneririz.</p>
""")

    sayfa(
        "hakkimizda.html", baslik=None, charset=False, canonical=TABAN + "/hakkimizda",
        aciklama="Çaylıbahçe'nin hikâyesi: küçük bir aile işletmesinden doğan, üreticilerle doğrudan çalışan ve "
                 "çayı küçük partilerle paketleyen çay mağazası.",
        h1="<h1>Hakkımızda</h1>",
        govde="""
<p>Çaylıbahçe, 2014 yılında Trabzon'un Of ilçesinde bir aile işletmesi olarak kuruldu. Kurucularımız, yıllarca
kendi bahçelerinde yetiştirdikleri çayı komşularına ve tanıdıklarına gönderirken, iyi saklanmış ve doğru
demlenmiş taze çayın büyük şehirlerde ne kadar zor bulunduğunu fark ettiler. Mağazamız, bu basit fikirden yola
çıkarak doğdu: bahçeden gelen çayı, raflarda beklemeden ve tazeliğini kaybetmeden sofralara ulaştırmak.</p>
<p>Bugün Doğu Karadeniz'deki on iki küçük üreticiyle doğrudan çalışıyoruz. Hasat dönemlerinde bahçeleri
ziyaret ediyor, yaprakların toplanma zamanını üreticilerle birlikte planlıyoruz. Çaylarımızı büyük
fabrikalarda değil, küçük işleme atölyelerinde kurutuyor ve kendi depomuzda küçük partiler halinde
paketliyoruz. Bu yöntem daha fazla emek istiyor, ancak her paketin hangi bahçeden ve hangi hasattan geldiğini
bilmemizi sağlıyor.</p>
<h2>Neye önem veriyoruz?</h2>
<p>Tazelik bizim için her şeyden önce gelir. Siparişleri depodaki stoktan değil, her hafta yeniden paketlenen
ürünlerden gönderiyoruz. Paketlerimizde plastik kullanmamaya özen gösteriyor, geri dönüştürülebilir kâğıt ve
karton tercih ediyoruz. Üreticilerimize ürünlerinin karşılığını hasattan hemen sonra ödüyor, uzun vadeli
anlaşmalarla onların da geleceğini planlayabilmesini sağlıyoruz.</p>
<p>Bitki çaylarımızı Ege ve Akdeniz'deki toplayıcılardan temin ediyoruz. Bitkilerin doğadan sürdürülebilir
biçimde toplanması için toplayıcılarımızla birlikte belirlediğimiz kurallara uyuyor, her bitkinin yalnızca
uygun mevsimde toplanmasına dikkat ediyoruz.</p>
<h2>Ekibimiz</h2>
<p>Küçük ekibimiz depoda paketleme, müşteri hizmetleri ve bahçe ziyaretleri arasında görevleri paylaşan sekiz
kişiden oluşuyor. Sorularınızı yanıtlayan kişi, çoğu zaman çayınızı paketleyen kişiyle aynı odada çalışıyor.
Bu yakınlık, müşterilerimizden gelen her geri bildirimi hızla ürünlerimize yansıtmamızı sağlıyor.</p>
""")

    sayfa(
        "iletisim.html", lang=None, baslik="İletişim",
        aciklama="Çaylıbahçe iletişim bilgileri: adres, telefon, e-posta ve çalışma saatleri. Sipariş ve ürün "
                 "sorularınız için bize ulaşın.",
        h1="<h1>İletişim</h1>",
        govde="""
<p>Siparişleriniz, ürünlerimiz ya da kurumsal hediye paketleri hakkındaki sorularınız için aşağıdaki
kanallardan bize ulaşabilirsiniz. Hafta içi gün boyunca, cumartesi günleri ise öğlene kadar sorularınızı
yanıtlıyoruz. Yoğun hasat dönemlerinde yanıt süremiz biraz uzayabilir; bu durumda anlayışınız için şimdiden
teşekkür ederiz.</p>
<h2>Adres</h2>
<p>Çaylıbahçe Depo ve Mağaza<br>Atatürk Caddesi No: 12<br>Of / Trabzon</p>
<p>Depomuzun bir bölümünü küçük bir mağaza olarak düzenledik. Trabzon'a yolunuz düşerse uğrayıp çaylarımızı
yerinde tadabilir, harmanların hazırlanışını izleyebilirsiniz. Ziyaret etmeden önce telefonla haber vermeniz,
size daha iyi vakit ayırmamızı sağlar.</p>
<h2>Telefon ve e-posta</h2>
<p>Telefon: 0462 000 00 00<br>E-posta: merhaba@caylibahce.example</p>
<p>E-posta ile yazdığınızda sipariş numaranızı da eklerseniz sorununuzu çok daha hızlı çözebiliriz. Ürünlerle
ilgili önerilerinizi, beğendiğiniz harmanları ya da denemek istediğiniz yeni çayları da bize yazabilirsiniz;
okuduğumuz her mesaj, gelecek sezonun ürünlerini planlarken bize yol gösteriyor.</p>
<h2>Çalışma saatleri</h2>
<p>Pazartesi – Cuma: 09.00 – 18.00<br>Cumartesi: 09.00 – 13.00<br>Pazar: kapalı</p>
<h2>Kurumsal siparişler</h2>
<p>Şirketler ve kurumlar için toplu hediye paketleri hazırlıyoruz. Kutuların üzerine kurum adınızı ya da
logonuzu baskı olarak ekleyebilir, paketlerin içeriğini bütçenize göre düzenleyebiliriz. Kurumsal siparişler
için en az iki hafta önceden bizimle iletişime geçmenizi öneririz; böylece ürünleri istediğiniz tarihte
eksiksiz hazırlayabiliriz.</p>
<p>Kargo süreleri ve iade koşulları hakkında ayrıntılı bilgiye kargo ve iade sayfamızdan ulaşabilirsiniz.
Sık sorulan soruların yanıtlarını da ayrı bir sayfada topladık.</p>
""")

    sayfa(
        "sss.html", charset=False,
        baslik="Sıkça Sorulan Sorular | Çaylıbahçe",
        aciklama="Çaylıbahçe siparişleri, kargo süreleri, ödeme seçenekleri ve ürün saklama koşulları hakkında "
                 "sıkça sorulan sorular.",
        h1="<h1>Sıkça Sorulan Sorular</h1>",
        govde="""
<h2>Siparişim ne zaman kargoya verilir?</h2>
<p>Hafta içi saat on beşe kadar verilen siparişler aynı gün kargoya teslim edilir.</p>
<h2>Çayı nasıl saklamalıyım?</h2>
<p>Işık almayan, nemsiz bir dolapta ve ağzı kapalı bir kapta saklayın.</p>
""")

    sayfa(
        "kargo-ve-iade.html",
        head_ek='<meta name="robots" content="noindex, follow">',
        baslik="Kargo ve İade Koşulları | Çaylıbahçe",
        aciklama="Çaylıbahçe kargo süreleri, gönderim ücretleri ve iade koşulları. Siparişinizin ne zaman "
                 "ulaşacağını ve nasıl iade edebileceğinizi öğrenin.",
        h1="<h1>Kargo ve İade Koşulları</h1>",
        govde="""
<p>Siparişlerinizi en kısa sürede ve en iyi koşullarda ulaştırmak için anlaşmalı kargo firmamızla çalışıyoruz.
Bu sayfada gönderim süreleri, kargo ücretleri ve iade sürecine ilişkin bilmeniz gereken her şeyi bulabilirsiniz.
Sorularınız için iletişim sayfamızdaki kanallardan bize her zaman ulaşabilirsiniz.</p>
<h2>Gönderim süresi</h2>
<p>Hafta içi saat on beşe kadar verilen siparişler aynı gün kargoya teslim edilir. Bu saatten sonra ya da hafta
sonu verilen siparişler ilk iş günü gönderilir. Kargonun size ulaşma süresi bulunduğunuz bölgeye göre bir ile
üç iş günü arasında değişir. Kargoya verilen her sipariş için takip numarası e-posta adresinize gönderilir.</p>
<h2>Kargo ücreti</h2>
<p>Belirli bir tutarın üzerindeki siparişlerde kargo ücretsizdir; bu tutarın altındaki siparişlerde sabit
kargo ücreti uygulanır. Güncel tutarlar sipariş özeti ekranında gösterilir. Demlik seti gibi kırılabilir
ürünler, köpük korumalı özel kutularda gönderildiği için ek ücret alınmaz.</p>
<h2>İade koşulları</h2>
<p>Açılmamış paketleri teslim tarihinden itibaren on dört gün içinde iade edebilirsiniz. Gıda ürünlerinde
hijyen nedeniyle açılmış paketlerin iadesini kabul edemiyoruz; ancak ürünün bozuk ya da hasarlı ulaşması
durumunda paket açılmış olsa bile değişim ya da ücret iadesi yapıyoruz. Bu durumda ürünün fotoğrafını
e-posta ile göndermeniz yeterlidir.</p>
<h2>Hasarlı teslimat</h2>
<p>Kargo paketinde ezilme ya da yırtılma fark ederseniz paketi teslim alırken kargo görevlisine tutanak
tutturmanızı rica ederiz. Tutanak, hasar bedelinin kargo firmasından karşılanabilmesi için gereklidir. Kırık
ulaşan demlik ve bardaklar için yeni ürünü ek ücret almadan hemen gönderiyoruz.</p>
<h2>Ücret iadesi</h2>
<p>İade edilen ürün depomuza ulaştıktan sonra iki iş günü içinde incelenir ve ücret, ödemeyi yaptığınız
yönteme iade edilir. Bankanıza bağlı olarak tutarın hesabınıza yansıması birkaç gün sürebilir.</p>
""")

    sayfa(
        "gizlilik.html", lang=None, aciklama=None,
        baslik="Gizlilik Politikası | Çaylıbahçe",
        h1="<h1>Gizlilik Politikası</h1>",
        govde="""
<p>Bu gizlilik politikası, Çaylıbahçe internet sitesini ziyaret ettiğinizde ve sipariş verdiğinizde hangi
bilgilerin toplandığını, bu bilgilerin hangi amaçlarla kullanıldığını ve nasıl korunduğunu açıklar. Sitemizi
kullanarak bu politikada anlatılan uygulamaları kabul etmiş olursunuz.</p>
<h2>Topladığımız bilgiler</h2>
<p>Sipariş verdiğinizde adınızı, teslimat adresinizi, telefon numaranızı ve e-posta adresinizi alırız. Bu
bilgiler yalnızca siparişinizi hazırlamak, kargoya vermek ve sizi sipariş durumunuz hakkında bilgilendirmek
için kullanılır. Ödeme bilgileriniz doğrudan ödeme hizmeti sağlayıcısı tarafından işlenir; kart bilgileriniz
sunucularımızda saklanmaz.</p>
<h2>Çerezler</h2>
<p>Sitemiz, sepetinizdeki ürünleri hatırlamak ve sayfaların doğru çalışmasını sağlamak için zorunlu çerezler
kullanır. Ziyaret istatistiklerini anlamak için kullanılan analiz çerezleri ise yalnızca onay vermeniz
durumunda etkinleştirilir. Tarayıcınızın ayarlarından çerezleri dilediğiniz zaman silebilir ya da
engelleyebilirsiniz.</p>
<h2>Bilgilerin paylaşılması</h2>
<p>Kişisel bilgilerinizi satmıyor ve pazarlama amacıyla üçüncü kişilerle paylaşmıyoruz. Teslimat için gerekli
olan ad, adres ve telefon bilgileri yalnızca anlaşmalı kargo firmamızla paylaşılır. Yasal bir zorunluluk
olması halinde bilgiler yetkili kurumlara iletilebilir.</p>
<h2>Bilgilerin saklanması</h2>
<p>Sipariş kayıtlarını yasal saklama süreleri boyunca güvenli sunucularda tutarız. Bu süre dolduğunda kayıtlar
silinir ya da anonim hale getirilir. Bültenimize abone olduysanız e-posta adresinizi, aboneliğinizi
sonlandırana kadar saklarız.</p>
<h2>Haklarınız</h2>
<p>Hakkınızda tuttuğumuz bilgileri öğrenme, düzeltilmesini ya da silinmesini isteme hakkına sahipsiniz. Bu
haklarınızı kullanmak için iletişim sayfamızdaki e-posta adresine yazabilirsiniz. Talebinizi en geç otuz gün
içinde yanıtlarız.</p>
""")

    sayfa(
        "en/index.html", lang="en",
        baslik="Çaylıbahçe | Natural Black Tea and Herbal Infusions",
        aciklama="Small-batch black teas from the Black Sea hills and hand-picked herbal infusions, packed fresh "
                 "and shipped from Trabzon.",
        h1="<h1>Natural Black Tea and Herbal Infusions</h1>",
        head_ek='<link rel="alternate" hreflang="en-UK" href="' + TABAN + '/en/">',
        govde="""
<p>Çaylıbahçe is a small tea shop based in Trabzon, on the Black Sea coast of Türkiye. We work directly with a
dozen family growers in the misty hills of the eastern Black Sea region and pack our teas in small batches,
so every pouch reaches you while the leaves are still fresh and fragrant.</p>
<p>Our range starts with classic Turkish black tea, brewed the traditional way in a double teapot, and extends
to delicate first flush leaves, spiced winter blends and herbal infusions gathered on the Aegean and
Mediterranean coasts. Each product page explains the water temperature, steeping time and storage tips that
bring out the best in the leaves.</p>
<h2>How we work</h2>
<p>During the harvest season we visit the gardens and plan the picking dates together with our growers. The
leaves are withered, rolled and dried in small workshops rather than large factories, then packed in our own
warehouse every week. This takes more effort, but it means we always know which garden and which harvest each
pouch comes from.</p>
<p>We avoid plastic packaging wherever we can and use recyclable paper and cardboard instead. Every order
includes a small card with brewing suggestions, so that even first time tea drinkers can make a balanced cup
at home.</p>
<h2>Brewing Turkish tea</h2>
<p>Turkish tea is brewed in two stacked pots. Water boils in the larger kettle below while the tea steeps in
the smaller pot on top for twelve to fifteen minutes. To serve, pour a little of the strong tea into a tulip
shaped glass and top it up with hot water until you reach the colour you like. Lighter cups are called açık,
stronger ones koyu.</p>
<h2>Shipping</h2>
<p>At the moment we ship within Türkiye only. If you would like to order from abroad, please write to us and we
will let you know when international shipping becomes available. We are happy to answer questions about our
teas in English.</p>
""")


def statik_dosyalar():
    (HEDEF / "css").mkdir(parents=True, exist_ok=True)
    (HEDEF / "css" / "site.css").write_text(
        "body{font-family:Georgia,serif;margin:0;color:#1b2a1d;background:#fbfaf5}"
        ".ust{display:flex;justify-content:space-between;align-items:center;padding:12px 24px;background:#e8efe2}"
        ".ust ul,.alt ul{list-style:none;display:flex;gap:16px;margin:0;padding:0}"
        "main{max-width:880px;margin:0 auto;padding:24px}img{max-width:100%;height:auto}"
        ".izgara{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:20px}"
        ".alt{padding:24px;background:#e8efe2;margin-top:40px}.fiyat{font-weight:bold}\n", encoding="utf-8")
    (HEDEF / "css" / "yazi-tipi.css").write_text(
        "@font-face{font-family:'Yaprak';src:local('Georgia')}h1,h2{font-family:'Yaprak',Georgia,serif}\n",
        encoding="utf-8")
    (HEDEF / "js").mkdir(parents=True, exist_ok=True)
    (HEDEF / "js" / "analitik.js").write_text(
        "(function(){var b=Date.now();while(Date.now()-b<30){}window.ziyaret={sayfa:location.pathname};})();\n",
        encoding="utf-8")
    (HEDEF / "js" / "kaydirici.js").write_text(
        "document.addEventListener('DOMContentLoaded',function(){var g=document.querySelector('main img');"
        "if(g){g.classList.add('kaydirici');}});\n", encoding="utf-8")
    (HEDEF / "js" / "hediye.js").write_text("""(function () {
  var kok = document.getElementById("app");
  fetch("/veri/hediye.json").then(function (r) { return r.json(); }).then(function (veri) {
    var h = '<header class="ust"><a class="logo" href="/">Çaylıbahçe</a></header><main>';
    h += "<h1>" + veri.baslik + "</h1><p>" + veri.giris + "</p>";
    veri.paketler.forEach(function (p) {
      h += '<article class="kart"><h2>' + p.ad + "</h2><p>" + p.aciklama + "</p><p class=\\"fiyat\\">Fiyat: " +
        p.fiyat + '</p><p>İçindeki çaylar: ' + p.icerik.map(function (c) {
          return '<a href="' + c.adres + '">' + c.ad + "</a>"; }).join(", ") + "</p></article>";
    });
    kok.innerHTML = h + "<p>" + veri.kapanis + "</p></main>";
  });
})();
""", encoding="utf-8")
    (HEDEF / "veri").mkdir(parents=True, exist_ok=True)
    (HEDEF / "veri" / "hediye.json").write_text(json.dumps({
        "baslik": "Hediye Paketleri",
        "giris": "Ahşap kutularda sunulan hediye paketlerimiz iki ya da dört farklı çaydan oluşur. Kutunun içine "
                 "kısa bir not ekleyebilir, paketi doğrudan sevdiklerinizin adresine gönderebilirsiniz. Her kutuda "
                 "demleme önerilerini anlatan bir kart ve çayların hangi bahçeden geldiğini gösteren küçük bir harita "
                 "bulunur. Kutular yeniden kullanılabilir masif ahşaptan üretilir.",
        "paketler": [
            {"ad": "İkili Tadım Kutusu", "fiyat": "390 TL",
             "aciklama": "Sabah ve akşam için iki farklı karakterde çay: filiz çayının yumuşak içimi ile kış "
                         "harmanının baharatlı sıcaklığı aynı kutuda buluşur.",
             "icerik": [{"ad": "Rize Filiz Çayı", "adres": "/urunler/rize-filiz-cayi.html"},
                        {"ad": "Kış Çayı Harmanı", "adres": "/urunler/Kis-Cayi.html"}]},
            {"ad": "Dörtlü Keşif Kutusu", "fiyat": "720 TL",
             "aciklama": "Siyah, beyaz ve bitki çaylarından oluşan dörtlü kutu, çay dünyasını tanımak isteyenler "
                         "için hazırlandı. Her çayın demleme süresi kutunun kapağında yazılıdır.",
             "icerik": [{"ad": "Özel Harman Siyah Çay", "adres": "/urunler/arsiv/2019/ozel-harman.html"},
                        {"ad": "Beyaz Çay", "adres": "/urunler/beyaz-cay.html"},
                        {"ad": "Ada Çayı", "adres": "/urunler/ada-cayi.html"},
                        {"ad": "Ihlamur", "adres": "/urunler/ihlamur.html"}]}],
        "kapanis": "Kurumsal hediye siparişleriniz için kutulara kurum adınızı ya da logonuzu baskı olarak "
                   "ekleyebiliriz. Toplu siparişler için en az iki hafta önceden bizimle iletişime geçmenizi öneririz."},
        ensure_ascii=False, indent=2), encoding="utf-8")

    svg_yaz(HEDEF / "img" / "logo.svg", "Çaylıbahçe", "#e8efe2", "#2e7d32", 160, 48)
    (HEDEF / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
        '<circle cx="16" cy="16" r="14" fill="#2e7d32"/></svg>\n', encoding="utf-8")
    svg_yaz(HEDEF / "img" / "ana-gorsel.svg", "Taze çay yaprakları", "#dcebd3", "#2e7d32", 800, 400)
    svg_yaz(HEDEF / "img" / "kampanya-afisi.svg", "Kış harmanlarında ücretsiz paketleme", "#f3e1c7", "#b5651d", 800, 200)
    for ad, etiket, zemin, vurgu in [("filiz-cayi", "Rize Filiz Çayı", "#eef5e6", "#8d6e3f"),
                                     ("ada-cayi", "Ada Çayı", "#eef2ee", "#6b8f71"),
                                     ("ihlamur", "Ihlamur", "#f6f1dc", "#c9a227"),
                                     ("beyaz-cay", "Beyaz Çay", "#f7f7f2", "#c8c3a8"),
                                     ("kis-cayi", "Kış Çayı Harmanı", "#f4e6dc", "#a0522d"),
                                     ("demlik", "Demlik Seti", "#eceff1", "#90a4ae"),
                                     ("ozel-harman", "Özel Harman", "#efe5dc", "#5d4037")]:
        svg_yaz(HEDEF / "img" / "urunler" / (ad + ".svg"), etiket, zemin, vurgu)
    svg_yaz(HEDEF / "img" / "blog" / "baharatlar.svg", "Tarçın, karanfil, portakal", "#f4e6dc", "#a0522d")
    svg_yaz(HEDEF / "img" / "blog" / "kis-cayi-bardak.svg", "Bir bardak kış çayı", "#f4e6dc", "#7b3f00")
    png_yaz(HEDEF / "img" / "urunler" / "demlik-seti-buyuk.png", 480, 360, gurultu=True)
    png_yaz(HEDEF / "img" / "paylasim.png", 120, 63)


def robots_ve_sitemap():
    (HEDEF / "robots.txt").write_text(
        "User-agent: *\nDisallow: /urunler/beyaz-cay.html\n\n"
        f"Sitemap: {TABAN}/sitemap_index.xml\nSitemap: {TABAN}/sitemap.xml\n", encoding="utf-8")
    adresler = ["/", "/urunler/", "/urunler/sayfa/2.html", "/urunler/rize-filiz-cayi.html", "/urunler/ada-cayi.html",
                "/urunler/ihlamur.html", "/urunler/beyaz-cay.html", "/urunler/Kis-Cayi.html",
                "/urunler/demlik-seti.html", "/urunler/hediye-paketleri.html", "/urunler/arsiv/",
                "/urunler/arsiv/2019/", "/urunler/arsiv/2019/ozel-harman.html", "/blog/",
                "/blog/cay-nasil-demlenir.html", "/blog/cay-demleme-rehberi.html", "/blog/kis-caylari.html",
                "/blog/yesil-cay-faydalari.html", "/blog/semaver-bakimi.html", "/hakkimizda.html", "/iletisim.html",
                "/kargo-ve-iade.html", "/gizlilik.html", "/en/", "/kampanya", "/eski-urunler"]
    satirlar = ['<?xml version="1.0" encoding="UTF-8"?>',
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    satirlar += [f"  <url><loc>{TABAN}{a}</loc></url>" for a in adresler]
    satirlar += ["</urlset>", ""]
    (HEDEF / "sitemap.xml").write_text("\n".join(satirlar), encoding="utf-8")


def main():
    if HEDEF.exists():
        shutil.rmtree(HEDEF)
    HEDEF.mkdir(parents=True)
    sayfalari_uret()
    statik_dosyalar()
    robots_ve_sitemap()
    html = sorted(p.relative_to(HEDEF).as_posix() for p in HEDEF.rglob("*.html"))
    from ortak import MANIFEST, klasor_hashleri
    MANIFEST.write_text(json.dumps(klasor_hashleri(HEDEF), indent=1), encoding="utf-8")
    print(len(html), "sayfa üretildi:", HEDEF)
    print("Hash manifesti:", MANIFEST)


if __name__ == "__main__":
    main()
