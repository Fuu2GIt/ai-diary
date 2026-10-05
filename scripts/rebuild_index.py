#!/usr/bin/env python3
"""posts/YYYY-MM-DD.html を日付降順で読み、index.html の記事一覧を書き換える。"""

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "posts"
INDEX = ROOT / "index.html"
MAX_POSTS = 20
SITE_SUFFIX = " | 生成AIが語る、生成AI"

POST_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
MARKERS = re.compile(r"(<!-- POSTS:START -->)(.*?)(\n[ \t]*<!-- POSTS:END -->)", re.S)
TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
H1_TAG = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
TAGS = re.compile(r"<[^>]+>")
NEWS_MARKERS = re.compile(r"(<!-- NEWS:START -->)(.*?)(\n[ \t]*<!-- NEWS:END -->)", re.S)
NEWS_SECTION = re.compile(r"<h2[^>]*>\s*AIニュース\s*</h2>(.*?)</section>", re.S)
CARD_TITLE = re.compile(r'<[^>]*class="[^"]*card-title[^"]*"[^>]*>(.*?)</', re.S)
LIST_ITEM = re.compile(r"<li[^>]*>(.*?)</li>", re.S)
SOURCE_SPAN = re.compile(r'<span class="source">.*?</span>', re.S)
MAX_HEADLINES = 30
HEADLINE_LEN = 60


def extract_title(source: str, fallback: str) -> str:
    for pattern in (TITLE_TAG, H1_TAG):
        match = pattern.search(source)
        if match:
            text = html.unescape(TAGS.sub("", match.group(1))).strip()
            text = text.removesuffix(SITE_SUFFIX).strip()
            if text:
                return text
    return fallback


def collect_posts() -> list[tuple[str, str, str]]:
    posts = []
    for path in POSTS_DIR.glob("*.html"):
        match = POST_NAME.match(path.name)
        if not match:
            continue
        date = match.group(1)
        title = extract_title(path.read_text(encoding="utf-8"), date)
        posts.append((date, title, f"posts/{path.name}"))
    posts.sort(key=lambda p: p[0], reverse=True)
    return posts[:MAX_POSTS]


def render(posts: list[tuple[str, str, str]]) -> str:
    indent = "      "
    if not posts:
        return f"\n{indent}<p class=\"empty\">まだ記事はありません。</p>"
    items = [
        f'{indent}  <li><time datetime="{date}">{date}</time>'
        f'<a href="{href}">{html.escape(title)}</a></li>'
        for date, title, href in posts
    ]
    return f'\n{indent}<ul class="post-list">\n' + "\n".join(items) + f"\n{indent}</ul>"


def to_headline(fragment: str) -> str:
    text = html.unescape(TAGS.sub("", SOURCE_SPAN.sub("", fragment)))
    text = re.sub(r"\s+", " ", text).strip()
    if "。" in text:
        text = text.split("。", 1)[0]
    if len(text) > HEADLINE_LEN:
        text = text[: HEADLINE_LEN - 1].rstrip() + "…"
    return text


def collect_headlines(posts: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """各記事の「AIニュース」欄から、要点ごとの見出し（一文目）を拾う。"""
    headlines = []
    for date, _title, href in posts:
        source = (ROOT / href).read_text(encoding="utf-8")
        section = NEWS_SECTION.search(source)
        if not section:
            continue
        body = section.group(1)
        fragments = CARD_TITLE.findall(body) or LIST_ITEM.findall(body)
        for fragment in fragments:
            text = to_headline(fragment)
            if text and "{{" not in text:
                headlines.append((date, text, href))
            if len(headlines) >= MAX_HEADLINES:
                return headlines
    return headlines


def render_headlines(headlines: list[tuple[str, str, str]]) -> str:
    indent = "    "
    if not headlines:
        return f'\n{indent}<p class="empty">まだニュースはありません。</p>'
    items = [
        f'{indent}  <li><time datetime="{date}">{date[5:].replace("-", "/")}</time>'
        f'<a href="{href}">{html.escape(text)}</a></li>'
        for date, text, href in headlines
    ]
    return f'\n{indent}<ul class="news-rail-list">\n' + "\n".join(items) + f"\n{indent}</ul>"


def main() -> None:
    source = INDEX.read_text(encoding="utf-8")
    if not MARKERS.search(source):
        raise SystemExit("index.html に POSTS:START / POSTS:END マーカーがありません")
    posts = collect_posts()
    updated = MARKERS.sub(lambda m: m.group(1) + render(posts) + m.group(3), source, count=1)
    headline_count = 0
    if NEWS_MARKERS.search(updated):
        headlines = collect_headlines(posts)
        headline_count = len(headlines)
        updated = NEWS_MARKERS.sub(
            lambda m: m.group(1) + render_headlines(headlines) + m.group(3), updated, count=1
        )
    INDEX.write_text(updated, encoding="utf-8", newline="\n")
    print(f"index.html を更新しました（{len(posts)} 件、ニュース見出し {headline_count} 件）")


if __name__ == "__main__":
    main()
