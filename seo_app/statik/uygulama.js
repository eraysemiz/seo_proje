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
let acikSatirlar = new Set();
let calisiyor = false;
let tabloImzasi = "";

// LM Studio ve model listesi durumu; hazirlik listesi bundan hesaplanir
const lm = { durum: "bekle", url: "", modeller: [] };

// ciddiyet anahtarlari CSS sinifi ve siralama icin ASCII kalir; ekranda Turkce adi gosterilir
const CIDDIYET_ADI = { yuksek: "yüksek", orta: "orta", dusuk: "düşük" };
const CIDDIYET_SINIF = { yuksek: "kotu", orta: "dikkat", dusuk: "" };
const CIDDIYET_SIRA = { yuksek: 0, orta: 1, dusuk: 2 };
const COZUM_ADI = { model: "model çözer", kural: "kural çözer", elle: "elle düzeltilir" };

// Rapordaki puan ve etiket aciklamalari (bilgi balonlari). Metinler kodun gercek hesabina dayanir:
// puanlar -> kurallar.py: puanlar / _normal_puan / _azami_ceza / SORUN_TANIMI / CIDDIYET_AGIRLIK
// cozum yollari -> kurallar.py: cozum_yolu, KURAL_SORUNLARI, ALAN_SORUN; uygula.py: kural_duzelt, apply_fixes
const IPUCU = {
  puanlar: "Sorunlar ciddiyete göre ceza alır: yüksek 15, orta 8, düşük 3. Toplam ceza olası en kötü cezaya bölünür; puan 100 × (1 − oran).",
  sayfa: "Yalnız sayfanın HTML kodunda görülen sorunları ölçer. Toplam ceza, HTML'de görülebilecek en kötü durumun cezasına oranlanıp 100'den düşülür.",
  site: "Canlı erişimle ölçülen sorunları ölçer: robots.txt, sitemap, HTTPS, sertifika, hız. Toplam ceza, bu alandaki en kötü duruma oranlanıp 100'den düşülür.",
  icerik: "Başlık, meta açıklama, H1, alt metin, başlık sırası, metin miktarı ve terim uyumunu ölçer. Toplam ceza, en kötü duruma oranlanıp 100'den düşülür.",
  teknik: "Canonical, dil, viewport, yapısal veri, paylaşım etiketleri, noindex, robots.txt, sitemap ve erişimi ölçer. Toplam ceza, en kötü duruma oranlanıp 100'den düşülür.",
  guvenlik: "HTTPS kullanımı, https yönlendirmesi, SSL sertifikası, HSTS ve karışık içeriği ölçer. Toplam ceza, en kötü duruma oranlanıp 100'den düşülür.",
  performans: "Sunucu yanıt süresi (TTFB), sıkıştırma, HTML boyutu ve dış kaynak sayısını ölçer. Toplam ceza, en kötü duruma oranlanıp 100'den düşülür.",
  cozum_model: "Dil modeli yeni metin önerir (title, meta açıklama, H1, görsel alt metni); doğrulamadan geçen öneriler düzeltilmiş HTML'e yazılır.",
  cozum_kural: "Araç bunu dil modeli olmadan, sabit bir kuralla düzeltilmiş HTML'de giderir: canonical, lang, viewport, Open Graph eklenir; fazla H1'ler H2 yapılır.",
  cozum_elle: "Araç bunu düzeltmez; site sahibinin sunucuda veya sayfa kodunda kendisinin değiştirmesi gerekir (ör. robots.txt, sitemap, HTTPS, sertifika, yapısal veri)."
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

  fetch("/api/aciklamalar").then((r) => r.json()).then((d) => { aciklamalar = d; tabloImzasi = ""; });
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
  maddeler.push(adet
    ? { d: "tamam", bas: adet + " adres taranacak" }
    : { d: "eksik", bas: "Taranacak adres yok", ac: "Her satıra bir adres yazın ya da alt siteleri keşfedin." });

  let uyari = null;
  if (lm.durum === "bekle") {
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

  if (lm.durum === "bagli") {
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

  const kutu = $("#model-uyarisi");
  kutu.classList.toggle("gizli", !uyari);
  kutu.classList.toggle("hata-tonu", !!(uyari && uyari.hata));
  if (uyari) {
    kutu.innerHTML = IMGE.uyari.replace('class="imge"', "") + "<span><strong>" + kacis(uyari.bas) + "</strong>" +
      kacis(uyari.ac) + "</span>";
  }

  // adimlar sirasiyla tamamlandikca numarasi koyulasir
  const adimlar = document.querySelectorAll(".adim");
  const modelTamam = lm.durum === "bagli" && !maddeler.slice(1).some((x) => x.d === "eksik");
  adimlar[0].classList.toggle("tamam", adet > 0);
  adimlar[1].classList.toggle("tamam", modelTamam);
  adimlar[2].classList.toggle("tamam", adet > 0 && modelTamam);

  const engel = maddeler.find((x) => x.d === "eksik") || (lm.durum === "bekle" ? maddeler[1] : null);
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
    model: $("#model").value,
    embed_model: $("#embed-model").value,
    retry: $("#retry").value,
    max_tokens: $("#max-tokens").value,
    uy_robots: $("#uy-robots").checked,
    bagimsiz_olcum: $("#bagimsiz-olcum").checked,
    bekleme_sn: $("#bekleme").value,
    zaman_asimi: $("#zaman-asimi").value
  };
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
  tabloyuCiz(sonuclar, d.toplam || 0, d.calisiyor);
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
  const o = ortalama(puanlari(gecerli, "once", "sayfa")), s = ortalama(puanlari(gecerli, "sonra", "sayfa"));
  const so = gecerli.reduce((t, k) => t + (k.once_sorun_sayisi || 0), 0);
  const ss = gecerli.reduce((t, k) => t + (k.sonra_sorun_sayisi || 0), 0);
  p.innerHTML = gecerli.length + " sayfa analiz edildi. Ortalama sayfa puanı " + sayi(o) + " → " + sayi(s) +
    ", toplam sorun " + sayi(so) + " → " + sayi(ss) + "." +
    (hatali ? ' <span class="ikincil-bilgi">' + hatali + " adres taranamadı.</span>" : "");
}

function ozetiCiz(sonuclar) {
  const kutu = $("#ozet");
  const gecerli = gecerliKayitlar(sonuclar);
  if (!gecerli.length) { kutu.classList.add("gizli"); return; }
  kutu.classList.remove("gizli");
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
  const imza = sonuclar.length + "|" + toplam + "|" + suruyor + "|" + Object.keys(aciklamalar).length;
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
    const po = k.once_puanlar || {}, ps = k.sonra_puanlar || {};
    const satir = yarat("tr", "ana");
    satir.innerHTML = adHucre +
      '<td class="puan-hucre"><div class="puan">' + olcekHtml(po.sayfa, ps.sayfa) +
        '<span class="puan-metin">' + onceSonra(po.sayfa, ps.sayfa, 1) + "</span></div></td>" +
      '<td class="sayi">' + onceSonra(k.once_sorun_sayisi, k.sonra_sorun_sayisi, -1) + "</td>" +
      '<td class="sayi gizle-dar">' + (var_mi(po.site) ? sayi(po.site) : "—") + "</td>" +
      '<td class="sayi">' + yuzde(k.cozum_orani) + "</td>" +
      '<td class="sayi">' + sureYaz(k.sure_toplam_sn) + "</td>" +
      '<td class="mobil-ozet">Sorun ' + (var_mi(k.once_sorun_sayisi) ? k.once_sorun_sayisi + " → " + k.sonra_sorun_sayisi : "—") +
        " · Model çözümü " + yuzde(k.cozum_orani) + " · " + sureYaz(k.sure_toplam_sn) + "</td>" +
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
function sorunMaddesi(kod, sorunlar) {
  const s = sorunlar[kod] || { sorun: kod };
  const meta = [s.katman && kacis(s.katman),
    s.cozum_yolu && ipucuHtml(COZUM_ADI[s.cozum_yolu] || s.cozum_yolu, "cozum_" + s.cozum_yolu),
    s.ayrinti && kacis(s.ayrinti)].filter(Boolean).join(" · ");
  const cip = s.ciddiyet ? '<span class="cip ' + (CIDDIYET_SINIF[s.ciddiyet] || "") + '">' +
    (CIDDIYET_ADI[s.ciddiyet] || s.ciddiyet) + "</span>" : "<span></span>";
  return "<li>" + cip + "<span>" + kacis(aciklamalar[kod] || kod) +
    (meta ? '<span class="ayr">' + meta + "</span>" : "") + "</span></li>";
}

function defterSutunu(sinif, baslik, kodlar, sorunlar, bosMetin) {
  const sirali = [...kodlar].sort((a, b) =>
    (CIDDIYET_SIRA[(sorunlar[a] || {}).ciddiyet] ?? 3) - (CIDDIYET_SIRA[(sorunlar[b] || {}).ciddiyet] ?? 3));
  return '<div class="defter-sutun ' + sinif + '"><h5><span class="adet">' + kodlar.length + "</span>" + baslik + "</h5>" +
    (kodlar.length ? "<ul>" + sirali.map((kod) => sorunMaddesi(kod, sorunlar)).join("") + "</ul>"
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
  if (Array.isArray(k.cozulen_sorunlar) || Array.isArray(k.kalan_sorunlar)) {
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
    h += '<p class="not">Tarama genelinde başka sayfalarla aynı: ' +
      k.tekrar_bulgulari.map((x) => kacis(aciklamalar[x] || x)).join(", ") + ". Puana katılmaz.</p>";
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
    if (k.fixes && k.fixes.length) {
      h += '<table class="oneri-tablosu"><tbody>' + k.fixes.map((f) =>
        "<tr><td>" + kacis(f.alan) + (f.hedef ? " / " + kacis(f.hedef) : "") + "</td>" +
        "<td>" + kacis(f.yeni_deger) + (f.gerekce ? '<span class="gerekce">' + kacis(f.gerekce) + "</span>" : "") + "</td></tr>"
      ).join("") + "</tbody></table>";
    }
    if (k.reddedilen && k.reddedilen.length) {
      h += '<details class="reddedilen"><summary>Reddedilen öneriler (' + k.reddedilen.length + ")</summary><ul>" +
        k.reddedilen.map((r) => "<li><strong>" + kacis(retNedeni(r.neden)) + "</strong>" +
          '<span class="ayr">' + kacis(((r.oneri && (r.oneri.alan + ": " + r.oneri.yeni_deger)) || "").slice(0, 180)) +
          "</span></li>").join("") + "</ul></details>";
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
      "</div></div>";
  }

  const parcalar = [];
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
