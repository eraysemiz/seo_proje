/* SEO Denetim Araci - arayuz mantigi
   Tarama sunucuda arka planda calisir; buradan duzenli araliklarla durumu sorup
   tabloyu, ozeti ve gunlugu guncelleriz. Taramadan once LM Studio ve model durumu
   "Başlamadan önce" listesinde gosterilir; eksik varsa baslat dugmesi nedenini soyler. */

"use strict";

const $ = (s) => document.querySelector(s);
const yarat = (etiket, sinif) => { const e = document.createElement(etiket); if (sinif) e.className = sinif; return e; };
const kacis = (m) => String(m === null || m === undefined ? "" : m)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const var_mi = (x) => x !== null && x !== undefined;

let sorguZamanlayici = null;
let aciklamalar = {};
let duzeltmeler = {};
let ozetImzasi = "";
let acikSatirlar = new Set();
let calisiyor = false;
let tabloImzasi = "";

// LM Studio ve model listesi durumu; hazirlik listesi bundan hesaplanir
const lm = { durum: "bekle", url: "", modeller: [] };

// ciddiyet anahtarlari CSS sinifi ve siralama icin ASCII kalir; ekranda Turkce adi gosterilir
const CIDDIYET_ADI = { yuksek: "yüksek", orta: "orta", dusuk: "düşük" };
const CIDDIYET_SINIF = { yuksek: "kotu", orta: "dikkat", dusuk: "" };
const CIDDIYET_SIRA = { yuksek: 0, orta: 1, dusuk: 2 };
// bulgu kategorileri tek yapilandirmadan gelir (kategoriler.py, /api/kategoriler); yuklenene kadar
// analiz akisindaki cozum yolundan yaklasik bir eslesme kullanilir
const KATEGORI_ADI = { kural: "Kural çözer", yz: "YZ önerir", elle: "Elle düzeltilir" };
const COZUM_YOLU_KATEGORI = { model: "yz", kural: "kural", elle: "elle" };
let kategoriler = {};
function kategoriEtiketi(kod, cozumYolu) {
  const k = (kategoriler[kod] && kategoriler[kod].kategori) || COZUM_YOLU_KATEGORI[cozumYolu];
  if (!k) return "";
  const risk = kategoriler[kod] && kategoriler[kod].risk === "yuksek" ? " · yüksek risk" : "";
  return ipucuHtml(KATEGORI_ADI[k] + risk, "cozum_" + k);
}

// Rapordaki puan ve etiket aciklamalari (bilgi balonlari). Metinler kodun gercek hesabina dayanir:
// puanlar -> puanlama.py (AGIRLIK, TAVAN, SAYFAYA_OZGU, TARAMA_CIDDIYETI) ve kurallar.puanlar / SORUN_TANIMI
// kategoriler -> kategoriler.py: KATEGORI, ETKI; yonetici modu: duzeltme.py, yonetici.py
const IPUCU = {
  puanlar: "Her sorun puanı kendi ağırlığı oranında düşürür: yüksek %20, orta %9, düşük %3,5 (aynı gruptaki sorunlar bir kez). " +
    "Puan = 100 × Π(1 − ağırlık). Kritik sorunlarda üst sınır vardır: noindex 60, robots engeli 50, yumuşak 404 40, kopya içerik 70, title yok 75. " +
    "Sayfa puanına o sayfaya ait site bulguları (kırık bağlantı, yönlendirme…) ve tarama geneli bulgular (tekrar eden title, kopya içerik, yetim sayfa) da girer; " +
    "HTTPS gibi site geneli sorunlar site puanında görünür. Yapılandırma: seo_app/puanlama.py.",
  sayfa: "Yalnız sayfanın HTML kodunda görülen sorunları ölçer. Toplam ceza, HTML'de görülebilecek en kötü durumun cezasına oranlanıp 100'den düşülür.",
  site: "Canlı erişimle ölçülen sorunları ölçer: robots.txt, sitemap, HTTPS, sertifika, hız. Toplam ceza, bu alandaki en kötü duruma oranlanıp 100'den düşülür.",
  icerik: "Başlık, meta açıklama, H1, alt metin, başlık sırası, metin miktarı ve terim uyumunu ölçer. Toplam ceza, en kötü duruma oranlanıp 100'den düşülür.",
  teknik: "Canonical, dil, viewport, yapısal veri, noindex/nofollow, yönlendirme, robots.txt, sitemap ve bağlantıları ölçer. Toplam ceza en kötü duruma oranlanıp 100'den düşülür.",
  guvenlik: "HTTPS kullanımı, https yönlendirmesi, SSL sertifikası, HSTS ve karışık içeriği ölçer. Toplam ceza, en kötü duruma oranlanıp 100'den düşülür.",
  performans: "Yanıt süresi, sıkıştırma, HTML boyutu, görseller ve (PageSpeed açıksa) Core Web Vitals ölçülür. Toplam ceza en kötü duruma oranlanıp 100'den düşülür.",
  cozum_kural: "Deterministik bir kuralla güvenle düzeltilir: eksik lang/charset/viewport, kırık iç bağlantı, görsellere width/height, robots.txt ve sitemap düzeltmeleri. Yönetici modunda grup olarak toplu onaylanabilir.",
  cozum_yz: "Yerel model (ya da sezgisel bir yöntem) öneri üretir: title/meta/H1, alt metni, içerik genişletme, JSON-LD, iç bağlantı. Her önerinin güven puanı vardır; eşiği (varsayılan 0,80) geçenler otomatik onaylı gelir, diğerleri ve [doğrulanmalı] yer tutuculu ya da indekslemeyi daraltan öneriler insan onayı ister. Canonical, noindex, yönlendirme ve hreflang gibi yapısal kararlar yüksek risklidir ve olası etkisiyle gösterilir. Model sitede olmayan bilgi uydurmaz; gerekirse [doğrulanmalı: …] yer tutucusu yazar.",
  cozum_elle: "Yapay zekânın kapsamı dışında: sunucu/barındırma ayarı, HTTPS ve sertifika, önbellek, gerçek görsel üretimi, firmaya özgü doğrulanmış bilgi, site dışı SEO. Yalnızca raporda öneri olarak kalır."
};
let ipucuSayaci = 0;
// klavyeyle odaklanabilen, ekran okuyucuya aria-describedby ile baglanan bilgi balonu
function ipucuHtml(etiket, anahtar) {
  if (!IPUCU[anahtar]) return kacis(etiket);
  const id = "ipucu-" + (++ipucuSayaci);
  return '<span class="ipucu-tetik" tabindex="0" aria-describedby="' + id + '">' + kacis(etiket) +
    '<span class="ipucu-balon" role="tooltip" id="' + id + '">' + kacis(IPUCU[anahtar]) + "</span></span>";
}

const IMGE = {
  tamam: '<svg class="imge" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="8" fill="currentColor"/><path d="M5.5 9.2l2.3 2.3 4.7-4.8" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  eksik: '<svg class="imge" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="8" fill="currentColor"/><path d="M6.2 6.2l5.6 5.6M11.8 6.2l-5.6 5.6" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>',
  uyari: '<svg class="imge" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="8" fill="currentColor"/><path d="M9 5v5" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/><circle cx="9" cy="12.8" r="1.1" fill="#fff"/></svg>',
  bekle: '<svg class="imge" viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="7.2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-dasharray="3 2.4"/></svg>',
  ok: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
};

/* ------------------------------------------------------------------ bicimleme */
const sayi = (x, ondalik = 0) => Number(x).toLocaleString("tr-TR",
  { minimumFractionDigits: ondalik, maximumFractionDigits: ondalik });
const yuzde = (oran) => (var_mi(oran) ? "%" + Math.round(oran * 100) : "—");
function sureYaz(sn) {
  if (!var_mi(sn)) return "—";
  if (sn < 60) return sayi(sn, sn < 10 ? 1 : 0) + " sn";
  return Math.floor(sn / 60) + " dk " + Math.round(sn % 60) + " sn";
}
// iyiYon: +1 puan gibi artmasi iyi olanlar, -1 sorun sayisi gibi azalmasi iyi olanlar
function farkHtml(fark, iyiYon) {
  if (!var_mi(fark) || Number.isNaN(fark)) return "";
  if (fark === 0) return '<span class="fark notr">±0</span>';
  const sinif = fark * iyiYon > 0 ? "iyi" : "kotu";
  return '<span class="fark ' + sinif + '">' + (fark > 0 ? "+" : "−") + sayi(Math.abs(fark)) + "</span>";
}
function onceSonra(once, sonra, iyiYon) {
  if (!var_mi(once)) return '<span class="once-deger">—</span>';
  return '<span class="once-deger">' + sayi(once) + '</span><span class="ok">→</span>' +
    '<span class="sonra-deger">' + (var_mi(sonra) ? sayi(sonra) : "—") + "</span>" +
    (var_mi(sonra) ? farkHtml(sonra - once, iyiYon) : "");
}
function olcekHtml(once, sonra) {
  if (!var_mi(once) || !var_mi(sonra)) return '<div class="olcek"></div>';
  const az = Math.min(once, sonra), cok = Math.max(once, sonra);
  return '<div class="olcek" aria-hidden="true">' +
    '<span class="aralik' + (sonra < once ? " dusus" : "") + '" style="left:' + az + "%;width:" + (cok - az) + '%"></span>' +
    '<span class="nokta o" style="left:' + once + '%"></span>' +
    '<span class="nokta s" style="left:' + sonra + '%"></span></div>';
}
function adresParcala(adres) {
  try {
    const u = new URL(adres);
    const yol = (u.pathname === "/" ? "" : u.pathname) + u.search;
    return { ana: u.hostname.replace(/^www\./, "") + yol, tam: adres };
  } catch (e) { return { ana: String(adres || ""), tam: adres }; }
}
function adresSayisi() {
  return $("#adresler").value.split("\n").map((s) => s.trim()).filter((s) => s && !s.startsWith("#")).length;
}
const yalnizcaDenetim = () => $("#yalnizca-denetim").checked;
const siteModu = () => $("#mod-site").checked;
const yoneticiModu = () => $("#mod-yonetici").checked;

