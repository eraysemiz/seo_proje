"use strict";
// Masaustu arayuzu. Sayilari hesaplamaz: hepsi /api uclarindan (yonetici_raporu.json vb.) aynen gosterilir.

const S = {
  jeton: "", ayar: {}, retNedenleri: [], ekran: "analiz", durum: null, son: 0, biten: 0,
  planKlasor: null, plan: null, secili: null, sekme: "bekleyen", filtre: { ara: "", kategori: "", risk: "", guven: "" },
  secimler: {}, kuralHepsi: false, kirli: false,
  sonuclar: null, sonucSecili: null, rapor: null, karsilastir: [], ara: "", deneyGizle: true,
  gunlukAcik: true, gunluk: [], tarama: null, sonTarama: null, ayarDegisti: false,
};
const MENU = [["analiz", "Analiz", "search"], ["onay", "Onay", "check-check"], ["sonuclar", "Sonuçlar", "history"],
  ["test", "Test sitesi", "server"], ["bilgi", "Bilgi tabanı", "book-open"], ["ayarlar", "Ayarlar", "settings"]];
const IKONLAR = ["search", "check-check", "history", "server", "book-open", "settings", "sun", "moon", "play", "square", "x",
  "circle-alert", "triangle-alert", "check", "chevron-right", "chevron-down", "folder-open", "file-text", "undo-2", "refresh-cw",
  "external-link", "terminal", "pencil", "shield-check", "rotate-ccw", "git-compare", "globe", "layers"];
const ASAMALAR = [["tarama", "Tarama"], ["analiz", "Analiz"], ["otomatik", "Otomatik düzeltme"], ["yeniden_kontrol", "Yeniden kontrol"]];
const SERIT = [["cozuldu_otomatik", "--serit-oto"], ["cozuldu_onayli", "--serit-onayli"], ["onay_bekliyor", "--serit-bekle"],
  ["reddedildi", "--serit-ret"], ["basarisiz", "--serit-hata"], ["dogrulanmadi", "--serit-kontrol"], ["elle", "--serit-elle"]];
const RISK = { dusuk: "Düşük risk", orta: "Orta risk", yuksek: "Yüksek risk" };

const $ = (s, k = document) => k.querySelector(s);
const $$ = (s, k = document) => [...k.querySelectorAll(s)];
const e = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ikon = (ad) => `<svg class="ikon" aria-hidden="true"><use href="#i-${ad}"/></svg>`;
const yuzde = (x) => (x === null || x === undefined ? "—" : "%" + Math.round(100 * x));
const tireli = (x) => (x === null || x === undefined ? "—" : e(x));
const guvenMetni = (g) => (g === null || g === undefined ? "—" : Number(g).toFixed(2).replace(".", ","));

async function api(yol, govde) {
  const ayar = govde === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", "X-Jeton": S.jeton }, body: JSON.stringify(govde) };
  const r = await fetch(yol, ayar);
  let v = {};
  try { v = await r.json(); } catch (_) { v = { hata: "Uygulama sunucusundan okunamayan bir cevap geldi (" + r.status + ").", baslik: "Hata" }; }
  if (!r.ok) { const h = new Error(v.hata || "Bilinmeyen hata"); h.baslik = v.baslik || "Hata"; throw h; }
  return v;
}
async function dene(fn) {
  try { return await fn(); } catch (h) { await uyari(h.baslik || "Hata", h.message); return undefined; }
}

// ---- modal
function modal(baslik, ileti, dugmeler) {
  return new Promise((coz) => {
    const kok = $("#modal-kok");
    kok.innerHTML = `<div class="modal-ort" role="dialog" aria-modal="true" aria-label="${e(baslik)}"><div class="modal"><h2>${e(baslik)}</h2><p>${e(ileti)}</p>
      <div class="eylemler">${dugmeler.map((d, i) => `<button class="btn ${d.sinif || ""}" data-i="${i}" id="${d.id || ""}">${e(d.ad)}</button>`).join("")}</div></div></div>`;
    const bitir = (v) => { kok.innerHTML = ""; document.removeEventListener("keydown", tus, true); coz(v); };
    const tus = (o) => { if (o.key === "Escape") { o.stopPropagation(); bitir(dugmeler[0].deger); } };
    document.addEventListener("keydown", tus, true);
    $$("button", kok).forEach((b) => { b.onclick = () => bitir(dugmeler[+b.dataset.i].deger); });
    $$("button", kok).at(-1).focus();
  });
}
const uyari = (b, i) => modal(b, i, [{ ad: "Tamam", deger: true, id: "modal-tamam", sinif: "ana" }]);
const sor = (b, i, evet = "Devam et", tehlike = false) => modal(b, i, [{ ad: "Vazgeç", deger: false, id: "modal-hayir" },
  { ad: evet, deger: true, id: "modal-evet", sinif: tehlike ? "tehlike" : "ana" }]);

// ---- tema
function temaUygula(t, kaydet = true) {
  S.tema = t; document.documentElement.dataset.tema = t;
  if (kaydet) api("/api/tema", { tema: t }).catch(() => {});
  $("#tema-dugmesi").innerHTML = ikon(t === "koyu" ? "sun" : "moon") + `<span>${t === "koyu" ? "Açık tema" : "Koyu tema"}</span>`;
}

