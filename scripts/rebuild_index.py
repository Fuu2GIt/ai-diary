#!/usr/bin/env python3
"""posts/YYYY-MM-DD.html をすべて読み、index.html・archive.html・search.json を作り直す。

同じ実行で en/posts/ も読み、en/index.html・en/archive.html・en/search.json を作り直す。
同じ実行で weekly/ monthly/ en/weekly/ en/monthly/ も読み、トップの recap-strip、
記事一覧の #recaps 棚、各まとめページの recap-pager を日英とも更新する。
まとめは search.json とニュース見出し欄（news-rail）には入れない。

引数なしで `python3 scripts/rebuild_index.py` と実行すればよい。

- index.html（サイトトップ）: 最新の記事（POSTS、最大 TOP_MAX_POSTS 件・タグなし）と
  ニュース見出し（NEWS、最大 TOP_MAX_HEADLINES 件）。まとめがあれば、features の直後に
  最新の週まとめ1件と月まとめ1件（RECAPS）。無い種類のカードは出さない。両方無ければ欄ごと出さない。
- archive.html（記事一覧）: 全記事（POSTS、タグ付き）、タグ一覧（TAGS）、
  ニュース見出し（NEWS、全件）。見出しの直後に週まとめ・月まとめの棚（RECAPS、新しい順・全件）。
- ニュース見出しは各記事の「AIニュース」欄の要点の一文目。見出しは出典記事へ
  （新しいタブ）、日付はその日の記事へリンクする。出典が無い要点は記事へリンク。
- 記事ごとのサムネイル: assets/YYYY-MM-DD-hero.webp があれば archive.html の一覧に
  小さく表示し、search.json の thumb にも入れる（無ければ何も出さない）。
- search.json: 全文検索用（日付・題名・URL・タグ・見出しと出典URL・サムネイル・本文）。
- ページにマーカーが無ければ、その部分は何もしない（ファイルが無ければ飛ばす）。

タグは記事内の <span class="tag tag-xxx">表示名</span> から拾う。

週まとめ・月まとめの追加手順:
毎週月曜に前週分を templates/weekly.html と templates/weekly.en.html から作り、
weekly/YYYY-MM-DD.html と en/weekly/YYYY-MM-DD.html に置く（日付はその週の月曜）。
毎月1日に前月分を templates/monthly.html と templates/monthly.en.html から作り、
monthly/YYYY-MM.html と en/monthly/YYYY-MM.html に置く。
そのあとこのスクリプトを1回実行する。入口（recap-strip と #recaps）と前後の pager が日英とも更新される。
"""

import html
import json
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "posts"
INDEX = ROOT / "index.html"
ARCHIVE = ROOT / "archive.html"
SEARCH_JSON = ROOT / "search.json"
EN_POSTS_DIR = ROOT / "en" / "posts"
EN_INDEX = ROOT / "en" / "index.html"
EN_ARCHIVE = ROOT / "en" / "archive.html"
EN_SEARCH_JSON = ROOT / "en" / "search.json"
WEEKLY_DIR = ROOT / "weekly"
MONTHLY_DIR = ROOT / "monthly"
EN_WEEKLY_DIR = ROOT / "en" / "weekly"
EN_MONTHLY_DIR = ROOT / "en" / "monthly"
ASSETS_DIR = ROOT / "assets"
SITE_SUFFIX = " | By AI, About AI"
HEADLINE_LEN = 60
HEADLINE_LEN_EN = 110
MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
TOP_MAX_POSTS = 20
TOP_MAX_HEADLINES = 30