/* ------------------------------------------------------------------ baslangic */
document.addEventListener("DOMContentLoaded", () => {
  $("#model-yenile").addEventListener("click", modelleriGetir);
  $("#kesif-dugmesi").addEventListener("click", kesfet);
  $("#basla").addEventListener("click", taramayiBaslat);
  $("#durdur").addEventListener("click", () => fetch("/api/durdur", { method: "POST" }));
  $("#adresler").addEventListener("input", hazirligiGuncelle);
  $("#model").addEventListener("change", hazirligiGuncelle);
  $("#embed-model").addEventListener("change", hazirligiGuncelle);
  $("#llm-url").addEventListener("change", modelleriGetir);
  $("#yalnizca-denetim").addEventListener("change", () => {
    $("#model-alanlari").classList.toggle("gizli", yalnizcaDenetim());
    hazirligiGuncelle();
  });
  document.querySelectorAll('input[name="tarama-modu"]').forEach((r) => r.addEventListener("change", () => {
    $("#site-ayarlari").classList.toggle("gizli", !siteModu());
    hazirligiGuncelle();
  }));
  $("#en-fazla-sayfa").addEventListener("input", hazirligiGuncelle);
  $("#en-fazla-derinlik").addEventListener("input", hazirligiGuncelle);
  document.querySelectorAll('input[name="calisma-modu"]').forEach((r) => r.addEventListener("change", () => {
    $("#yonetici-alanlari").classList.toggle("gizli", !yoneticiModu());
    // yonetici modunda baglanti grafigi (yetim/derin sayfa) icin site taramasi onerilir
    if (yoneticiModu() && !siteModu()) { $("#mod-site").checked = true; $("#site-ayarlari").classList.remove("gizli"); }
    hazirligiGuncelle();
  }));
  $("#yonetici-kok").addEventListener("input", hazirligiGuncelle);
  $("#yonetici-url").addEventListener("input", () => {
    if (!$("#adresler").value.trim()) $("#adresler").value = $("#yonetici-url").value.trim();
    hazirligiGuncelle();
  });
  $("#yonetici-uygula").addEventListener("click", yoneticiUygula);
  $("#yonetici-geri-al").addEventListener("click", yoneticiGeriAl);

  fetch("/api/kategoriler").then((r) => r.json()).then((d) => { kategoriler = d.kodlar || {}; tabloImzasi = ""; ozetImzasi = ""; });
  fetch("/api/aciklamalar").then((r) => r.json()).then((d) => { aciklamalar = d; tabloImzasi = ""; });
  fetch("/api/duzeltmeler").then((r) => r.json()).then((d) => { duzeltmeler = d; tabloImzasi = ""; ozetImzasi = ""; });
  modelleriGetir();
  durumuSor();           // sayfa yenilense bile suren tarama varsa yakala
});

/* --------------------------------------------------------------------- model */
function rozetYaz(durum, metin) {
  const rozet = $("#baglanti-rozeti");
  rozet.dataset.durum = durum;
  rozet.textContent = metin;
}

function modelleriGetir() {
  lm.durum = "bekle";
  lm.url = $("#llm-url").value.trim();
  lm.modeller = [];
  rozetYaz("sorgu", "LM Studio sorgulanıyor…");
  $("#model").disabled = true;
  $("#embed-model").disabled = true;
  $("#model-yenile").disabled = true;
  hazirligiGuncelle();

  fetch("/api/modeller?url=" + encodeURIComponent(lm.url))
    .then((r) => r.json())
    .then((d) => {
      const sohbet = $("#model"), gomme = $("#embed-model");
      const onceki = sohbet.value, oncekiGomme = gomme.value;
      sohbet.innerHTML = "";
      gomme.innerHTML = '<option value="">Yok: anahtar kelime eşleştirmesi</option>';
      if (d.hata || !d.modeller.length) {
        lm.durum = d.hata ? "kopuk" : "modelsiz";
        rozetYaz("kopuk", d.hata ? "LM Studio kapalı" : "LM Studio: model yok");
        sohbet.innerHTML = '<option value="">' + (d.hata ? "LM Studio'ya bağlanılamadı" : "Model bulunamadı") + "</option>";
        return;
      }
      lm.durum = "bagli";
      lm.modeller = d.modeller;
      // yuklu modeller once gelsin; yuklu olmayan secilirse tarama baslamaz
      const sirali = [...d.modeller].sort((a, b) => (b.yuklu === true) - (a.yuklu === true));
      sirali.forEach((m) => {
        const gommeMu = m.tur === "embeddings" || /embed/i.test(m.id);
        const se = yarat("option");
        se.value = m.id;
        se.textContent = m.id + (m.yuklu === false ? "  (yüklü değil)" : "");
        (gommeMu ? gomme : sohbet).appendChild(se);
      });
      if (!sohbet.options.length) sohbet.innerHTML = '<option value="">Sohbet modeli yok</option>';
      if ([...sohbet.options].some((o) => o.value === onceki)) sohbet.value = onceki;
      if ([...gomme.options].some((o) => o.value === oncekiGomme)) gomme.value = oncekiGomme;
      const yuklu = d.modeller.filter((m) => m.yuklu === true).length;
      const bilinmiyor = d.modeller.every((m) => m.yuklu === null);
      rozetYaz("bagli", "LM Studio: " + (bilinmiyor
        ? d.modeller.length + " model"
        : yuklu + " yüklü / " + d.modeller.length + " mevcut"));
    })
    .catch(() => { lm.durum = "kopuk"; rozetYaz("kopuk", "LM Studio kapalı"); })
    .finally(() => {
      $("#model").disabled = lm.durum !== "bagli";
      $("#embed-model").disabled = lm.durum !== "bagli";
      $("#model-yenile").disabled = false;
      hazirligiGuncelle();
    });
}

const modelBul = (id) => lm.modeller.find((m) => m.id === id);

/* Tarama oncesi neyin hazir oldugunu, neyin eksik oldugunu listeler. */
function hazirligiGuncelle() {
  const maddeler = [];
  const adet = adresSayisi();
  const yoneticiEksik = yoneticiModu() && (!$("#yonetici-kok").value.trim() || !$("#yonetici-url").value.trim());
  if (yoneticiModu()) {
    maddeler.push(yoneticiEksik
      ? { d: "eksik", bas: "Yönetici modu: hedef eksik", ac: "Site kök klasörünü ve temel adresi yazın." }
      : { d: "uyari", bas: "Yönetici modu: onaylanan düzeltmeler siteye yazılır",
          ac: $("#yonetici-kok").value.trim() + " · " + $("#yonetici-url").value.trim() });
  }
  maddeler.push(!adet
    ? { d: "eksik", bas: "Taranacak adres yok", ac: "Her satıra bir adres yazın ya da alt siteleri keşfedin." }
    : siteModu()
      ? { d: "tamam", bas: "Site taraması: en fazla " + ($("#en-fazla-sayfa").value || "?") + " sayfa",
          ac: adet + " başlangıç adresi; bağlantılar " + ($("#en-fazla-derinlik").value || "?") + " tıklama derinliğine kadar izlenir." }
      : { d: "tamam", bas: adet + " adres taranacak" });

  let uyari = null;
  if (yalnizcaDenetim()) {
    maddeler.push({ d: "tamam", bas: "Yalnızca denetim", ac: "Dil modeli kullanılmayacak; LM Studio gerekmez." });
  } else if (lm.durum === "bekle") {
    maddeler.push({ d: "bekle", bas: "LM Studio sorgulanıyor", ac: lm.url });
  } else if (lm.durum === "kopuk") {
    maddeler.push({ d: "eksik", bas: "LM Studio'ya ulaşılamadı", ac: lm.url });
    uyari = { hata: true, bas: "LM Studio'ya ulaşılamadı (" + lm.url + ")",
              ac: "LM Studio'yu açıp Developer sekmesinden sunucuyu başlatın, sonra “Modelleri getir”e basın." };
  } else if (lm.durum === "modelsiz") {
    maddeler.push({ d: "eksik", bas: "LM Studio'da model yok", ac: lm.url });
    uyari = { hata: true, bas: "LM Studio açık ama hiç model listelenmedi.", ac: "LM Studio'da bir model indirip yükleyin." };
  } else {
    maddeler.push({ d: "tamam", bas: "LM Studio bağlı", ac: lm.url });
  }

  if (yalnizcaDenetim()) {
    // model secimi gerekmez
  } else if (lm.durum === "bagli") {
    const secili = $("#model").value;
    const m = modelBul(secili);
    if (!secili) {
      maddeler.push({ d: "eksik", bas: "Sohbet modeli seçilmedi" });
    } else if (m && m.yuklu === false) {
      maddeler.push({ d: "eksik", bas: "Sohbet modeli yüklü değil", ac: secili });
      uyari = { bas: "Seçilen model LM Studio'da yüklü değil: " + secili,
                ac: "Modeli LM Studio'da yükleyip “Modelleri getir”e basın ya da yüklü bir model seçin." };
    } else {
      maddeler.push({ d: m && m.yuklu === null ? "uyari" : "tamam", bas: "Sohbet modeli: " + secili,
                      ac: m && m.yuklu === null ? "Yükleme durumu bu sunucudan okunamadı." : "" });
    }
    const gomme = $("#embed-model").value;
    const g = modelBul(gomme);
    if (!gomme) {
      maddeler.push({ d: "tamam", bas: "Gömme modeli yok", ac: "Bilgi tabanı anahtar kelimeyle seçilir." });
    } else if (g && g.yuklu === false) {
      maddeler.push({ d: "eksik", bas: "Gömme modeli yüklü değil", ac: gomme });
      uyari = uyari || { bas: "Seçilen gömme modeli LM Studio'da yüklü değil: " + gomme,
                         ac: "Modeli yükleyin ya da “Yok” seçeneğini seçin." };
    } else {
      maddeler.push({ d: "tamam", bas: "Gömme modeli: " + gomme });
    }
  } else {
    maddeler.push({ d: "bekle", bas: "Sohbet modeli", ac: "LM Studio'ya bağlanınca seçilebilir." });
  }

  $("#hazirlik-listesi").innerHTML = maddeler.map((x) =>
    '<li data-d="' + x.d + '">' + IMGE[x.d] + '<span><span class="bas">' + kacis(x.bas) + "</span>" +
    (x.ac ? '<span class="ac">' + kacis(x.ac) + "</span>" : "") + "</span></li>").join("");

  if (yalnizcaDenetim()) uyari = null;
  const kutu = $("#model-uyarisi");
  kutu.classList.toggle("gizli", !uyari);
  kutu.classList.toggle("hata-tonu", !!(uyari && uyari.hata));
  if (uyari) {
    kutu.innerHTML = IMGE.uyari.replace('class="imge"', "") + "<span><strong>" + kacis(uyari.bas) + "</strong>" +
      kacis(uyari.ac) + "</span>";
  }

  // adimlar sirasiyla tamamlandikca numarasi koyulasir
  const adimlar = document.querySelectorAll(".adim");
  const ilkModel = yoneticiModu() ? 2 : 1;        // hazirlik listesinde model maddelerinin basladigi yer
  const modelTamam = yalnizcaDenetim() || (lm.durum === "bagli" && !maddeler.slice(ilkModel).some((x) => x.d === "eksik"));
  adimlar[0].classList.toggle("tamam", !yoneticiEksik);
  adimlar[1].classList.toggle("tamam", adet > 0);
  adimlar[2].classList.toggle("tamam", modelTamam);
  adimlar[3].classList.toggle("tamam", adet > 0 && modelTamam && !yoneticiEksik);

  const engel = maddeler.find((x) => x.d === "eksik") || (lm.durum === "bekle" && !yalnizcaDenetim() ? maddeler[ilkModel] : null);
  const dugme = $("#basla");
  dugme.disabled = calisiyor || !!engel;
  dugme.textContent = calisiyor ? "Tarama sürüyor…" : "Taramayı başlat";
  dugme.title = engel && !calisiyor ? engel.bas : "";
}

