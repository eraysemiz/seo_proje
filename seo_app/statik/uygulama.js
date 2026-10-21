/* SEO Denetim Araci - arayuz mantigi
   Tarama sunucuda arka planda calisir; buradan duzenli araliklarla durumu sorup
   tabloyu, ozeti ve gunlugu guncelleriz. */

"use strict";

const $ = (s) => document.querySelector(s);
const yarat = (etiket, sinif) => { const e = document.createElement(etiket); if (sinif) e.className = sinif; return e; };
const kacis = (m) => String(m === null || m === undefined ? "" : m)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

let mod = "canli";
let sorguZamanlayici = null;
let aciklamalar = {};
let acikSatirlar = new Set();

const KOSUL_ACIKLAMA = {
  "sifir": "Modele ek bilgi verilmez. Karsilastirma icin temel kosul.",
  "ornek": "Isteme birkac ornek cozum (few-shot) eklenir.",
  "bilgi": "SEO bilgi tabanindan ilgili parcalar eklenir. Gomme modeli secilirse anlamsal getirme (RAG), secilmezse anahtar kelime eslestirmesi kullanilir.",
  "ornek+bilgi": "Hem ornekler hem bilgi tabani parcalari eklenir."
};

/* ------------------------------------------------------------------ baslangic */
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".sekme").forEach((d) => d.addEventListener("click", () => modDegistir(d.dataset.mod)));
  $("#llm-kullan").addEventListener("change", (e) => $("#llm-ayarlari").classList.toggle("gizli", !e.target.checked));
  $("#kosul").addEventListener("change", kosulAciklamasiGuncelle);
  $("#model-yenile").addEventListener("click", modelleriGetir);
  $("#kesif-dugmesi").addEventListener("click", kesfet);
  $("#basla").addEventListener("click", taramayiBaslat);
  $("#durdur").addEventListener("click", () => fetch("/api/durdur", { method: "POST" }));

  kosulAciklamasiGuncelle();
  fetch("/api/aciklamalar").then((r) => r.json()).then((d) => { aciklamalar = d; });
  modelleriGetir();
  durumuSor();           // sayfa yenilense bile suren tarama varsa yakala
});

function modDegistir(yeni) {
  mod = yeni;
  document.querySelectorAll(".sekme").forEach((d) => d.classList.toggle("etkin", d.dataset.mod === yeni));
  $("#alan-canli").classList.toggle("gizli", yeni !== "canli");
  $("#alan-dosya").classList.toggle("gizli", yeni !== "dosya");
}

function kosulAciklamasiGuncelle() {
  $("#kosul-aciklamasi").textContent = KOSUL_ACIKLAMA[$("#kosul").value] || "";
}

/* --------------------------------------------------------------------- model */
function modelleriGetir() {
  const rozet = $("#baglanti-rozeti");
  rozet.textContent = "LM Studio: sorgulaniyor...";
  rozet.className = "rozet";
  fetch("/api/modeller?url=" + encodeURIComponent($("#llm-url").value))
    .then((r) => r.json())
    .then((d) => {
      const sohbet = $("#model"), gomme = $("#embed-model");
      sohbet.innerHTML = "";
      gomme.innerHTML = '<option value="">— yok (anahtar kelime eslestirmesi) —</option>';
      if (d.hata || !d.modeller.length) {
        rozet.textContent = "LM Studio: baglanti yok";
        rozet.className = "rozet kopuk";
        sohbet.innerHTML = '<option value="">— model bulunamadi —</option>';
        return;
      }
      // yuklu modeller once gelsin; yuklu olmayani secmek LM Studio'da onu da bellege yukler
      const sirali = [...d.modeller].sort((a, b) => (b.yuklu === true) - (a.yuklu === true));
      sirali.forEach((m) => {
        const gommeMu = m.tur === "embeddings" || /embed/i.test(m.id);
        const se = yarat("option");
        se.value = m.id;
        se.textContent = m.id + (m.yuklu === false ? "  (yuklu degil — secilirse yuklenir)" : "");
        (gommeMu ? gomme : sohbet).appendChild(se);
      });
      if (!sohbet.options.length) sohbet.innerHTML = '<option value="">— sohbet modeli yok —</option>';
      const yuklu = d.modeller.filter((m) => m.yuklu === true).length;
      const bilinmiyor = d.modeller.every((m) => m.yuklu === null);
      rozet.textContent = "LM Studio: " + (bilinmiyor
        ? d.modeller.length + " model"
        : yuklu + " yuklu / " + d.modeller.length + " mevcut");
      rozet.className = "rozet bagli";
    })
    .catch(() => { rozet.textContent = "LM Studio: baglanti yok"; rozet.className = "rozet kopuk"; });
}