POST_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
WEEKLY_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
MONTHLY_NAME = re.compile(r"^(\d{4}-\d{2})\.html$")
TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
H1_TAG = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
TAGS = re.compile(r"<[^>]+>")
MAIN_TAG = re.compile(r"<main[^>]*>(.*?)</main>", re.S | re.I)
TAG_SPAN = re.compile(r'<span[^>]*class="[^"]*\btag\b[^"]*"[^>]*>(.*?)</span>', re.S)
NEWS_SECTION = re.compile(r"<h2[^>]*>\s*AIニュース\s*</h2>(.*?)</section>", re.S)
NEWS_SECTION_EN = re.compile(r"<h2[^>]*>\s*AI News\s*</h2>(.*?)</section>", re.S)
CARD_TITLE = re.compile(r'<[^>]*class="[^"]*card-title[^"]*"[^>]*>(.*?)</', re.S)
LIST_ITEM = re.compile(r"<li[^>]*>(.*?)</li>", re.S)
SOURCE_SPAN = re.compile(r'<span class="source">.*?</span>', re.S)
EXTERNAL_HREF = re.compile(r'<a\b[^>]*\bhref="(https?://[^"]+)"', re.S | re.I)
CARD_START = re.compile(r'<[^>]*class="[^"]*card-title[^"]*"', re.S)
FIGURE = re.compile(r"<figure.*?</figure>", re.S)
POST_HEADER = re.compile(r'<header class="post-header">.*?</header>', re.S)

MARKERS = {
    "POSTS": re.compile(r"(<!-- POSTS:START -->)(.*?)(\n[ \t]*<!-- POSTS:END -->)", re.S),
    "NEWS": re.compile(r"(<!-- NEWS:START -->)(.*?)(\n[ \t]*<!-- NEWS:END -->)", re.S),
    "TAGS": re.compile(r"(<!-- TAGS:START -->)(.*?)(\n[ \t]*<!-- TAGS:END -->)", re.S),
    "RECAPS": re.compile(r"(<!-- RECAPS:START -->)(.*?)(\n[ \t]*<!-- RECAPS:END -->)", re.S),
    "RECAP_PAGER": re.compile(r"(<!-- RECAP_PAGER:START -->)(.*?)(\n[ \t]*<!-- RECAP_PAGER:END -->)", re.S),
}

MONTHS_EN_FULL = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# 表示名 → 色のクラス。ここにない名前は tag-other の色になる。
TAG_CLASS = {
    "openai": "openai", "chatgpt": "openai",
    "xai": "xai", "grok": "xai", "grok bot": "xai",
    "anthropic": "anthropic", "claude": "anthropic",
    "nvidia": "nvidia",
    "google": "google", "gemini": "google", "deepmind": "google",
    "meta": "meta", "llama": "meta",
    "政策": "policy", "政策・規制": "policy", "規制": "policy", "policy": "policy",
    "policy & regulation": "policy",
}


def clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAGS.sub(" ", fragment))).strip()


def tag_class(name: str) -> str:
    return "tag-" + TAG_CLASS.get(name.strip().lower(), "other")


def tag_html(name: str) -> str:
    return f'<span class="tag {tag_class(name)}">{html.escape(name)}</span>'


def extract_title(source: str, fallback: str) -> str:
    for pattern in (TITLE_TAG, H1_TAG):
        match = pattern.search(source)
        if match:
            text = clean(match.group(1)).removesuffix(SITE_SUFFIX).strip()
            if text:
                return text
    return fallback


def extract_tags(source: str) -> list[str]:
    seen: list[str] = []
    for raw in TAG_SPAN.findall(source):
        name = clean(raw)
        if name and "{{" not in name and name not in seen:
            seen.append(name)
    return seen


GENERIC_TAGS = {"政策・規制", "政策", "規制", "その他", "国内"}


_EN_ABBREV = {
    "u.s", "u.k", "u.n", "e.g", "i.e", "mr", "mrs", "ms", "dr", "jr", "sr",
    "inc", "ltd", "co", "st", "no", "vs", "etc", "fig", "gen", "gov",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}


