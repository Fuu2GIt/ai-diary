#!/usr/bin/env python3
"""各ページの共有カード（description / OGP / canonical / favicon）を本文から入れ直す。

rebuild_index.py から呼ぶ。見出しの切れ方や前後リンクとは独立している。

ページ 1 枚から取り出す項目:

- title: <title> の全文（og:title / twitter:title に使う）
- description: 「AIのひとこと」（英語は A Word from AI）を文の区切りで約 120 字。
  無い、またはひな形のままならニュースの要点。それも無ければ題名。
  120 字以内に収まる文は足す。一文だけが 140 字以内ならその文を残す。
  それより長い一文は 120 字以内の句点・読点・語の区切りで切る。
- url: canonical と og:url。絶対 URL。トップは末尾スラッシュ。
- og_type: 日付記事は article。週まとめ・月まとめ・トップ・一覧は website。
- locale: ja_JP / en_US
- image: url は絶対。日付記事はその日のヒーロー（横長）、無ければ assets/og.png。
  まとめ・トップ・一覧は共通画像。幅と高さはファイルから読む。
- image_alt: ヒーローなら題名、共通画像ならサイト名。
- icon: favicon.svg への相対パス。ページの深さに合わせ、絶対パスにはしない。

posts/sample.html は対象外。2 回実行しても head は変わらない。
"""

import html
import re
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "posts"
INDEX = ROOT / "index.html"
ARCHIVE = ROOT / "archive.html"
EN_POSTS_DIR = ROOT / "en" / "posts"
EN_INDEX = ROOT / "en" / "index.html"
EN_ARCHIVE = ROOT / "en" / "archive.html"
WEEKLY_DIR = ROOT / "weekly"
MONTHLY_DIR = ROOT / "monthly"
EN_WEEKLY_DIR = ROOT / "en" / "weekly"
EN_MONTHLY_DIR = ROOT / "en" / "monthly"
ASSETS_DIR = ROOT / "assets"

SITE_NAME = "By AI, About AI"
SITE_SUFFIX = " | By AI, About AI"
ORIGIN = "https://fuu2git.github.io/ai-diary"
FALLBACK_IMAGE = "assets/og.png"
DESC_TARGET = 120
DESC_HARD = 140
HOME_DESCRIPTION = {
    "ja": "ニュースと使い方を、AI自身の視点で",
    "en": "News and how-tos, from AI's own point of view",
}
ARCHIVE_DESCRIPTION = {
    "ja": "By AI, About AI の全記事。キーワード検索とタグで絞り込めます。",
    "en": "All posts on By AI, About AI. Narrow them with keyword search and tags.",
}
GENERIC_DESCRIPTION = set(HOME_DESCRIPTION.values())

POST_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
MONTHLY_NAME = re.compile(r"^(\d{4}-\d{2})\.html$")
TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
H1_TAG = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
TAGS = re.compile(r"<[^>]+>")
TAG_SPAN = re.compile(r'<span[^>]*class="[^"]*\btag\b[^"]*"[^>]*>(.*?)</span>', re.S)
SOURCE_SPAN = re.compile(r'<span class="source">.*?</span>', re.S)
RECAP_FROM = re.compile(r'<a\b[^>]*class="[^"]*\brecap-from\b[^"]*"[^>]*>.*?</a>', re.S)
AI_COMMENT = re.compile(r'<div[^>]*class="[^"]*\bai-comment\b[^"]*"[^>]*>(.*?)</div>', re.S)
NEWS_H2 = {
    "ja": re.compile(r"<h2[^>]*>\s*(?:AIニュース|今週のAIニュース)\s*</h2>(.*?)</section>", re.S),
    "en": re.compile(r"<h2[^>]*>\s*(?:AI News|This Week in AI News)\s*</h2>(.*?)</section>", re.S),
}
SHARE_BLOCK = re.compile(r"[ \t]*<!-- share:start -->.*?<!-- share:end -->\n?", re.S)
LEGACY_SHARE = re.compile(
    r'\n[ \t]*<meta\s[^>]*(?:name="description"|property="og:|name="twitter:)[^>]*>'
    r'|\n[ \t]*<link\s[^>]*rel="(?:canonical|icon)"[^>]*>',
    re.I,
)
PRECONNECT = re.compile(r'\n[ \t]*<link\b[^>]*\brel="preconnect"', re.I)
_EN_ABBREV = {
    "u.s", "u.k", "u.n", "e.g", "i.e", "mr", "mrs", "ms", "dr", "jr", "sr",
    "inc", "ltd", "etc", "fig", "gen", "gov", "vs",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}
