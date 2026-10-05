#!/usr/bin/env python3
"""posts/YYYY-MM-DD.html をすべて読み、index.html・archive.html・search.json を作り直す。

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
- ページにマーカーが無ければ、その部分は何もしない（ファイルが無ければ飛ばす）。

タグは記事内の <span class="tag tag-xxx">表示名</span> から拾う。
"""

import html
import json
import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "posts"
INDEX = ROOT / "index.html"
ARCHIVE = ROOT / "archive.html"
SEARCH_JSON = ROOT / "search.json"
ASSETS_DIR = ROOT / "assets"
SITE_SUFFIX = " | 生成AIが語る、生成AI"
HEADLINE_LEN = 60
TOP_MAX_POSTS = 20
TOP_MAX_HEADLINES = 30

POST_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
H1_TAG = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
TAGS = re.compile(r"<[^>]+>")
MAIN_TAG = re.compile(r"<main[^>]*>(.*?)</main>", re.S | re.I)
TAG_SPAN = re.compile(r'<span[^>]*class="[^"]*\btag\b[^"]*"[^>]*>(.*?)</span>', re.S)
NEWS_SECTION = re.compile(r"<h2[^>]*>\s*AIニュース\s*</h2>(.*?)</section>", re.S)
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


def to_headline(fragment: str) -> str:
    text = clean(TAG_SPAN.sub("", SOURCE_SPAN.sub("", fragment)))
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


def extract_headlines(source: str) -> list[dict]:
    """「AIニュース」欄の要点ごとに {"text": 見出し, "url": 出典URL or ""} を返す。"""
    section = NEWS_SECTION.search(source)
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
        text = to_headline(title_part)
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
    body = FIGURE.sub("", POST_HEADER.sub("", body))
    body = TAG_SPAN.sub(" ", SOURCE_SPAN.sub(" ", body))
    body = re.sub(r'<p class="back">.*?</p>', "", body, flags=re.S)
    return clean(body)


def find_thumb(date: str) -> str:
    """assets/YYYY-MM-DD-hero.webp があればサイトルートからの相対パス、無ければ空文字。"""
    name = f"{date}-hero.webp"
    return f"assets/{name}" if (ASSETS_DIR / name).is_file() else ""


def collect_posts() -> list[dict]:
    posts = []
    for path in POSTS_DIR.glob("*.html"):
        match = POST_NAME.match(path.name)
        if not match:
            continue
        date = match.group(1)
        source = path.read_text(encoding="utf-8")
        posts.append({
            "date": date,
            "title": extract_title(source, date),
            "url": f"posts/{path.name}",
            "tags": extract_tags(source),
            "headlines": extract_headlines(source),
            "thumb": find_thumb(date),
            "text": extract_text(source),
        })
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def render_posts(posts: list[dict], with_tags: bool = True, indent: str = "      ") -> str:
    if not posts:
        return f'\n{indent}<p class="empty">まだ記事はありません。</p>'
    items = []
    for p in posts:
        if not with_tags:
            items.append(
                f'{indent}  <li><time datetime="{p["date"]}">{p["date"]}</time>'
                f'<a href="{p["url"]}">{html.escape(p["title"])}</a></li>'
            )
            continue
        tags = ""
        if p["tags"]:
            tags = '<span class="post-tags">' + "".join(tag_html(t) for t in p["tags"]) + "</span>"
        data_tags = html.escape("|".join(p["tags"]))
        body = (
            f'<time datetime="{p["date"]}">{p["date"]}</time>'
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


def headline_html(p: dict, h: dict) -> str:
    day = p["date"][5:].replace("-", "/")
    date_link = (
        f'<a class="news-date" href="{p["url"]}" title="{p["date"]} の記事を読む">'
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
    return f'<li>{date_link}<div class="news-body">{tags}{link}</div></li>'


def render_headlines(posts: list[dict], limit: int | None = None, indent: str = "      ") -> str:
    pairs = [(p, h) for p in posts for h in p["headlines"]]
    if limit is not None:
        pairs = pairs[:limit]
    items = [f"{indent}  {headline_html(p, h)}" for p, h in pairs]
    if not items:
        return f'\n{indent}<p class="empty">まだニュースはありません。</p>'
    return f'\n{indent}<ul class="news-rail-list">\n' + "\n".join(items) + f"\n{indent}</ul>"


def render_tags(posts: list[dict]) -> str:
    indent = "      "
    counts: dict[str, int] = {}
    for p in posts:
        for t in p["tags"]:
            counts[t] = counts.get(t, 0) + 1
    if not counts:
        return f'\n{indent}<p class="empty">まだタグはありません。</p>'
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


if __name__ == "__main__":
    main()