def first_sentence_en(text: str) -> str:
    """英語の一文目。日本語の「。」切りと同じく、終端のピリオドは見出しに含めない。"""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in ".?!":
            if ch == "." and text.startswith("...", i):
                i += 3
                continue
            if (
                ch == "."
                and i > 0
                and i + 1 < n
                and text[i - 1].isdigit()
                and text[i + 1].isdigit()
            ):
                i += 1
                continue
            if ch == ".":
                j = i - 1
                while j >= 0 and (text[j].isalpha() or text[j] == "."):
                    j -= 1
                word = text[j + 1:i].lower()
                if word in _EN_ABBREV or word.replace(".", "") in _EN_ABBREV:
                    i += 1
                    continue
            nxt = text[i + 1:] if i + 1 < n else ""
            if nxt.startswith(" ") and len(nxt) > 1 and nxt[1].islower():
                i += 1
                continue
            if nxt == "" or nxt[0] in " \t\n\"'”’)]}":
                return text[:i].strip()
        i += 1
    return text.strip()


def clip_headline_en(text: str) -> str:
    """110字を超える英語見出しは、制限より前の最後の空白で切り、末尾の読点を落として … を付ける。"""
    if len(text) <= HEADLINE_LEN_EN:
        return text
    cut = text[:HEADLINE_LEN_EN]
    space = cut.rfind(" ")
    if space > 0:
        cut = cut[:space]
    else:
        cut = cut[: HEADLINE_LEN_EN - 1]
    cut = cut.rstrip(" ,;:.!?\"'”’")
    return cut + "…"


def to_headline(fragment: str, lang: str = "ja") -> str:
    text = clean(TAG_SPAN.sub("", SOURCE_SPAN.sub("", fragment)))
    if lang == "en":
        return clip_headline_en(first_sentence_en(text))
    if "。" in text:
        text = text.split("。", 1)[0].strip()
    if len(text) > HEADLINE_LEN:
        text = text[: HEADLINE_LEN - 1].rstrip() + "…"
    return text


def source_url(fragment: str) -> str:
    """要点の出典URL。出典欄（span.source）の最初の http(s) リンク、無ければ要点内の最初の外部リンク。"""
    span = SOURCE_SPAN.search(fragment)
    for part in ((span.group(0),) if span else ()) + (fragment,):
        match = EXTERNAL_HREF.search(part)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def extract_headlines(source: str, lang: str = "ja") -> list[dict]:
    """「AIニュース」欄の要点ごとに {"text": 見出し, "url": 出典URL or ""} を返す。"""
    section = (NEWS_SECTION_EN if lang == "en" else NEWS_SECTION).search(source)
    if not section:
        return []
    body = section.group(1)
    if CARD_TITLE.search(body):
        # カード形式: card-title ごとに区切り、その区間の外部リンクを出典とみなす
        starts = [m.start() for m in CARD_START.finditer(body)] + [len(body)]
        pairs = [
            (CARD_TITLE.search(body[a:b]).group(1), body[a:b])
            for a, b in zip(starts, starts[1:])
            if CARD_TITLE.search(body[a:b])
        ]
    else:
        pairs = [(f, f) for f in LIST_ITEM.findall(body)]
    headlines = []
    for title_part, chunk in pairs:
        text = to_headline(title_part, lang)
        if not text or "{{" in text:
            continue
        url = source_url(chunk)
        tags = []
        for raw in TAG_SPAN.findall(chunk):
            name = clean(raw)
            if name and name not in tags and "{{" not in name:
                tags.append(name)
        headlines.append({"text": text, "url": "" if "{{" in url else url, "tags": tags})
    return headlines


def extract_text(source: str) -> str:
    match = MAIN_TAG.search(source)
    body = match.group(1) if match else source
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r'<nav class="lang-switch"[^>]*>.*?</nav>', "", body, flags=re.S)
    body = FIGURE.sub("", POST_HEADER.sub("", body))
    body = TAG_SPAN.sub(" ", SOURCE_SPAN.sub(" ", body))
    body = re.sub(r'<p class="back">.*?</p>', "", body, flags=re.S)
    return clean(body)


def find_thumb(date: str, prefix: str = "assets/") -> str:
    """assets/YYYY-MM-DD-hero.webp があればサイトルートからの相対パス、無ければ空文字。"""
    name = f"{date}-hero.webp"
    return f"{prefix}{name}" if (ASSETS_DIR / name).is_file() else ""