/* --------------------------------------------------------------------- kesif */
function kesfet() {
  const kutu = $("#kesif-sonucu");
  kutu.classList.remove("gizli");
  if (!$("#kesif-adresi").value.trim()) { kutu.textContent = "Alt sitelerini keşfetmek istediğiniz sitenin adresini yazın."; return; }
  kutu.textContent = "Alt siteler aranıyor…";
  fetch("/api/kesif", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ adres: $("#kesif-adresi").value })
  })
    .then((r) => r.json())
    .then((d) => {
      kutu.innerHTML = "";
      if (d.hata) { kutu.textContent = "Keşif başarısız: " + d.hata; return; }
      if (!d.adresler.length) { kutu.textContent = "Alt site bulunamadı."; return; }
      const ust = yarat("div", "kesif-ust");
      ust.innerHTML = "<strong>" + d.adresler.length + " adres bulundu</strong>" +
        '<button class="dugme ikincil" type="button" id="kesif-ekle">Seçilenleri ekle</button>';
      kutu.appendChild(ust);
      d.adresler.forEach((a) => {
        const l = yarat("label");
        l.innerHTML = '<input type="checkbox" checked value="' + kacis(a.adres) + '">' +
          "<span>" + kacis(a.adres) +
          (a.baglanti_metni ? ' <span class="not">' + kacis(a.baglanti_metni) + "</span>" : "") + "</span>";
        kutu.appendChild(l);
      });
      $("#kesif-ekle").addEventListener("click", () => {
        const secili = [...kutu.querySelectorAll("input:checked")].map((i) => i.value);
        const mevcut = $("#adresler").value.split("\n").map((s) => s.trim()).filter(Boolean);
        $("#adresler").value = [...new Set(mevcut.concat(secili))].join("\n");
        kutu.classList.add("gizli");
        hazirligiGuncelle();
      });
    })
    .catch((e) => { kutu.textContent = "Keşif başarısız: " + e; });
}

/* -------------------------------------------------------------------- tarama */
function formHatasi(baslik, mesaj) {
  const hata = $("#form-hatasi");
  if (!mesaj) { hata.classList.add("gizli"); return; }
  hata.innerHTML = IMGE.eksik.replace('class="imge"', "") + "<span><strong>" + kacis(baslik) + "</strong>" +
    kacis(mesaj) + "</span>";
  hata.classList.remove("gizli");
}

function taramayiBaslat() {
  formHatasi();
  const govde = {
    adresler: $("#adresler").value,
    url: $("#llm-url").value,
    model: yalnizcaDenetim() ? "" : $("#model").value,
    embed_model: yalnizcaDenetim() ? "" : $("#embed-model").value,
    yalnizca_denetim: yalnizcaDenetim(),
    tarama_modu: siteModu() ? "site" : "liste",
    en_fazla_sayfa: $("#en-fazla-sayfa").value,
    en_fazla_derinlik: $("#en-fazla-derinlik").value,
    link_denetimi: $("#link-denetimi").checked,
    link_siniri: $("#link-siniri").value,
    js_render: $("#js-render").checked,
    sitemap_tohum: $("#sitemap-tohum").checked,
    ssl_zorunlu: $("#ssl-zorunlu").checked,
    retry: $("#retry").value,
    max_tokens: $("#max-tokens").value,
    uy_robots: $("#uy-robots").checked,
    bagimsiz_olcum: $("#bagimsiz-olcum").checked,
    bekleme_sn: $("#bekleme").value,
    zaman_asimi: $("#zaman-asimi").value,
    mod: yoneticiModu() ? "yonetici" : "standart",
    kok: yoneticiModu() ? $("#yonetici-kok").value.trim() : "",
    temel_url: yoneticiModu() ? $("#yonetici-url").value.trim() : "",
    oto_esik: yoneticiModu() ? $("#oto-esik").value : ""
  };
  yoneticiImzasi = "";
  $("#basla").disabled = true;
  fetch("/api/tara", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(govde)
  })
    .then((r) => r.json().then((d) => ({ ok: r.ok, durum: r.status, d })))
    .then(({ ok, durum, d }) => {
      if (!ok) {
        formHatasi("Tarama başlatılamadı", d.hata || "Bilinmeyen hata.");
        if (durum === 503) modelleriGetir();      // model/LM Studio sorunu: listeyi tazele
        else hazirligiGuncelle();
        return;
      }
      acikSatirlar = new Set();
      tabloImzasi = "";
      ozetImzasi = "";
      durumuSor();
    })
    .catch((e) => { formHatasi("Sunucuya ulaşılamadı", String(e)); hazirligiGuncelle(); });
}

function durumuSor() {
  fetch("/api/durum").then((r) => r.json()).then((d) => {
    ekraniCiz(d);
    clearTimeout(sorguZamanlayici);
    if (d.calisiyor) sorguZamanlayici = setTimeout(durumuSor, 1200);
  }).catch(() => { clearTimeout(sorguZamanlayici); });
}

/* --------------------------------------------------------------------- cizim */
function ekraniCiz(d) {
  calisiyor = d.calisiyor;
  // yonetici modunda "sonra" degerleri duzeltilmis kopyadan degil, siteye yazildiktan sonraki yeniden taramadan gelir
  yoneticiOzeti = d.mod === "yonetici" && d.yonetici && d.yonetici.ozet ? d.yonetici.ozet : null;
  hazirligiGuncelle();
  $(".hazirlik").classList.toggle("gizli", d.calisiyor);
  const sonuclar = d.sonuclar || [];
  const varlik = d.toplam || sonuclar.length;
  $("#durdur").classList.toggle("gizli", !d.calisiyor);
  $("#ilerleme-kutusu").classList.toggle("gizli", !d.toplam);
  $("#indirmeler").classList.toggle("gizli", !sonuclar.length);
  $("#bos-durum").classList.toggle("gizli", !!varlik);
  $("#tablo-paneli").classList.toggle("gizli", !varlik);

  if (d.toplam) ilerlemeyiCiz(d);
  bulguyuYaz(d, sonuclar);

  const gunluk = $("#gunluk");
  gunluk.textContent = (d.gunluk || []).join("\n");
  if ($("#gunluk-kutusu").open) gunluk.scrollTop = gunluk.scrollHeight;

  ozetiCiz(sonuclar);
  siteOzetiniGetir(sonuclar, d.calisiyor);
  tabloyuCiz(sonuclar, d.toplam || 0, d.calisiyor);
  yoneticiDurumu(d);
}

/* ------------------------------------------------------------- yonetici modu
   Tarama yonetici modunda bittiyse sunucu bir degisiklik plani uretir (siteye yazmaz). Panel:
   "Kural çözer" toplu onay kutusu; "YZ önerir" her oneri icin onay/ret ve duzenlenebilir deger;
   yuksek riskli onerilerde olasi etki ve ayrica risk onayi. Onaysiz hicbir degisiklik uygulanmaz. */
let yoneticiImzasi = "";
let yoneticiPlan = null;
let yoneticiOzeti = null;

function yoneticiDurumu(d) {
  const panel = $("#yonetici-paneli");
  const y = d.mod === "yonetici" ? d.yonetici : null;
  panel.classList.toggle("gizli", !y || y.asama === "taraniyor");
  if (!y || y.asama === "taraniyor") return;
  const imza = y.asama + "|" + (y.klasor || "") + "|" + d.calisiyor + "|" + JSON.stringify((y.ozet || {}).sayilar || {});
  if (imza === yoneticiImzasi) return;
  yoneticiImzasi = imza;
  const uyari = $("#yonetici-uyari");
  uyari.classList.add("gizli");
  if (y.asama === "hata") {
    uyari.textContent = "Yönetici modu hatası: " + (y.hata || "bilinmeyen hata");
    uyari.classList.remove("gizli");
    return;
  }
  if (y.asama === "uygulaniyor") {
    $("#yonetici-notu").textContent = "Onaylı aşama: kararlar yazılıyor, site yeniden taranıyor…";
    $("#yonetici-uygula").disabled = true;
    return;
  }
  fetch("/api/yonetici/plan").then((r) => r.json()).then((p) => { yoneticiPlan = p; yoneticiPaneliniCiz(p, y); })
    .catch((e) => { uyari.textContent = "Plan okunamadı: " + e; uyari.classList.remove("gizli"); });
}

const DURUM_ADI = { oneriliyor: "önerildi", uygulandi: "uygulandı", reddedildi: "reddedildi", basarisiz: "başarısız",
  onay_bekliyor: "onay verilmedi", gecersiz: "doğrulamadan geçmedi", geri_alindi: "geri alındı" };
const ASAMA_KISA = { otomatik: "otomatik aşamada", onayli: "onaylı aşamada" };

function guvenHtml(x) {
  if (x.guven === undefined || x.guven === null) return "";
  const oto = x.onay_turu === "otomatik";
  return '<span class="cip ' + (oto ? "iyi" : "dikkat") + '">güven ' + Number(x.guven).toFixed(2) +
    (oto ? " · otomatik onaylı" : " · onay gerekir") + "</span>" +
    (x.zorunlu_onay ? ' <span class="cip kotu">her zaman onay: ' + kacis(x.zorunlu_onay) + "</span>" : "");
}

