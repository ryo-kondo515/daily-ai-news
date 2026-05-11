from __future__ import annotations

import html
import os
import re
import smtplib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path

JST = timezone(timedelta(hours=9), "JST")
OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)
HTML_PATH = OUT_DIR / "digest.html"

LABEL_DIRECT = "\u76f4\u63a5\u4f7f\u3048\u308b"
LABEL_INDIRECT = "\u9593\u63a5\u7684\u306b\u6709\u7528"
LABEL_NONE = "\u95a2\u4fc2\u306a\u3057"


@dataclass
class FeedSource:
    name: str
    url: str
    source_type: str


@dataclass
class Item:
    title: str
    link: str
    source_name: str
    source_type: str
    published_at: datetime
    summary: str
    display_title: str = ""
    importance: str = "Low"
    applicability: str = LABEL_NONE
    copilot_tip: str = ""
    why: str = ""
    community: str = ""
    deadline: str = ""
    score: int = 0


FEEDS: list[FeedSource] = [
    FeedSource("OpenAI News", "https://openai.com/news/rss.xml", "official"),
    FeedSource("Anthropic News", "https://www.anthropic.com/news/rss.xml", "official"),
    FeedSource("GitHub Blog", "https://github.blog/feed/", "official"),
    FeedSource("GitHub Changelog", "https://github.blog/changelog/feed/", "official"),
    FeedSource("Google Blog AI", "https://blog.google/technology/ai/rss/", "official"),
    FeedSource("NVIDIA Blog", "https://blogs.nvidia.com/blog/category/ai/feed/", "official"),
    FeedSource("OpenAI on Hacker News", "https://hnrss.org/newest?q=OpenAI", "community"),
    FeedSource("Anthropic on Hacker News", "https://hnrss.org/newest?q=Anthropic", "community"),
    FeedSource("Copilot on Hacker News", "https://hnrss.org/newest?q=%22GitHub%20Copilot%22", "community"),
    FeedSource("r/LocalLLaMA", "https://www.reddit.com/r/LocalLLaMA/new/.rss", "community"),
    FeedSource("r/MachineLearning", "https://www.reddit.com/r/MachineLearning/new/.rss", "community"),
    FeedSource("Impress Watch AI", "https://www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf", "press"),
]