def display_date(iso: str, lang: str) -> str:
    if lang != "en":
        return iso
    year, month, day = iso.split("-")
    return f"{MONTHS_EN[int(month) - 1]} {int(day)}, {year}"


def rail_day(iso: str, lang: str) -> str:
    if lang != "en":
        return iso[5:].replace("-", "/")
    _year, month, day = iso.split("-")
    return f"{MONTHS_EN[int(month) - 1]} {int(day)}"


def collect_posts(
    posts_dir: Path = POSTS_DIR,
    url_prefix: str = "posts/",
    thumb_prefix: str = "assets/",
    lang: str = "ja",
) -> list[dict]:
    posts = []
    if not posts_dir.is_dir():
        return posts
    for path in posts_dir.glob("*.html"):
        match = POST_NAME.match(path.name)
        if not match:
            continue
        date = match.group(1)
        source = path.read_text(encoding="utf-8")
        posts.append({
            "date": date,
            "title": extract_title(source, date),
            "url": f"{url_prefix}{path.name}",
            "tags": extract_tags(source),
            "headlines": extract_headlines(source, lang),
            "thumb": find_thumb(date, thumb_prefix),
            "text": extract_text(source),
        })
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def render_posts(posts: list[dict], with_tags: bool = True, indent: str = "      ", lang: str = "ja") -> str:
    if not posts:
        empty = "No posts yet." if lang == "en" else "まだ記事はありません。"
        return f'\n{indent}<p class="empty">{empty}</p>'
    items = []
    for p in posts:
        shown = display_date(p["date"], lang)
        if not with_tags:
            items.append(
                f'{indent}  <li><time datetime="{p["date"]}">{shown}</time>'
                f'<a href="{p["url"]}">{html.escape(p["title"])}</a></li>'
            )
            continue
        tags = ""
        if p["tags"]:
            tags = '<span class="post-tags">' + "".join(tag_html(t) for t in p["tags"]) + "</span>"
        data_tags = html.escape("|".join(p["tags"]))
        body = (
            f'<time datetime="{p["date"]}">{shown}</time>'
            f'<a href="{p["url"]}">{html.escape(p["title"])}</a>{tags}'
        )
        if p["thumb"]:
            items.append(
                f'{indent}  <li class="has-thumb" data-tags="{data_tags}">'
                f'<a class="post-thumb" href="{p["url"]}" tabindex="-1">'
                f'<img src="{p["thumb"]}" alt="{html.escape(p["title"])}" width="320" height="180"'
                f' loading="lazy" decoding="async"></a>'
                f'<div class="post-body">{body}</div></li>'
            )
        else:
            items.append(f'{indent}  <li data-tags="{data_tags}">{body}</li>')
    return f'\n{indent}<ul class="post-list">\n' + "\n".join(items) + f"\n{indent}</ul>"


def headline_html(p: dict, h: dict, lang: str = "ja") -> str:
    day = rail_day(p["date"], lang)
    if lang == "en":
        title = f'Read the {display_date(p["date"], "en")} post'
    else:
        title = f'{p["date"]} の記事を読む'
    date_link = (
        f'<a class="news-date" href="{p["url"]}" title="{title}">'
        f'<time datetime="{p["date"]}">{day}</time></a>'
    )
    if h["url"]:
        link = (
            f'<a class="news-link" href="{html.escape(h["url"])}" target="_blank" rel="noopener">'
            f'{html.escape(h["text"])}</a>'
        )
    else:
        link = f'<a class="news-link" href="{p["url"]}">{html.escape(h["text"])}</a>'
    tags = ""
    if h.get("tags"):
        tags = '<span class="news-tags">' + "".join(tag_html(t) for t in h["tags"]) + "</span>"
    return f'<li>{date_link}<div class="news-body">{link}{tags}</div></li>'