_EN_CLOSE = "\"'”’)]}"


def clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAGS.sub(" ", fragment))).strip()


def usable(fragment: str) -> str:
    text = clean(fragment)
    if not text or "{{" in text:
        return ""
    return text


def extract_title(source: str, fallback: str) -> str:
    for pattern in (TITLE_TAG, H1_TAG):
        match = pattern.search(source)
        if match:
            text = clean(match.group(1)).removesuffix(SITE_SUFFIX).strip()
            if text:
                return text
    return fallback


def document_title(source: str, fallback: str) -> str:
    match = TITLE_TAG.search(source)
    if match:
        text = clean(match.group(1))
        if text:
            return text
    return fallback


def extract_ai_comment(source: str) -> str:
    match = AI_COMMENT.search(source)
    return usable(match.group(1)) if match else ""


def extract_news_prose(source: str, lang: str) -> str:
    match = NEWS_H2[lang].search(source)
    if not match:
        return ""
    body = RECAP_FROM.sub("", match.group(1))
    body = SOURCE_SPAN.sub(" ", TAG_SPAN.sub(" ", body))
    return usable(body)


def _en_sentence_end(text: str, i: int) -> int | None:
    """text[i] が文末記号なら、閉じ引用を含めた直後の位置。文末でなければ None。"""
    ch = text[i]
    if ch not in ".?!":
        return None
    n = len(text)
    if ch == "." and text.startswith("...", i):
        return None
    if (
        ch == "."
        and i > 0
        and i + 1 < n
        and text[i - 1].isdigit()
        and text[i + 1].isdigit()
    ):
        return None
    if ch == ".":
        j = i - 1
        while j >= 0 and (text[j].isalpha() or text[j] == "."):
            j -= 1
        word = text[j + 1:i].lower()
        if word in _EN_ABBREV or word.replace(".", "") in _EN_ABBREV:
            return None
    nxt = text[i + 1:] if i + 1 < n else ""
    if nxt.startswith(" ") and len(nxt) > 1 and nxt[1].islower():
        return None
    if nxt == "" or nxt[0] in " \t\n\"'”’)]}":
        end = i + 1
        while end < n and text[end] in _EN_CLOSE:
            end += 1
        return end
    return None


def split_sentences(text: str, lang: str) -> list[str]:
    if lang == "ja":
        return [part for part in re.findall(r"[^。]*。|[^。]+", text) if part.strip()]
    parts: list[str] = []
    start = 0
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("...", i):
            i += 3
            continue
        end = _en_sentence_end(text, i)
        if end is not None:
            parts.append(text[start:end])
            start = end
            i = end
            continue
        i += 1
    if start < n and text[start:].strip():
        parts.append(text[start:])
    return parts


def clip_inside(text: str, lang: str) -> str:
    """120字を超える一文を、句点・読点・語の区切りで 120 字以内にする。"""
    window = text[:DESC_TARGET]
    if lang == "ja":
        for sep in ("。", "、"):
            index = window.rfind(sep)
            if index >= DESC_TARGET // 2:
                if sep == "。":
                    return window[: index + 1]
                return window[:index].rstrip() + "…"
    else:
        for sep in (". ", "? ", "! ", "。"):
            index = window.rfind(sep)
            if index >= DESC_TARGET // 2:
                return window[: index + 1].rstrip()
        for sep in ("; ", ", ", ": ", "、", "—"):
            index = window.rfind(sep)
            if index >= DESC_TARGET // 2:
                return window[:index].rstrip(" ,;:、—") + "…"
    space = window.rfind(" ")
    if space >= DESC_TARGET // 2:
        return window[:space].rstrip(" ,;:、—") + "…"
    return window[: DESC_TARGET - 1].rstrip() + "…"


def clip_description(text: str, lang: str) -> str:
    text = clean(text)
    if len(text) <= DESC_TARGET:
        return text
    acc = ""
    for raw in split_sentences(text, lang):
        piece = raw.strip()
        if not piece:
            continue
        joiner = "" if (not acc or lang == "ja") else " "
        candidate = piece if not acc else acc + joiner + piece
        if len(candidate) <= DESC_TARGET:
            acc = candidate
            continue
        if not acc and len(piece) <= DESC_HARD:
            return piece
        break
    if acc:
        return acc
    return clip_inside(text, lang)