/* --------------------------------------------------------------------- kesif */
function kesfet() {
  const kutu = $("#kesif-sonucu");
  kutu.classList.remove("gizli");
  kutu.textContent = "Araniyor...";
  fetch("/api/kesif", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ adres: $("#kesif-adresi").value })
  })
    .then((r) => r.json())
    .then((d) => {
      kutu.innerHTML = "";
      if (d.hata) { kutu.textContent = "Hata: " + d.hata; return; }
      if (!d.adresler.length) { kutu.textContent = "Alt site bulunamadi."; return; }
      const ust = yarat("div");
      ust.innerHTML = '<strong>' + d.adresler.length + ' adres bulundu.</strong> ' +
        '<button class="ikincil" id="kesif-ekle">Secilenleri listeye ekle</button>';
      kutu.appendChild(ust);
      d.adresler.forEach((a) => {
        const l = yarat("label");
        l.innerHTML = '<input type="checkbox" checked value="' + kacis(a.adres) + '">' +
          '<span class="adres">' + kacis(a.adres) + '</span>' +
          (a.baglanti_metni ? ' <span class="not">' + kacis(a.baglanti_metni) + '</span>' : "");
        kutu.appendChild(l);
      });
      $("#kesif-ekle").addEventListener("click", () => {
        const secili = [...kutu.querySelectorAll("input:checked")].map((i) => i.value);
        const mevcut = $("#adresler").value.split("\n").map((s) => s.trim()).filter(Boolean);
        $("#adresler").value = [...new Set(mevcut.concat(secili))].join("\n");
        kutu.classList.add("gizli");
      });
    })
    .catch((e) => { kutu.textContent = "Hata: " + e; });
}

/* -------------------------------------------------------------------- tarama */
function taramayiBaslat() {
  const hata = $("#form-hatasi");
  hata.classList.add("gizli");
  const govde = {
    mod: mod,
    adresler: $("#adresler").value,
    klasor: $("#klasor").value,
    cikti: $("#cikti").value,
    llm_kullan: $("#llm-kullan").checked,
    url: $("#llm-url").value,
    model: $("#model").value,
    kosul: $("#kosul").value,
    embed_model: $("#embed-model").value,
    retry: $("#retry").value,
    max_tokens: $("#max-tokens").value,
    uy_robots: $("#uy-robots").checked,
    bagimsiz_olcum: $("#bagimsiz-olcum").checked,
    bekleme_sn: $("#bekleme").value,
    zaman_asimi: $("#zaman-asimi").value
  };
  fetch("/api/tara", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(govde)
  })
    .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
    .then(({ ok, d }) => {
      if (!ok) { hata.textContent = d.hata || "Tarama baslatilamadi."; hata.classList.remove("gizli"); return; }
      acikSatirlar = new Set();
      $("#bos-durum").classList.add("gizli");
      durumuSor();
    })
    .catch((e) => { hata.textContent = "Sunucuya ulasilamadi: " + e; hata.classList.remove("gizli"); });
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
  $("#basla").disabled = d.calisiyor;
  $("#durdur").classList.toggle("gizli", !d.calisiyor);
  $("#ilerleme-kutusu").classList.toggle("gizli", !d.toplam);
  $("#indirmeler").classList.toggle("gizli", !d.sonuclar.length);
  if (d.sonuclar.length) $("#bos-durum").classList.add("gizli");

  if (d.toplam) {
    const yuzde = Math.round((d.biten / d.toplam) * 100);
    $("#ilerleme-dolgu").style.width = yuzde + "%";
    const sure = d.baslangic ? Math.round(((d.bitis || Date.now() / 1000) - d.baslangic)) : 0;
    $("#ilerleme-metni").textContent =
      d.biten + " / " + d.toplam + " sayfa" + (d.calisiyor ? " taraniyor" : " tamamlandi") +
      " — " + sure + " sn" + (d.cikti_klasoru ? " — " + d.cikti_klasoru : "");
  }

  $("#gunluk").textContent = (d.gunluk || []).join("\n");
  const gk = $("#gunluk-kutusu");
  if (gk.open) $("#gunluk").scrollTop = $("#gunluk").scrollHeight;

  ozetiCiz(d.sonuclar);
  tabloyuCiz(d.sonuclar);
}

