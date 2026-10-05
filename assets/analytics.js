// Cloudflare Web Analytics。Google Analytics は使わない。
// 発行したビーコン トークンで {{CF_BEACON_TOKEN}} を手動で差し替える（実値はチャットや Issue に貼らない）。
(function () {
  var token = "{{CF_BEACON_TOKEN}}";
  if (!token || token.indexOf("{{") !== -1) return;

  var script = document.createElement("script");
  script.defer = true;
  script.src = "https://static.cloudflareinsights.com/beacon.min.js";
  script.setAttribute("data-cf-beacon", JSON.stringify({ token: token }));
  document.body.appendChild(script);
})();