def render_headlines(posts: list[dict], limit: int | None = None, indent: str = "      ", lang: str = "ja") -> str:
    pairs = [(p, h) for p in posts for h in p["headlines"]]
    if limit is not None:
        pairs = pairs[:limit]
    items = [f"{indent}  {headline_html(p, h, lang)}" for p, h in pairs]
    if not items:
        empty = "No news yet." if lang == "en" else "まだニュースはありません。"
        return f'\n{indent}<p class="empty">{empty}</p>'
    return f'\n{indent}<ul class="news-rail-list">\n' + "\n".join(items) + f"\n{indent}</ul>"


def render_tags(posts: list[dict], lang: str = "ja") -> str:
    indent = "      "
    counts: dict[str, int] = {}
    for p in posts:
        for t in p["tags"]:
            counts[t] = counts.get(t, 0) + 1
    if not counts:
        empty = "No tags yet." if lang == "en" else "まだタグはありません。"
        return f'\n{indent}<p class="empty">{empty}</p>'
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    items = [
        f'{indent}  <li><a class="tag-filter" href="?tag={html.escape(quote(name))}" data-tag="{html.escape(name)}">'
        f'{tag_html(name)}<span class="tag-count">{n}</span></a></li>'
        for name, n in ordered
    ]
    return f'\n{indent}<ul class="tag-rail-list">\n' + "\n".join(items) + f"\n{indent}</ul>"


# ページごとに、どのマーカーをどう埋めるか（マーカーが無いものは飛ばす）
PAGES = {
    INDEX: {
        "POSTS": lambda posts: render_posts(posts[:TOP_MAX_POSTS], with_tags=False),
        "NEWS": lambda posts: render_headlines(posts, limit=TOP_MAX_HEADLINES, indent="    "),
    },
    ARCHIVE: {
        "POSTS": lambda posts: render_posts(posts),
        "NEWS": lambda posts: render_headlines(posts),
        "TAGS": render_tags,
    },
}

EN_PAGES = {
    EN_INDEX: {
        "POSTS": lambda posts: render_posts(posts[:TOP_MAX_POSTS], with_tags=False, lang="en"),
        "NEWS": lambda posts: render_headlines(posts, limit=TOP_MAX_HEADLINES, indent="    ", lang="en"),
    },
    EN_ARCHIVE: {
        "POSTS": lambda posts: render_posts(posts, lang="en"),
        "NEWS": lambda posts: render_headlines(posts, lang="en"),
        "TAGS": lambda posts: render_tags(posts, lang="en"),
    },
}


def extract_h1(source: str, fallback: str) -> str:
    match = H1_TAG.search(source)
    if not match:
        return fallback
    text = clean(match.group(1))
    return text or fallback


def week_bounds(monday_iso: str) -> tuple[date, date]:
    start = date.fromisoformat(monday_iso)
    return start, start + timedelta(days=6)


def period_spaced(start: date, end: date) -> str:
    """Sep 07 – 13、月をまたぐときは Sep 28 – Oct 04。区切りは en dash。"""
    left = f"{MONTHS_EN[start.month - 1]} {start.day:02d}"
    if start.month == end.month:
        right = f"{end.day:02d}"
    else:
        right = f"{MONTHS_EN[end.month - 1]} {end.day:02d}"
    return f"{left} – {right}"


def period_archive(start: date, end: date, lang: str) -> str:
    """一覧の time 表示。日本語は 09/07–13 または 09/28–10/04。英語は Sep 07–13 または Sep 28–Oct 04。"""
    if lang == "en":
        left = f"{MONTHS_EN[start.month - 1]} {start.day:02d}"
        if start.month == end.month:
            right = f"{end.day:02d}"
        else:
            right = f"{MONTHS_EN[end.month - 1]} {end.day:02d}"
        return f"{left}–{right}"
    left = f"{start.month:02d}/{start.day:02d}"
    if start.month == end.month:
        right = f"{end.day:02d}"
    else:
        right = f"{end.month:02d}/{end.day:02d}"
    return f"{left}–{right}"


def month_full(iso: str) -> str:
    year, month = iso.split("-")
    return f"{MONTHS_EN_FULL[int(month) - 1]} {year}"


def month_archive_en(iso: str) -> str:
    year, month = iso.split("-")
    return f"{MONTHS_EN[int(month) - 1]} {year}"