function ozetiCiz(sonuclar) {
  const kutu = $("#ozet");
  const gecerli = sonuclar.filter((k) => !k.hata && !k.atlandi && k.once_puan !== undefined);
  if (!gecerli.length) { kutu.classList.add("gizli"); return; }
  kutu.classList.remove("gizli");
  const ort = (f) => Math.round(gecerli.reduce((t, k) => t + (f(k) || 0), 0) / gecerli.length);
  const toplamOnce = gecerli.reduce((t, k) => t + (k.once_sorun_sayisi || 0), 0);
  const toplamSonra = gecerli.reduce((t, k) => t + (k.sonra_sorun_sayisi || 0), 0);
  const oranlar = gecerli.map((k) => k.toplam_cozum_orani).filter((x) => x !== null && x !== undefined);
  const ortOran = oranlar.length ? Math.round((oranlar.reduce((a, b) => a + b, 0) / oranlar.length) * 100) : null;
  const hatali = sonuclar.filter((k) => k.hata || k.atlandi).length;

  const kutucuk = (deger, etiket) => '<div class="kutucuk"><div class="deger">' + deger +
    '</div><div class="etiket">' + etiket + "</div></div>";
  // site puani yalnizca canli modda olculur; olculmeyen kayitlar ortalamaya katilmaz
  const ortPuan = (an, kap) => {
    const p = gecerli.map((k) => (k[an + "_puanlar"] || {})[kap]).filter((x) => x !== null && x !== undefined);
    return p.length ? Math.round(p.reduce((a, b) => a + b, 0) / p.length) : "—";
  };
  kutu.innerHTML =
    kutucuk(gecerli.length, "analiz edilen sayfa") +
    kutucuk(toplamOnce + " &rarr; " + toplamSonra, "toplam sorun") +
    kutucuk(ortPuan("once", "sayfa") + " &rarr; " + ortPuan("sonra", "sayfa"), "ortalama sayfa puani") +
    kutucuk(ortPuan("once", "site"), "ortalama site puani") +
    kutucuk(ortOran === null ? "—" : "%" + ortOran, "ortalama cozum orani") +
    (hatali ? kutucuk(hatali, "hatali / atlanan") : "");
}

function tabloyuCiz(sonuclar) {
  const tablo = $("#sonuc-tablosu");
  const govde = tablo.querySelector("tbody");
  tablo.classList.toggle("gizli", !sonuclar.length);
  govde.innerHTML = "";

  sonuclar.forEach((k, i) => {
    const satir = yarat("tr", "ana");
    if (k.hata || k.atlandi) {
      satir.innerHTML =
        '<td class="sayfa-adi">' + kacis(k.ad) + "</td>" +
        '<td colspan="6" class="azalis">' + kacis(k.atlandi ? "Atlandi: " + k.atlandi : "Hata: " + k.hata) + "</td><td></td>";
      govde.appendChild(satir);
      return;
    }
    const po = k.once_puanlar || {}, ps = k.sonra_puanlar || {};
    const fark = (ps.sayfa ?? 0) - (po.sayfa ?? 0);
    const oran = k.cozum_orani === null || k.cozum_orani === undefined ? "—" : "%" + Math.round(k.cozum_orani * 100);
    satir.innerHTML =
      '<td class="sayfa-adi">' + kacis(k.ad) + "</td>" +
      '<td class="sayi">' + (k.once_sorun_sayisi ?? "—") + "</td>" +
      '<td class="sayi">' + (k.sonra_sorun_sayisi ?? "—") + "</td>" +
      '<td class="sayi">' + (po.sayfa ?? "—") + " &rarr; " + (ps.sayfa ?? "—") +
      (fark ? ' <span class="' + (fark > 0 ? "artis" : "azalis") + '">' + (fark > 0 ? "+" : "") + fark + "</span>" : "") + "</td>" +
      '<td class="sayi">' + (po.site ?? "—") + "</td>" +
      '<td class="sayi">' + oran + "</td>" +
      '<td class="sayi">' + (k.sure_toplam_sn ?? "—") + " sn</td>" +
      '<td><button class="ikincil" data-i="' + i + '">Ayrinti</button></td>';
    govde.appendChild(satir);

    const ayrintiSatiri = yarat("tr", "ayrinti-satiri");
    const hucre = yarat("td");
    hucre.colSpan = 8;
    hucre.innerHTML = ayrintiHtml(k);
    ayrintiSatiri.appendChild(hucre);
    ayrintiSatiri.style.display = acikSatirlar.has(i) ? "" : "none";
    govde.appendChild(ayrintiSatiri);

    satir.querySelector("button").addEventListener("click", () => {
      const acik = ayrintiSatiri.style.display !== "none";
      ayrintiSatiri.style.display = acik ? "none" : "";
      if (acik) acikSatirlar.delete(i); else acikSatirlar.add(i);
    });
  });
}

function sorunListesi(sorunlar) {
  if (!sorunlar || !sorunlar.length) return "<p class='not'>Sorun bulunamadi.</p>";
  const sira = { yuksek: 0, orta: 1, dusuk: 2 };
  return "<ul>" + [...sorunlar].sort((a, b) => sira[a.ciddiyet] - sira[b.ciddiyet]).map((s) =>
    "<li>" +
    '<span class="etiket-rozet c-' + s.ciddiyet + '">' + s.ciddiyet + "</span>" +
    '<span class="etiket-rozet k-' + s.katman + '">' + s.katman + "</span>" +
    kacis(aciklamalar[s.sorun] || s.sorun) +
    (s.ayrinti ? ' <span class="not">(' + kacis(s.ayrinti) + ")</span>" : "") +
    ' <span class="not">[' + kacis(s.cozum_yolu) + "]</span>" +
    "</li>").join("") + "</ul>";
}

