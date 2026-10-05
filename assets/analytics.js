// Cloudflare Web Analytics。Google Analytics は使わない。
// ビーコン トークンはここにだけ置く。チャットや公開 Issue には貼らない。
(function () {
  var token = "39db5b3b944d47a0a31784b1eb004b62";
  if (!token) return;

  var script = document.createElement("script");
  script.type = "module";
  script.src = "https://static.cloudflareinsights.com/beacon.min.js";
  script.setAttribute("data-cf-beacon", JSON.stringify({ token: token }));
  document.body.appendChild(script);
})();