def share_description(source: str, lang: str, title: str) -> str:
    comment = extract_ai_comment(source)
    if comment:
        return clip_description(comment, lang)
    news = extract_news_prose(source, lang)
    if news:
        return clip_description(news, lang)
    return clip_description(title, lang)


def find_hero(date: str) -> str:
    name = f"{date}-hero.webp"
    return f"assets/{name}" if (ASSETS_DIR / name).is_file() else ""


def webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[0:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
    if chunk == b"VP8 " and len(data) >= 30:
        return (
            int.from_bytes(data[26:28], "little") & 0x3FFF,
            int.from_bytes(data[28:30], "little") & 0x3FFF,
        )
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def image_info(rel: str) -> dict:
    path = ROOT / rel
    data = path.read_bytes()
    mime, width, height = "application/octet-stream", None, None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        mime = "image/png"
    else:
        size = webp_size(data)
        if size or (len(data) >= 12 and data[8:12] == b"WEBP"):
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


def pick_share_image(kind: str, path: Path) -> dict:
    rel = find_hero(path.stem) if kind == "post" else ""
    return image_info(rel or FALLBACK_IMAGE)


def page_url(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel == "index.html":
        return ORIGIN + "/"
    if rel == "en/index.html":
        return ORIGIN + "/en/"
    return f"{ORIGIN}/{rel}"


def icon_href(path: Path) -> str:
    depth = len(path.relative_to(ROOT).parts) - 1
    return f"{'../' * depth}favicon.svg"


def share_targets() -> list[tuple[Path, str, str]]:
    """(path, kind, lang)。kind は home / archive / post / weekly / monthly。sample は含めない。"""
    found: list[tuple[Path, str, str]] = []

    def add_file(path: Path, kind: str, lang: str) -> None:
        if path.is_file():
            found.append((path, kind, lang))

    add_file(INDEX, "home", "ja")
    add_file(ARCHIVE, "archive", "ja")
    add_file(EN_INDEX, "home", "en")
    add_file(EN_ARCHIVE, "archive", "en")
    for directory, kind, lang, pattern in (
        (POSTS_DIR, "post", "ja", POST_NAME),
        (EN_POSTS_DIR, "post", "en", POST_NAME),
        (WEEKLY_DIR, "weekly", "ja", POST_NAME),
        (EN_WEEKLY_DIR, "weekly", "en", POST_NAME),
        (MONTHLY_DIR, "monthly", "ja", MONTHLY_NAME),
        (EN_MONTHLY_DIR, "monthly", "en", MONTHLY_NAME),
    ):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.html")):
            if pattern.match(path.name):
                found.append((path, kind, lang))
    return found


def page_meta(path: Path, kind: str, lang: str) -> dict:
    source = path.read_text(encoding="utf-8")
    plain = extract_title(source, path.stem)
    if kind == "home":
        description = HOME_DESCRIPTION[lang]
    elif kind == "archive":
        description = ARCHIVE_DESCRIPTION[lang]
    else:
        description = share_description(source, lang, plain)
    image = pick_share_image(kind, path)
    return {
        "title": document_title(source, plain if kind == "home" else plain + SITE_SUFFIX),
        "description": description,
        "url": page_url(path),
        "og_type": "article" if kind == "post" else "website",
        "locale": "ja_JP" if lang == "ja" else "en_US",
        "image": image,
        "image_alt": plain if image["rel"] != FALLBACK_IMAGE else SITE_NAME,
        "icon": icon_href(path),
        "kind": kind,
        "lang": lang,
    }


def share_lines(meta: dict) -> str:
    def esc(value: str) -> str:
        return html.escape(value, quote=True)

    image = meta["image"]
    lines = [
        "<!-- share:start -->",
        f'<meta name="description" content="{esc(meta["description"])}">',
        f'<meta property="og:type" content="{esc(meta["og_type"])}">',
        f'<meta property="og:site_name" content="{esc(SITE_NAME)}">',
        f'<meta property="og:locale" content="{esc(meta["locale"])}">',
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
        f'<link rel="icon" href="{esc(meta["icon"])}" type="image/svg+xml">',
        "<!-- share:end -->",
    ]
    return "\n".join("  " + line for line in lines) + "\n"


def upsert_share(source: str, block: str) -> str:
    """共有タグを preconnect の直前に 1 つだけ置く。hreflang は動かさない。"""
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


def apply_share(path: Path, meta: dict) -> bool:
    source = path.read_text(encoding="utf-8")
    updated = upsert_share(source, share_lines(meta))
    if updated == source:
        return False
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def refresh_share() -> int:
    changed = 0
    for path, kind, lang in share_targets():
        changed += apply_share(path, page_meta(path, kind, lang))
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


def ends_sentence(text: str) -> bool:
    return bool(re.search(r"[。．.!?…][\"'”’)]*$", text))


def _check_rules(errors: list[str]) -> None:
    """本文が無くても確かめられる切り方。公開ページを書き換えない。"""
    long_two = "あ" * 40 + "。" + "い" * 90 + "。"
    if clip_description(long_two, "ja") != "あ" * 40 + "。":
        errors.append("日本語の説明が 120 字で文を足しすぎている")
    slight = "う" * 125 + "。"
    if clip_description(slight, "ja") != slight:
        errors.append("140 字以内の一文を残せていない")
    huge = clip_description("え" * 200 + "。", "ja")
    if len(huge) > DESC_TARGET or not huge.endswith("…"):
        errors.append(f"長すぎる日本語の一文を切れていない ({huge})")
    abbrev = "The U.S. agency published a note. " + ("More context follows here. " * 12)
    clipped = clip_description(abbrev, "en")
    if not clipped.startswith("The U.S. agency published a note."):
        errors.append(f"英語の略語で文が切れた ({clipped})")
    if len(clipped) > DESC_HARD:
        errors.append(f"英語の説明が長すぎる ({len(clipped)})")
    news = (
        "<section><h2>AIニュース</h2><ul><li>"
        '<span class="tag tag-openai">OpenAI</span> 要点はこれだ。続きもある。 '
        '<span class="source">（出典: <a href="https://example.com/a">https://example.com/a</a>）</span>'
        "</li></ul></section>"
    )
    if share_description(news, "ja", "題名") != "要点はこれだ。続きもある。":
        errors.append(f"ニュース要点の切り出しが違う ({share_description(news, 'ja', '題名')})")
    placeholder = '<div class="ai-comment"><p>{{AI_COMMENT}}</p></div>' + news
    if share_description(placeholder, "ja", "題名") != "要点はこれだ。続きもある。":
        errors.append("ひな形のひとことを説明に使っている")
    if share_description("<h1>x</h1>", "ja", "題名だけ") != "題名だけ":
        errors.append("題名へのフォールバックが違う")
    if share_description("<h1>x</h1>", "en", "Title only") != "Title only":
        errors.append("英語の題名へのフォールバックが違う")
    weekly = (
        "<section><h2>今週のAIニュース</h2><ul><li>"
        '<span class="tag tag-policy">政策・規制</span> 週の要点だ。 '
        '<a class="recap-from" href="../posts/2026-10-12.html">→ 10/12の記事</a>'
        "</li></ul></section>"
    )
    if share_description(weekly, "ja", "題") != "週の要点だ。":
        errors.append(f"週まとめの要点にリンク文言が残った ({share_description(weekly, 'ja', '題')})")
    fallback = image_info(FALLBACK_IMAGE)
    if fallback["width"] != 1200 or fallback["height"] != 1200 or fallback["type"] != "image/png":
        errors.append("共通画像の寸法を読めていない")
    hero = image_info("assets/2026-10-19-hero.webp")
    if hero["width"] != 1280 or hero["height"] != 720 or hero["type"] != "image/webp":
        errors.append("ヒーローの寸法を読めていない")
    missing = pick_share_image("post", Path("1999-01-01.html"))
    if missing["rel"] != FALLBACK_IMAGE:
        errors.append("ヒーローが無い日付が共通画像に落ちない")
    if pick_share_image("weekly", Path("2026-10-12.html"))["rel"] != FALLBACK_IMAGE:
        errors.append("まとめページが日付のヒーローを使っている")
    probe = {
        "title": 'A "B" & C',
        "description": '引用「x」と "y" & <z>',
        "url": ORIGIN + "/",
        "og_type": "website",
        "locale": "ja_JP",
        "image": fallback,
        "image_alt": "A & B",
        "icon": "favicon.svg",
    }
    block = share_lines(probe)
    described = re.search(r'<meta name="description" content="([^"]*)">', block)
    if not described or html.unescape(described.group(1)) != probe["description"]:
        errors.append("description のエスケープが往復しない")
    skeleton = (
        "<head>\n  <title>T</title>\n"
        '  <link rel="alternate" hreflang="ja" href="https://fuu2git.github.io/ai-diary/">\n'
        '  <meta name="description" content="old">\n'
        '  <meta property="og:title" content="old">\n'
        '  <link rel="preconnect" href="https://fonts.googleapis.com">\n'
        "</head>"
    )
    once = upsert_share(skeleton, block)
    if upsert_share(once, block) != once:
        errors.append("共有タグの挿入が冪等でない")
    if once.count('rel="alternate"') != 1 or once.count('content="old"') != 0:
        errors.append("挿入が hreflang を消すか、古い共有タグを残している")
    if icon_href(ROOT / "posts" / "2026-10-19.html") != "../favicon.svg":
        errors.append("記事の favicon 相対パスが違う")
    if icon_href(ROOT / "en" / "posts" / "2026-10-19.html") != "../../favicon.svg":
        errors.append("英語記事の favicon 相対パスが違う")
    if icon_href(INDEX) != "favicon.svg":
        errors.append("トップの favicon 相対パスが違う")


def verify_share() -> list[str]:
    errors: list[str] = []
    _check_rules(errors)
    favicon = ROOT / "favicon.svg"
    if not favicon.is_file() or "<svg" not in favicon.read_text(encoding="utf-8"):
        errors.append("favicon.svg がありません")
    if not (ROOT / FALLBACK_IMAGE).is_file():
        errors.append("assets/og.png がありません")

    required = (
        "description", "og:title", "og:description", "og:image", "og:url",
        "og:type", "twitter:card", "canonical", "icon",
    )
    lengths: dict[str, list[int]] = {"ja": [], "en": []}
    heroes = fallbacks = 0
    for path, kind, lang in share_targets():
        rel = path.relative_to(ROOT).as_posix()
        meta = page_meta(path, kind, lang)
        source = path.read_text(encoding="utf-8")
        if upsert_share(source, share_lines(meta)) != source:
            errors.append(f"{rel}: 再実行で head が変わる")
        head_match = re.search(r"<head\b[^>]*>(.*?)</head>", source, re.S | re.I)
        if not head_match:
            errors.append(f"{rel}: head がない")
            continue
        head = head_match.group(1)
        counts: dict[str, int] = {}
        values: dict[str, str] = {}
        for _tag, key, value in head_tags(head):
            counts[key] = counts.get(key, 0) + 1
            values.setdefault(key, value)
        for key in required:
            if counts.get(key) != 1:
                errors.append(f"{rel}: {key} が {counts.get(key, 0)} 個")
        if values.get("og:type") != meta["og_type"]:
            errors.append(f"{rel}: og:type が {values.get('og:type')}")
        if values.get("og:locale") != meta["locale"]:
            errors.append(f"{rel}: og:locale が {values.get('og:locale')}")
        if values.get("twitter:card") != "summary_large_image":
            errors.append(f"{rel}: twitter:card が違う")
        if values.get("description") != meta["description"] or values.get("og:description") != meta["description"]:
            errors.append(f"{rel}: description が本文からの値と一致しない")
        if values.get("twitter:description") != meta["description"]:
            errors.append(f"{rel}: twitter:description が description と違う")
        if values.get("og:title") != meta["title"] or values.get("twitter:title") != meta["title"]:
            errors.append(f"{rel}: og:title が title と違う")
        if values.get("og:url") != meta["url"] or values.get("canonical") != meta["url"]:
            errors.append(f"{rel}: canonical と og:url が一致しない")
        if values.get("og:image") != meta["image"]["url"] or values.get("twitter:image") != meta["image"]["url"]:
            errors.append(f"{rel}: og:image と twitter:image が違う")
        icon_line = f'<link rel="icon" href="{meta["icon"]}" type="image/svg+xml">'
        if icon_line not in source or values.get("icon") != meta["icon"]:
            errors.append(f"{rel}: favicon の相対パスが違う")
        else:
            resolved = (path.parent / meta["icon"]).resolve()
            if resolved != favicon.resolve():
                errors.append(f"{rel}: favicon がファイルに届かない")
        image_url = values.get("og:image", "")
        if not image_url.startswith(ORIGIN + "/"):
            errors.append(f"{rel}: og:image が完全な URL ではない")
            image_path = None
        else:
            try:
                image_path = url_to_path(image_url)
            except ValueError:
                errors.append(f"{rel}: og:image のパスが不正 ({image_url})")
                image_path = None
        if image_path is not None and not image_path.is_file():
            errors.append(f"{rel}: og:image のファイルがない ({image_url})")
        elif image_path is not None:
            if meta["image"]["rel"] == FALLBACK_IMAGE:
                fallbacks += 1
            else:
                heroes += 1
        if meta["image"]["width"] and values.get("og:image:width") != str(meta["image"]["width"]):
            errors.append(f"{rel}: og:image:width が実寸と違う")
        if meta["image"]["height"] and values.get("og:image:height") != str(meta["image"]["height"]):
            errors.append(f"{rel}: og:image:height が実寸と違う")
        expect_image = f"{ORIGIN}/{find_hero(path.stem) or FALLBACK_IMAGE}" if kind == "post" else f"{ORIGIN}/{FALLBACK_IMAGE}"
        if image_url and image_url != expect_image:
            errors.append(f"{rel}: og:image が {expect_image} ではない")
        desc = values.get("description", "")
        if not desc or "{{" in desc or len(desc) > DESC_HARD:
            errors.append(f"{rel}: description が空・ひな形・長すぎ ({len(desc)}字)")
        elif len(desc) > DESC_TARGET and not ends_sentence(desc):
            errors.append(f"{rel}: 120字を超える説明が文末で終わっていない")
        if kind in {"post", "weekly", "monthly"}:
            lengths[lang].append(len(desc))
            if desc in GENERIC_DESCRIPTION:
                errors.append(f"{rel}: 説明がサイト共通の文のまま")
        if lang == "ja" and desc and not re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", desc):
            errors.append(f"{rel}: description に日本語がない")
        if lang == "en" and desc and not re.search(r"[A-Za-z]", desc):
            errors.append(f"{rel}: description に英語がない")
        low = source.lower()
        if low.count("</head>") != 1 or low.count("</body>") != 1 or low.count("</html>") != 1:
            errors.append(f"{rel}: html の閉じタグが崩れている")
        if not (low.find("<head") < low.find("</head>") < low.find("<body") < low.find("</body>")):
            errors.append(f"{rel}: head と body の順が崩れている")
        try:
            parser = HTMLParser()
            parser.feed(source)
            parser.close()
        except Exception as exc:
            errors.append(f"{rel}: HTML を解釈できない ({exc})")
        if len(re.findall(r'<link\b[^>]*rel="alternate"', head, re.I)) != 3:
            errors.append(f"{rel}: hreflang が 3 本ではない")

    sample = ROOT / "posts" / "sample.html"
    if sample.is_file() and "<!-- share:start -->" in sample.read_text(encoding="utf-8"):
        errors.append("posts/sample.html を書き換えた")
    for path in sorted((ROOT / "templates").glob("*.html")):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        if "{{DESCRIPTION}}" not in text or 'rel="canonical"' not in text or 'rel="icon"' not in text:
            errors.append(f"{rel}: ひな形に description / canonical / icon の穴がない")

    if not errors and (lengths["ja"] or lengths["en"]):
        def span(nums: list[int]) -> str:
            return f"{min(nums)}–{max(nums)}（{len(nums)}）" if nums else "なし"
        print(
            f"description 字数: ja {span(lengths['ja'])} / en {span(lengths['en'])}"
            f"、og:image ヒーロー {heroes} / 共通画像 {fallbacks}"
        )
    return errors


def main() -> None:
    if "--check" not in sys.argv[1:]:
        changed = refresh_share()
        print(f"共有タグ: {changed} ページを更新" if changed else "共有タグ: 差分なし")
    errors = verify_share()
    if errors:
        print("\n".join(errors))
        raise SystemExit(f"共有タグの確認に失敗（{len(errors)} 件）")
    print(f"共有タグの確認: OK（{len(share_targets())} ページ）")


if __name__ == "__main__":
    main()