KEYWORD_SCORES = {
    "copilot": 22,
    "github": 18,
    "code": 15,
    "coding": 15,
    "agent": 16,
    "api": 16,
    "model": 14,
    "release": 14,
    "security": 18,
    "compliance": 18,
    "enterprise": 16,
    "open source": 12,
    "oss": 12,
    "voice": 10,
    "audio": 10,
    "pricing": 12,
    "price": 12,
    "policy": 12,
    "safety": 12,
    "governance": 12,
    "openai": 10,
    "anthropic": 10,
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; DailyAINewsDigest/1.0; +https://github.com/)"
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def fetch_text(url: str) -> str:
    return fetch(url).decode("utf-8")


def text_content(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    raw = re.sub(r"<br\s*/?>", " ", raw, flags=re.I)
    raw = re.sub(r"</p>", " ", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def looks_mostly_english(text: str) -> bool:
    if not text:
        return False
    letters = re.findall(r"[A-Za-z]", text)
    if len(letters) < 8:
        return False
    japanese = re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]", text)
    return len(japanese) == 0


def translate_to_japanese(text: str) -> str:
    query = urllib.parse.quote(text)
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl=ja&dt=t&q={query}"
    )
    try:
        payload = fetch_text(url)
        matches = re.findall(r'\[\s*"((?:[^"\\]|\\.)*)"', payload)
        translated = "".join(bytes(match, "utf-8").decode("unicode_escape") for match in matches[:4]).strip()
        return translated or text
    except Exception:
        return text


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(JST)
    except Exception:
        pass
    cleaned = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(JST)
    except ValueError:
        return None


def parse_feed(feed: FeedSource, payload: bytes) -> list[Item]:
    root = ET.fromstring(payload)
    items: list[Item] = []
    nodes = root.findall(".//item") if root.tag.endswith("rss") or root.tag.endswith("RDF") else root.findall(".//{*}entry")

    for node in nodes:
        if node.tag.endswith("item"):
            title = text_content(node.find("title"))
            link = text_content(node.find("link"))
            pub = text_content(node.find("pubDate")) or text_content(node.find("{http://purl.org/dc/elements/1.1/}date"))
            summary = text_content(node.find("description")) or text_content(
                node.find("{http://purl.org/rss/1.0/modules/content/}encoded")
            )
        else:
            title = text_content(node.find("{*}title"))
            link = ""
            for link_node in node.findall("{*}link"):
                href = link_node.attrib.get("href")
                if href:
                    link = href
                    break
            pub = text_content(node.find("{*}published")) or text_content(node.find("{*}updated"))
            summary = text_content(node.find("{*}summary")) or text_content(node.find("{*}content"))

        published_at = parse_datetime(pub)
        if not title or not link or not published_at:
            continue
        items.append(
            Item(
                title=title,
                link=link,
                source_name=feed.name,
                source_type=feed.source_type,
                published_at=published_at,
                summary=strip_html(summary),
            )
        )
    return items


def normalize_title(title: str) -> str:
    return re.sub(r"\W+", "", title.lower())


def build_why(item: Item) -> str:
    if item.source_type == "official":
        return (
            "\u4e00\u6b21\u30bd\u30fc\u30b9\u767a\u306e\u66f4\u65b0\u3067\u3059\u3002"
            "\u88fd\u54c1\u3001API\u3001\u904b\u7528\u65b9\u91dd\u306b\u76f4\u63a5\u5f71\u97ff\u3059\u308b"
            "\u53ef\u80fd\u6027\u304c\u3042\u308a\u307e\u3059\u3002"
        )
    if item.source_type == "community":
        return (
            "\u30b3\u30df\u30e5\u30cb\u30c6\u30a3\u306e\u6ce8\u76ee\u70b9\u3092\u793a\u3059\u88dc\u8db3\u6750\u6599\u3067\u3059\u3002"
            "\u4e00\u6b21\u30bd\u30fc\u30b9\u306e\u91cd\u8981\u6027\u5224\u65ad\u3084\u73fe\u5834\u306e\u95a2\u5fc3\u3092"
            "\u88dc\u3046\u7528\u9014\u306b\u5411\u3044\u3066\u3044\u307e\u3059\u3002"
        )
    return (
        "\u65e5\u672c\u8a9e\u570f\u3067\u306e\u53d7\u3051\u6b62\u3081\u65b9\u3092\u78ba\u8a8d\u3057\u3084\u3059\u3044\u8a71\u984c\u3067\u3059\u3002"
        "\u56fd\u5185\u904b\u7528\u3084\u793e\u5185\u5468\u77e5\u306b\u305d\u306e\u307e\u307e\u4f7f\u3048\u308b\u8996\u70b9\u304c\u3042\u308a\u307e\u3059\u3002"
    )


def build_community(item: Item) -> str:
    if item.source_type == "community":
        return f"\U0001f4e3 \u30b3\u30df\u30e5\u30cb\u30c6\u30a3\u3067\u7d99\u7d9a\u7684\u306b\u53c2\u7167\u3055\u308c\u3066\u3044\u308b\u8a71\u984c\u3067\u3059 \u2014 {item.source_name}"
    return ""


def summarize(item: Item) -> None:
    haystack = f"{item.title} {item.summary}".lower()
    score = 20 if item.source_type == "official" else 8 if item.source_type == "press" else 0
    for keyword, bonus in KEYWORD_SCORES.items():
        if keyword in haystack:
            score += bonus

    item.score = score
    item.importance = "High" if score >= 42 else "Medium" if score >= 24 else "Low"

    if any(k in haystack for k in ("copilot", "coding", "code", "api", "developer", "github")):
        item.applicability = LABEL_DIRECT
        item.copilot_tip = (
            "Copilot\u3067\u5f71\u97ff\u7bc4\u56f2\u306e\u68da\u5378\u3057\u3001\u8a2d\u5b9a\u5909\u66f4\u306e\u5dee\u5206\u78ba\u8a8d\u3001"
            "\u30ac\u30fc\u30c9\u30ec\u30fc\u30eb\u3084\u79fb\u884c\u30bf\u30b9\u30af\u306e\u4e0b\u66f8\u304d\u3092\u5148\u306b\u4f5c\u308b\u3068\u5b9f\u52d9\u306b\u4e57\u305b\u3084\u3059\u3044\u3067\u3059\u3002"
        )
    elif any(k in haystack for k in ("enterprise", "voice", "pricing", "policy", "security", "openai", "anthropic")):
        item.applicability = LABEL_INDIRECT
        item.copilot_tip = (
            "Copilot\u305d\u306e\u3082\u306e\u306e\u65b0\u6a5f\u80fd\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u304c\u3001"
            "\u793e\u5185\u30ac\u30a4\u30c9\u30e9\u30a4\u30f3\u3001PoC\u8981\u4ef6\u3001\u6bd4\u8f03\u8868\u306e\u521d\u7248\u3092"
            "Copilot\u306b\u4f5c\u3089\u305b\u308b\u6750\u6599\u3068\u3057\u3066\u4f7f\u3048\u307e\u3059\u3002"
        )
    else:
        item.applicability = LABEL_NONE

    item.why = build_why(item)
    item.community = build_community(item)
    item.display_title = translate_to_japanese(item.title) if looks_mostly_english(item.title) else item.title


def target_date() -> datetime.date:
    override = os.getenv("TARGET_DATE_JST", "").strip()
    if override:
        return datetime.strptime(override, "%Y-%m-%d").date()
    return (datetime.now(JST) - timedelta(days=1)).date()


def collect_items() -> list[Item]:
    selected = target_date()
    collected: list[Item] = []
    for feed in FEEDS:
        try:
            payload = fetch(feed.url)
            parsed = parse_feed(feed, payload)
        except (urllib.error.URLError, TimeoutError, ET.ParseError) as exc:
            print(f"[warn] feed failed: {feed.name}: {exc}", file=sys.stderr)
            continue
        for item in parsed:
            if item.published_at.date() != selected:
                continue
            summarize(item)
            collected.append(item)

    unique: dict[str, Item] = {}
    for item in sorted(collected, key=lambda x: (x.score, x.published_at), reverse=True):
        key = normalize_title(item.title)
        if key not in unique:
            unique[key] = item
    return list(unique.values())


def pick_sections(items: list[Item]) -> tuple[list[Item], list[Item], list[Item]]:
    ranked = sorted(items, key=lambda x: (x.score, x.published_at), reverse=True)
    top = ranked[:5]
    used = {normalize_title(item.title) for item in top}
    business = [item for item in ranked if normalize_title(item.title) not in used and item.applicability != LABEL_NONE][:5]
    used.update(normalize_title(item.title) for item in business)
    watchlist = [item for item in ranked if normalize_title(item.title) not in used][:5]
    return top, business, watchlist


def theme_lines(items: list[Item]) -> list[str]:
    corpus = " ".join(f"{item.title} {item.summary}".lower() for item in items)
    themes: list[str] = []
    if any(k in corpus for k in ("agent", "copilot", "coding", "github")):
        themes.append(
            "AI\u5c0e\u5165\u306e\u7126\u70b9\u304c\u3001\u500b\u5225\u6a5f\u80fd\u306e\u9a5a\u304d\u3088\u308a\u3082"
            "\u30a8\u30fc\u30b8\u30a7\u30f3\u30c8\u904b\u7528\u3068\u958b\u767a\u30ef\u30fc\u30af\u30d5\u30ed\u30fc\u306e\u5b9a\u7740\u3078\u79fb\u3063\u3066\u3044\u307e\u3059\u3002"
        )
    if any(k in corpus for k in ("voice", "audio", "speech")):
        themes.append(
            "\u97f3\u58f0AI\u306f\u591a\u8a00\u8a9e\u5bfe\u5fdc\u3068\u4f4e\u9045\u5ef6UX\u304c\u5dee\u5225\u5316\u8981\u56e0\u306b\u306a\u3063\u3066\u304a\u308a\u3001\u30b9\u30de\u30db\u524d\u63d0\u306e\u8a2d\u8a08\u304c\u91cd\u8981\u3067\u3059\u3002"
        )
    if any(k in corpus for k in ("policy", "safety", "governance", "security", "compliance")):
        themes.append(
            "\u5b89\u5168\u6027\u3001\u30ac\u30d0\u30ca\u30f3\u30b9\u3001\u30b3\u30f3\u30d7\u30e9\u30a4\u30a2\u30f3\u30b9\u306e\u66f4\u65b0\u304c\u3001\u30e2\u30c7\u30eb\u6027\u80fd\u3068\u540c\u3058\u304f\u3089\u3044\u5c0e\u5165\u5224\u65ad\u3092\u5de6\u53f3\u3057\u3066\u3044\u307e\u3059\u3002"
        )
    if not themes:
        themes.append("\u6628\u65e5\u306f\u5927\u578b\u30ea\u30ea\u30fc\u30b9\u65e5\u3088\u308a\u3082\u3001\u904b\u7528\u3084\u63d0\u4f9b\u5f62\u614b\u306e\u5909\u5316\u3092\u8ffd\u3046\u65e5\u3067\u3057\u305f\u3002")
    return themes[:3]


def badge_html(item: Item) -> str:
    importance_class = {"High": "badge-high", "Medium": "badge-medium", "Low": "badge-low"}[item.importance]
    importance_icon = {"High": "\U0001f534", "Medium": "\U0001f7e1", "Low": "\U0001f7e2"}[item.importance]
    applicability_class = {LABEL_DIRECT: "badge-direct", LABEL_INDIRECT: "badge-indirect", LABEL_NONE: "badge-na"}[item.applicability]
    applicability_icon = {LABEL_DIRECT: "\u2705", LABEL_INDIRECT: "\U0001f7e3", LABEL_NONE: "\u26aa"}[item.applicability]
    return (
        '<div class="badges">'
        f'<span class="badge {importance_class}">{importance_icon} {html.escape(item.importance)}</span>'
        f'<span class="badge {applicability_class}">{applicability_icon} {html.escape(item.applicability)}</span>'
        "</div>"
    )


def source_html(item: Item) -> str:
    return f'<div class="source">\U0001f4ce <a href="{html.escape(item.link)}">{html.escape(item.source_name)}</a></div>'


def item_html(label: str, item: Item) -> str:
    deadline_html = ""
    if item.deadline:
        deadline_html = (
            '<span class="badge badge-deadline" style="font-size:10px; vertical-align:middle; margin-left:6px;">'
            f'\u26a0\ufe0f {html.escape(item.deadline)} \u7de0\u5207</span>'
        )
    parts = [
        '  <div class="card">',
        '    <div class="card-row">',
        f'      <span class="card-num">{html.escape(label)}</span>',
        '      <div class="card-body">',
        f'        <div class="headline">{html.escape(item.display_title or item.title)}{deadline_html}</div>',
        f'        <p class="why">{html.escape(item.why)}</p>',
        f"        {badge_html(item)}",
    ]
    if item.applicability != LABEL_NONE and item.copilot_tip:
        parts.append(f'        <div class="copilot-tip">\U0001f4a1 {html.escape(item.copilot_tip)}</div>')
    if item.community:
        parts.append(f'        <p class="community">{html.escape(item.community)}</p>')
    parts.extend(
        [
            f"        {source_html(item)}",
            "      </div>",
            "    </div>",
            "  </div>",
        ]
    )
    return "\n".join(parts)


def render_html(items: list[Item]) -> str:
    digest_date = datetime.now(JST).strftime("%Y-%m-%d")
    top, business, watchlist = pick_sections(items)
    themes = theme_lines(items)

    if not top:
        top = [
            Item(
                title="\u9ad8\u4fe1\u983c\u306e\u91cd\u8981\u9805\u76ee\u304c\u5c11\u306a\u3044\u305f\u3081\u77ed\u7e2e\u7248\u3067\u9001\u4fe1",
                link="https://news.ycombinator.com/",
                source_name="Digest Engine",
                source_type="press",
                published_at=datetime.now(JST),
                importance="Low",
                applicability=LABEL_NONE,
                summary="",
                why="\u6628\u65e5JST\u306b\u521d\u516c\u958b\u3055\u308c\u305f\u9ad8\u4fe1\u983c\u30bd\u30fc\u30b9\u306e\u3046\u3061\u3001\u91cd\u8981\u5ea6\u304c\u9ad8\u3044\u9805\u76ee\u304c\u9650\u5b9a\u7684\u3067\u3057\u305f\u3002\u5f31\u3044\u8a71\u984c\u3067\u57cb\u3081\u305a\u3001\u77ed\u7e2e\u7248\u306b\u3057\u3066\u3044\u307e\u3059\u3002",
            )
        ]

    lines = [
        "<!DOCTYPE html>",
        '<html lang="ja">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        "<style>",
        "  * { box-sizing: border-box; margin: 0; padding: 0; }",
        "  body { font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif; background: #f1f5f9; color: #1a1a1a; }",
        "  .wrap { max-width: 430px; margin: 0 auto; background: #ffffff; }",
        "  .header { background: #0f172a; padding: 18px 16px 14px; }",
        "  .header-eyebrow { font-size: 11px; color: #64748b; letter-spacing: 1px; margin-bottom: 4px; }",
        "  .header-title { font-size: 20px; font-weight: 500; color: #f1f5f9; line-height: 1.2; }",
        "  .header-date { font-size: 12px; color: #475569; margin-top: 4px; }",
        "  .section-label { padding: 10px 16px 7px; background: #f8fafc; border-top: 0.5px solid #e2e8f0; border-bottom: 0.5px solid #e2e8f0; font-size: 10px; font-weight: 500; letter-spacing: 1px; color: #64748b; }",
        "  .card { padding: 14px 16px; border-bottom: 0.5px solid #f1f5f9; }",
        "  .card-row { display: flex; gap: 10px; align-items: flex-start; }",
        "  .card-num { font-size: 11px; font-weight: 500; color: #94a3b8; min-width: 20px; padding-top: 2px; flex-shrink: 0; }",
        "  .card-body { flex: 1; }",
        "  .headline { font-size: 15px; font-weight: 500; color: #0f172a; line-height: 1.35; margin-bottom: 6px; }",
        "  .why { font-size: 13px; color: #475569; line-height: 1.55; margin-bottom: 10px; }",
        "  .badges { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }",
        "  .badge { font-size: 10px; font-weight: 500; padding: 3px 9px; border-radius: 20px; }",
        "  .badge-high     { background: #fef2f2; color: #991b1b; }",
        "  .badge-medium   { background: #fffbeb; color: #92400e; }",
        "  .badge-low      { background: #f0fdf4; color: #166534; }",
        "  .badge-direct   { background: #eff6ff; color: #1e40af; }",
        "  .badge-indirect { background: #f5f3ff; color: #5b21b6; }",
        "  .badge-na       { background: #f8fafc; color: #64748b; }",
        "  .badge-deadline { background: #fef2f2; color: #991b1b; }",
        "  .copilot-tip { font-size: 12px; color: #1e40af; background: #eff6ff; border-left: 3px solid #3b82f6; border-radius: 0 6px 6px 0; padding: 8px 10px; line-height: 1.55; margin-bottom: 8px; }",
        "  .community { font-size: 12px; color: #94a3b8; font-style: italic; margin-bottom: 6px; }",
        "  .source { font-size: 11px; color: #3b82f6; }",
        "  .source a { color: #3b82f6; text-decoration: none; }",
        "  .themes { background: #0f172a; padding: 14px 16px; }",
        "  .themes-label { font-size: 10px; letter-spacing: 1px; color: #64748b; font-weight: 500; margin-bottom: 10px; }",
        "  .theme-item { font-size: 13px; color: #cbd5e1; line-height: 1.65; padding: 5px 0; border-bottom: 0.5px solid #1e293b; }",
        "  .theme-item:last-child { border-bottom: none; }",
        "  .theme-item::before { content: '-> '; color: #3b82f6; }",
        "  .footer { padding: 10px 16px; background: #f8fafc; border-top: 0.5px solid #e2e8f0; font-size: 11px; color: #94a3b8; text-align: center; }",
        "</style>",
        "</head>",
        "<body>",
        '<div class="wrap">',
        '  <div class="header">',
        '    <div class="header-eyebrow">AI NEWS</div>',
        '    <div class="header-title">Daily Digest</div>',
        f'    <div class="header-date">{digest_date} · Japan Edition</div>',
        "  </div>",
        '  <div class="section-label">🏆 TOP 5 — 今週の最重要</div>',
    ]
    for index, item in enumerate(top, start=1):
        lines.append(item_html(f"#{index}", item))

    lines.append('  <div class="section-label">💼 BUSINESS PICKS — 実務で使えるトピック</div>')
    for index, item in enumerate(business, start=1):
        lines.append(item_html(f"B{index}", item))

    lines.append('  <div class="section-label">👀 WATCHLIST — 動向を追うべきトピック</div>')
    for index, item in enumerate(watchlist, start=1):
        lines.append(item_html(f"W{index}", item))

    lines.append('  <div class="themes">')
    lines.append('    <div class="themes-label">🔭 THEMES</div>')
    for theme in themes:
        lines.append(f'    <div class="theme-item">{html.escape(theme)}</div>')
    lines.append("  </div>")
    lines.append(f'  <div class="footer">{digest_date} 自動生成 · ソースはメール本文内リンクで確認可</div>')
    lines.append("</div>")
    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


def send_email(subject: str, html_body: str) -> None:
    sender = os.environ["GMAIL_SMTP_USER"]
    password = os.environ["GMAIL_SMTP_APP_PASSWORD"]
    recipient = os.environ.get("DIGEST_TO_EMAIL", "fact.facter@gmail.com")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content("This message requires an HTML-capable mail client.")
    message.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.starttls(context=context)
        smtp.login(sender, password)
        smtp.send_message(message)


def main() -> int:
    items = collect_items()
    html_body = render_html(items)
    HTML_PATH.write_text(html_body, encoding="utf-8")
    subject = f"[AI News] {datetime.now(JST).strftime('%Y-%m-%d')} Daily Digest"
    if os.getenv("SEND_EMAIL", "true").lower() == "true":
        send_email(subject, html_body)
    print(f"Wrote {HTML_PATH}")
    print(f"Collected {len(items)} items for {target_date()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