function ayrintiHtml(k) {
  let h = '<div class="ayrinti">';

  if (k.once_puanlar) {
    const etiketler = { sayfa: "Sayfa", site: "Site", icerik: "Icerik", teknik: "Teknik",
                        guvenlik: "Guvenlik", performans: "Performans" };
    h += "<h4>Puanlar (once &rarr; sonra)</h4><div class='bilgi-izgara'>" +
      Object.keys(etiketler).map((kap) => {
        const o = k.once_puanlar[kap], s = (k.sonra_puanlar || {})[kap];
        const deger = o === null || o === undefined ? "olculmedi" : o + " → " + (s ?? "—");
        return '<div><span class="etiket">' + etiketler[kap] + "</span>" + kacis(deger) + "</div>";
      }).join("") + "</div>";
  }
  h += "<h4>Tespit edilen sorunlar (" + (k.once_sorun_sayisi || 0) + ")</h4>" + sorunListesi(k.sorunlar);

  if (k.fixes && k.fixes.length) {
    h += "<h4>Modelin kabul edilen onerileri (" + k.fixes.length + ")</h4><table><tbody>";
    k.fixes.forEach((f) => {
      h += "<tr><td><strong>" + kacis(f.alan) + (f.hedef ? " / " + kacis(f.hedef) : "") + "</strong></td>" +
        "<td>" + kacis(f.yeni_deger) + '<br><span class="not">' + kacis(f.gerekce || "") + "</span></td></tr>";
    });
    h += "</tbody></table>";
  }
  if (k.reddedilen && k.reddedilen.length) {
    h += "<h4>Reddedilen oneriler (" + k.reddedilen.length + ")</h4><ul>";
    k.reddedilen.forEach((r) => {
      h += "<li><strong>" + kacis(r.neden) + "</strong> &mdash; " +
        kacis((r.oneri && (r.oneri.alan + ": " + r.oneri.yeni_deger)) || "").slice(0, 160) + "</li>";
    });
    h += "</ul>";
  }
  if (k.kural_duzeltmeleri && k.kural_duzeltmeleri.length) {
    h += "<h4>Kural tabanli duzeltmeler</h4><ul>" +
      k.kural_duzeltmeleri.map((x) => "<li>" + kacis(x) + "</li>").join("") + "</ul>";
  }

  const sb = k.site_bilgi;
  if (sb && !sb.hata) {
    const s = sb.sertifika || {};
    const r = sb.robots || {};
    const sm = sb.sitemap || {};
    const alan = (etiket, deger) => '<div><span class="etiket">' + etiket + "</span>" + kacis(deger) + "</div>";
    h += "<h4>Canli erisim olcumleri</h4><div class='bilgi-izgara'>" +
      alan("Durum kodu", sb.durum_kodu) +
      alan("Yanit suresi (TTFB)", (sb.ttfb_ms ?? "—") + " ms") +
      alan("Indirme", (sb.toplam_ms ?? "—") + " ms / " + (sb.boyut_kb ?? "—") + " KB") +
      alan("Sikistirma", sb.sikistirma || "yok") +
      alan("HSTS", sb.hsts ? "var" : "yok") +
      alan("Sertifika", s.veren ? (s.kalan_gun + " gun kaldi" + (s.zincir_eksik ? " — zincir eksik" : "")) : "—") +
      alan("robots.txt", r.var ? (r.satir_sayisi + " satir, " + (r.sitemapler || []).length + " sitemap") : "yok") +
      alan("sitemap", sm.var ? (sm.tur + ", " + sm.url_sayisi + " adres") : "yok") +
      "</div>";
  }

  if (k.model) {
    h += "<h4>Model calismasi</h4><div class='bilgi-izgara'>" +
      '<div><span class="etiket">Model</span>' + kacis(k.model) + "</div>" +
      '<div><span class="etiket">Kosul</span>' + kacis(k.kosul) + " / " + kacis(k.ogretme_yontemi || "—") + "</div>" +
      '<div><span class="etiket">Sure</span>' + kacis(k.sure_sn) + " sn</div>" +
      '<div><span class="etiket">Deneme</span>' + ((k.denemeler || []).length) + "</div>" +
      "</div>";
  }
  if (k.duzeltilmis_dosya) {
    h += '<p class="not">Duzeltilmis sayfa: ' + kacis(k.duzeltilmis_dosya) + "</p>";
  }
  return h + "</div>";
}
