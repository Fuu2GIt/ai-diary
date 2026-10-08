#!/usr/bin/env python3
"""posts/YYYY-MM-DD.html をすべて読み、index.html・archive.html・search.json を作り直す。

同じ実行で en/posts/ も読み、en/index.html・en/archive.html・en/search.json を作り直す。

引数なしで `python3 scripts/rebuild_index.py` と実行すればよい。

- index.html（サイトトップ）: 最新の記事（POSTS、最大 TOP_MAX_POSTS 件・タグなし）と
  ニュース見出し（NEWS、最大 TOP_MAX_HEADLINES 件）。
- archive.html（記事一覧）: 全記事（POSTS、タグ付き）、タグ一覧（TAGS）、
  ニュース見出し（NEWS、全件）。
- ニュース見出しは各記事の「AIニュース」欄の要点の一文目。見出しは出典記事へ
  （新しいタブ）、日付はその日の記事へリンクする。出典が無い要点は記事へリンク。
- 記事ごとのサムネイル: assets/YYYY-MM-DD-hero.webp があれば archive.html の一覧に
  小さく表示し、search.json の thumb にも入れる（無ければ何も出さない）。
- search.json: 全文検索用（日付・題名・URL・タグ・見出しと出典URL・サムネイル・本文）。
- 日本語の index / archive / 日付記事の head に、共有カード用の description・OGP・
  twitter:card・canonical・favicon を入れる。説明は「AIのひとこと」を文の区切りで
  120字以内にしたもの。og:image はヒーロー、無ければ assets/og.png。
  posts/sample.html と英語版（en/）は対象外。2回実行しても head は変わらない。
- ページにマーカーが無ければ、その部分は何もしない（ファイルが無ければ飛ばす）。

タグは記事内の <span class="tag tag-xxx">表示名</span> から拾う。
"""

import html
import json
import re
import struct
import sys
from html.parser import HTMLParser
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
ASSETS_DIR = ROOT / "assets"
SITE_SUFFIX = " | By AI, About AI"
SITE_NAME = "By AI, About AI"
ORIGIN = "https://fuu2git.github.io/ai-diary"
FAVICON_URL = ORIGIN + "/favicon.svg"
# ヒーローが無い記事・トップ・一覧の og:image。実ファイルは 1200×1200 の PNG。
FALLBACK_IMAGE = "assets/og.png"
DESC_LIMIT = 120
HOME_DESCRIPTION = "ニュースと使い方を、AI自身の視点で"
ARCHIVE_DESCRIPTION = "By AI, About AI の全記事。キーワード検索とタグで絞り込めます。"
HEADLINE_LEN = 60
HEADLINE_LEN_EN = 110
MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
TOP_MAX_POSTS = 20
TOP_MAX_HEADLINES = 30

POST_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
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
AI_COMMENT = re.compile(r'<div class="ai-comment">\s*<p>(.*?)</p>', re.S)
SHARE_BLOCK = re.compile(r"[ \t]*<!-- share:start -->.*?<!-- share:end -->\n?", re.S)
# 以前からある共有タグ。hreflang の alternate は含めない。
LEGACY_SHARE = re.compile(
    r'\n[ \t]*<meta\s[^>]*(?:name="description"|property="og:|name="twitter:)[^>]*>'
    r'|\n[ \t]*<link\s[^>]*rel="(?:canonical|icon)"[^>]*>',
    re.I,
)
PRECONNECT = re.compile(r'\n[ \t]*<link\b[^>]*\brel="preconnect"', re.I)

MARKERS = {
    "POSTS": re.compile(r"(<!-- POSTS:START -->)(.*?)(\n[ \t]*<!-- POSTS:END -->)", re.S),
    "NEWS": re.compile(r"(<!-- NEWS:START -->)(.*?)(\n[ \t]*<!-- NEWS:END -->)", re.S),
    "TAGS": re.compile(r"(<!-- TAGS:START -->)(.*?)(\n[ \t]*<!-- TAGS:END -->)", re.S),
}

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


def webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[0:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
    if chunk == b"VP8 ":
        return (
            int.from_bytes(data[26:28], "little") & 0x3FFF,
            int.from_bytes(data[28:30], "little") & 0x3FFF,
        )
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def image_info(rel: str) -> dict:
    """幅と高さはファイルから読む。ヒーローは webp、共通画像は png で、決め打ちだと共有カードがずれる。"""
    path = ROOT / rel
    data = path.read_bytes()
    mime, width, height = "application/octet-stream", None, None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        mime = "image/png"
    else:
        size = webp_size(data)
        if size or data[8:12] == b"WEBP":
            mime = "image/webp"
            if size:
                width, height = size
    return {
        "rel": rel,
        "url": f"{ORIGIN}/{rel}",
        "type": mime,
        "width": width,
        "height": height,
    }


def pick_image(date: str | None) -> dict:
    rel = find_thumb(date) if date else ""
    return image_info(rel or FALLBACK_IMAGE)


def clip_description(text: str, limit: int = DESC_LIMIT) -> str:
    text = clean(text)
    if len(text) <= limit:
        return text
    acc = ""
    for sentence in re.findall(r".+?。", text):
        if len(acc) + len(sentence) <= limit:
            acc += sentence
        else:
            break
    if acc:
        return acc
    cut = text[:limit]
    for sep in ("。", "、"):
        index = cut.rfind(sep)
        if index >= limit // 2:
            return cut[: index + 1] if sep == "。" else cut[:index].rstrip() + "…"
    return cut[: limit - 1].rstrip() + "…"


def article_description(source: str, title: str) -> str:
    """共有カードと検索結果の説明。その日の要約である「AIのひとこと」を、文の区切りで120字以内にする。"""
    match = AI_COMMENT.search(source)
    text = clean(match.group(1)) if match else ""
    if not text:
        bits = [item["text"] for item in extract_headlines(source) if item["text"]]
        text = "。".join(bits[:3])
        if text and not text.endswith("。"):
            text += "。"
    return clip_description(text or title)


def document_title(source: str, fallback: str) -> str:
    match = TITLE_TAG.search(source)
    if match:
        text = clean(match.group(1))
        if text:
            return text
    return fallback


def share_lines(meta: dict) -> str:
    def esc(value: str) -> str:
        return html.escape(value, quote=True)

    image = meta["image"]
    lines = [
        "<!-- share:start -->",
        f'<meta name="description" content="{esc(meta["description"])}">',
        f'<meta property="og:type" content="{esc(meta["og_type"])}">',
        f'<meta property="og:site_name" content="{esc(SITE_NAME)}">',
        '<meta property="og:locale" content="ja_JP">',
        f'<meta property="og:title" content="{esc(meta["title"])}">',
        f'<meta property="og:description" content="{esc(meta["description"])}">',
        f'<meta property="og:url" content="{esc(meta["url"])}">',
        f'<meta property="og:image" content="{esc(image["url"])}">',
    ]
    if image["type"] != "application/octet-stream":
        lines.append(f'<meta property="og:image:type" content="{esc(image["type"])}">')
    if image["width"] and image["height"]:
        lines.append(f'<meta property="og:image:width" content="{image["width"]}">')
        lines.append(f'<meta property="og:image:height" content="{image["height"]}">')
    lines += [
        f'<meta property="og:image:alt" content="{esc(meta["image_alt"])}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{esc(meta["title"])}">',
        f'<meta name="twitter:description" content="{esc(meta["description"])}">',
        f'<meta name="twitter:image" content="{esc(image["url"])}">',
        f'<meta name="twitter:image:alt" content="{esc(meta["image_alt"])}">',
        f'<link rel="canonical" href="{esc(meta["url"])}">',
        f'<link rel="icon" href="{esc(FAVICON_URL)}" type="image/svg+xml">',
        "<!-- share:end -->",
    ]
    return "\n".join("  " + line for line in lines) + "\n"


def upsert_share(source: str, block: str) -> str:
    """共有タグを preconnect の直前に1つだけ置く。言語切替の hreflang は動かさない。"""
    match = re.search(r"(<head\b[^>]*>)(.*?)(</head>)", source, re.S | re.I)
    if not match:
        raise SystemExit("head がありません")
    head = LEGACY_SHARE.sub("", SHARE_BLOCK.sub("", match.group(2)))
    inserted = block.rstrip("\n")
    pre = PRECONNECT.search(head)
    if pre:
        head = head[: pre.start()] + "\n" + inserted + head[pre.start() :]
    else:
        title = re.search(r"</title>", head, re.I)
        if not title:
            raise SystemExit("title がありません")
        rest = head[title.end() :].lstrip("\n")
        head = head[: title.end()] + "\n" + block + rest
    return source[: match.start(2)] + head + source[match.end(2) :]


def ja_post_paths() -> list[Path]:
    return sorted(path for path in POSTS_DIR.glob("*.html") if POST_NAME.match(path.name))


def post_meta(path: Path) -> dict:
    source = path.read_text(encoding="utf-8")
    plain = extract_title(source, path.stem)
    return {
        "title": document_title(source, plain + SITE_SUFFIX),
        "description": article_description(source, plain),
        "url": f"{ORIGIN}/posts/{path.name}",
        "og_type": "article",
        "image": pick_image(path.stem),
        "image_alt": plain,
    }


def site_meta(path: Path, description: str, url: str) -> dict:
    source = path.read_text(encoding="utf-8")
    return {
        "title": document_title(source, SITE_NAME),
        "description": description,
        "url": url,
        "og_type": "website",
        "image": pick_image(None),
        "image_alt": SITE_NAME,
    }


def apply_share(path: Path, meta: dict) -> bool:
    source = path.read_text(encoding="utf-8")
    updated = upsert_share(source, share_lines(meta))
    if updated == source:
        return False
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def refresh_share() -> int:
    changed = 0
    for path in ja_post_paths():
        changed += apply_share(path, post_meta(path))
    for path, description, url in (
        (INDEX, HOME_DESCRIPTION, ORIGIN + "/"),
        (ARCHIVE, ARCHIVE_DESCRIPTION, ORIGIN + "/archive.html"),
    ):
        if path.exists():
            changed += apply_share(path, site_meta(path, description, url))
    return changed


def head_tags(head: str) -> list[tuple[str, str, str]]:
    found = []
    for match in re.finditer(r"<(meta|link)\b([^>]*)>", head, re.I):
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', match.group(2)))
        tag = match.group(1).lower()
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name") or ""
            value = attrs.get("content", "")
        else:
            key = attrs.get("rel", "")
            value = attrs.get("href", "")
        found.append((tag, key, html.unescape(value)))
    return found


def url_to_path(url: str) -> Path:
    prefix = ORIGIN + "/"
    if not url.startswith(prefix):
        raise ValueError(url)
    rel = url[len(prefix):].split("?", 1)[0].split("#", 1)[0]
    if rel.startswith("/") or ".." in Path(rel).parts:
        raise ValueError(rel)
    return ROOT / rel


def verify_share() -> list[str]:
    errors: list[str] = []
    favicon = ROOT / "favicon.svg"
    if not favicon.is_file() or "<svg" not in favicon.read_text(encoding="utf-8"):
        errors.append("favicon.svg がありません")
    fallback = pick_image(None)
    if fallback["url"] != f"{ORIGIN}/{FALLBACK_IMAGE}" or not (ROOT / FALLBACK_IMAGE).is_file():
        errors.append("共通画像へのフォールバックが壊れている")
    if pick_image("1999-01-01")["url"] != fallback["url"]:
        errors.append("ヒーローが無い日付が共通画像に落ちない")

    probe = {
        "title": 'A "B" & C',
        "description": '引用「x」と "y" & <z>',
        "url": ORIGIN + "/",
        "og_type": "website",
        "image": fallback,
        "image_alt": "A & B",
    }
    probed = share_lines(probe)
    described = re.search(r'<meta name="description" content="([^"]*)">', probed)
    if not described or html.unescape(described.group(1)) != probe["description"]:
        errors.append("description のエスケープが往復しない")
    once = upsert_share("<head><title>T</title>\n<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\"></head>", probed)
    if upsert_share(once, probed) != once:
        errors.append("共有タグの挿入が冪等でない")

    required = (
        "description", "og:title", "og:description", "og:image", "og:url",
        "og:type", "og:site_name", "og:locale", "twitter:card", "canonical", "icon",
    )
    lengths: list[int] = []
    pages: list[tuple[Path, dict]] = [(path, post_meta(path)) for path in ja_post_paths()]
    pages.append((INDEX, site_meta(INDEX, HOME_DESCRIPTION, ORIGIN + "/")))
    pages.append((ARCHIVE, site_meta(ARCHIVE, ARCHIVE_DESCRIPTION, ORIGIN + "/archive.html")))
    for path, meta in pages:
        rel = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        if upsert_share(source, share_lines(meta)) != source:
            errors.append(f"{rel}: 再実行で head が変わる")
        head_match = re.search(r"<head\b[^>]*>(.*?)</head>", source, re.S | re.I)
        if not head_match:
            errors.append(f"{rel}: head がない")
            continue
        head = head_match.group(1)
        tags = head_tags(head)
        counts: dict[str, int] = {}
        values: dict[str, str] = {}
        for _tag, key, value in tags:
            counts[key] = counts.get(key, 0) + 1
            values.setdefault(key, value)
        for key in required:
            if counts.get(key) != 1:
                errors.append(f"{rel}: {key} が {counts.get(key, 0)} 個")
        if values.get("og:type") != meta["og_type"]:
            errors.append(f"{rel}: og:type が {values.get('og:type')}")
        if values.get("og:locale") != "ja_JP" or values.get("og:site_name") != SITE_NAME:
            errors.append(f"{rel}: site_name または locale が違う")
        if values.get("twitter:card") != "summary_large_image":
            errors.append(f"{rel}: twitter:card が違う")
        if values.get("description") != meta["description"] or values.get("og:description") != meta["description"]:
            errors.append(f"{rel}: description が本文からの値と一致しない")
        if values.get("og:title") != meta["title"] or values.get("og:url") != meta["url"]:
            errors.append(f"{rel}: title または url が違う")
        if values.get("canonical") != meta["url"] or values.get("og:url") != meta["url"]:
            errors.append(f"{rel}: canonical が og:url と違う")
        if values.get("og:image") != meta["image"]["url"] or values.get("twitter:image") != meta["image"]["url"]:
            errors.append(f"{rel}: og:image と twitter:image が違う")
        if values.get("icon") != FAVICON_URL:
            errors.append(f"{rel}: favicon の URL が違う")
        image_url = values.get("og:image", "")
        try:
            image_path = url_to_path(image_url)
        except ValueError:
            errors.append(f"{rel}: og:image がサイトの URL ではない ({image_url})")
            image_path = None
        if image_path is not None and not image_path.is_file():
            errors.append(f"{rel}: og:image のファイルがない ({image_url})")
        desc = values.get("description", "")
        if meta["og_type"] == "article":
            lengths.append(len(desc))
            if not desc or len(desc) > DESC_LIMIT or desc == HOME_DESCRIPTION or "{{" in desc:
                errors.append(f"{rel}: description が空・長すぎ・共通文 ({len(desc)}字)")
            if not re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", desc):
                errors.append(f"{rel}: description に日本語がない")
            hero = find_thumb(path.stem)
            expect = f"{ORIGIN}/{hero}" if hero else f"{ORIGIN}/{FALLBACK_IMAGE}"
            if image_url != expect:
                errors.append(f"{rel}: og:image が {expect} ではない")
        low = source.lower()
        if low.count("</head>") != 1 or low.count("</body>") != 1 or low.count("</html>") != 1:
            errors.append(f"{rel}: html の閉じタグが崩れている")
        if not (low.find("<head") < low.find("</head>") < low.find("<body") < low.find("</body>")):
            errors.append(f"{rel}: head と body の順が崩れている")
        try:
            parser = HTMLParser()
            parser.feed(source)
            parser.close()
        except Exception as exc:  # HTML として解釈できない
            errors.append(f"{rel}: HTML を解釈できない ({exc})")
        alternates = re.findall(r'<link\b[^>]*rel="alternate"', head, re.I)
        if len(alternates) != 3:
            errors.append(f"{rel}: hreflang が {len(alternates)} 本")
        if meta["image"]["width"] and values.get("og:image:width") != str(meta["image"]["width"]):
            errors.append(f"{rel}: og:image:width が実寸と違う")
        if meta["image"]["height"] and values.get("og:image:height") != str(meta["image"]["height"]):
            errors.append(f"{rel}: og:image:height が実寸と違う")

    for path in [ROOT / "posts" / "sample.html", *EN_POSTS_DIR.glob("*.html"), EN_INDEX, EN_ARCHIVE]:
        if path.is_file() and "<!-- share:start -->" in path.read_text(encoding="utf-8"):
            errors.append(f"{path.relative_to(ROOT).as_posix()} は対象外")

    if not errors and lengths:
        print(f"description 字数: {min(lengths)}–{max(lengths)}（記事 {len(lengths)}）")
    return errors


def main() -> None:
    if "--check" in sys.argv[1:]:
        errors = verify_share()
        if errors:
            print("\n".join(errors))
            raise SystemExit(f"共有タグの確認に失敗（{len(errors)} 件）")
        print(f"共有タグの確認: OK（記事 {len(ja_post_paths())}、index、archive）")
        return

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
    changed = refresh_share()
    print(f"共有タグ: {changed} ページを更新" if changed else "共有タグ: 差分なし")
    errors = verify_share()
    if errors:
        print("\n".join(errors))
        raise SystemExit(f"共有タグの確認に失敗（{len(errors)} 件）")
    print(f"共有タグの確認: OK（記事 {len(ja_post_paths())}、index、archive）")


if __name__ == "__main__":
    main()
