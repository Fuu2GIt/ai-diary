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


def main() -> None:
    source = INDEX.read_text(encoding="utf-8")
    if not MARKERS.search(source):
        raise SystemExit("index.html に POSTS:START / POSTS:END マーカーがありません")
    posts = collect_posts()
    updated = MARKERS.sub(lambda m: m.group(1) + render(posts) + m.group(3), source, count=1)
    INDEX.write_text(updated, encoding="utf-8", newline="\n")
    print(f"index.html を更新しました（{len(posts)} 件）")


if __name__ == "__main__":
    main()
