#!/usr/bin/env python3
"""出典リンクの表示文字を媒体名（無ければドメイン）に揃える。

記事の <span class="source"> は、これまで次の形だった。

    （出典: <a href="URL">URL</a>（TechCrunch） ／ <a href="URL">URL</a>（CNBC））
    (Source: <a href="URL">URL</a> (TechCrunch) / <a href="URL">URL</a>)

CSS の font-size: 0 で「出典:」や括弧を隠し、見える文字は途中で切れた URL だった。
このスクリプトは span の中身をリンクだけにする。

    <a href="URL" target="_blank" rel="noopener">TechCrunch</a><a href="URL" target="_blank" rel="noopener">CNBC</a>

見える文字は、そのリンクの直後にある括弧書き（全角・半角）から取る。
括弧が無い、またはリンク文字がすでに URL でないときは、その文字を残す。
URL のままで媒体名も無いときは、www. を外したホスト名にする。
「いずれも…」「both …」は複数リンクに共通の媒体名として、いずれも／both を外して各リンクに付ける。
href はそのまま、target="_blank" rel="noopener" は付ける。2回実行しても結果は変わらない。

引数なしでは posts/ と en/posts/ を変換する。週まとめも同じ印なので、
weekly/ と en/weekly/ を引数に足して実行できる。--check は書き換えない。
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIRS = ("posts", "en/posts")
SPAN_RE = re.compile(r'(<span class="source">)(.*?)(</span>)', re.S)
ANCHOR_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
LABEL_RE = re.compile(r"[（(]([^（）()]*)[）)]")
GROUP_RE = re.compile(r"^(?:いずれも|both\b)\s*", re.I)


def attr(attrs: str, name: str) -> str | None:
    match = re.search(
        rf"""\b{name}\s*=\s*(?:"([^"]*)"|'([^']*)')""",
        attrs,
        re.I,
    )
    if not match:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def first_label(gap: str) -> str | None:
    for raw in LABEL_RE.findall(gap):
        label = re.sub(r"\s+", " ", raw).strip()
        if label:
            return label
    return None


def is_url_text(text: str, href: str) -> bool:
    current = re.sub(r"\s+", " ", html.unescape(text)).strip()
    target = html.unescape(href).strip()
    if not current or current == target:
        return True
    return current.startswith(("http://", "https://"))


def domain_label(href: str) -> str:
    raw = html.unescape(href).strip()
    host = urlparse(raw).hostname or ""
    if host.lower().startswith("www."):
        host = host[4:]
    return host or raw


def media_name(label: str) -> str:
    trimmed = GROUP_RE.sub("", label).strip()
    return trimmed or label.strip()


def link_text(href: str, current: str, label: str | None) -> str:
    if label:
        return media_name(label)
    shown = re.sub(r"\s+", " ", html.unescape(current)).strip()
    if is_url_text(current, href):
        return domain_label(href)
    return shown


def render_anchor(href: str, text: str) -> str:
    return (
        f'<a href="{href}" target="_blank" rel="noopener">'
        f"{html.escape(text, quote=False)}</a>"
    )


def normalize_inner(inner: str) -> str:
    anchors = list(ANCHOR_RE.finditer(inner))
    if not anchors:
        return inner
    items: list[dict] = []
    for index, match in enumerate(anchors):
        href = attr(match.group(1), "href")
        if href is None or "{{" in href or "{{" in match.group(2):
            return inner
        nxt = anchors[index + 1].start() if index + 1 < len(anchors) else len(inner)
        items.append(
            {
                "href": href,
                "text": match.group(2),
                "label": first_label(inner[match.end() : nxt]),
            }
        )
    group = next((item["label"] for item in items if item["label"] and GROUP_RE.match(item["label"])), None)
    parts = []
    for item in items:
        label = item["label"]
        if group and label is None and is_url_text(item["text"], item["href"]):
            label = group
        parts.append(render_anchor(item["href"], link_text(item["href"], item["text"], label)))
    return "".join(parts)


def normalize_html(source: str) -> str:
    return SPAN_RE.sub(lambda match: match.group(1) + normalize_inner(match.group(2)) + match.group(3), source)


def iter_files(dirs: list[str]) -> list[Path]:
    files: list[Path] = []
    for name in dirs:
        root = Path(name)
        if not root.is_absolute():
            root = ROOT / root
        if root.is_file():
            files.append(root)
            continue
        files.extend(sorted(root.glob("*.html")))
    return files


def convert(dirs: list[str], check: bool) -> tuple[int, int, int]:
    changed_files = 0
    changed_links = 0
    scanned = 0
    for path in iter_files(dirs):
        text = path.read_bytes().decode("utf-8")
        updated = normalize_html(text)
        scanned += 1
        if updated == text:
            continue
        changed_files += 1
        changed_links += sum(len(ANCHOR_RE.findall(inner)) for _, inner, _ in SPAN_RE.findall(text))
        if not check:
            path.write_bytes(updated.encode("utf-8"))
    return scanned, changed_files, changed_links