// ---- gezinme
function menuCiz() {
  const sayi = S.plan && !S.plan.kilitli ? S.plan.degisiklikler.filter(bekliyor).length : 0;
  $("#menu-baglantilar").innerHTML = MENU.map(([k, ad, ik], i) => `<a class="menu-oge" href="#/${k}" id="menu-${k}" title="${ad} (Ctrl+${i + 1})"
    ${S.ekran === k ? 'aria-current="page"' : ""}>${ikon(ik)}<span>${ad}</span>${k === "onay" && sayi ? `<span class="sayi">${sayi}</span>` : ""}</a>`).join("");
}
function git(ekran) { location.hash = "#/" + ekran; }
function rotaOku() {
  const [yol, sorgu] = location.hash.replace(/^#\/?/, "").split("?");
  const p = new URLSearchParams(sorgu || "");
  if (p.get("tema")) temaUygula(p.get("tema"), false);
  if (p.get("sekme")) S.sekme = p.get("sekme");
  S.ekran = MENU.some((m) => m[0] === yol) ? yol : "analiz";
  ciz();
}
const EKRANLAR = {};
async function ciz() {
  menuCiz();
  const sayfa = $("#sayfa");
  sayfa.classList.toggle("tam", S.ekran === "onay" || S.ekran === "sonuclar");
  sayfa.scrollTop = 0;
  await EKRANLAR[S.ekran]();
  ustCiz(); isCiz();
}
function ustCiz() {
  const k = S.planKlasor, a = S.ayar;
  $("#ust-baglam").textContent = k && S.plan ? `${S.plan.bilgi.site} · ${S.plan.bilgi.zaman} · ${S.plan.bilgi.durum}` : (a.site_url || "") + (a.site_koku ? " · " + a.site_koku : "");
}

// ---- durum dongusu
async function yokla() {
  try {
    const d = await api("/api/durum?son=" + S.son);
    S.durum = d;
    for (const g of d.gunluk) { S.gunluk.push(g); gunlukEkle(g); }
    S.gunluk.splice(0, Math.max(0, S.gunluk.length - 3000));
    if (d.gunluk.length) S.son = d.gunluk.at(-1).n;
    for (const b of d.bildirimler) { S.son = Math.max(S.son, b.n); await uyari(b.baslik, b.ileti); }
    durumCiz(d); isCiz();
    if (d.plan_klasoru && d.plan_klasoru !== S.planKlasor) await planYukle(d.plan_klasoru);
    if (d.biten !== S.biten) { S.biten = d.biten; await isBitti(d); }
  } catch (_) { /* sunucu kapaniyor */ }
  setTimeout(yokla, 500);
}
async function isBitti(d) {
  if (S.tarama) { S.sonTarama = { ...S.tarama, basarili: d.son_is && d.son_is.kod === 0 && !d.son_is.iptal }; S.tarama = null; }
  if (S.planKlasor) await planYukle(S.planKlasor);
  S.sonuclar = null;
  if (S.ekran !== "ayarlar") ciz();
}
function durumCiz(d) {
  const lm = d.lm;
  $("#d-lm").innerHTML = !lm ? `<i class="nokta"></i>LM Studio denetleniyor`
    : !lm.erisim ? `<i class="nokta kotu"></i>LM Studio kapalı`
    : (lm.eksik.length || lm.yuklu_degil.length) ? `<i class="nokta uyari"></i>LM Studio açık · model eksik` : `<i class="nokta iyi"></i>LM Studio hazır`;
  $("#d-lm").title = d.lm_iletisi || d.lm_url;
  const pt = S.ayar.test_portu;
  $("#d-test").innerHTML = d.test ? `<i class="nokta iyi"></i>Test sitesi açık` : `<i class="nokta"></i>Test sitesi kapalı`;
  $("#d-test").title = d.test ? `http://127.0.0.1:${pt}/` + (d.test_bizim ? "" : " (bu uygulama dışında başlatıldı)") : "";
  $("#d-web").innerHTML = d.web ? `<i class="nokta iyi"></i>Tarayıcı arayüzü açık` : "";
  if (S.ekran === "test" && S.testDurum !== String(d.test) + d.test_bizim) { S.testDurum = String(d.test) + d.test_bizim; ciz(); }
}
function isCiz() {
  const d = S.durum; if (!d) return;
  const s = d.is;
  const gecen = s ? Math.max(0, Math.floor(Date.now() / 1000 - s.baslangic)) : 0;
  const sure = `${String(Math.floor(gecen / 60)).padStart(2, "0")}:${String(gecen % 60).padStart(2, "0")}`;
  $("#d-is").textContent = s ? `Çalışıyor: ${s.ad} (${sure})` : "Boşta";
  const ust = $("#ust-is");
  const anahtar = s ? s.ad + s.iptal_edilebilir : "";
  if (ust.dataset.a !== anahtar) {
    ust.dataset.a = anahtar;
    ust.innerHTML = s ? `<span class="soluk">${e(s.ad)}</span>` + (s.iptal_edilebilir ? `<button class="btn" id="iptal" title="Çalışan işi iptal et">${ikon("square")}İptal</button>` : `<span class="rozet uyari" title="Yazma işlemi yarıda kesilemez">Yazılıyor</span>`) : "";
    const b = $("#iptal"); if (b) b.onclick = () => dene(() => api("/api/iptal", {}));
    $$("[data-is]").forEach((b2) => { b2.disabled = !!s; });
  }
  $$("[data-is]").forEach((b2) => { b2.disabled = !!s || b2.hasAttribute("data-kapali"); });
  adimlarCiz();
}

// ---- gunluk
function gunlukEkle(g) {
  const k = $("#gunluk"); if (!k) return;
  const alta = k.scrollHeight - k.scrollTop - k.clientHeight < 30;
  k.insertAdjacentHTML("beforeend", `<div class="${e(g.t || "")}">${e(g.m)}</div>`);
  if (alta) k.scrollTop = k.scrollHeight;
}
function gunlukHtml(baslik = "Canlı günlük") {
  return `<div class="gunluk-baslik"><button class="btn sade" id="gunluk-ac" aria-expanded="${S.gunlukAcik}" title="Günlüğü aç/kapat">${ikon(S.gunlukAcik ? "chevron-down" : "chevron-right")}${baslik}</button>
    <span class="bosluk"></span><button class="btn sade kucuk" id="gunluk-sil" title="Görünen günlüğü temizle">Temizle</button></div>
    ${S.gunlukAcik ? `<div class="gunluk" id="gunluk" tabindex="0">${S.gunluk.map((g) => `<div class="${e(g.t || "")}">${e(g.m)}</div>`).join("")}</div>` : ""}`;
}
function gunlukBagla() {
  const k = $("#gunluk"); if (k) k.scrollTop = k.scrollHeight;
  const a = $("#gunluk-ac"); if (a) a.onclick = () => { S.gunlukAcik = !S.gunlukAcik; ciz(); };
  const s = $("#gunluk-sil"); if (s) s.onclick = () => { S.gunluk = []; if ($("#gunluk")) $("#gunluk").innerHTML = ""; };
}

// ---- ortak ozet: bulgu seridi ve puan yolu (yonetici_raporu.json)
function seritHtml(oz, adlar) {
  const say = oz.sayilar || {};
  const parcalar = SERIT.filter(([k]) => say[k]);
  return `<div class="serit" role="img" aria-label="${parcalar.map(([k]) => `${adlar[k]} ${say[k]}`).join(", ")}">${parcalar.map(([k, r]) => `<i style="flex:${say[k]};background:var(${r})" title="${e(adlar[k])}: ${say[k]}"></i>`).join("")}</div>
    <div class="lejant">${parcalar.map(([k, r]) => `<span><i style="background:var(${r})"></i>${e(adlar[k])} <b data-sayi="${k}">${say[k]}</b></span>`).join("")}</div>`;
}
function puanYolu(oz) {
  const adlar = { baslangic: "Başlangıç", otomatik: "Otomatik sonrası", onayli: "Onay sonrası" };
  return ["baslangic", "otomatik", "onayli"].map((a) => {
    const x = (oz.asamalar || []).find((y) => y.ad === a);
    const p = x && x.olculdu ? x.puanlar.sayfa : null;
    return `<div class="yol-adim"><strong data-puan="${a}">${p ?? "—"}</strong><div class="sutun"><i class="${p === null ? "yok" : ""}" style="width:${p ?? 0}%"></i></div><small>${adlar[a]}</small></div>`;
  }).join("");
}
function sonAsama(oz) { const o = (oz.asamalar || []).filter((a) => a.olculdu); return o.at(-1); }
function ozetKartlari(p) {
  const oz = p.ozet;
  if (!oz) return `<p class="soluk">Bu plan için henüz rapor yok.</p>`;
  const s = oz.sayaclar || {}, a = sonAsama(oz);
  return `<div class="sayilar3">
    <div class="kart"><div class="ad">Aktif sorun</div><div class="deger" id="k-aktif">${tireli(s.aktif)}</div><div class="not">toplam ${tireli(s.toplam)} bulgudan</div></div>
    <div class="kart"><div class="ad">Çözülen</div><div class="deger" id="k-cozulen">${tireli(s.cozulen)}</div><div class="not">otomatik ${tireli(s.cozuldu_otomatik)}, onaylı ${tireli(s.cozuldu_onayli)}</div></div>
    <div class="kart"><div class="ad">Çözüm oranı</div><div class="deger" id="k-oran">${a ? yuzde(a.cozum_orani) : "—"}</div><div class="not">${a ? `${e(a.cozulen)}/${e(a.cozulebilir)} düzeltilebilir bulgu` : ""}</div></div>
    <div class="kart"><div class="ad">Elle düzeltilir</div><div class="deger">${tireli(a && a.elle)}</div><div class="not" title="${e(oz.tanim)}">araç bunları yazmaz</div></div>
  </div><div style="margin-top:14px">${seritHtml(oz, p.bulgu_durum_adi)}</div><div class="yol" aria-label="Sayfa puanı"><div class="yol-baslik">Sayfa puanı</div>${puanYolu(oz)}</div>`;
}

// ---- Analiz
function adimlarCiz() {
  const k = $("#adimlar"); if (!k) return;
  const d = S.durum, s = d && d.is;
  const salt = (S.tarama || S.sonTarama || {}).mod === "salt";
  const liste = salt ? ASAMALAR.slice(0, 2) : ASAMALAR;
  const taranıyor = S.tarama && s;
  const simdi = taranıyor ? (s.asama || "tarama") : null;
  const i = simdi ? liste.findIndex((a) => a[0] === simdi) : (S.sonTarama && S.sonTarama.basarili ? liste.length : -1);
  const html = liste.map(([, ad], n) => `<span class="adim ${n < i ? "bitti" : n === i && simdi ? "simdi" : ""}" ${n === i && simdi ? 'aria-current="step"' : ""}><span class="top">${n < i ? ikon("check") : ""}</span>${ad}</span>`).join('<span class="adim-cizgi"></span>');
  if (k.dataset.h !== html) { k.dataset.h = html; k.innerHTML = html; }
}
EKRANLAR.analiz = async function () {
  const a = S.ayar, f = S.form || (S.form = { mod: "yonetici", adres: a.site_url, kok: a.site_koku, model: true, sohbet: a.sohbet_modeli, gomme: a.gomme_modeli, sayfa: 60, derinlik: 6, site_modu: true });
  const p = S.plan, yon = f.mod === "yonetici";
  const salt = S.durum && S.durum.salt_sonuc;
  const planBolum = p && yon ? `
    <div class="baslik-satiri" style="margin-bottom:12px"><div><h2>Son plan</h2><div class="alt kucuk">${e(p.bilgi.site)} · ${e(p.bilgi.zaman)} · ${e(p.bilgi.durum)}</div></div>
      <div class="eylemler"><button class="btn ana" id="onaya-git">${ikon("check-check")}Onaya git (${p.degisiklikler.filter(bekliyor).length} öneri)</button>
      ${p.rapor_var ? `<button class="btn" id="rapora-git">${ikon("file-text")}Rapor</button>` : ""}</div></div>
    ${ozetKartlari(p)}`
    : !yon && salt ? `<div class="baslik-satiri" style="margin-bottom:0"><div><h2>Son salt okunur tarama</h2><div class="alt kucuk">${e(salt)}</div></div><div class="eylemler"><button class="btn" id="salt-rapor">${ikon("file-text")}Raporu aç</button></div></div>`
    : `<div class="bos"><h2>Henüz tarama yok</h2><p>Soldaki adresi tarayın ya da Sonuçlar ekranından önceki bir planı açın.</p></div>`;
  $("#sayfa").innerHTML = `
    <div class="baslik-satiri"><div><h1>Analiz</h1><div class="alt">${yon ? "Onaylanan düzeltmeler yalnızca kök klasöre yazılır; her yazmadan önce tam yedek alınır." : "Siteye hiçbir şey yazılmaz."}</div></div>
      <div class="eylemler"><button class="btn ana" id="tara" data-is>${ikon("play")}Taramayı başlat</button></div></div>
    <div class="analiz-izgara">
      <div class="sol-kolon">
        <div id="adimlar" class="adimlar" aria-label="Tarama aşamaları"></div>
        ${planBolum}
        ${gunlukHtml()}
      </div>
      <form id="tarama-formu" class="form-izgara" onsubmit="return false">
        <div class="genis"><div class="etiket" style="margin-bottom:5px">Mod</div><div class="bolumlu" role="group" aria-label="Mod">
          <button type="button" id="mod-yonetici" aria-pressed="${yon}" title="Onaylanan düzeltmeleri siteye yazar">Yönetici</button>
          <button type="button" id="mod-salt" aria-pressed="${!yon}" title="Yalnızca analiz; siteye yazmaz">Salt okunur</button></div></div>
        <label class="alan genis"><span>${yon ? "Site adresi" : "Adresler (boşlukla ayırın)"}</span><input type="text" id="f-adres" value="${e(f.adres)}" spellcheck="false"></label>
        ${yon ? `<label class="alan genis"><span>Site kök klasörü</span><span class="yan" style="font-weight:400"><input type="text" id="f-kok" value="${e(f.kok)}" spellcheck="false"><button type="button" class="btn" id="f-kok-sec" title="Klasör seç">${ikon("folder-open")}</button></span></label>` : ""}
        <label class="onay-kutu genis" title="Kapalıysa yalnızca denetim yapılır; YZ metin önerisi üretilmez"><input type="checkbox" id="f-model" ${f.model ? "checked" : ""}>Dil modeli kullan (LM Studio)</label>
        <label class="alan genis"><span>Sohbet modeli</span><input type="text" id="f-sohbet" list="l-sohbet" value="${e(f.sohbet)}" ${f.model ? "" : "disabled"} spellcheck="false"><datalist id="l-sohbet"></datalist></label>
        <label class="alan genis"><span>Gömme modeli</span><input type="text" id="f-gomme" list="l-gomme" value="${e(f.gomme)}" ${f.model ? "" : "disabled"} spellcheck="false"><datalist id="l-gomme"></datalist></label>
        <div class="genis"><button type="button" class="btn" id="f-modeller" title="LM Studio'daki modelleri listele">${ikon("refresh-cw")}Modelleri getir</button></div>
        <label class="alan"><span>En fazla sayfa</span><input type="number" id="f-sayfa" min="1" max="500" value="${e(f.sayfa)}"></label>
        <label class="alan"><span>Derinlik</span><input type="number" id="f-derinlik" min="0" max="10" value="${e(f.derinlik)}"></label>
        ${yon ? "" : `<label class="onay-kutu genis" title="Site içi bağlantıları izle"><input type="checkbox" id="f-site" ${f.site_modu ? "checked" : ""}>Site modu</label>`}
      </form>
    </div>`;
  const oku = () => { for (const [k, id] of [["adres", "f-adres"], ["kok", "f-kok"], ["sohbet", "f-sohbet"], ["gomme", "f-gomme"], ["sayfa", "f-sayfa"], ["derinlik", "f-derinlik"]]) { const x = document.getElementById(id); if (x) f[k] = x.value; } const m = $("#f-model"); f.model = m.checked; const sm = $("#f-site"); if (sm) f.site_modu = sm.checked; };
  $("#tarama-formu").oninput = oku;
  $("#f-model").onchange = () => { oku(); ciz(); };
  $("#mod-yonetici").onclick = () => { oku(); f.mod = "yonetici"; ciz(); };
  $("#mod-salt").onclick = () => { oku(); f.mod = "salt"; ciz(); };
  const ks = $("#f-kok-sec"); if (ks) ks.onclick = () => klasorSec((v) => { f.kok = v; ciz(); });
  $("#f-modeller").onclick = () => dene(async () => {
    const m = await api("/api/modeller");
    $("#l-sohbet").innerHTML = m.sohbet.map((x) => `<option value="${e(x)}">`).join("");
    $("#l-gomme").innerHTML = m.gomme.map((x) => `<option value="${e(x)}">`).join("");
  });
  $("#tara").onclick = () => dene(async () => {
    oku();
    await api("/api/tara", f);
    S.tarama = { mod: f.mod }; S.sonTarama = null;
    if (!S.gunlukAcik) { S.gunlukAcik = true; ciz(); }
  });
  const og = $("#onaya-git"); if (og) og.onclick = () => git("onay");
  const rg = $("#rapora-git"); if (rg) rg.onclick = () => { S.sonucSecili = S.planKlasor; S.rapor = "yonetici_raporu.html"; git("sonuclar"); };
  const sr = $("#salt-rapor"); if (sr) sr.onclick = () => { S.sonucSecili = salt; S.rapor = "rapor.html"; git("sonuclar"); };
  gunlukBagla(); adimlarCiz();
};
async function klasorSec(sonra) {
  const r = await dene(() => api("/api/klasor-sec", {}));
  if (r && r.klasor) sonra(r.klasor);
}

// ---- Onay
const bekliyor = (d) => d.durum !== "gecersiz" && d.durum !== "uygulandi" && d.durum !== "reddedildi" && d.durum !== "geri_alindi" && d.durum !== "basarisiz";
async function planYukle(k) {
  const p = await api("/api/plan?klasor=" + encodeURIComponent(k));
  S.plan = p; S.planKlasor = k; S.secimler = p.secimler; S.kuralHepsi = p.kural_hepsi; S.kirli = false;
  if (!p.degisiklikler.some((d) => d.id === S.secili)) S.secili = null;
  menuCiz(); ustCiz();
}
function sekmeListesi(p) {
  return { bekleyen: p.degisiklikler.filter(bekliyor), uygulanan: p.degisiklikler.filter((d) => d.durum === "uygulandi"),
    diger: p.degisiklikler.filter((d) => !bekliyor(d) && d.durum !== "uygulandi") };
}
function suzgec(liste) {
  const f = S.filtre, q = f.ara.toLocaleLowerCase("tr");
  return liste.filter((d) => (!f.kategori || d.kategori === f.kategori) && (!f.risk || d.risk === f.risk)
    && (!f.guven || (f.guven === "dusuk" ? (d.guven ?? 0) < S.plan.esik : f.guven === "yuksek" ? (d.guven ?? 0) >= S.plan.esik : d.yer_tutucu))
    && (!q || [d.id, d.bulgu, d.bulgu_aciklamasi, d.dosya, d.url, d.yeni].join(" ").toLocaleLowerCase("tr").includes(q)));
}
const gruplama = (d) => (d.risk === "yuksek" ? "yuksek" : d.kategori);
function kararIsaret(d) {
  const k = (S.secimler[d.id] || {}).karar;
  if (k === "onay") return `<span class="karar-isaret onay">Onay</span>`;
  if (k === "ret") return `<span class="karar-isaret ret">${d.durum === "uygulandi" ? "Geri çekilecek" : "Ret"}</span>`;
  return "";
}
function guvenRozet(d) {
  if (d.guven === null || d.guven === undefined) return "";
  return `<span class="rozet ${d.guven >= S.plan.esik ? "iyi" : "uyari"}" title="Güven puanı; eşik ${guvenMetni(S.plan.esik)}">${guvenMetni(d.guven)}</span>`;
}
function satirHtml(d) {
  return `<button class="satir" data-id="${d.id}" role="option" aria-selected="${S.secili === d.id}">
    <span class="kimlik">${d.id}</span><span class="baslik">${e(d.bulgu_aciklamasi || d.bulgu)}</span><span>${guvenRozet(d)}</span>
    <span class="alt"><span>${e(d.dosya)}</span>${d.yer_tutucu ? `<span class="rozet uyari">doğrulanmalı</span>` : ""}${d.risk === "yuksek" ? `<span class="rozet kotu">yüksek risk</span>` : ""}<span class="bosluk"></span>${kararIsaret(d)}</span></button>`;
}
function kuyrukCiz() {
  const p = S.plan, k = $("#kuyruk-liste"); if (!k) return;
  const liste = suzgec(sekmeListesi(p)[S.sekme] || []);
  const adlar = { yuksek: "Yüksek risk", ...p.kategoriler };
  const gruplar = ["yuksek", "yz", "kural"].map((g) => [g, liste.filter((d) => gruplama(d) === g)]).filter(([, x]) => x.length);
  const acik = !p.kilitli && S.sekme === "bekleyen";
  k.innerHTML = gruplar.length ? gruplar.map(([g, x]) => `<div class="grup-baslik"><span>${e(adlar[g] || g)} (${x.length})</span>
      ${acik && g !== "yuksek" ? `<span><button class="btn" data-toplu="onay" data-g="${g}" title="Bu gruptaki görünen, tek tek onay gerektirmeyen önerileri onayla">Tümünü onayla</button> <button class="btn" data-toplu="ret" data-g="${g}">Reddet</button></span>` : ""}</div>${x.map(satirHtml).join("")}`).join("")
    : `<div class="bos" style="margin:14px;border:0"><h2>${S.sekme === "bekleyen" ? "Bekleyen öneri yok" : "Burada kayıt yok"}</h2><p>${S.filtre.ara || S.filtre.kategori || S.filtre.risk || S.filtre.guven ? "Filtrelere uyan öneri bulunamadı." : ""}</p></div>`;
  $$(".satir", k).forEach((b) => { b.onclick = () => sec(b.dataset.id); });
  $$("[data-toplu]", k).forEach((b) => { b.onclick = () => topluKarar(liste.filter((d) => gruplama(d) === b.dataset.g), b.dataset.toplu); });
}
function topluKarar(liste, karar) {
  let atlanan = 0;
  for (const d of liste) {
    if (karar === "onay" && (d.zorunlu_onay || d.yer_tutucu)) { atlanan++; continue; }
    S.secimler[d.id] = { ...S.secimler[d.id], karar };
  }
  S.kirli = true; kuyrukCiz(); ayrintiCiz(); altCiz();
  if (atlanan) uyari("Tek tek onay gerekir", `${atlanan} öneri atlandı: yer tutucu içeriyor ya da her zaman tek tek onay istiyor.`);
}
function sec(id) {
  S.secili = id; kuyrukCiz(); ayrintiCiz();
  const b = $(`.satir[data-id="${id}"]`); if (b) { b.scrollIntoView({ block: "nearest" }); }
}
function diffHtml(metin) {
  const satirlar = (metin || "").split("\n").filter((s) => !s.startsWith("#") && !s.startsWith("---") && !s.startsWith("+++"));
  let html = `<div class="bas sol">Önce</div><div class="bas">Sonra</div>`, sil = [], ekle = [];
  const bosalt = () => { const n = Math.max(sil.length, ekle.length);
    for (let i = 0; i < n; i++) html += `<div class="sol ${i < sil.length ? "sil" : ""}">${e(sil[i] ?? "")}</div><div class="${i < ekle.length ? "ekle" : ""}">${e(ekle[i] ?? "")}</div>`;
    sil = []; ekle = []; };
  for (const s of satirlar) {
    if (s.startsWith("@@")) { bosalt(); html += `<div class="konum">${e(s)}</div>`; }
    else if (s.startsWith("-")) sil.push(s.slice(1));
    else if (s.startsWith("+")) ekle.push(s.slice(1));
    else { bosalt(); html += `<div class="sol">${e(s.slice(1))}</div><div>${e(s.slice(1))}</div>`; }
  }
  bosalt();
  return `<div class="diff" id="diff">${html}</div>`;
}
function ayrintiCiz() {
  const k = $("#ayrinti"); if (!k) return;
  const p = S.plan, d = p.degisiklikler.find((x) => x.id === S.secili);
  if (!d) { k.innerHTML = `<div class="bos" style="border:0"><h2>Bir öneri seçin</h2><p>Soldaki kuyruktan seçin. J ve K ile gezinin, A ile onaylayın, R ile reddedin.</p></div>`; return; }
  const s = S.secimler[d.id] || (S.secimler[d.id] = {});
  const kapali = p.kilitli || d.durum === "gecersiz" || d.durum === "reddedildi" || d.durum === "basarisiz";
  const model = d.uretici === "model";
  k.innerHTML = `
    <div class="baslik-satiri" style="margin-bottom:0"><div><h2><span class="mono soluk">${d.id}</span> ${e(d.bulgu_aciklamasi || d.bulgu)}</h2><div class="alt kucuk">${e(d.url)}</div></div></div>
    <div class="rozetler"><span class="rozet">${e(p.kategoriler[d.kategori] || d.kategori)}</span>
      <span class="rozet ${d.risk === "yuksek" ? "kotu" : ""}">${e(RISK[d.risk] || d.risk)}</span>${guvenRozet(d)}
      <span class="rozet ${d.durum === "uygulandi" ? "iyi" : d.durum === "gecersiz" || d.durum === "basarisiz" ? "kotu" : ""}">${e(d.durum_metni)}</span>
      <span class="rozet mono" title="Bulgu kodu ve dosya">${e(d.bulgu)}</span><span class="rozet">${e(d.dosya)}${d.konum ? ":" + e(d.konum.satir) : ""}</span></div>
    ${d.yer_tutucu ? `<div class="not-kutu" id="yer-tutucu">${ikon("triangle-alert")}<div><b>[doğrulanmalı]</b> yer tutucusu var. Değer elle doldurulmadan uygulanamaz; modelin bilmediği bir bilgi uydurulmaması için konuldu.</div></div>` : ""}
    ${d.durum === "gecersiz" ? `<div class="not-kutu kotu">${ikon("circle-alert")}<div>Doğrulamadan geçmedi, uygulanamaz: ${e(d.gecersiz_neden)}</div></div>` : ""}
    <p class="gerekce">${e(d.gerekce)}</p>
    ${d.durum_nedeni ? `<p class="soluk kucuk" style="margin-top:4px">${e(d.durum_nedeni)}</p>` : ""}
    ${(d.guven_nedenleri || []).length ? `<p class="kucuk" style="margin-top:4px;color:var(--warning)">${d.guven_nedenleri.map(e).join(" · ")}</p>` : ""}
    ${d.etki ? `<div class="not-kutu kotu" style="margin-top:8px">${ikon("triangle-alert")}<div><b>Olası etki:</b> ${e(d.etki)}</div></div>` : ""}
    ${(d.kaynaklar || []).length ? `<p class="kucuk soluk" style="margin-top:6px">Kaynak: ${d.kaynaklar.map((x) => e(x.id + (x.baslik ? " " + x.baslik : ""))).join(", ")}</p>` : ""}
    ${kapali ? "" : `<div class="karar-satiri">
      <button class="btn ${s.karar === "onay" ? "ana" : ""}" id="k-onay" title="Onayla (A)" aria-pressed="${s.karar === "onay"}">${ikon("check")}${d.durum === "uygulandi" ? "Yerinde kalsın" : "Onayla"}</button>
      <button class="btn ${s.karar === "ret" ? "tehlike" : ""}" id="k-ret" title="Reddet (R)" aria-pressed="${s.karar === "ret"}">${ikon("x")}${d.durum === "uygulandi" ? "Geri çek" : "Reddet"}</button>
      ${s.karar ? `<button class="btn sade" id="k-temizle">Kararı temizle</button>` : ""}
      ${s.karar === "ret" && model ? `<select id="k-neden" style="width:190px" aria-label="Ret nedeni" title="Öğrenme döngüsüne yazılır"><option value="">Ret nedeni (isteğe bağlı)</option>${S.retNedenleri.map((n) => `<option ${s.neden === n ? "selected" : ""}>${e(n)}</option>`).join("")}</select>` : ""}
      ${d.risk === "yuksek" ? `<label class="onay-kutu"><input type="checkbox" id="k-risk" ${s.risk ? "checked" : ""}>Olası etkiyi okudum, yüksek riski kabul ediyorum</label>` : ""}
    </div>
    ${d.duzenlenebilir ? `<label class="alan" style="margin-bottom:6px"><span>Yeni değer (düzenlenebilir)</span><textarea id="k-deger" rows="${Math.min(8, 1 + Math.ceil(String(s.deger ?? d.yeni ?? "").length / 90))}">${e(s.deger ?? d.yeni ?? "")}</textarea></label>` : ""}`}
    ${d.diff ? diffHtml(d.diff) : `<p class="soluk" style="margin-top:10px">Bu öneri için diff yok.</p>`}`;
  const kisayol = (fn) => { fn(); S.kirli = true; kuyrukCiz(); ayrintiCiz(); altCiz(); };
  const b = (id, fn) => { const x = document.getElementById(id); if (x) x.onclick = () => kisayol(fn); };
  b("k-onay", () => { s.karar = "onay"; });
  b("k-ret", () => { s.karar = "ret"; });
  b("k-temizle", () => { s.karar = null; });
  const n = $("#k-neden"); if (n) n.onchange = () => { s.neden = n.value || null; S.kirli = true; altCiz(); };
  const r = $("#k-risk"); if (r) r.onchange = () => { s.risk = r.checked; S.kirli = true; altCiz(); };
  const dg = $("#k-deger"); if (dg) dg.oninput = () => { s.deger = dg.value; S.kirli = true; altCiz(); };
}
function altCiz() {
  const k = $("#onay-alt"); if (!k) return;
  const p = S.plan;
  const v = Object.values(S.secimler);
  const uygulaAcik = !p.kilitli && !S.kirli && (p.onaylar_var || p.otomatik_var);
  k.innerHTML = `<span class="soluk">${v.filter((x) => x.karar === "onay").length} onay · ${v.filter((x) => x.karar === "ret").length} ret${S.kirli ? " · <b style='color:var(--warning);font-weight:500'>kaydedilmemiş kararlar var</b>" : ""}</span>
    <span class="bosluk"></span>
    <label class="onay-kutu" title="Tek tek onay gerektirmeyen tüm kural düzeltmelerini onayla"><input type="checkbox" id="kural-hepsi" ${S.kuralHepsi ? "checked" : ""} ${p.kilitli ? "disabled" : ""}>Kural düzeltmelerinin tümünü onayla</label>
    <button class="btn" id="kaydet" data-is ${p.kilitli || !S.kirli ? "data-kapali disabled" : ""} title="Kararları kaydet (Ctrl+S)">Kararları kaydet</button>
    <button class="btn ana" id="uygula" data-is ${uygulaAcik ? "" : "data-kapali disabled"} title="${S.kirli ? "Önce kararları kaydedin" : "Onaylı değişiklikleri siteye yaz"}">Onaylı aşamayı uygula</button>`;
  $("#kural-hepsi").onchange = (o) => { S.kuralHepsi = o.target.checked; S.kirli = true; altCiz(); };
  $("#kaydet").onclick = kararlariKaydet;
  $("#uygula").onclick = uygulaSor;
  isCiz();
}
async function kararlariKaydet() {
  await dene(async () => {
    const g = { klasor: S.planKlasor, secimler: S.secimler, kural_hepsi: S.kuralHepsi };
    let r = await api("/api/onayla", g);
    if (r.uyarilar) {
      if (!await sor("Uyarılar", r.uyarilar.join("\n\n") + "\n\nYine de kaydedilsin mi?", "Kaydet")) return;
      r = await api("/api/onayla", { ...g, zorla: true });
    }
    S.kirli = false; altCiz();
  });
}
async function uygulaSor() {
  await dene(async () => {
    const o = await api("/api/uygula/ozet?klasor=" + encodeURIComponent(S.planKlasor));
    const ileti = `${o.yazilacak} değişiklik siteye yazılacak${o.geri_cekilecek ? `, otomatik aşamada yazılmış ${o.geri_cekilecek} değişiklik geri çekilecek` : ""}.\n${o.kok}\n\n` +
      (o.zaten ? `Otomatik aşamada ${o.zaten} değişiklik zaten yazıldı.\n\n` : "") +
      "İlk yazmadan önce tam yedek alınır; Sonuçlar ekranından geri alınabilir. Ardından site yeniden taranır. Bu işlem yarıda kesilemez.";
    if (await sor("Siteye yazılsın mı?", ileti, "Siteye yaz", true)) await api("/api/uygula", { klasor: S.planKlasor });
  });
}
EKRANLAR.onay = async function () {
  const sayfa = $("#sayfa");
  if (S.planKlasor && !S.plan) await dene(() => planYukle(S.planKlasor));
  const p = S.plan;
  if (!p) {
    sayfa.innerHTML = `<div style="padding:24px"><h1>Onay</h1><div class="bos" style="margin-top:18px"><h2>Onaylanacak plan yok</h2><p>Önce yönetici modunda bir tarama yapın ya da Sonuçlar ekranından bir plan açın.</p><button class="btn ana" id="bos-git">Analize git</button></div></div>`;
    $("#bos-git").onclick = () => git("analiz");
    return;
  }
  const l = sekmeListesi(p), f = S.filtre;
  const elleMi = S.sekme === "elle";
  sayfa.innerHTML = `<div class="onay-ust">
      <div class="baslik-satiri"><div><h1>Onay</h1><div class="alt">${e(p.bilgi.site)} · ${e(p.bilgi.zaman)} · güven eşiği ${guvenMetni(p.esik)}${p.kilitli ? " · bu plan kilitli, kararlar yalnızca görüntülenir" : ""}</div></div></div>
      <div class="sekmeler" role="tablist">
        ${[["bekleyen", "Bekleyen", l.bekleyen.length], ["uygulanan", "Uygulanan", l.uygulanan.length], ["diger", "Geçersiz ve diğer", l.diger.length], ["elle", "Elle düzeltilir", p.elle.length]].map(([k, a, n]) => `<button role="tab" data-sekme="${k}" aria-selected="${S.sekme === k}">${a}<span class="sayi">${n}</span></button>`).join("")}
      </div></div>
    ${elleMi ? `<div class="elle-liste"><table><thead><tr><th>Bulgu</th><th>Yapılması gereken</th><th class="sag">Sayfa</th></tr></thead><tbody>${p.elle.map((x) => `<tr><td>${e(x.bulgu_aciklamasi)}</td><td>${e(x.duzeltme)}</td><td class="sag">${(x.sayfalar || []).length}</td></tr>`).join("")}</tbody></table></div>` : `
    <div class="onay-govde">
      <div class="kuyruk">
        <div class="filtre">
          <input type="search" id="f-ara" placeholder="Ara: kimlik, bulgu, dosya, metin ( / )" value="${e(f.ara)}" aria-label="Ara">
          <select id="f-kategori" aria-label="Kategori"><option value="">Kategori</option>${Object.entries(p.kategoriler).filter(([k]) => k !== "elle").map(([k, a]) => `<option value="${k}" ${f.kategori === k ? "selected" : ""}>${e(a)}</option>`).join("")}</select>
          <select id="f-risk" aria-label="Risk"><option value="">Risk</option>${Object.entries(RISK).map(([k, a]) => `<option value="${k}" ${f.risk === k ? "selected" : ""}>${a}</option>`).join("")}</select>
          <select id="f-guven" aria-label="Güven"><option value="">Güven</option><option value="dusuk" ${f.guven === "dusuk" ? "selected" : ""}>Eşik altı</option><option value="yuksek" ${f.guven === "yuksek" ? "selected" : ""}>Eşik üstü</option><option value="yer" ${f.guven === "yer" ? "selected" : ""}>Doğrulanmalı</option></select>
        </div>
        <div class="kuyruk-liste" id="kuyruk-liste" role="listbox" aria-label="Öneriler"></div>
      </div>
      <div class="ayrinti" id="ayrinti"></div>
    </div>`}
    <div class="onay-alt" id="onay-alt"></div>`;
  $$("[data-sekme]").forEach((b) => { b.onclick = () => { S.sekme = b.dataset.sekme; S.secili = null; ciz(); }; });
  for (const a of ["kategori", "risk", "guven"]) { const x = document.getElementById("f-" + a); if (x) x.onchange = () => { f[a] = x.value; kuyrukCiz(); }; }
  const ara = $("#f-ara"); if (ara) ara.oninput = () => { f.ara = ara.value; kuyrukCiz(); };
  if (!elleMi) {
    if (!S.secili) { const ilk = suzgec(l[S.sekme] || [])[0]; S.secili = ilk ? ilk.id : null; }
    kuyrukCiz(); ayrintiCiz();
  }
  altCiz();
};
function sira(yon) {
  const liste = $$(".satir").map((b) => b.dataset.id); if (!liste.length) return;
  const i = liste.indexOf(S.secili);
  sec(liste[Math.max(0, Math.min(liste.length - 1, i + yon))]);
}

// ---- Sonuclar
EKRANLAR.sonuclar = async function () {
  if (!S.sonuclar) { const r = await dene(() => api("/api/sonuclar")); S.sonuclar = r ? r.liste : []; }
  const q = S.ara.toLocaleLowerCase("tr");
  const liste = S.sonuclar.filter((x) => (!S.deneyGizle || x.tur !== "Deney") && (!q || (x.site + " " + x.zaman + " " + x.tur + " " + x.durum).toLocaleLowerCase("tr").includes(q)));
  const x = S.sonuclar.find((y) => y.klasor === S.sonucSecili);
  const yolu = (r) => (r.puanlar.length ? r.puanlar.map((p) => p.puan ?? "—").join(" → ") : "—");
  $("#sayfa").innerHTML = `<div class="sonuc-ust"><div class="baslik-satiri" style="margin-bottom:10px"><div><h1>Sonuçlar</h1><div class="alt">${liste.length} tarama · puan ve çözüm oranı yönetici raporundan</div></div>
      <div class="eylemler"><button class="btn" id="yenile" title="Listeyi yenile">${ikon("refresh-cw")}Yenile</button></div></div>
      <div class="araclar"><input type="search" id="s-ara" placeholder="Site, tarih, durum ara" value="${e(S.ara)}" aria-label="Sonuç ara">
        <label class="onay-kutu"><input type="checkbox" id="s-deney" ${S.deneyGizle ? "checked" : ""}>Deney klasörlerini gizle</label>
        <button class="btn" id="s-karsilastir" ${S.karsilastir.length === 2 ? "" : "disabled"} title="İşaretli iki taramayı yan yana göster">${ikon("git-compare")}Karşılaştır (${S.karsilastir.length}/2)</button></div></div>
    <div class="sonuc-tablo">${liste.length ? `<table><thead><tr><th style="width:30px"></th><th>Tarih</th><th>Site</th><th>Tür</th><th>Durum</th><th class="sag">Puan</th><th class="sag">Çözüm oranı</th><th class="sag">Aktif</th></tr></thead><tbody>
      ${liste.map((r) => `<tr class="secilebilir" data-k="${e(r.klasor)}" aria-selected="${r.klasor === S.sonucSecili}"><td><input type="checkbox" class="kars" aria-label="Karşılaştırmaya ekle" ${S.karsilastir.includes(r.klasor) ? "checked" : ""} ${r.puanlar.length ? "" : "disabled"}></td>
        <td>${e(r.zaman)}</td><td>${e(r.site)}</td><td>${e(r.tur)}</td><td><span class="rozet ${r.durum.includes("uygulandı") ? "iyi" : r.durum === "geri alındı" ? "" : ""}">${e(r.durum)}</span></td>
        <td class="sag">${yolu(r)}</td><td class="sag">${r.cozum_orani === null ? "—" : yuzde(r.cozum_orani)}</td><td class="sag">${r.sayaclar ? e(r.sayaclar.aktif) : "—"}</td></tr>`).join("")}</tbody></table>`
      : `<div class="bos" style="margin:10px"><h2>Henüz tarama yok</h2><p>İlk taramanız burada listelenir.</p></div>`}</div>
    <div class="sonuc-alt" id="sonuc-alt"></div>`;
  $("#yenile").onclick = () => { S.sonuclar = null; ciz(); };
  const a = $("#s-ara"); a.oninput = () => { S.ara = a.value; clearTimeout(S.araZaman); S.araZaman = setTimeout(async () => { await ciz(); const y = $("#s-ara"); y.focus(); y.setSelectionRange(y.value.length, y.value.length); }, 150); };
  $("#s-deney").onchange = (o) => { S.deneyGizle = o.target.checked; ciz(); };
  $("#s-karsilastir").onclick = karsilastirCiz;
  $$("tr[data-k]").forEach((t) => {
    t.onclick = (o) => {
      if (o.target.classList.contains("kars")) {
        const k = t.dataset.k;
        S.karsilastir = o.target.checked ? [...S.karsilastir, k].slice(-2) : S.karsilastir.filter((y) => y !== k);
        ciz(); return;
      }
      S.sonucSecili = t.dataset.k; S.rapor = null; ciz();
    };
  });
  altSonucCiz(x);
};
async function altSonucCiz(x) {
  const k = $("#sonuc-alt");
  if (!x) { k.innerHTML = `<div class="bos" style="margin:18px 24px;border:0"><h2>Bir tarama seçin</h2><p>Raporu burada açılır.</p></div>`; return; }
  const g = await dene(() => api("/api/geri-al/bilgi?klasor=" + encodeURIComponent(x.klasor)));
  if (!S.rapor || !x.raporlar.some((r) => r.dosya === S.rapor)) S.rapor = x.raporlar[0] ? x.raporlar[0].dosya : null;
  k.innerHTML = `<div class="sonuc-alt-ust">
      <div class="sekmeler" role="tablist" style="border:0">${x.raporlar.map((r) => `<button role="tab" data-rapor="${e(r.dosya)}" aria-selected="${r.dosya === S.rapor}">${e(r.ad)}</button>`).join("")}</div>
      <span class="bosluk" style="flex:1"></span>
      ${x.tur === "Yönetici" ? `<button class="btn" id="s-plan">${ikon("check-check")}Planı aç</button>` : ""}
      <button class="btn" id="s-klasor">${ikon("folder-open")}Klasör</button>
      <button class="btn tehlike" id="s-geri" data-is ${g && g.alinabilir ? "" : "data-kapali disabled"} title="${g && g.alinabilir ? `${e(g.site)}: son uygulama ${e(g.zaman)} (${e(g.sonuc)})` : "Bu site için geri alınacak uygulama yok"}">${ikon("undo-2")}Son uygulamayı geri al</button></div>
    ${S.rapor ? `<iframe id="rapor-cerceve" title="Rapor" src="/rapor?klasor=${encodeURIComponent(x.klasor)}&dosya=${encodeURIComponent(S.rapor)}"></iframe>` : `<div class="bos" style="margin:0 24px 18px"><h2>Bu klasörde rapor yok</h2><p>Tarama yarıda kalmış ya da bir deneyin parçası olabilir.</p></div>`}`;
  $$("[data-rapor]", k).forEach((b) => { b.onclick = () => { S.rapor = b.dataset.rapor; altSonucCiz(x); }; });
  const pl = $("#s-plan"); if (pl) pl.onclick = () => dene(async () => { await api("/api/plan/sec", { klasor: x.klasor }); await planYukle(x.klasor); S.sekme = "bekleyen"; git("onay"); });
  $("#s-klasor").onclick = () => dene(() => api("/api/klasor-ac", { klasor: x.klasor }));
  $("#s-geri").onclick = () => geriAl(x, g);
  isCiz();
}
async function geriAl(x, g) {
  if (!await sor("Son uygulama geri alınsın mı?", `${g.sonuc} uygulamasıyla yazılan dosyalar yedekten geri yüklenecek:\n${g.kok}`, "Geri al", true)) return;
  await dene(() => api("/api/geri-al", { klasor: x.klasor }));
}
function karsilastirCiz() {
  const [a, b] = S.karsilastir.map((k) => S.sonuclar.find((x) => x.klasor === k));
  if (!a || !b) return;
  const satir = (ad, fn) => `<tr><td>${ad}</td><td class="sag">${fn(a)}</td><td class="sag">${fn(b)}</td></tr>`;
  const say = (k) => (r) => (r.sayilar && r.sayilar[k] !== undefined ? r.sayilar[k] : "—");
  $("#sonuc-alt").innerHTML = `<div class="karsilastir"><h2 style="margin-bottom:6px">Karşılaştırma</h2><table><thead><tr><th>Ölçü</th><th class="sag">${e(a.site)} · ${e(a.zaman)}</th><th class="sag">${e(b.site)} · ${e(b.zaman)}</th></tr></thead><tbody>
    ${satir("Puan yolu", (r) => r.puanlar.map((p) => p.puan ?? "—").join(" → "))}${satir("Çözüm oranı", (r) => `${yuzde(r.cozum_orani)} (${r.cozulen}/${r.cozulebilir})`)}
    ${satir("Aktif", (r) => (r.sayaclar ? r.sayaclar.aktif : "—"))}${satir("Çözülen otomatik", say("cozuldu_otomatik"))}${satir("Çözülen onaylı", say("cozuldu_onayli"))}
    ${satir("Onay bekliyor", say("onay_bekliyor"))}${satir("Başarısız", say("basarisiz"))}${satir("Elle düzeltilir", say("elle"))}</tbody></table></div>`;
}

// ---- Test sitesi
EKRANLAR.test = async function () {
  const d = S.durum || {}, pt = S.ayar.test_portu;
  if (!S.sonuclar) { const r = await dene(() => api("/api/sonuclar")); S.sonuclar = r ? r.liste : []; }
  const yon = S.sonuclar.filter((x) => x.site === "127.0.0.1" && x.tur === "Yönetici").sort((a, b) => (b.durum.includes("uygulandı") ? 1 : 0) - (a.durum.includes("uygulandı") ? 1 : 0));
  if (!yon.some((x) => x.klasor === S.degKlasor)) S.degKlasor = yon[0] ? yon[0].klasor : "";
  const sec = yon.find((x) => x.klasor === S.degKlasor);
  const degRapor = sec && sec.raporlar.some((r) => r.dosya === "degerlendirme.md");
  const islem = (id, ad, aciklama, sinif = "", ek = "") => `<div class="islem"><div><h3>${ad}</h3><p>${aciklama}</p></div><button class="btn ${sinif}" id="${id}" data-is ${ek}>${ad}</button></div>`;
  $("#sayfa").innerHTML = `<div class="baslik-satiri"><div><h1>Test sitesi</h1><div class="alt"><span class="rozet ${d.test ? "iyi" : ""}" id="test-rozet">${d.test ? "Çalışıyor" : "Durdu"}</span> &nbsp;http://127.0.0.1:${e(pt)}/${d.test && !d.test_bizim ? " · bu uygulama dışında başlatıldı" : ""}</div></div>
      <div class="eylemler">
        <button class="btn ana" id="t-baslat" ${d.test ? "disabled" : ""}>${ikon("play")}Başlat</button>
        <button class="btn" id="t-durdur" ${d.test_bizim ? "" : "disabled"}>${ikon("square")}Durdur</button>
        <button class="btn" id="t-ac" ${d.test ? "" : "disabled"}>${ikon("external-link")}Tarayıcıda aç</button></div></div>
    <div class="liste-izgara"><section><h2>Site işlemleri</h2>
      ${islem("t-dogrula", "Doğrula", "Kayıtlı 47 sorunun sitede gerçekten var olduğunu denetler. Sunucu açık olmalı.")}
      ${islem("t-hash", "Hash karşılaştır", "Siteyi değiştirmeden orijinal kopyayla karşılaştırır.")}
      ${islem("t-sifirla", "Sıfırla", "Siteyi sorunlu orijinal haline döndürür ve hash'leri doğrular. Uygulanmış düzeltmeler silinir.", "tehlike")}
    </section><section><h2>Değerlendir</h2>
      <div class="islem" style="grid-template-columns:1fr"><label class="alan"><span>Yönetici modu sonucu</span><select id="t-deg-sec" ${yon.length ? "" : "disabled"}>${yon.length ? yon.map((x) => `<option value="${e(x.klasor)}" ${x.klasor === S.degKlasor ? "selected" : ""}>${e(x.zaman)} · ${e(x.durum)}</option>`).join("") : "<option>Henüz sonuç yok</option>"}</select></label>
        <p>Uygulanmış sonuçlar önce gelir. Araç, sonucu kayıtlı 47 sorunla karşılaştırır.</p>
        <div class="eylemler" style="justify-content:flex-start"><button class="btn" id="t-deg" data-is ${yon.length ? "" : "data-kapali disabled"}>Değerlendir</button>
        <button class="btn" id="t-deg-rapor" ${degRapor ? "" : "disabled"}>${ikon("file-text")}Raporu aç</button></div></div>
    </section></div>${gunlukHtml("Günlük")}`;
  const sunucu = (islem_) => dene(() => api("/api/sunucu", { ad: "test", islem: islem_ }));
  $("#t-baslat").onclick = () => sunucu("baslat");
  $("#t-durdur").onclick = () => sunucu("durdur");
  $("#t-ac").onclick = () => dene(() => api("/api/tarayicida-ac", { hedef: "test" }));
  $("#t-dogrula").onclick = () => dene(() => api("/api/test/dogrula", {}));
  $("#t-hash").onclick = () => dene(() => api("/api/test/hash_karsilastir", {}));
  $("#t-sifirla").onclick = async () => { if (await sor("Test sitesi sıfırlansın mı?", "test_sitesi/site/ klasörü orijinal sorunlu kopyayla değiştirilecek. Uygulanmış düzeltmeler silinir (sonuç klasörlerindeki yedekler kalır).", "Sıfırla", true)) dene(() => api("/api/test/sifirla", {})); };
  $("#t-deg-sec").onchange = (o) => { S.degKlasor = o.target.value; ciz(); };
  $("#t-deg").onclick = () => dene(() => api("/api/test/degerlendir", { klasor: S.degKlasor }));
  $("#t-deg-rapor").onclick = () => { S.sonucSecili = S.degKlasor; S.rapor = "degerlendirme.md"; git("sonuclar"); };
  gunlukBagla();
};

// ---- Bilgi tabani
EKRANLAR.bilgi = async function () {
  const b = await dene(() => api("/api/bilgi-tabani"));
  if (!b) { $("#sayfa").innerHTML = `<h1>Bilgi tabanı</h1><div class="bos" style="margin-top:18px"><h2>Okunamadı</h2><p>Ayarlar ekranından proje klasörünü denetleyin.</p></div>`; return; }
  const model = S.ayar.gomme_modeli, onb = b.onbellek[model];
  const guncel = onb === b.parca;
  const kal = Object.entries(b.kalibrasyon);
  $("#sayfa").innerHTML = `<div class="baslik-satiri"><div><h1>Bilgi tabanı</h1><div class="alt">Modelin yazarken dayandığı yönergeler. İçerik elle güncellenir; bu ekran yalnızca durumu gösterir.</div></div>
      <div class="eylemler"><button class="btn" id="b-gomme" data-is title="Yalnızca değişen parçaların gömmesini hesaplar; LM Studio açık olmalı">${ikon("refresh-cw")}Gömme önbelleğini yenile</button></div></div>
    <div class="sayilar3">
      <div class="kart"><div class="ad">Parça</div><div class="deger">${b.parca}</div><div class="not">${b.alanlar.length} konu alanı</div></div>
      <div class="kart"><div class="ad">Few-shot örnek</div><div class="deger">${b.ornek}</div><div class="not">isteme en fazla 2 örnek girer</div></div>
      <div class="kart"><div class="ad">Gömme önbelleği</div><div class="deger" style="color:${guncel ? "inherit" : "var(--warning)"}">${onb ?? 0}/${b.parca}</div><div class="not">${guncel ? "güncel" : "yenilenmeli"} · ${e(model || "model seçilmedi")}</div></div>
      <div class="kart"><div class="ad">Kullanıcı kararı</div><div class="deger">${b.geri_bildirim}</div><div class="not">öğrenme döngüsü kaydı</div></div>
    </div>
    <div class="liste-izgara bolum"><section><h2>Konu alanları</h2><table><thead><tr><th>Alan</th><th class="sag">Parça</th></tr></thead><tbody>${b.alanlar.map(([a, n]) => `<tr><td>${e(a)}</td><td class="sag">${n}</td></tr>`).join("")}</tbody></table></section>
    <section><h2>Kaynaklar</h2><table><thead><tr><th>Site</th><th class="sag">Parça</th></tr></thead><tbody>${b.kaynaklar.map(([a, n]) => `<tr><td>${e(a)}</td><td class="sag">${n}</td></tr>`).join("")}</tbody></table>
      <dl class="ozellikler" style="margin:14px 0 0"><dt>Son erişim tarihi</dt><dd>${tireli(b.son_erisim)}</dd><dt>En eski erişim</dt><dd>${tireli(b.ilk_erisim)}</dd><dt>En eski kaynak güncellemesi</dt><dd>${tireli(b.en_eski_kaynak)}</dd></dl>
      <h2 style="margin:22px 0 8px">Güven kalibrasyonu</h2>
      ${kal.length ? `<table><thead><tr><th>Alan</th><th class="sag">Karar</th><th class="sag">Doğruluk</th><th class="sag">Alt sınır</th></tr></thead><tbody>${kal.map(([a, o]) => `<tr><td>${e(a)}</td><td class="sag">${o.n}</td><td class="sag">${yuzde(o.oran)}</td><td class="sag">${String(o.alt_sinir).replace(".", ",")}</td></tr>`).join("")}</tbody></table>` : `<p class="soluk">Henüz ölçüm yok. Ölçülene kadar model önerileri onay ister.</p>`}
    </section></div>${gunlukHtml("Günlük")}`;
  $("#b-gomme").onclick = () => dene(() => api("/api/bilgi-tabani/gomme", {}));
  gunlukBagla();
};

// ---- Ayarlar
EKRANLAR.ayarlar = async function () {
  const a = S.ayar, d = S.durum || {};
  const alan = (k, ad, ipucu = "") => `<label class="alan"><span>${ad}</span><input type="text" id="a-${k}" value="${e(a[k])}" spellcheck="false" title="${e(ipucu)}"></label>`;
  const bol = (b, ac, ic) => `<section class="ayar-bolum"><div><h2>${b}</h2><p>${ac}</p></div><div class="ayar-alanlar">${ic}</div></section>`;
  const hata = S.ayarHatalari && S.ayarHatalari.length ? `<div class="not-kutu kotu" style="margin-bottom:14px">${ikon("circle-alert")}<div>${S.ayarHatalari.map(e).join("<br>")}</div></div>` : "";
  $("#sayfa").innerHTML = `<div class="baslik-satiri"><div><h1>Ayarlar</h1><div class="alt kucuk">${e(S.ayarDosyasi)}</div></div>
      <div class="eylemler"><button class="btn" id="a-varsayilan">Varsayılanlar</button><button class="btn ana" id="a-kaydet">Kaydet</button></div></div>
    ${hata}
    ${bol("Proje", "yonet.py'nin bulunduğu klasör. Betikler ve sonuçlar buradan okunur.", `<label class="alan"><span>Proje klasörü</span><span class="yan" style="font-weight:400"><input type="text" id="a-proje_koku" value="${e(a.proje_koku)}" spellcheck="false"><button class="btn" id="a-gozat" type="button">${ikon("folder-open")}Gözat</button></span></label>`)}
    ${bol("Dil modeli", "Yalnızca bu makinedeki LM Studio kullanılır.", alan("lm_url", "LM Studio adresi") + alan("sohbet_modeli", "Varsayılan sohbet modeli") + alan("gomme_modeli", "Varsayılan gömme modeli"))}
    ${bol("Varsayılan site", "Analiz ekranında hazır gelir.", alan("site_url", "Site adresi") + alan("site_koku", "Site kök klasörü"))}
    ${bol("Yerel sunucular", "Yalnızca 127.0.0.1'de çalışır.", alan("test_portu", "Test sitesi portu") + alan("web_portu", "Tarayıcı arayüzü portu") + `<div class="eylemler" style="justify-content:flex-start"><button class="btn" id="a-web-baslat" ${d.web ? "disabled" : ""}>${ikon("play")}Tarayıcı arayüzünü başlat</button><button class="btn" id="a-web-durdur" ${d.web_bizim ? "" : "disabled"}>${ikon("square")}Durdur</button><button class="btn" id="a-web-ac" ${d.web ? "" : "disabled"}>${ikon("external-link")}Aç</button></div>`)}
    ${bol("Görünüm ve ses", "", `<div class="bolumlu" role="group" aria-label="Tema"><button id="a-acik" aria-pressed="${S.tema === "acik"}">Açık</button><button id="a-koyu" aria-pressed="${S.tema === "koyu"}">Koyu</button></div><label class="onay-kutu"><input type="checkbox" id="a-ses" ${a.ses ? "checked" : ""}>İş bitince, hata olunca ses çal</label>`)}`;
  const kaydetVeri = () => { const v = {}; for (const k of ["proje_koku", "lm_url", "sohbet_modeli", "gomme_modeli", "site_url", "site_koku", "test_portu", "web_portu"]) v[k] = document.getElementById("a-" + k).value; v.ses = $("#a-ses").checked; return v; };
  $("#a-kaydet").onclick = () => dene(async () => { const r = await api("/api/ayarlar", kaydetVeri()); S.ayar = r.ayar; S.ayarHatalari = []; S.form = null; ciz(); });
  $("#a-varsayilan").onclick = async () => { const proje = $("#a-proje_koku").value; S.ayar = { ...S.varsayilan, proje_koku: proje }; ciz(); };
  $("#a-gozat").onclick = () => klasorSec((v) => { $("#a-proje_koku").value = v; });
  $("#a-acik").onclick = () => { temaUygula("acik"); ciz(); };
  $("#a-koyu").onclick = () => { temaUygula("koyu"); ciz(); };
  const web = (i) => dene(async () => { await api("/api/sunucu", { ad: "web", islem: i }); });
  $("#a-web-baslat").onclick = () => web("baslat");
  $("#a-web-durdur").onclick = () => web("durdur");
  $("#a-web-ac").onclick = () => dene(() => api("/api/tarayicida-ac", { hedef: "web" }));
};

// ---- kisayollar
document.addEventListener("keydown", (o) => {
  if ($("#modal-kok").firstChild) return;
  if (o.ctrlKey && /^[1-6]$/.test(o.key)) { o.preventDefault(); git(MENU[+o.key - 1][0]); return; }
  if (o.ctrlKey && (o.key === "d" || o.key === "D")) { o.preventDefault(); temaUygula(S.tema === "koyu" ? "acik" : "koyu"); ciz(); return; }
  if (S.ekran !== "onay") return;
  if (o.ctrlKey && (o.key === "s" || o.key === "S")) { o.preventDefault(); if (S.kirli && !(S.durum && S.durum.is)) kararlariKaydet(); return; }
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(o.target.tagName)) return;
  const k = o.key.toLowerCase();
  if (k === "j" || o.key === "ArrowDown") { o.preventDefault(); sira(1); }
  else if (k === "k" || o.key === "ArrowUp") { o.preventDefault(); sira(-1); }
  else if (k === "a") { const b = $("#k-onay"); if (b) b.click(); }
  else if (k === "r") { const b = $("#k-ret"); if (b) b.click(); }
  else if (o.key === "/") { o.preventDefault(); const a = $("#f-ara"); if (a) a.focus(); }
});