function degisiklikHtml(x, duzenlenebilir, kilitli) {
  const yuksek = x.risk === "yuksek";
  const gecersiz = x.durum === "gecersiz";
  const oto = x.onay_turu === "otomatik";
  const isaretler = [guvenHtml(x), yuksek ? '<span class="cip kotu">yüksek risk</span>' : "",
    x.yer_tutucu ? '<span class="cip dikkat">yer tutucu: değer doldurulmadan uygulanamaz</span>' : "",
    gecersiz ? '<span class="cip kotu">doğrulamadan geçmedi: ' + kacis(x.dogrulama && x.dogrulama.neden) + "</span>" : "",
    x.durum && !["oneriliyor", "gecersiz"].includes(x.durum) ? '<span class="cip' + (x.durum === "uygulandi" ? " iyi" : "") + '">' +
      kacis(DURUM_ADI[x.durum] || x.durum) + (x.durum === "uygulandi" && x.asama ? " (" + ASAMA_KISA[x.asama] + ")" : "") +
      (x.durum_nedeni ? ": " + kacis(x.durum_nedeni) : "") + "</span>" : ""].join(" ");
  const uygulandi = x.durum === "uygulandi";
  let kontrol = "";
  if (!kilitli && !gecersiz) {
    if (x.kategori === "kural") {
      // her zaman onay isteyen kural duzeltmesi toplu onaya girmez; isaretsiz gelir, tek tek onaylanir
      const zorunlu = x.zorunlu_onay && !uygulandi;
      kontrol = '<label class="kutu"><input type="checkbox" class="kural-onay' + (zorunlu ? " zorunlu" : "") + '" data-id="' + x.id + '"' +
        (zorunlu ? "" : " checked") + "><span>" +
        (uygulandi ? "Uygulandı · işareti kaldırırsanız geri çekilir" : zorunlu ? "Onayla (tek tek)" : "Onayla") + "</span></label>";
    } else {
      // guven esigini gecen oneri onayli gelir; kullanici reddedebilir
      kontrol = '<span class="karar"><label class="kutu"><input type="radio" name="k-' + x.id + '" value="onay" data-id="' + x.id +
        '"' + (oto || uygulandi ? " checked" : "") + '><span>' + (uygulandi ? "Yerinde kalsın" : "Onayla") +
        '</span></label><label class="kutu"><input type="radio" name="k-' + x.id +
        '" value="ret" data-id="' + x.id + '"><span>' + (uygulandi ? "Reddet (geri çek)" : "Reddet") + "</span></label></span>" +
        (yuksek ? '<label class="kutu risk-onay"><input type="checkbox" class="risk-onay-kutu" data-id="' + x.id + '"' +
          (oto ? " checked" : "") + '><span>Olası etkiyi okudum, bu yüksek riskli değişikliği onaylıyorum</span></label>' : "");
    }
  }
  const duzen = duzenlenebilir && !kilitli && !gecersiz
    ? '<label class="duzen-etiketi" for="d-' + x.id + '">Önerilen değer (düzenleyebilirsiniz)</label><textarea id="d-' + x.id +
      '" class="duzen" data-id="' + x.id + '" rows="' + Math.min(10, 1 + Math.ceil(String(x.yeni).length / 90)) + '">' + kacis(x.yeni) + "</textarea>"
    : "";
  return '<li class="degisiklik' + (yuksek ? " yuksek-risk" : "") + '"><div class="degisiklik-ust"><strong>' + x.id + "</strong> " +
    kacis(x.bulgu_aciklamasi) + ' <span class="ayr">' + kacis(x.dosya) + " · " + kacis(x.uretici) + "</span> " + isaretler + "</div>" +
    '<p class="gerekce">' + kacis(x.gerekce) + "</p>" +
    (!oto && x.guven_nedenleri && x.guven_nedenleri.length
      ? '<p class="ayr">Düşük güven nedeni: ' + x.guven_nedenleri.map(kacis).join("; ") + "</p>" : "") +
    (yuksek && x.etki ? '<p class="etki"><strong>Olası etki:</strong> ' + kacis(x.etki) + "</p>" : "") +
    (x.kaynaklar && x.kaynaklar.length ? '<p class="ayr">Kaynak: ' + x.kaynaklar.map((k) => kacis(k.id + (k.baslik ? " " + k.baslik : ""))).join(", ") + "</p>" : "") +
    duzen + "<details><summary>Değişiklik (diff)</summary><pre class=\"diff\">" + kacis(x.diff || "") + "</pre></details>" +
    (kontrol ? '<div class="degisiklik-kontrol">' + kontrol + "</div>" : "") + "</li>";
}

function yoneticiPaneliniCiz(p, y) {
  const kilitli = p.asama !== "plan_hazir";
  const s = p.sayilar;
  $("#yonetici-notu").textContent = s.kural + " kural · " + s.yz + " YZ önerisi (" + s.yuksek_risk + " yüksek risk) · " +
    p.elle.length + " elle yapılacak iş" + (p.model ? " · model " + p.model : " · model seçilmedi") +
    (p.esik !== undefined && p.esik !== null ? " · güven eşiği " + Number(p.esik).toFixed(2) + ": " + s.otomatik +
      " otomatik onaylı, " + s.onay_gerekli + " onay bekliyor" : "") + " · " + p.klasor;
  let h = "";
  const oz = p.ozet;
  if (oz && oz.asamalar.length > 1) h += asamaTablosuHtml(oz);
  if (y.asama === "geri_alindi") h += '<div class="yonetici-sonuc">Uygulama geri alındı (otomatik ve onaylı tüm aşamalar); site uygulama öncesi haline döndü, durumlar başlangıca döndü.</div>';
  const kural = p.gruplar.kural;
  h += '<h3>' + ipucuHtml(KATEGORI_ADI.kural, "cozum_kural") + " (" + kural.length + ")</h3>";
  if (!kilitli && kural.some((x) => x.durum !== "gecersiz")) {
    h += '<label class="kutu toplu"><input type="checkbox" id="kural-hepsi" checked><span>Kural çözer grubunun tamamını onayla</span></label>';
  }
  h += '<ul class="degisiklik-listesi">' + kural.map((x) => degisiklikHtml(x, false, kilitli)).join("") + "</ul>";
  const yz = p.gruplar.yz;
  h += '<h3>' + ipucuHtml(KATEGORI_ADI.yz, "cozum_yz") + " (" + yz.length + ")</h3>" +
    (kilitli ? "" : '<p class="not">Güven eşiğini geçen öneriler tarama sonunda onay beklemeden uygulandı; istemediğinizi ' +
      "reddedin, onaylı aşamada geri çekilir. Diğerlerini tek tek onaylayın, düzenleyin ya da reddedin. Karar verilmeyen öneri uygulanmaz.</p>") +
    '<ul class="degisiklik-listesi">' + yz.map((x) => degisiklikHtml(x, x.duzenlenebilir, kilitli)).join("") + "</ul>";
  h += '<h3>' + ipucuHtml(KATEGORI_ADI.elle, "cozum_elle") + " (" + p.elle.length + ")</h3><ul class=\"elle-listesi\">" +
    p.elle.map((e) => "<li>" + kacis(e.bulgu_aciklamasi) + ' <span class="ayr">' + e.sayfalar.length + " sayfa</span>" +
      (e.duzeltme ? '<span class="duzeltme">' + kacis(e.duzeltme) + "</span>" : "") + "</li>").join("") + "</ul>";
  if (p.atlanan.length) {
    h += '<details class="reddedilen"><summary>Otomatik öneri üretilemeyenler (' + p.atlanan.length + ")</summary><ul>" +
      p.atlanan.map((a) => "<li>" + kacis(a.bulgu_aciklamasi) + ' <span class="ayr">' + kacis(a.url) + " — " + kacis(a.neden) + "</span></li>").join("") +
      "</ul></details>";
  }
  $("#yonetici-icerik").innerHTML = h;
  $("#yonetici-uygula").classList.toggle("gizli", kilitli);
  $("#yonetici-uygula").disabled = kilitli;
  $("#yonetici-uygula").textContent = s.uygulandi ? "Onaylı aşamayı uygula" : "Onaylananları uygula";
  $("#yonetici-geri-al").classList.toggle("gizli", !(y.asama === "tamam" || (y.asama === "plan_hazir" && s.uygulandi)));
  $("#yonetici-rapor").classList.toggle("gizli", !["plan_hazir", "tamam", "geri_alindi"].includes(y.asama));
  const hepsi = $("#kural-hepsi");
  if (hepsi) hepsi.addEventListener("change", () => document.querySelectorAll(".kural-onay:not(.zorunlu)").forEach((k) => { k.checked = hepsi.checked; }));
}

function asamaTablosuHtml(oz) {
  const as = oz.asamalar;
  const sutun = (f) => as.map((a) => "<td>" + (a.olculdu ? f(a) : "—") + "</td>").join("");
  const durumlar = Object.entries(oz.sayilar).filter(([, n]) => n)
    .map(([d, n]) => '<span class="cip ' + (BULGU_DURUM_SINIF[d] || "") + '">' + kacis(BULGU_DURUM_ADI[d] || d) + " " + n + "</span>").join(" ");
  return '<div class="yonetici-sonuc"><strong>Aşamalara göre metrikler</strong><div class="tablo-kap"><table class="asama-tablosu"><thead><tr><th></th>' +
    as.map((a) => "<th>" + kacis(a.adi) + "</th>").join("") + "</tr></thead><tbody>" +
    "<tr><th>Ortalama sayfa puanı</th>" + sutun((a) => sayi(a.puanlar.sayfa)) + "</tr>" +
    "<tr><th>Sorun sayısı</th>" + sutun((a) => sayi(a.bulgu_sayisi)) + "</tr>" +
    '<tr><th title="' + kacis(oz.tanim) + '">Çözüm oranı ⓘ</th>' +
      sutun((a) => (a.cozum_orani === null ? "—" : yuzde(a.cozum_orani)) + " (" + a.cozulen + "/" + a.cozulebilir + ")") + "</tr>" +
    "<tr><th>Elle düzeltilir (açık)</th>" + sutun((a) => sayi(a.elle)) + "</tr>" +
    "<tr><th>Yeni çıkan sorun</th>" + sutun((a) => sayi(a.yeni_bulgu)) + "</tr>" +
    "</tbody></table></div><p>Sorun durumları (" + oz.toplam + "): " + durumlar + '</p><p class="not">' + kacis(oz.tanim) + "</p></div>";
}

function yoneticiKararlari() {
  const kararlar = {};
  const kuralKutulari = [...document.querySelectorAll(".kural-onay")];
  const toplu = kuralKutulari.filter((k) => !k.classList.contains("zorunlu"));
  const hepsi = toplu.length > 0 && toplu.every((k) => k.checked) && $("#kural-hepsi") && $("#kural-hepsi").checked;
  kuralKutulari.forEach((k) => {
    // isaretsiz zorunlu onayli oneri reddedilmis sayilmaz, onay bekler
    if (k.checked || !k.classList.contains("zorunlu")) kararlar[k.dataset.id] = { karar: k.checked ? "onay" : "ret" };
  });
  document.querySelectorAll('.karar input[type="radio"]:checked').forEach((r) => { kararlar[r.dataset.id] = { karar: r.value }; });
  document.querySelectorAll(".risk-onay-kutu:checked").forEach((k) => { if (kararlar[k.dataset.id]) kararlar[k.dataset.id].risk_onay = true; });
  document.querySelectorAll("textarea.duzen").forEach((t) => {
    const oneri = (yoneticiPlan.gruplar.yz.find((x) => x.id === t.dataset.id) || {}).yeni;
    if (kararlar[t.dataset.id] && kararlar[t.dataset.id].karar === "onay" && t.value !== oneri) kararlar[t.dataset.id].deger = t.value;
  });
  return { kural_hepsi: hepsi, kararlar };
}