def self_test() -> None:
    cases = [
        (
            "（出典: <a href=\"https://techcrunch.com/a\" target=\"_blank\" rel=\"noopener\">https://techcrunch.com/a</a>（TechCrunch） ／ <a href=\"https://www.cnbc.com/b\" target=\"_blank\" rel=\"noopener\">https://www.cnbc.com/b</a>（CNBC））",
            '<a href="https://techcrunch.com/a" target="_blank" rel="noopener">TechCrunch</a>'
            '<a href="https://www.cnbc.com/b" target="_blank" rel="noopener">CNBC</a>',
        ),
        (
            '(Source: <a href="https://www.theverge.com/x" target="_blank" rel="noopener">https://www.theverge.com/x</a>)',
            '<a href="https://www.theverge.com/x" target="_blank" rel="noopener">theverge.com</a>',
        ),
        (
            "（出典: <a href=\"https://www.investing.com/a\" target=\"_blank\" rel=\"noopener\">https://www.investing.com/a</a>）（Reuters配信）",
            '<a href="https://www.investing.com/a" target="_blank" rel="noopener">Reuters配信</a>',
        ),
        (
            '(Source: <a href="https://www.investing.com/a" target="_blank" rel="noopener">https://www.investing.com/a</a>) (via Reuters)',
            '<a href="https://www.investing.com/a" target="_blank" rel="noopener">via Reuters</a>',
        ),
        (
            "（出典: <a href=\"https://www.cbsnews.com/a\" target=\"_blank\" rel=\"noopener\">CBS News</a> ／ <a href=\"https://www.npr.org/b\" target=\"_blank\" rel=\"noopener\">NPR</a>）",
            '<a href="https://www.cbsnews.com/a" target="_blank" rel="noopener">CBS News</a>'
            '<a href="https://www.npr.org/b" target="_blank" rel="noopener">NPR</a>',
        ),
        (
            "（出典: <a href=\"https://www.investing.com/a\" target=\"_blank\" rel=\"noopener\">https://www.investing.com/a</a> ／ <a href=\"https://au.investing.com/b\" target=\"_blank\" rel=\"noopener\">https://au.investing.com/b</a> （いずれもReuters配信））",
            '<a href="https://www.investing.com/a" target="_blank" rel="noopener">Reuters配信</a>'
            '<a href="https://au.investing.com/b" target="_blank" rel="noopener">Reuters配信</a>',
        ),
        (
            '(Source: <a href="https://openai.com/a" target="_blank" rel="noopener">https://openai.com/a</a> / <a href="https://economictimes.indiatimes.com/b" target="_blank" rel="noopener">https://economictimes.indiatimes.com/b</a> (carried by Reuters))',
            '<a href="https://openai.com/a" target="_blank" rel="noopener">openai.com</a>'
            '<a href="https://economictimes.indiatimes.com/b" target="_blank" rel="noopener">carried by Reuters</a>',
        ),
        (
            '(Source: <a href="https://blog.google/a" target="_blank" rel="noopener">https://blog.google/a</a> (Google) / <a href="https://techcrunch.com/b" target="_blank" rel="noopener">https://techcrunch.com/b</a> (TechCrunch))',
            '<a href="https://blog.google/a" target="_blank" rel="noopener">Google</a>'
            '<a href="https://techcrunch.com/b" target="_blank" rel="noopener">TechCrunch</a>',
        ),
        (
            "（出典: <a href=\"https://www.nikkei.com/a\" target=\"_blank\" rel=\"noopener\">https://www.nikkei.com/a</a>（日経、11/1））",
            '<a href="https://www.nikkei.com/a" target="_blank" rel="noopener">日経、11/1</a>',
        ),
        (
            '(Source: <a href="https://www.motir.go.kr/a" target="_blank" rel="noopener">https://www.motir.go.kr/a</a> (South Korea\'s Ministry of Trade, Industry and Energy))',
            '<a href="https://www.motir.go.kr/a" target="_blank" rel="noopener">South Korea\'s Ministry of Trade, Industry and Energy</a>',
        ),
    ]
    page = "<li>" + "".join(f'<span class="source">{inner}</span>' for inner, _ in cases) + "</li>"
    once = normalize_html(page)
    twice = normalize_html(once)
    if once != twice:
        raise SystemExit("self-test: not idempotent")
    for inner, expected in cases:
        got = normalize_inner(inner)
        if got != expected:
            raise SystemExit(f"self-test failed\n got: {got}\n want: {expected}")
    print(f"self-test: OK（{len(cases)} 件）")


def main() -> None:
    args = sys.argv[1:]
    if "--self-test" in args:
        self_test()
        args = [arg for arg in args if arg != "--self-test"]
    check = "--check" in args
    dirs = [arg for arg in args if arg != "--check"] or list(DEFAULT_DIRS)
    action = "要変換" if check else "変換"
    failed = False
    for name in dirs:
        scanned, changed_files, changed_links = convert([name], check)
        print(f"{action}: {name} {changed_files} ファイル / 走査 {scanned}（出典リンク {changed_links}）")
        failed = failed or (check and changed_files > 0)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