// ---- baslangic
async function baslat() {
  const svgler = await Promise.all(IKONLAR.map(async (ad) => {
    const m = await (await fetch(`/varlik/ikonlar/${ad}.svg`)).text();
    const ic = m.slice(m.indexOf(">", m.indexOf("<svg")) + 1, m.lastIndexOf("</svg>"));
    return `<symbol id="i-${ad}" viewBox="0 0 24 24">${ic}</symbol>`;
  }));
  $("#sprite").innerHTML = svgler.join("");
  const b = await api("/api/baslangic");
  S.jeton = b.jeton; S.ayar = b.ayar; S.retNedenleri = b.ret_nedenleri; S.ayarDosyasi = b.ayar_dosyasi; S.varsayilan = b.varsayilan; S.ayarHatalari = b.hatalar;
  temaUygula(b.ayar.tema || (matchMedia("(prefers-color-scheme: dark)").matches ? "koyu" : "acik"), false);
  $("#tema-dugmesi").onclick = () => { temaUygula(S.tema === "koyu" ? "acik" : "koyu"); if (S.ekran === "ayarlar") ciz(); };
  if (b.plan_klasoru) await dene(() => planYukle(b.plan_klasoru));
  await api("/api/durum?son=0").then((d) => { S.durum = d; S.biten = d.biten; durumCiz(d); });
  window.addEventListener("hashchange", rotaOku);
  if (b.hatalar.length && !location.hash) location.hash = "#/ayarlar"; else rotaOku();
  yokla();
}
window.SEO = S;      // oto-test durumu okur
baslat();