def collect_recaps(directory: Path, kind: str) -> list[dict]:
    """古い順。kind は weekly または monthly。題名は h1。"""
    pattern = WEEKLY_NAME if kind == "weekly" else MONTHLY_NAME
    items = []
    if not directory.is_dir():
        return items
    for path in directory.glob("*.html"):
        match = pattern.match(path.name)
        if not match:
            continue
        source = path.read_text(encoding="utf-8")
        stamp = match.group(1)
        items.append({
            "id": stamp,
            "title": extract_h1(source, stamp),
            "path": path,
            "kind": kind,
        })
    items.sort(key=lambda item: item["id"])
    return items


def weekly_period(item: dict) -> tuple[date, date]:
    return week_bounds(item["id"])


def render_weekly_card(item: dict, lang: str) -> str:
    start, end = weekly_period(item)
    period = period_spaced(start, end)
    title = html.escape(item["title"])
    more = "Read →" if lang == "en" else "読む →"
    if lang == "en":
        badge = '<span class="recap-badge">Weekly Recap</span>'
    else:
        badge = '<span class="recap-badge">Weekly Recap <span>週まとめ</span></span>'
    return (
        f'<a class="recap-card" href="weekly/{item["id"]}.html">{badge}'
        f'<span class="recap-period">{period}</span>'
        f'<span class="recap-card-title">{title}</span>'
        f'<span class="recap-card-more">{more}</span></a>'
    )


def render_monthly_card(item: dict, lang: str) -> str:
    period = month_full(item["id"])
    title = html.escape(item["title"])
    more = "Read →" if lang == "en" else "読む →"
    if lang == "en":
        badge = '<span class="recap-badge recap-badge--monthly">Monthly Recap</span>'
    else:
        badge = '<span class="recap-badge recap-badge--monthly">Monthly Recap <span>月まとめ</span></span>'
    return (
        f'<a class="recap-card recap-card--monthly" href="monthly/{item["id"]}.html">{badge}'
        f'<span class="recap-period">{period}</span>'
        f'<span class="recap-card-title">{title}</span>'
        f'<span class="recap-card-more">{more}</span></a>'
    )


def render_strip(weekly: list[dict], monthly: list[dict], lang: str) -> str:
    latest_w = weekly[-1] if weekly else None
    latest_m = monthly[-1] if monthly else None
    if not latest_w and not latest_m:
        return ""
    indent = "  "
    inner = "    "
    label = "Recaps" if lang == "en" else "まとめ"
    more = "All recaps →" if lang == "en" else "すべてのまとめ →"
    cards = []
    if latest_w:
        cards.append(f"{inner}  {render_weekly_card(latest_w, lang)}")
    if latest_m:
        cards.append(f"{inner}  {render_monthly_card(latest_m, lang)}")
    lines = [
        f'{indent}<section class="recap-strip" aria-label="{label}">',
        f'{inner}<p class="latest-kicker">Recap</p>',
        f'{inner}<h2 class="latest-title">{label}</h2>',
        f'{inner}<div class="recap-cards">',
        *cards,
        f"{inner}</div>",
        f'{inner}<p class="latest-more"><a href="archive.html#recaps">{more}</a></p>',
        f"{indent}</section>",
    ]
    return "\n" + "\n".join(lines)


def render_shelf_weekly(items: list[dict], lang: str) -> list[str]:
    indent = "      "
    if lang == "en":
        heading = '<h2><span class="recap-badge">Weekly</span>Recaps</h2>'
    else:
        heading = '<h2><span class="recap-badge">Weekly</span>週まとめ</h2>'
    lines = [f"{indent}<section>", f"{indent}  {heading}", f"{indent}  <ul>"]
    for item in reversed(items):
        start, end = weekly_period(item)
        shown = period_archive(start, end, lang)
        title = html.escape(item["title"])
        lines.append(
            f'{indent}    <li><a href="weekly/{item["id"]}.html">'
            f'<time datetime="{item["id"]}">{shown}</time>{title}</a></li>'
        )
    lines.append(f"{indent}  </ul>")
    lines.append(f"{indent}</section>")
    return lines


