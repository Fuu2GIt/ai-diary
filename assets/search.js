// 記事の全文検索とタグ絞り込み（search.json を読み込んでブラウザ内で絞り込む）
(function () {
  var input = document.getElementById("search-input");
  var results = document.getElementById("search-results");
  var status = document.getElementById("search-status");
  var staticList = document.getElementById("post-list-static");
  if (!input || !results) return;

  var data = null;
  var params = new URLSearchParams(location.search);
  var activeTag = params.get("tag") || "";
  if (params.get("q")) input.value = params.get("q");
  var TAG_CLASS = {
    openai: "openai", chatgpt: "openai", xai: "xai", grok: "xai", "grok bot": "xai",
    anthropic: "anthropic", claude: "anthropic", nvidia: "nvidia",
    google: "google", gemini: "google", deepmind: "google", meta: "meta", llama: "meta",
    "政策": "policy", "政策・規制": "policy", "規制": "policy", policy: "policy"
  };

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function tagHtml(name) {
    var cls = TAG_CLASS[name.toLowerCase()] || "other";
    return '<span class="tag tag-' + cls + '">' + esc(name) + "</span>";
  }
  function norm(s) { return String(s).toLowerCase().normalize("NFKC"); }
  function byDateDesc(a, b) {
    if (a.date === b.date) return 0;
    return a.date < b.date ? 1 : -1;
  }

  function snippet(text, terms) {
    var t = norm(text), at = -1;
    for (var i = 0; i < terms.length && at < 0; i++) at = t.indexOf(terms[i]);
    if (at < 0) return esc(text.slice(0, 90)) + (text.length > 90 ? "…" : "");
    var start = Math.max(0, at - 30), end = Math.min(text.length, at + 70);
    var part = esc(text.slice(start, end));
    terms.forEach(function (w) {
      if (!w) return;
      var re = new RegExp(w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
      part = part.replace(re, function (m) { return "<mark>" + m + "</mark>"; });
    });
    return (start > 0 ? "…" : "") + part + (end < text.length ? "…" : "");
  }

  function markTagButtons() {
    document.querySelectorAll(".tag-filter").forEach(function (a) {
      a.classList.toggle("is-active", a.getAttribute("data-tag") === activeTag);
    });
  }

  function showStatic() {
    results.hidden = true;
    results.innerHTML = "";
    status.hidden = true;
    status.textContent = "";
    if (staticList) staticList.hidden = false;
  }

  function render() {
    markTagButtons();
    var q = input.value.trim();
    if (!q && !activeTag) {
      showStatic();
      return;
    }
    if (!data) { status.hidden = false; status.textContent = "読み込み中…"; return; }
    var terms = norm(q).split(/\s+/).filter(Boolean);
    var hits = data.filter(function (p) {
      if (activeTag && p.tags.indexOf(activeTag) < 0) return false;
      if (!terms.length) return true;
      var hay = norm(p.title + " " + p.tags.join(" ") + " " + p.text);
      return terms.every(function (w) { return hay.indexOf(w) >= 0; });
    }).sort(byDateDesc);
    if (staticList) staticList.hidden = true;
    results.hidden = false;
    status.hidden = false;
    var label = [];
    if (activeTag) label.push('タグ ' + tagHtml(activeTag));
    if (q) label.push("「" + esc(q) + "」");
    status.innerHTML = label.join(" ＋ ") + " の記事：" + hits.length + "件" +
      ' <button type="button" class="search-clear">条件をクリア</button>';
    results.innerHTML = hits.length ? hits.map(function (p) {
      var body = '<time datetime="' + p.date + '">' + p.date + "</time>" +
        '<a href="' + esc(p.url) + '">' + esc(p.title) + "</a>" +
        (q ? '<p class="search-snippet">' + snippet(p.text, terms) + "</p>" : "") +
        (p.tags.length ? '<span class="post-tags">' + p.tags.map(tagHtml).join("") + "</span>" : "");
      if (!p.thumb) return "<li>" + body + "</li>";
      return '<li class="has-thumb"><a class="post-thumb" href="' + esc(p.url) + '" tabindex="-1">' +
        '<img src="' + esc(p.thumb) + '" alt="' + esc(p.title) + '" width="320" height="180" loading="lazy" decoding="async"></a>' +
        '<div class="post-body">' + body + "</div></li>";
    }).join("") : '<li class="search-empty">見つかりませんでした。別の言葉で試してみてください。</li>';
  }

  status.addEventListener("click", function (e) {
    if (e.target.classList.contains("search-clear")) {
      input.value = ""; activeTag = "";
      history.replaceState(null, "", location.pathname + "#latest");
      render();
    }
  });
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest(".tag-filter");
    if (!a) return;
    e.preventDefault();
    var tag = a.getAttribute("data-tag");
    activeTag = activeTag === tag ? "" : tag;
    history.replaceState(null, "", activeTag ? "?tag=" + encodeURIComponent(activeTag) + "#latest" : location.pathname + "#latest");
    render();
    document.getElementById("latest").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  input.addEventListener("input", render);

  fetch("search.json", { cache: "no-cache" })
    .then(function (r) { return r.json(); })
    .then(function (json) { data = json; render(); })
    .catch(function () { data = []; render(); });
  render();
})();