function yoneticiUygula() {
  const k = yoneticiKararlari();
  const onay = Object.values(k.kararlar).filter((x) => x.karar === "onay");
  // otomatik onayli yuksek riskli oneride risk guven puaniyla karsilanmistir; ayrica risk onayi istenmez
  const riskEksik = yoneticiPlan.gruplar.yz.filter((x) => x.risk === "yuksek" && x.onay_turu !== "otomatik" && k.kararlar[x.id] &&
    k.kararlar[x.id].karar === "onay" && !k.kararlar[x.id].risk_onay).map((x) => x.id);
  const uyari = $("#yonetici-uyari");
  if (riskEksik.length) {
    uyari.textContent = "Yüksek riskli öneriler için risk onayı kutusunu işaretleyin: " + riskEksik.join(", ");
    uyari.classList.remove("gizli");
    return;
  }
  // yeni yazilacaklar: henuz uygulanmamis onaylilar; geri cekilecekler: uygulanmisken reddedilenler
  const tum = [...yoneticiPlan.gruplar.kural, ...yoneticiPlan.gruplar.yz];
  const yeni = tum.filter((x) => x.durum !== "uygulandi" && x.durum !== "gecersiz" && (k.kararlar[x.id] || {}).karar === "onay").length;
  const geri = tum.filter((x) => x.durum === "uygulandi" && (k.kararlar[x.id] || {}).karar === "ret").length;
  const metin = (yeni || geri)
    ? yeni + " değişiklik siteye yazılacak" + (geri ? ", " + geri + " otomatik değişiklik geri çekilecek" : "") +
      ". İlk yazmadan önce sitenin tam yedeği alınmıştır/alınır. Devam edilsin mi?"
    : "Yeni yazılacak değişiklik yok; onaylı aşama kaydedilecek ve rapor güncellenecek. Devam edilsin mi?";
  if (!onay.length && !geri && !yoneticiPlan.sayilar.uygulandi) {
    uyari.textContent = "Onaylanan değişiklik yok."; uyari.classList.remove("gizli"); return;
  }
  if (!window.confirm(metin)) return;
  uyari.classList.add("gizli");
  fetch("/api/yonetici/uygula", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kararlar: k }) })
    .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
    .then(({ ok, d }) => {
      if (!ok) { uyari.textContent = d.hata || "Uygulama başlatılamadı."; uyari.classList.remove("gizli"); return; }
      yoneticiImzasi = "";
      durumuSor();
    });
}