def render_shelf_monthly(items: list[dict], lang: str) -> list[str]:
    indent = "      "
    if lang == "en":
        heading = '<h2><span class="recap-badge recap-badge--monthly">Monthly</span>Recaps</h2>'
    else:
        heading = '<h2><span class="recap-badge recap-badge--monthly">Monthly</span>月まとめ</h2>'
    lines = [f"{indent}<section>", f"{indent}  {heading}", f"{indent}  <ul>"]
    for item in reversed(items):
        shown = month_archive_en(item["id"]) if lang == "en" else item["id"]
        title = html.escape(item["title"])
        lines.append(
            f'{indent}    <li><a href="monthly/{item["id"]}.html">'
            f'<time datetime="{item["id"]}">{shown}</time>{title}</a></li>'
        )
    lines.append(f"{indent}  </ul>")
    lines.append(f"{indent}</section>")
    return lines


def render_shelf(weekly: list[dict], monthly: list[dict], lang: str) -> str:
    if not weekly and not monthly:
        return ""
    indent = "    "
    lines = [f'{indent}<div class="recap-shelf" id="recaps">']
    if weekly:
        lines.extend(render_shelf_weekly(weekly, lang))
    if monthly:
        lines.extend(render_shelf_monthly(monthly, lang))
    lines.append(f"{indent}</div>")
    return "\n" + "\n".join(lines)


def pager_visible(item: dict, lang: str) -> str:
    if item["kind"] == "weekly":
        start, end = weekly_period(item)
        return period_spaced(start, end)
    return month_full(item["id"])


def render_pager(items: list[dict], index: int, lang: str) -> str:
    prev_item = items[index - 1] if index > 0 else None
    next_item = items[index + 1] if index + 1 < len(items) else None
    if not prev_item and not next_item:
        return ""
    kind = items[index]["kind"]
    if kind == "weekly":
        aria = "Weekly recaps" if lang == "en" else "週まとめの移動"
        prev_small = "← Previous week" if lang == "en" else "← 前の週"
        next_small = "Next week →" if lang == "en" else "次の週 →"
    else:
        aria = "Monthly recaps" if lang == "en" else "月まとめの移動"
        prev_small = "← Previous month" if lang == "en" else "← 前の月"
        next_small = "Next month →" if lang == "en" else "次の月 →"
    indent = "      "
    lines = [f'{indent}<nav class="recap-pager" aria-label="{aria}">']
    if prev_item:
        lines.append(
            f'{indent}  <a class="prev" href="{prev_item["id"]}.html">'
            f"<small>{prev_small}</small>{pager_visible(prev_item, lang)}</a>"
        )
    if next_item:
        lines.append(
            f'{indent}  <a class="next" href="{next_item["id"]}.html">'
            f"<small>{next_small}</small>{pager_visible(next_item, lang)}</a>"
        )
    lines.append(f"{indent}</nav>")
    return "\n" + "\n".join(lines)


def fill_marker(path: Path, key: str, body: str) -> bool:
    """マーカーを埋める。マーカーが無ければ False。中身が同じなら書き戻さない。"""
    if not path.exists():
        return False
    source = path.read_text(encoding="utf-8")
    pattern = MARKERS[key]
    if not pattern.search(source):
        return False
    updated = pattern.sub(lambda m: m.group(1) + body + m.group(3), source, count=1)
    if updated != source:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def update_recaps(lang: str) -> str:
    if lang == "en":
        weekly = collect_recaps(EN_WEEKLY_DIR, "weekly")
        monthly = collect_recaps(EN_MONTHLY_DIR, "monthly")
        index, archive = EN_INDEX, EN_ARCHIVE
    else:
        weekly = collect_recaps(WEEKLY_DIR, "weekly")
        monthly = collect_recaps(MONTHLY_DIR, "monthly")
        index, archive = INDEX, ARCHIVE
    fill_marker(index, "RECAPS", render_strip(weekly, monthly, lang))
    fill_marker(archive, "RECAPS", render_shelf(weekly, monthly, lang))
    missing = []
    for index_in_list, item in enumerate(weekly):
        if not fill_marker(item["path"], "RECAP_PAGER", render_pager(weekly, index_in_list, lang)):
            missing.append(item["path"].relative_to(ROOT).as_posix())
    for index_in_list, item in enumerate(monthly):
        if not fill_marker(item["path"], "RECAP_PAGER", render_pager(monthly, index_in_list, lang)):
            missing.append(item["path"].relative_to(ROOT).as_posix())
    note = f"weekly {len(weekly)} / monthly {len(monthly)}"
    if missing:
        note += "（pager マーカーなし: " + ", ".join(missing) + "）"
    return note


