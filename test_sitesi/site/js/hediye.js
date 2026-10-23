(function () {
  var kok = document.getElementById("app");
  fetch("/veri/hediye.json").then(function (r) { return r.json(); }).then(function (veri) {
    var h = '<header class="ust"><a class="logo" href="/">Çaylıbahçe</a></header><main>';
    h += "<h1>" + veri.baslik + "</h1><p>" + veri.giris + "</p>";
    veri.paketler.forEach(function (p) {
      h += '<article class="kart"><h2>' + p.ad + "</h2><p>" + p.aciklama + "</p><p class=\"fiyat\">Fiyat: " +
        p.fiyat + '</p><p>İçindeki çaylar: ' + p.icerik.map(function (c) {
          return '<a href="' + c.adres + '">' + c.ad + "</a>"; }).join(", ") + "</p></article>";
    });
    kok.innerHTML = h + "<p>" + veri.kapanis + "</p></main>";
  });
})();