function yoneticiGeriAl() {
  if (!window.confirm("Otomatik ve onaylı tüm aşamalarda yazılan değişiklikler yedekten geri alınacak. Devam edilsin mi?")) return;
  fetch("/api/yonetici/geri-al", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
    .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
    .then(({ ok, d }) => {
      const uyari = $("#yonetici-uyari");
      uyari.textContent = ok ? (d.eslesiyor ? "Geri alındı: tüm dosyaların hash'i yedekle eşleşiyor." : "Geri alındı ama dosya hash'leri eşleşmiyor!")
        : (d.hata || "Geri alınamadı.");
      uyari.classList.remove("gizli");
      yoneticiImzasi = "";
      durumuSor();
    });
}

/* Site ozeti: en cok sayfayi etkileyen sorunlar ve nasil duzeltilecegi; tarama geneli bulgular.
   Sunucuda hesaplanir (kurallar.site_ozeti); her yeni sayfa ve tarama sonunda bir kez istenir. */
function siteOzetiniGetir(sonuclar, suruyor) {
  const imza = sonuclar.length + "|" + suruyor;
  if (imza === ozetImzasi) return;
  ozetImzasi = imza;
  const panel = $("#site-ozeti-paneli");
  if (!gecerliKayitlar(sonuclar).length) { panel.classList.add("gizli"); return; }
  fetch("/api/ozet").then((r) => r.json()).then((d) => siteOzetiniCiz(d, suruyor)).catch(() => {});
}

function ciddiyetCipi(c) {
  if (c === "bilgi") return '<span class="cip">bilgi</span>';
  return '<span class="cip ' + (CIDDIYET_SINIF[c] || "") + '">' + (CIDDIYET_ADI[c] || c) + "</span>";
}

function siteOzetiniCiz(d, suruyor) {
  const panel = $("#site-ozeti-paneli");
  const ozet = d.ozet || [];
  panel.classList.toggle("gizli", !ozet.length);
  if (!ozet.length) return;
  const ilk = ozet.slice(0, 12);
  $("#site-ozeti-notu").textContent = ozet.length + " farklı sorun" + (suruyor ? " · tarama sürüyor" : "") +
    (ozet.length > ilk.length ? " · en etkili " + ilk.length + " tanesi" : "");
  let h = '<table class="ozet-tablosu"><thead><tr><th>Önem</th><th>Sorun ve nasıl düzeltilir</th>' +
    '<th class="sayi">Sayfa</th><th class="gizle-dar">Çözüm</th></tr></thead><tbody>' +
    ilk.map((s) => "<tr><td>" + ciddiyetCipi(s.ciddiyet) + "</td><td>" + kacis(s.aciklama) +
      (s.duzeltme ? '<span class="duzeltme">' + kacis(s.duzeltme) + "</span>" : "") + "</td>" +
      '<td class="sayi">' + s.sayfa_sayisi + '</td><td class="gizle-dar">' +
      kategoriEtiketi(s.sorun, s.cozum_yolu) +
      "</td></tr>").join("") + "</tbody></table>";
  if (ozet.length > ilk.length) {
    h += '<details class="reddedilen"><summary>Diğer sorunlar (' + (ozet.length - ilk.length) + ")</summary><ul>" +
      ozet.slice(ilk.length).map((s) => "<li>" + ciddiyetCipi(s.ciddiyet) + " " + kacis(s.aciklama) +
        ' <span class="ayr">' + s.sayfa_sayisi + " sayfa</span></li>").join("") + "</ul></details>";
  }
  (d.bulgular || []).forEach((g) => {
    h += '<details class="reddedilen"><summary>' + kacis(aciklamalar[g.sorun] || g.sorun) +
      ' <span class="ayr">(' + kacis(g.deger) + ")</span></summary>" +
      (duzeltmeler[g.sorun] ? '<p class="duzeltme">' + kacis(duzeltmeler[g.sorun]) + "</p>" : "") +
      '<ul class="adres-listesi">' + g.sayfalar.slice(0, 30).map((a) => "<li>" + kacis(a) + "</li>").join("") +
      (g.sayfalar.length > 30 ? "<li>… " + (g.sayfalar.length - 30) + " adres daha</li>" : "") + "</ul></details>";
  });
  $("#site-ozeti").innerHTML = h;
}

function ilerlemeyiCiz(d) {
  const oran = Math.round((d.biten / d.toplam) * 100);
  $("#ilerleme-dolgu").style.width = oran + "%";
  $("#ilerleme-cubugu").setAttribute("aria-valuenow", oran);
  const sure = d.baslangic ? Math.round((d.bitis || Date.now() / 1000) - d.baslangic) : 0;
  const durum = d.calisiyor ? "Taranıyor" : d.hata ? "Hatayla durdu" : d.biten < d.toplam ? "Durduruldu" : "Tamamlandı";
  $("#ilerleme-metni").textContent = durum + ": " + d.biten + " / " + d.toplam + " sayfa · " + sureYaz(sure);
  $("#ilerleme-yol").textContent = d.cikti_klasoru ? "Çıktı: " + d.cikti_klasoru : "";
  const simdi = $("#ilerleme-simdi");
  simdi.style.color = d.hata ? "var(--kotu)" : "";
  if (d.hata) simdi.textContent = "Beklenmeyen hata: " + d.hata;
  else if (d.calisiyor && d.gunluk && d.gunluk.length) simdi.textContent = d.gunluk[d.gunluk.length - 1].replace(/^\S+\s+/, "");
  else simdi.textContent = "";
}

const gecerliKayitlar = (sonuclar) => sonuclar.filter((k) => !k.hata && !k.atlandi && var_mi(k.once_puan));
const ortalama = (dizi) => (dizi.length ? Math.round(dizi.reduce((a, b) => a + b, 0) / dizi.length) : null);
const puanlari = (kayitlar, an, kap) =>
  kayitlar.map((k) => (k[an + "_puanlar"] || {})[kap]).filter(var_mi);

function bulguyuYaz(d, sonuclar) {
  const p = $("#bulgu");
  const gecerli = gecerliKayitlar(sonuclar);
  const hatali = sonuclar.length - gecerli.length;
  if (!gecerli.length) {
    p.textContent = d.calisiyor ? "Tarama sürüyor; ilk sayfanın sonucu bekleniyor."
      : sonuclar.length ? "Hiçbir sayfa analiz edilemedi; ayrıntı tabloda."
      : "Henüz tarama yapılmadı. Yukarıdaki formu doldurup taramayı başlatın.";
    return;
  }
  const o = ortalama(puanlari(gecerli, "once", "sayfa"));
  const ek = hatali ? ' <span class="ikincil-bilgi">' + hatali + " adres taranamadı.</span>" : "";
  if (yoneticiOzeti && yoneticiOzeti.sayaclar && var_mi(yoneticiOzeti.sayaclar.toplam)) {
    // yonetici modu: sayaclar bulgu durumlarindan (HTML/JSON raporla ayni kaynak)
    const c = yoneticiOzeti.sayaclar, son = [...yoneticiOzeti.asamalar].reverse().find((a) => a.olculdu) || {};
    p.innerHTML = gecerli.length + " sayfa analiz edildi. Ortalama sayfa puanı " + sayi(o) + " → " +
      sayi((son.puanlar || {}).sayfa) + ". " + sayi(c.toplam) + " sorundan " + sayi(c.aktif) + " aktif" +
      (c.sayfa ? " (" + sayi(c.sayfa.aktif) + " sayfa sorunu, " + sayi(c.site_ayari.aktif) + " site geneli ayar)" : "") + ", " +
      sayi(c.cozulen) + " çözüldü (" + sayi(c.cozuldu_otomatik) + " otomatik, " + sayi(c.cozuldu_onayli) + " onaylı)." + ek;
    return;
  }
  const s = ortalama(puanlari(gecerli, "sonra", "sayfa"));
  const so = gecerli.reduce((t, k) => t + (k.once_sorun_sayisi || 0), 0);
  const ss = gecerli.reduce((t, k) => t + (k.sonra_sorun_sayisi || 0), 0);
  p.innerHTML = gecerli.length + " sayfa analiz edildi. Ortalama sayfa puanı " + sayi(o) + " → " + sayi(s) +
    ", toplam sorun " + sayi(so) + " → " + sayi(ss) + "." + ek;
}

function asamaHucresi(asamalar, alan, bicim) {
  return asamalar.map((a) => (a.olculdu ? bicim(a[alan], a) : "—")).join(" → ");
}

function yoneticiOzetiniCiz(kutu, oz) {
  const as = oz.asamalar.filter((a) => a.ad !== "geri_alma" || oz.geri_alindi);
  const son = [...as].reverse().find((a) => a.olculdu) || as[0];
  const hucre = (etiket, deger, alt, ana, ipucu) => '<div class="hucre' + (ana ? " ana" : "") + '"' +
    (ipucu ? ' title="' + kacis(ipucu) + '"' : "") + '><div class="etiket">' + etiket + '</div><div class="deger">' + deger +
    "</div>" + (alt ? '<div class="alt-satir">' + alt + "</div>" : "") + "</div>";
  const adlar = as.map((a) => kacis(a.adi.replace(" düzeltmeler sonrası", ""))).join(" → ");
  const durumlar = Object.entries(oz.sayilar).filter(([, n]) => n).map(([d, n]) => kacis(BULGU_DURUM_ADI[d] || d) + " " + n).join(" · ");
  kutu.innerHTML =
    hucre("Ortalama sayfa puanı", asamaHucresi(as, "puanlar", (p) => sayi(p.sayfa)), adlar, true) +
    hucre("Aktif sorun", asamaHucresi(as, "aktif", sayi), (son.cozuldu_otomatik ?? 0) + " otomatik + " +
      (son.cozuldu_onayli ?? 0) + " onaylı çözüldü · " + (son.yeni_bulgu ?? 0) + " yeni çıktı") +
    hucre("Çözüm oranı ⓘ", son.cozum_orani === null || son.cozum_orani === undefined ? "—" : yuzde(son.cozum_orani),
      (son.cozulen ?? 0) + " / " + (son.cozulebilir ?? 0) + " çözülebilir · elle " + (son.elle ?? 0), false, oz.tanim) +
    hucre("Sorun durumları", sayi(oz.toplam), durumlar);
}

function ozetiCiz(sonuclar) {
  const kutu = $("#ozet");
  const gecerli = gecerliKayitlar(sonuclar);
  if (!gecerli.length) { kutu.classList.add("gizli"); return; }
  kutu.classList.remove("gizli");
  if (yoneticiOzeti && yoneticiOzeti.asamalar.length) { yoneticiOzetiniCiz(kutu, yoneticiOzeti); return; }
  const toplamOnce = gecerli.reduce((t, k) => t + (k.once_sorun_sayisi || 0), 0);
  const toplamSonra = gecerli.reduce((t, k) => t + (k.sonra_sorun_sayisi || 0), 0);
  const cozulen = gecerli.reduce((t, k) => t + (k.cozulen_sorunlar || []).length, 0);
  const yeni = gecerli.reduce((t, k) => t + (k.yeni_cikan_sorunlar || []).length, 0);
  const oranlar = gecerli.map((k) => k.toplam_cozum_orani).filter(var_mi);
  const ortOran = oranlar.length ? oranlar.reduce((a, b) => a + b, 0) / oranlar.length : null;
  const hatali = sonuclar.length - gecerli.length;
  const siteOrt = ortalama(puanlari(gecerli, "once", "site"));

  const hucre = (etiket, deger, alt, ana) => '<div class="hucre' + (ana ? " ana" : "") + '">' +
    '<div class="etiket">' + etiket + '</div><div class="deger">' + deger + "</div>" +
    (alt ? '<div class="alt-satir">' + alt + "</div>" : "") + "</div>";
  kutu.innerHTML =
    hucre("Ortalama sayfa puanı", onceSonra(ortalama(puanlari(gecerli, "once", "sayfa")),
      ortalama(puanlari(gecerli, "sonra", "sayfa")), 1), "100 üzerinden; düzeltmeden önce ve sonra", true) +
    hucre("Sorun", onceSonra(toplamOnce, toplamSonra, -1), cozulen + " çözüldü · " + yeni + " yeni çıktı") +
    hucre("Çözüm oranı", ortOran === null ? "—" : yuzde(ortOran), "ortalama, tüm sorunlarda") +
    hucre("Site puanı", var_mi(siteOrt) ? sayi(siteOrt) : "—", "ortalama; robots, HTTPS") +
    hucre("Sayfa", sayi(gecerli.length), hatali ? hatali + " adres taranamadı" : "hepsi analiz edildi");
}

function tabloyuCiz(sonuclar, toplam, suruyor) {
  // veri degismediyse tabloyu yeniden kurma: acik satirlar ve odak korunur
  const imza = sonuclar.length + "|" + toplam + "|" + suruyor + "|" + Object.keys(aciklamalar).length + "|" +
    (yoneticiOzeti ? JSON.stringify(yoneticiOzeti.sayilar) + JSON.stringify(yoneticiOzeti.sayaclar) +
      yoneticiOzeti.asamalar.length + String(yoneticiOzeti.geri_alindi) : "");
  if (imza === tabloImzasi) return;
  tabloImzasi = imza;

  const tablo = $("#sonuc-tablosu");
  const govde = tablo.querySelector("tbody");
  const gecerli = gecerliKayitlar(sonuclar);
  const bekleyen = suruyor ? Math.max(0, toplam - sonuclar.length) : 0;
  tablo.classList.toggle("gizli", !sonuclar.length && !bekleyen);
  $("#tablo-notu").textContent = suruyor
    ? sonuclar.length + " / " + toplam + " sayfa hazır"
    : gecerli.length + " sayfa" + (sonuclar.length > gecerli.length ? ", " + (sonuclar.length - gecerli.length) + " hatalı" : "");
  govde.innerHTML = "";

  sonuclar.forEach((k, i) => {
    const ad = adresParcala(k.ad);
    const adHucre = '<td class="sayfa-adi" title="' + kacis(ad.tam) + '"><span class="ana-ad">' + kacis(ad.ana) + "</span>" +
      (k.title ? '<span class="yol-ad">' + kacis(k.title) + "</span>" : "") + "</td>";
    if (k.hata || k.atlandi) {
      const satir = yarat("tr", "hata-satiri");
      satir.innerHTML = adHucre + '<td colspan="5" class="hata-mesaj"><span class="cip ' + (k.hata ? "kotu" : "") + '">' +
        (k.hata ? "Hata" : "Atlandı") + "</span> " + kacis(k.atlandi || k.hata) + "</td><td></td>";
      govde.appendChild(satir);
      return;
    }
    let po = k.once_puanlar || {};
    let ps = k.sonra_puanlar || {}, onceSorun = k.once_sorun_sayisi, sonraSorun = k.sonra_sorun_sayisi, oran = k.cozum_orani;
    if (yoneticiOzeti) {
      // yonetici modu: baslangictaki sorun → aktif sorun, puan ve oran sayfa sayaclarindan
      const g = (yoneticiOzeti.sayfalar || {})[k.ad] || {};
      po = Object.assign({}, po, { sayfa: g.puan_once ?? po.sayfa });
      ps = { sayfa: g.puan_guncel };
      onceSorun = g.toplam;
      sonraSorun = g.aktif;
      oran = g.cozum_orani;
    }
    const satir = yarat("tr", "ana");
    satir.innerHTML = adHucre +
      '<td class="puan-hucre"><div class="puan">' + olcekHtml(po.sayfa, ps.sayfa) +
        '<span class="puan-metin">' + onceSonra(po.sayfa, ps.sayfa, 1) + "</span></div></td>" +
      '<td class="sayi" data-sayac="sorun">' + onceSonra(onceSorun, sonraSorun, -1) + "</td>" +
      '<td class="sayi gizle-dar">' + (var_mi(po.site) ? sayi(po.site) : "—") + "</td>" +
      '<td class="sayi">' + yuzde(oran) + "</td>" +
      '<td class="sayi">' + sureYaz(k.sure_toplam_sn) + "</td>" +
      '<td class="mobil-ozet">Sorun ' + (var_mi(onceSorun) ? onceSorun + " → " + (sonraSorun ?? "—") : "—") +
        " · Çözüm " + yuzde(oran) + " · " + sureYaz(k.sure_toplam_sn) + "</td>" +
      '<td class="ac-kapa"><button type="button" aria-expanded="false" aria-label="' +
        kacis(ad.ana) + ' ayrıntısını aç">' + IMGE.ok + "</button></td>";
    govde.appendChild(satir);

    const ayrintiSatiri = yarat("tr", "ayrinti-satiri");
    const hucre = yarat("td");
    hucre.colSpan = 7;
    hucre.innerHTML = ayrintiHtml(k);
    ayrintiSatiri.appendChild(hucre);
    govde.appendChild(ayrintiSatiri);

    const dugme = satir.querySelector("button");
    const uygula = (acik) => {
      ayrintiSatiri.style.display = acik ? "" : "none";
      satir.classList.toggle("acik", acik);
      dugme.setAttribute("aria-expanded", acik);
    };
    uygula(acikSatirlar.has(i));
    satir.addEventListener("click", () => {
      const acik = !acikSatirlar.has(i);
      if (acik) acikSatirlar.add(i); else acikSatirlar.delete(i);
      uygula(acik);
    });
  });

  for (let j = 0; j < Math.min(bekleyen, 6); j++) {
    const satir = yarat("tr", "bekleyen");
    satir.innerHTML = '<td class="sayfa-adi"><span class="iskelet" style="width:' + (62 - j * 6) + '%"></span>' +
      '<span class="yol-ad">' + (j === 0 ? "taranıyor…" : "sırada") + "</span></td>" +
      '<td class="puan-hucre"><span class="iskelet" style="width:150px"></span></td>' +
      '<td class="sayi"><span class="iskelet" style="width:56px;margin-left:auto"></span></td>' +
      '<td class="sayi gizle-dar"><span class="iskelet" style="width:24px;margin-left:auto"></span></td>' +
      '<td class="sayi"><span class="iskelet" style="width:36px;margin-left:auto"></span></td>' +
      '<td class="sayi"><span class="iskelet" style="width:40px;margin-left:auto"></span></td><td></td>';
    govde.appendChild(satir);
  }
}

/* ------------------------------------------------------------------- ayrinti */
const BULGU_DURUM_ADI = { cozuldu_otomatik: "Çözüldü (otomatik)", cozuldu_onayli: "Çözüldü (onaylı)",
  onay_bekliyor: "Onay bekliyor", reddedildi: "Reddedildi", basarisiz: "Başarısız",
  dogrulanmadi: "Uygulandı, yeniden kontrol yapılmadı", elle: "Elle düzeltilir" };
const BULGU_DURUM_SINIF = { cozuldu_otomatik: "iyi", cozuldu_onayli: "iyi", basarisiz: "kotu", onay_bekliyor: "dikkat",
  dogrulanmadi: "dikkat" };

// yonetici modu: sayfanin bulgulari (sorun kodu → durum), bulgu durumlarindan
function sayfaBulgulari(url) {
  const sonuc = {};
  Object.entries(yoneticiOzeti.durumlar).forEach(([a, b]) => {
    const i = a.indexOf("|");
    if (a.slice(i + 1) === url) sonuc[a.slice(0, i)] = b;
  });
  return sonuc;
}

function takmaNotu(t, n) {
  return t.tur === "gecersiz"
    ? "Bu adres geçersiz bir sayfa (" + (aciklamalar[t.asil_sorun] || t.asil_sorun) + "); içerikle ilgili " + n + " bulgusu bu tek sorunun altında sayılır."
    : "Bu adres " + t.asil_url + " sayfasının " + (t.tur === "yonlendirme" ? "yönlendirmesi" : "parametreli adresi") +
      "; aynı dosyaya ait " + n + " bulgusu asıl sayfada bir kez sayılır ve onunla birlikte çözülür.";
}

function durumCipi(kod, url) {
  const b = yoneticiOzeti && url ? yoneticiOzeti.durumlar[kod + "|" + url] : null;
  if (!b) return "";
  // cozulen bulgu: nasil cozuldugu (uygulanan degisiklik ozeti, guven, onay kaynagi)
  const cozum = (b.cozum || []).map((c) => '<span class="ayr">' + kacis(c.id + ": " + c.ozet) +
    (var_mi(c.guven) ? " · güven " + Number(c.guven).toFixed(2) : "") +
    (c.onay_kaynagi ? " · onay: " + kacis(c.onay_kaynagi) : "") + "</span>").join("");
  const takma = (b.takma_adresler || []).length ? '<span class="ayr">Ayrıca görüldüğü adresler (bir kez sayılır): ' +
    b.takma_adresler.map((t) => kacis(t.url)).join(", ") + "</span>" : "";
  return ' <span class="cip ' + (BULGU_DURUM_SINIF[b.durum] || "") + '" title="' + kacis(b.neden) + '">' +
    kacis(b.durum_adi) + "</span>" + cozum + takma;
}

function sorunMaddesi(kod, sorunlar, url) {
  const s = sorunlar[kod] || { sorun: kod };
  const meta = [s.katman && kacis(s.katman),
    kategoriEtiketi(kod, s.cozum_yolu),
    s.ayrinti && kacis(s.ayrinti)].filter(Boolean).join(" · ");
  const cip = s.ciddiyet ? '<span class="cip ' + (CIDDIYET_SINIF[s.ciddiyet] || "") + '">' +
    (CIDDIYET_ADI[s.ciddiyet] || s.ciddiyet) + "</span>" : "<span></span>";
  return "<li>" + cip + "<span>" + kacis(aciklamalar[kod] || kod) + durumCipi(kod, url) +
    (meta ? '<span class="ayr">' + meta + "</span>" : "") +
    (duzeltmeler[kod] ? '<span class="duzeltme">' + kacis(duzeltmeler[kod]) + "</span>" : "") + "</span></li>";
}

function defterSutunu(sinif, baslik, kodlar, sorunlar, bosMetin, url) {
  const sirali = [...kodlar].sort((a, b) =>
    (CIDDIYET_SIRA[(sorunlar[a] || {}).ciddiyet] ?? 3) - (CIDDIYET_SIRA[(sorunlar[b] || {}).ciddiyet] ?? 3));
  return '<div class="defter-sutun ' + sinif + '"><h5><span class="adet">' + kodlar.length + "</span>" + baslik + "</h5>" +
    (kodlar.length ? "<ul>" + sirali.map((kod) => sorunMaddesi(kod, sorunlar, url)).join("") + "</ul>"
      : '<p class="bos">' + bosMetin + "</p>") + "</div>";
}

// dogrulayicinin ret kodlarini okunur cumleye cevirir; tanimadigi kodu oldugu gibi gosterir
function retNedeni(kod) {
  const m = String(kod || "");
  let r;
  if ((r = m.match(/^title_uzunluk_(\d+)$/))) return "Başlık " + r[1] + " karakter; izin verilen aralığın dışında";
  if ((r = m.match(/^meta_uzunluk_(\d+)$/))) return "Açıklama " + r[1] + " karakter; izin verilen aralığın dışında";
  if ((r = m.match(/^sayfada_olmayan_ifade:\s*(.*)$/))) return "Sayfada geçmeyen ifade: " + r[1];
  return m;
}

function ayrintiHtml(k) {
  let h = '<div class="ayrinti">';
  const sorunlar = {};
  (k.sorunlar || []).forEach((s) => { sorunlar[s.sorun] = s; });

  // sorun defteri: neyin cozuldugu, neyin kaldigi, neyin yeni ciktigi yan yana
  if (yoneticiOzeti) {
    // yonetici modu: aktif ve cozulen sorunlar ayri; cozuldu yalnizca yeniden kontrolle dogrulanmissa
    // site geneli ayarlar (HTTPS, guvenlik basliklari…) sayfada sayilmaz; bir kez, site ozetinde gosterilir
    const bs = sayfaBulgulari(k.ad);
    // takma adres (yonlendirme, parametre) ya da gecersiz sayfa bulgusu asil bulguda bir kez sayilir
    const sayfaKodlari = Object.keys(bs).filter((kod) => !bs[kod].site_ayari && !bs[kod].takma);
    const takma = Object.keys(bs).filter((kod) => bs[kod].takma);
    const aktif = sayfaKodlari.filter((kod) => bs[kod].aktif !== false);
    const cozulen = sayfaKodlari.filter((kod) => bs[kod].aktif === false);
    const siteAcik = Object.keys(bs).filter((kod) => bs[kod].site_ayari && bs[kod].aktif !== false);
    h += '<div class="bolum"><h4>Sorunlar ve güncel durumları <span class="sayac">' + aktif.length + " aktif · " +
      cozulen.length + ' çözüldü</span></h4><div class="defter">' +
      defterSutunu("kaldi", "aktif sorun", aktif, sorunlar, "Aktif sorun yok.", k.ad) +
      defterSutunu("cozuldu", "çözülen sorun", cozulen, sorunlar, "Bu sayfada henüz çözülen sorun yok.", k.ad) +
      "</div>" + (takma.length ? '<p class="not">' + kacis(takmaNotu(bs[takma[0]].takma, takma.length)) + "</p>" : "") +
      (siteAcik.length ? '<p class="not">Ayrıca ' + siteAcik.length + " site geneli ayar bu sayfayı da etkiliyor: " +
        siteAcik.map((x) => kacis(aciklamalar[x] || x)).join(", ") + ". Bir kez sayılır; ayrıntı site özetinde.</p>" : "");
  } else if (Array.isArray(k.cozulen_sorunlar) || Array.isArray(k.kalan_sorunlar)) {
    h += '<div class="bolum"><h4>Sorunlar <span class="sayac">önce ' + (k.once_sorun_sayisi ?? 0) +
      ", sonra " + (k.sonra_sorun_sayisi ?? 0) + '</span></h4><div class="defter">' +
      defterSutunu("cozuldu", "çözüldü", k.cozulen_sorunlar || [], sorunlar, "Bu sayfada çözülen sorun yok.") +
      defterSutunu("kaldi", "kaldı", k.kalan_sorunlar || [], sorunlar, "Kalan sorun yok.") +
      defterSutunu("yeni", "yeni çıktı", k.yeni_cikan_sorunlar || [], sorunlar, "Düzeltme yeni sorun çıkarmadı.") +
      "</div>";
  } else {
    h += '<div class="bolum"><h4>Tespit edilen sorunlar <span class="sayac">' + (k.once_sorun_sayisi || 0) +
      '</span></h4><div class="defter">' + defterSutunu("kaldi", "sorun", Object.keys(sorunlar), sorunlar, "Sorun bulunamadı.") + "</div>";
  }
  if (k.tekrar_bulgulari && k.tekrar_bulgulari.length) {
    h += '<p class="not">Tarama geneli bulgular: ' +
      k.tekrar_bulgulari.map((x) => kacis(aciklamalar[x] || x)).join(", ") + ". Puana katılmaz; ayrıntı site özetinde.</p>";
  }
  h += "</div>";

  if (k.once_puanlar) {
    const etiketler = { sayfa: "Sayfa", site: "Site", icerik: "İçerik", teknik: "Teknik",
                        guvenlik: "Güvenlik", performans: "Performans" };
    h += '<div class="bolum"><h4>' + ipucuHtml("Puanlar", "puanlar") + ' <span class="sayac">önce → sonra</span></h4><div class="kategoriler">' +
      Object.keys(etiketler).map((kap) => {
        const o = k.once_puanlar[kap], s = (k.sonra_puanlar || {})[kap];
        return '<div class="kategori"><span class="ad">' + ipucuHtml(etiketler[kap], kap) + "</span>" +
          (var_mi(o) ? olcekHtml(o, var_mi(s) ? s : o) + '<span class="puan-metin">' + onceSonra(o, s, 1) + "</span>"
            : '<span></span><span class="olculmedi">ölçülmedi</span>') + "</div>";
      }).join("") + "</div></div>";
  }

  if ((k.fixes && k.fixes.length) || (k.reddedilen && k.reddedilen.length)) {
    h += '<div class="bolum"><h4>Modelin önerileri <span class="sayac">' + (k.fixes || []).length + " kabul, " +
      (k.reddedilen || []).length + " ret</span></h4>";
    // modelin dayandigi bilgi tabani parcalari; kimlik, kaynagina baglanti olarak gosterilir
    const parcaBul = {};
    (k.ogretme_parcalar || []).forEach((p) => { parcaBul[p.id] = p; });
    const kaynakCipi = (id) => {
      const p = parcaBul[id] || {};
      const ipucu = [p.baslik, p.kaynak_basligi].filter(Boolean).join(" — ");
      return p.kaynak
        ? '<a class="kaynak-cip" href="' + kacis(p.kaynak) + '" target="_blank" rel="noopener" title="' + kacis(ipucu) + '">' + kacis(id) + "</a>"
        : '<span class="kaynak-cip">' + kacis(id) + "</span>";
    };
    if (k.fixes && k.fixes.length) {
      h += '<table class="oneri-tablosu"><tbody>' + k.fixes.map((f) =>
        "<tr><td>" + kacis(f.alan) + (f.hedef ? " / " + kacis(f.hedef) : "") + "</td>" +
        "<td>" + kacis(f.yeni_deger) + (f.gerekce ? '<span class="gerekce">' + kacis(f.gerekce) + "</span>" : "") +
        ((f.kaynaklar || []).length ? '<span class="kaynak-satiri">Dayandığı yönerge: ' + f.kaynaklar.map(kaynakCipi).join(" ") + "</span>" : "") +
        "</td></tr>"
      ).join("") + "</tbody></table>";
    }
    if (k.reddedilen && k.reddedilen.length) {
      h += '<details class="reddedilen"><summary>Reddedilen öneriler (' + k.reddedilen.length + ")</summary><ul>" +
        k.reddedilen.map((r) => "<li><strong>" + kacis(retNedeni(r.neden)) + "</strong>" +
          '<span class="ayr">' + kacis(((r.oneri && (r.oneri.alan + ": " + r.oneri.yeni_deger)) || "").slice(0, 180)) +
          "</span></li>").join("") + "</ul></details>";
    }
    if ((k.ogretme_parcalar || []).length) {
      h += '<details class="reddedilen"><summary>Modele verilen bilgi parçaları (' + k.ogretme_parcalar.length + ")</summary><ul>" +
        k.ogretme_parcalar.map((p) => "<li>" + kaynakCipi(p.id) + " <strong>" + kacis(p.baslik || "") + "</strong>" +
          '<span class="ayr">' + kacis([p.alan, p.kaynak_basligi].filter(Boolean).join(" · ")) + "</span></li>").join("") +
        "</ul></details>";
    }
    h += "</div>";
  }

  if (k.kural_duzeltmeleri && k.kural_duzeltmeleri.length) {
    h += '<div class="bolum"><h4>Kural tabanlı düzeltmeler <span class="sayac">' + k.kural_duzeltmeleri.length +
      '</span></h4><ul class="basit-liste">' + k.kural_duzeltmeleri.map((x) => "<li>" + kacis(x) + "</li>").join("") + "</ul></div>";
  }

  const sb = k.site_bilgi;
  if (sb && !sb.hata) {
    const s = sb.sertifika || {};
    const r = sb.robots || {};
    const sm = sb.sitemap || {};
    const alan = (etiket, deger, kotu) => '<div><span class="etiket">' + etiket + "</span>" +
      (kotu ? '<span class="kotu-deger">' + kacis(deger) + "</span>" : kacis(deger)) + "</div>";
    const sertKotu = s.veren && (s.zincir_eksik || (var_mi(s.kalan_gun) && s.kalan_gun < 30));
    h += '<div class="bolum"><h4>Canlı erişim ölçümleri</h4><div class="olcumler">' +
      alan("Durum kodu", sb.durum_kodu, sb.durum_kodu >= 400) +
      alan("Yanıt süresi (TTFB)", var_mi(sb.ttfb_ms) ? sayi(sb.ttfb_ms) + " ms" : "—") +
      alan("İndirme", (var_mi(sb.toplam_ms) ? sayi(sb.toplam_ms) + " ms" : "—") + " · " + (var_mi(sb.boyut_kb) ? sayi(sb.boyut_kb) + " KB" : "—")) +
      alan("Sıkıştırma", sb.sikistirma || "yok", !sb.sikistirma) +
      alan("HSTS", sb.hsts ? "var" : "yok", !sb.hsts) +
      alan("Sertifika", s.veren ? (s.kalan_gun + " gün kaldı" + (s.zincir_eksik ? ", zincir eksik" : "")) : "—", sertKotu) +
      alan("robots.txt", r.var ? (r.satir_sayisi + " satır, " + (r.sitemapler || []).length + " sitemap") : "yok", !r.var) +
      alan("sitemap", sm.var ? (sm.tur + ", " + sayi(sm.url_sayisi) + " adres") : "yok", !sm.var) +
      (var_mi(sb.sitemapte) ? alan("Sayfa sitemap'te", sb.sitemapte ? "evet" : "hayır") : "") +
      ((sb.yonlendirme_zinciri || []).length ? alan("Yönlendirme", sb.yonlendirme_zinciri.length + " adım") : "") +
      "</div></div>";
  }
  const zincir = (k.site_bilgi || {}).yonlendirme_zinciri || [];
  if (zincir.length) {
    h += '<div class="bolum"><h4>Yönlendirme zinciri</h4><ul class="basit-liste">' +
      zincir.map((z) => "<li>" + kacis(z) + "</li>").join("") +
      (k.site_url ? "<li>200 " + kacis(k.site_url) + "</li>" : "") + "</ul></div>";
  }

  // baglantilar, tarama konumu ve Core Web Vitals
  const bo = k.baglanti_ozeti, bd = k.baglanti_denetimi;
  const lhO = (k.lighthouse || {}).once || {};
  const cwv = lhO.cwv;
  if (bo || var_mi(k.derinlik) || cwv || k.render) {
    const olc = (etiket, deger, kotu) => '<div><span class="etiket">' + etiket + "</span>" +
      (kotu ? '<span class="kotu-deger">' + kacis(deger) + "</span>" : kacis(deger)) + "</div>";
    let ic = "";
    if (bo) ic += olc("Bağlantılar", bo.ic + " site içi · " + bo.dis + " dış" + (bo.nofollow ? " · " + bo.nofollow + " nofollow" : ""));
    if (bd) ic += olc("Kırık bağlantı", (bd.kirik_ic.length + bd.kirik_dis.length) + " (" + bd.denetlenen + " adres denetlendi)",
                      bd.kirik_ic.length + bd.kirik_dis.length > 0);
    if (var_mi(k.derinlik)) ic += olc("Tıklama derinliği", k.derinlik);
    if (var_mi(k.gelen_baglanti)) ic += olc("Gelen site içi bağlantı", k.gelen_baglanti, k.gelen_baglanti === 0 && k.derinlik !== 0);
    if (k.kesif_kaynagi && k.kesif_kaynagi !== "başlangıç") ic += olc("Bulunduğu yer", k.kesif_kaynagi);
    if (k.render) ic += olc("Render", k.render.hata ? "yapılamadı" : sayi(k.render.ham_kelime) + " → " + sayi(k.render.render_kelime) + " kelime", !!k.render.hata);
    if (cwv) {
      const ms = (x) => (var_mi(x) ? sayi(Math.round(x)) + " ms" : "—");
      ic += olc("LCP", var_mi(cwv.lcp_ms) ? sayi(cwv.lcp_ms / 1000, 1) + " sn" : "—", cwv.lcp_ms > 2500) +
        olc(var_mi(cwv.inp_ms) ? "INP" : "TBT (INP yerine)", var_mi(cwv.inp_ms) ? ms(cwv.inp_ms) : ms(cwv.tbt_ms),
            var_mi(cwv.inp_ms) ? cwv.inp_ms > 200 : cwv.tbt_ms > 200) +
        olc("CLS", var_mi(cwv.cls) ? sayi(cwv.cls, 2) : "—", cwv.cls > 0.1) +
        (var_mi(lhO.performans_puani) ? olc("Performans puanı", lhO.performans_puani, lhO.performans_puani < 50) : "");
    }
    h += '<div class="bolum"><h4>Bağlantılar ve performans' + (cwv ? ' <span class="sayac">' + kacis(cwv.kaynak) + "</span>" : "") +
      '</h4><div class="olcumler">' + ic + "</div>";
    if (bd && (bd.kirik_ic.length || bd.kirik_dis.length || bd.kirik_gorsel.length)) {
      h += '<details class="reddedilen"><summary>Kırık adresler</summary><ul class="adres-listesi">' +
        bd.kirik_ic.concat(bd.kirik_dis, bd.kirik_gorsel).map((a) => "<li>" + kacis(a) + "</li>").join("") + "</ul></details>";
    }
    h += "</div>";
  }

  const parcalar = [];
  if (k.yalnizca_denetim) parcalar.push("<strong>Yalnızca denetim</strong> (dil modeli kullanılmadı)");
  if (k.model) parcalar.push("Model <strong>" + kacis(k.model) + "</strong>");
  if (k.kosul) parcalar.push("koşul <strong>" + kacis(k.kosul) + (k.ogretme_yontemi ? " / " + kacis(k.ogretme_yontemi) : "") + "</strong>");
  if (var_mi(k.sure_sn)) parcalar.push("model süresi <strong>" + sureYaz(k.sure_sn) + "</strong>");
  if (k.denemeler) parcalar.push("<strong>" + k.denemeler.length + "</strong> deneme");
  const lh = k.lighthouse && k.lighthouse.once;
  if (lh && var_mi(lh.seo_puani)) parcalar.push("Lighthouse SEO (mobil, önce) <strong>" + lh.seo_puani + "</strong>");
  if (k.duzeltilmis_dosya) parcalar.push("düzeltilmiş sayfa <strong>" + kacis(k.duzeltilmis_dosya) + "</strong>");
  if (parcalar.length) h += '<p class="model-satiri">' + parcalar.join(" · ") + "</p>";
  return h + "</div>";
}

/* ------------------------------------------------------------- bilgi balonlari
   Fare ile uzerine gelince, klavyeyle odaklaninca ve dokununca acilir. Balon ekrana gore
   (position: fixed) konumlanir ve kenarlara 8 px kala durdurulur; Esc ile kapanir. */
function ipucuKonumla(tetik) {
  const balon = tetik.querySelector(".ipucu-balon");
  if (!balon) return;
  const r = tetik.getBoundingClientRect();
  const w = balon.offsetWidth, h = balon.offsetHeight;
  const x = Math.min(Math.max(8, r.left), innerWidth - w - 8);
  let y = r.bottom + 6;
  if (y + h > innerHeight - 8) y = Math.max(8, r.top - h - 6);
  balon.style.left = x + "px";
  balon.style.top = y + "px";
}
const acikIpuclari = () => document.querySelectorAll(".ipucu-tetik.acik, .ipucu-tetik:hover, .ipucu-tetik:focus");
document.addEventListener("mouseover", (e) => { const t = e.target.closest(".ipucu-tetik"); if (t) ipucuKonumla(t); });
document.addEventListener("focusin", (e) => { const t = e.target.closest(".ipucu-tetik"); if (t) ipucuKonumla(t); });
document.addEventListener("focusout", (e) => { const t = e.target.closest(".ipucu-tetik"); if (t) t.classList.remove("acik", "kapali"); });
document.addEventListener("mouseout", (e) => {
  const t = e.target.closest(".ipucu-tetik");
  if (t && !t.contains(e.relatedTarget)) t.classList.remove("kapali");
});
document.addEventListener("click", (e) => {
  const t = e.target.closest(".ipucu-tetik");
  document.querySelectorAll(".ipucu-tetik.acik").forEach((x) => { if (x !== t) x.classList.remove("acik"); });
  if (t) { t.classList.remove("kapali"); t.classList.toggle("acik"); ipucuKonumla(t); }
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  acikIpuclari().forEach((t) => { t.classList.remove("acik"); t.classList.add("kapali"); });
});
["scroll", "resize"].forEach((olay) => window.addEventListener(olay, () => acikIpuclari().forEach(ipucuKonumla), true));