def fill_page(path: Path, renderers: dict, posts: list[dict]) -> list[str]:
    """path のマーカーを埋め直し、埋めたマーカー名を返す。"""
    if not path.exists():
        return []
    source = path.read_text(encoding="utf-8")
    filled = []
    for key, render in renderers.items():
        pattern = MARKERS[key]
        if pattern.search(source):
            body = render(posts)
            source = pattern.sub(lambda m: m.group(1) + body + m.group(3), source, count=1)
            filled.append(key)
    path.write_text(source, encoding="utf-8", newline="\n")
    return filled


def main() -> None:
    if not MARKERS["POSTS"].search(INDEX.read_text(encoding="utf-8")):
        raise SystemExit("index.html に POSTS:START / POSTS:END マーカーがありません")
    posts = collect_posts()
    report = []
    for path, renderers in PAGES.items():
        filled = fill_page(path, renderers, posts)
        if filled:
            report.append(f"{path.name}（{'/'.join(filled)}）")
        elif not path.exists():
            report.append(f"{path.name} なし（スキップ）")

    search = [
        {k: p[k] for k in ("date", "title", "url", "tags", "headlines", "thumb", "text")}
        for p in posts
    ]
    SEARCH_JSON.write_text(
        json.dumps(search, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    headlines = [h for p in posts for h in p["headlines"]]
    with_url = sum(1 for h in headlines if h["url"])
    tag_count = len({t for p in posts for t in p["tags"]})
    print(
        f"更新: {'、'.join(report)}、search.json"
        f"（{len(posts)} 件、ニュース見出し {len(headlines)} 件"
        f"［出典リンク {with_url} / 記事リンク {len(headlines) - with_url}］、タグ {tag_count} 種類）"
    )

    en_posts = collect_posts(
        EN_POSTS_DIR, url_prefix="posts/", thumb_prefix="../assets/", lang="en"
    )
    en_report = []
    for path, renderers in EN_PAGES.items():
        filled = fill_page(path, renderers, en_posts)
        if filled:
            en_report.append(f"{path.relative_to(ROOT).as_posix()}（{'/'.join(filled)}）")
        elif not path.exists():
            en_report.append(f"{path.relative_to(ROOT).as_posix()} なし（スキップ）")
    en_search = [
        {k: p[k] for k in ("date", "title", "url", "tags", "headlines", "thumb", "text")}
        for p in en_posts
    ]
    EN_SEARCH_JSON.parent.mkdir(parents=True, exist_ok=True)
    EN_SEARCH_JSON.write_text(
        json.dumps(en_search, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    en_headlines = [h for p in en_posts for h in p["headlines"]]
    en_with_url = sum(1 for h in en_headlines if h["url"])
    en_tag_count = len({t for p in en_posts for t in p["tags"]})
    print(
        f"更新(en): {'、'.join(en_report)}、en/search.json"
        f"（{len(en_posts)} 件、ニュース見出し {len(en_headlines)} 件"
        f"［出典リンク {en_with_url} / 記事リンク {len(en_headlines) - en_with_url}］、タグ {en_tag_count} 種類）"
    )

    print(f"まとめ: {update_recaps('ja')}")
    print(f"まとめ(en): {update_recaps('en')}")


if __name__ == "__main__":
    main()
