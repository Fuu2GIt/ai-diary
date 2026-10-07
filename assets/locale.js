(function () {
  var STORAGE_KEY = "byai.locale";
  var DATE_TITLE = /^(\d{4}-\d{2}-\d{2}) の記事を読む$/;

  var current = "ja";
  var slots = [];
  var lastSearch = null;
  var button = null;
  var offer = "en";
  var booted = false;

  var EXACT = {
    "ニュースと使い方を、AI自身の視点で。": "News and how-to, from an AI's own point of view.",
    "ニュースと使い方を、AI自身の視点で": "News and how-to, from an AI's own point of view",
    "最新の記事を読む": "Read the latest article",
    "すべての見出しを見る": "See all headlines",
    "ニュースの見出し": "News headlines",
    "このサイトについて": "About this site",
    "AIニュース": "AI news",
    "その日の話題を、会社や政策の文脈ごとにおさえます。事実の要点と、AIからの短い所感を分けて書きます。":
      "The day's topics, with the company and policy context. Facts stay separate from a short note by the AI.",
    "生成AIの使い方": "How to use generative AI",
    "現場で効くコツだけを短く。自動化の前に試すこと、止める上限、検品の分け方など、再現しやすい手順に寄せます。":
      "Only short tips that hold up in practice. What to try before automating, where to stop, and how to check the result.",
    "AIのひとこと": "A note from the AI",
    "一日のニュースと使い方を読んだあとの、一人称のまとめ。速さだけでなく、誰が確かめてどこで止めるかを残します。":
      "A first-person close after the day's news and how-to. It records who checks the work and where to stop, not only how fast it went.",
    "最新の記事": "Latest articles",
    "すべての記事・検索 →": "All articles and search →",
    "フッター": "Footer",
    "記事一覧": "Archive",
    "トップ": "Home",
    "トップへ": "Home",
    "この記事は自動生成です": "This article was generated automatically.",
    "記事一覧 | By AI, About AI": "Archive | By AI, About AI",
    "By AI, About AI の全記事。キーワード検索とタグで絞り込めます。":
      "Every article on By AI, About AI. Filter by keyword and by tag.",
    "記事を検索（例: OpenAI 規制）": "Search articles (e.g. OpenAI)",
    "記事を全文検索": "Search the full text of the articles",
    "タグで絞り込む": "Filter by tag",
    "タグ": "Tags",
    "ページ移動": "Page navigation",
    "戻る": "Back",
    "← 記事一覧へ": "← Archive",
    "まだ記事はありません。": "No articles yet.",
    "まだニュースはありません。": "No news yet.",
    "まだタグはありません。": "No tags yet.",
    "読み込み中…": "Loading…",
    "条件をクリア": "Clear",
    "見つかりませんでした。別の言葉で試してみてください。": "Nothing matched. Try different words."
  };

  var SEARCH = {
    ja: {
      tagLabel: "タグ ",
      queryOpen: "「",
      queryClose: "」",
      joiner: " ＋ ",
      suffix: function (n) { return " の記事：" + n + "件"; }
    },
    en: {
      tagLabel: "Tag ",
      queryOpen: '"',
      queryClose: '"',
      joiner: " + ",
      suffix: function (n) { return ": " + n + (n === 1 ? " article" : " articles"); }
    }
  };

  var BINDINGS = [
    { selector: 'meta[name="description"]', field: "attr", attr: "content" },
    { selector: "title", field: "text" },
    { selector: ".hero-lead", field: "text" },
    { selector: ".hero-cta", field: "own-text" },
    { selector: ".news-rail", field: "attr", attr: "aria-label" },
    { selector: ".rail-title", field: "text" },
    { selector: ".news-date", field: "attr", attr: "title" },
    { selector: ".features", field: "attr", attr: "aria-label" },
    { selector: ".feature-copy h2", field: "text" },
    { selector: ".feature-copy p", field: "text" },
    { selector: ".latest-title", field: "text" },
    { selector: ".latest-more a", field: "text" },
    { selector: ".tag-rail", field: "attr", attr: "aria-label" },
    { selector: "#search-input", field: "attr", attr: "placeholder" },
    { selector: "#search-input", field: "attr", attr: "aria-label" },
    { selector: ".post-nav", field: "attr", attr: "aria-label" },
    { selector: ".post-nav-back", field: "own-text" },
    { selector: ".post-nav-link", field: "text" },
    { selector: "main.post > section > h2", field: "text" },
    { selector: "p.back a", field: "text" },
    { selector: ".site-subtitle", field: "text" },
    { selector: ".footer-nav", field: "attr", attr: "aria-label" },
    { selector: ".footer-nav a", field: "text" },
    { selector: ".footer-note", field: "text" },
    { selector: ".topbar-btn", field: "text" },
    { selector: "p.empty", field: "text" }
  ];

  function coerceLocale(raw) {
    return raw === "en" ? "en" : "ja";
  }

  function readStored() {
    var raw;
    try {
      raw = localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return "ja";
    }
    if (raw === null || raw === "ja" || raw === "en") return coerceLocale(raw);
    try {
      localStorage.setItem(STORAGE_KEY, "ja");
    } catch (e2) {}
    return "ja";
  }

  function toEnglish(raw) {
    var core = raw.trim();
    var dated = DATE_TITLE.exec(core);
    var en = dated ? "Read the article for " + dated[1] : null;
    if (!en) {
      if (!Object.prototype.hasOwnProperty.call(EXACT, core)) return null;
      en = EXACT[core];
    }
    var at = raw.indexOf(core);
    return { ja: raw, en: raw.slice(0, at) + en + raw.slice(at + core.length) };
  }

  function writeOwnText(textNode, value) {
    textNode.nodeValue = value;
  }

  function readField(el, binding) {
    if (binding.field === "attr") {
      var name = binding.attr;
      if (!el.hasAttribute(name)) return null;
      var rawAttr = el.getAttribute(name);
      if (rawAttr === null) return null;
      return {
        raw: rawAttr,
        write: function (value) { el.setAttribute(name, value); }
      };
    }
    if (binding.field === "text") {
      if (el.children.length !== 0) return null;
      return {
        raw: el.textContent,
        write: function (value) { el.textContent = value; }
      };
    }
    if (binding.field === "own-text") {
      var node = null;
      var count = 0;
      for (var i = 0; i < el.childNodes.length; i++) {
        var child = el.childNodes[i];
        if (child.nodeType !== 3) continue;
        if (!child.nodeValue || child.nodeValue.trim() === "") continue;
        count += 1;
        node = child;
      }
      if (count !== 1) return null;
      return {
        raw: node.nodeValue,
        write: function (value) { writeOwnText(node, value); }
      };
    }
    return null;
  }

  function seenSlot(seen, el, field, attr) {
    for (var i = 0; i < seen.length; i++) {
      var row = seen[i];
      if (row.el === el && row.field === field && row.attr === attr) return true;
    }
    return false;
  }

  function capture(doc) {
    var out = [];
    var seen = [];
    for (var b = 0; b < BINDINGS.length; b++) {
      var binding = BINDINGS[b];
      var nodes = doc.querySelectorAll(binding.selector);
      for (var i = 0; i < nodes.length; i++) {
        var el = nodes[i];
        var attr = binding.attr || "";
        if (seenSlot(seen, el, binding.field, attr)) continue;
        var field = readField(el, binding);
        if (!field) continue;
        var pair = toEnglish(field.raw);
        if (!pair) continue;
        seen.push({ el: el, field: binding.field, attr: attr });
        out.push({ write: field.write, ja: pair.ja, en: pair.en });
      }
    }
    return out;
  }

  function apply(locale) {
    document.documentElement.lang = locale;
    for (var i = 0; i < slots.length; i++) {
      slots[i].write(locale === "en" ? slots[i].en : slots[i].ja);
    }
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function sentence(locale, ja) {
    return locale === "en" ? EXACT[ja] : ja;
  }

  function statusHtml(locale, tagHtml, query, count) {
    var words = SEARCH[locale];
    var parts = [];
    if (tagHtml) parts.push(words.tagLabel + tagHtml);
    if (query) parts.push(words.queryOpen + esc(query) + words.queryClose);
    return parts.join(words.joiner) + words.suffix(count) +
      ' <button type="button" class="search-clear">' + sentence(locale, "条件をクリア") + "</button>";
  }

  function writeSearch(nodes, parts, locale) {
    if (parts.phase === "idle") {
      nodes.status.hidden = true;
      nodes.status.textContent = "";
      return;
    }
    if (parts.phase === "loading") {
      nodes.status.hidden = false;
      nodes.status.textContent = sentence(locale, "読み込み中…");
      return;
    }
    nodes.status.hidden = false;
    nodes.status.innerHTML = statusHtml(locale, parts.tagHtml, parts.query, parts.count);
    if (nodes.miss) {
      nodes.miss.textContent = sentence(locale, "見つかりませんでした。別の言葉で試してみてください。");
    }
  }

  function paintSearch(nodes, parts) {
    lastSearch = { nodes: nodes, parts: parts };
    writeSearch(nodes, parts, current);
  }

  function replaySearch() {
    if (!lastSearch) return;
    if (!lastSearch.nodes.status.isConnected) return;
    writeSearch(lastSearch.nodes, lastSearch.parts, current);
  }

  function mountSwitch() {
    var topbar = document.querySelector("header.topbar");
    var header = topbar ? null : document.querySelector("header.site-header");
    var title = header ? header.querySelector(".site-title") : null;
    if (!topbar && !title) return;

    button = document.createElement("button");
    button.type = "button";
    button.className = "locale-switch";
    button.textContent = "English";
    offer = "en";
    button.addEventListener("click", function () { choose(offer); });

    var tools = document.createElement("div");
    tools.className = "locale-tools";
    if (topbar) {
      var anchor = topbar.querySelector("a.topbar-btn");
      if (anchor) tools.appendChild(anchor);
      tools.appendChild(button);
      topbar.appendChild(tools);
      return;
    }
    tools.appendChild(button);
    title.insertAdjacentElement("afterend", tools);
  }

  function press(locale) {
    offer = locale === "en" ? "ja" : "en";
    if (!button) return;
    button.textContent = offer === "en" ? "English" : "日本語";
  }

  function choose(next) {
    next = coerceLocale(next);
    if (next === current) {
      press(current);
      return;
    }
    try { localStorage.setItem(STORAGE_KEY, next); } catch (e) {}
    apply(next);
    current = next;
    press(current);
    replaySearch();
  }

  function onStorage(e) {
    if (!e || e.key !== STORAGE_KEY) return;
    var next = coerceLocale(e.newValue);
    if (next === current) return;
    apply(next);
    current = next;
    press(current);
    replaySearch();
  }

  function boot() {
    if (booted) return;
    booted = true;
    var stored = readStored();
    slots = capture(document);
    mountSwitch();
    if (stored === "en") apply(stored);
    current = stored;
    press(current);
    window.addEventListener("storage", onStorage);
    window.siteChrome = { paintSearch: paintSearch };
  }

  boot();
})();
