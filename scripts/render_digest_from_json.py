from __future__ import annotations

import html
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9), "JST")
OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)
HTML_PATH = OUT_DIR / "digest.html"
TEXT_PATH = OUT_DIR / "digest.txt"

CSS = r"""
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif; background: #f1f5f9; color: #1a1a1a; }
  .wrap { max-width: 430px; margin: 0 auto; background: #ffffff; }
  .header { background: #0f172a; padding: 18px 16px 14px; }
  .header-eyebrow { font-size: 11px; color: #64748b; letter-spacing: 1px; margin-bottom: 4px; }
  .header-title { font-size: 20px; font-weight: 500; color: #f1f5f9; line-height: 1.2; }
  .header-date { font-size: 12px; color: #94a3b8; margin-top: 4px; }
  .section-label { padding: 10px 16px 7px; background: #f8fafc; border-top: 0.5px solid #e2e8f0; border-bottom: 0.5px solid #e2e8f0; font-size: 10px; font-weight: 500; letter-spacing: 1px; color: #64748b; }
  .card { padding: 14px 16px; border-bottom: 0.5px solid #f1f5f9; }
  .card-row { display: flex; gap: 10px; align-items: flex-start; }
  .card-num { font-size: 11px; font-weight: 500; color: #94a3b8; min-width: 20px; padding-top: 2px; flex-shrink: 0; }
  .card-body { flex: 1; }
  .headline { font-size: 15px; font-weight: 500; color: #0f172a; line-height: 1.35; margin-bottom: 6px; }
  .why { font-size: 13px; color: #475569; line-height: 1.55; margin-bottom: 10px; }
  .badges { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
  .badge { font-size: 10px; font-weight: 500; padding: 3px 9px; border-radius: 20px; }
  .badge-high     { background: #fef2f2; color: #991b1b; }
  .badge-medium   { background: #fffbeb; color: #92400e; }
  .badge-low      { background: #f0fdf4; color: #166534; }
  .badge-direct   { background: #eff6ff; color: #1e40af; }
  .badge-indirect { background: #f5f3ff; color: #5b21b6; }
  .badge-na       { background: #f8fafc; color: #64748b; }
  .badge-claude   { background: #fff7ed; color: #9a3412; }
  .badge-deadline { background: #fef2f2; color: #991b1b; }
  .tip { font-size: 12px; border-left: 3px solid; border-radius: 0 6px 6px 0; padding: 8px 10px; line-height: 1.55; margin-bottom: 8px; }
  .copilot-tip { color: #1e40af; background: #eff6ff; border-left-color: #3b82f6; }
  .claude-tip { color: #9a3412; background: #fff7ed; border-left-color: #f97316; }
  .community { font-size: 12px; color: #94a3b8; font-style: italic; margin-bottom: 6px; }
  .source { font-size: 11px; color: #3b82f6; }
  .source a { color: #3b82f6; text-decoration: none; }
  .themes { background: #0f172a; padding: 14px 16px; }
  .themes-label { font-size: 10px; letter-spacing: 1px; color: #64748b; font-weight: 500; margin-bottom: 10px; }
  .theme-item { font-size: 13px; color: #cbd5e1; line-height: 1.65; padding: 5px 0; border-bottom: 0.5px solid #1e293b; }
  .theme-item:last-child { border-bottom: none; }
  .theme-item::before { content: '→ '; color: #3b82f6; }
  .notes { font-size: 12px; color: #64748b; background: #f8fafc; padding: 12px 16px; line-height: 1.55; border-top: 0.5px solid #e2e8f0; }
  .footer { padding: 10px 16px; background: #f8fafc; border-top: 0.5px solid #e2e8f0; font-size: 11px; color: #94a3b8; text-align: center; }
"""

IMPORTANCE = {
    "High": ("badge-high", "🔴 High"),
    "Medium": ("badge-medium", "🟡 Medium"),
    "Low": ("badge-low", "🟢 Low"),
}

COPILOT = {
    "直接使える": ("badge-direct", "✅ GitHub Copilot: 直接使える"),
    "間接的に有用": ("badge-indirect", "🟣 GitHub Copilot: 間接的に有用"),
    "関係なし": ("badge-na", "⚪ GitHub Copilot: 関係なし"),
}


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Digest JSON must be an object")
    validate_json(data)
    return data


def validate_json(data: dict[str, Any]) -> None:
    required = ["schema_version", "target_date_jst", "sections"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError("Missing required field(s): " + ", ".join(missing))
    sections = data.get("sections")
    if not isinstance(sections, dict):
        raise ValueError("sections must be an object")
    for name in ["top5", "business_picks", "watchlist"]:
        value = sections.get(name, [])
        if not isinstance(value, list):
            raise ValueError(f"sections.{name} must be a list")
    themes = sections.get("themes", [])
    if not isinstance(themes, list):
        raise ValueError("sections.themes must be a list")


def source_html(sources: list[dict[str, str]]) -> str:
    links: list[str] = []
    for source in sources or []:
        label = esc(source.get("label", "Source"))
        url = esc(source.get("url", "#"))
        if not url or url == "#":
            continue
        links.append(f'<a href="{url}">{label}</a>')
    if not links:
        return '<div class="source">📎 ソース未設定</div>'
    return f'<div class="source">📎 {" · ".join(links)}</div>'


def badges_html(item: dict[str, Any]) -> str:
    importance = str(item.get("business_importance") or "Low")
    copilot = str(item.get("copilot_applicability") or "関係なし")
    importance_class, importance_label = IMPORTANCE.get(importance, IMPORTANCE["Low"])
    copilot_class, copilot_label = COPILOT.get(copilot, COPILOT["関係なし"])
    badges = [
        f'<span class="badge {importance_class}">{esc(importance_label)}</span>',
        f'<span class="badge {copilot_class}">{esc(copilot_label)}</span>',
    ]

    claude_relevance = str(item.get("claude_code_relevance") or "").strip()
    if claude_relevance and claude_relevance.lower() not in {"none", "関係なし"}:
        badges.append(f'<span class="badge badge-claude">🟠 Claude Code: {esc(claude_relevance)}</span>')

    return '<div class="badges">' + "".join(badges) + '</div>'


def card_html(item: dict[str, Any], fallback_num: str) -> str:
    num = esc(item.get("num") or fallback_num)
    headline = esc(item.get("headline"))
    why = esc(item.get("why"))
    deadline = str(item.get("deadline") or "").strip()
    copilot = str(item.get("copilot_applicability") or "関係なし")
    copilot_tip = str(item.get("copilot_tip") or "").strip()
    claude_tip = str(item.get("claude_code_tip") or "").strip()
    community = str(item.get("community") or "").strip()
    sources = item.get("sources") or []

    deadline_html = ""
    if deadline:
        deadline_html = (
            '<span class="badge badge-deadline" style="font-size:10px; vertical-align:middle; margin-left:6px;">'
            f'⚠️ {esc(deadline)}</span>'
        )

    parts = [
        '<div class="card">',
        '  <div class="card-row">',
        f'    <span class="card-num">{num}</span>',
        '    <div class="card-body">',
        f'      <div class="headline">{headline}{deadline_html}</div>',
        f'      <p class="why">{why}</p>',
        f'      {badges_html(item)}',
    ]

    if copilot != "関係なし" and copilot_tip:
        parts.append(f'      <div class="tip copilot-tip">💡 GitHub Copilotでの活用方法: {esc(copilot_tip)}</div>')
    if claude_tip:
        parts.append(f'      <div class="tip claude-tip">🟠 Claude Codeでの活用方法: {esc(claude_tip)}</div>')
    if community:
        parts.append(f'      <p class="community">📣 {esc(community)}</p>')

    parts.extend([
        f'      {source_html(sources)}',
        '    </div>',
        '  </div>',
        '</div>',
    ])
    return "\n".join(parts)


def section_html(label: str, items: list[dict[str, Any]], prefix: str) -> str:
    parts = [f'<div class="section-label">{label}</div>']
    for i, item in enumerate(items or [], start=1):
        fallback = f"#{i}" if prefix == "#" else f"{prefix}{i}"
        parts.append(card_html(item, fallback))
    return "\n\n".join(parts)


def themes_html(themes: list[str]) -> str:
    parts = ['<div class="themes">', '  <div class="themes-label">🔭 THEMES</div>']
    for theme in themes or []:
        parts.append(f'  <div class="theme-item">{esc(theme)}</div>')
    if not themes:
        parts.append('  <div class="theme-item">高信頼なニュースが少ないため、短縮版で配信しています。</div>')
    parts.append('</div>')
    return "\n".join(parts)


def render_html(data: dict[str, Any]) -> str:
    target_date = str(data.get("target_date_jst") or datetime.now(JST).date())
    edition = str(data.get("edition") or "Japan Edition")
    title = str(data.get("title") or "Daily Digest")
    sections = data.get("sections") or {}
    notes = str(data.get("notes") or "").strip()

    body_parts = [
        '<!DOCTYPE html>',
        '<html lang="ja">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '<style>',
        CSS,
        '</style>',
        '</head>',
        '<body>',
        '<div class="wrap">',
        '  <div class="header">',
        '    <div class="header-eyebrow">AI NEWS</div>',
        f'    <div class="header-title">{esc(title)}</div>',
        f'    <div class="header-date">{esc(target_date)} · {esc(edition)}</div>',
        '  </div>',
        '',
        section_html('🏆 TOP 5 — 今週の最重要', sections.get("top5") or [], "#"),
        '',
        section_html('💼 BUSINESS PICKS — 実務で使えるトピック', sections.get("business_picks") or [], "B"),
        '',
        section_html('👀 WATCHLIST — 動向を追うべきトピック', sections.get("watchlist") or [], "W"),
        '',
        themes_html(sections.get("themes") or []),
    ]
    if notes:
        body_parts.append(f'<div class="notes">📝 {esc(notes)}</div>')
    body_parts.extend([
        f'  <div class="footer">{esc(target_date)} 自動生成 · ソースはメール本文内リンクで確認可</div>',
        '</div>',
        '</body>',
        '</html>',
    ])
    return "\n".join(body_parts)


def render_text(data: dict[str, Any]) -> str:
    target_date = str(data.get("target_date_jst") or datetime.now(JST).date())
    sections = data.get("sections") or {}
    lines = ["AI NEWS", "Daily Digest", f"{target_date} · {data.get('edition', 'Japan Edition')}", ""]
    labels = [
        ("🏆 TOP 5 — 今週の最重要", sections.get("top5") or []),
        ("💼 BUSINESS PICKS — 実務で使えるトピック", sections.get("business_picks") or []),
        ("👀 WATCHLIST — 動向を追うべきトピック", sections.get("watchlist") or []),
    ]
    for label, items in labels:
        if not items:
            continue
        lines.append(label)
        for item in items:
            lines.append(f"{item.get('num', '')} {item.get('headline', '')}".strip())
            lines.append(str(item.get("why", "")))
            lines.append(f"重要度: {item.get('business_importance', '')} / GitHub Copilot適用度: {item.get('copilot_applicability', '')}")
            if item.get("copilot_tip"):
                lines.append(f"GitHub Copilotでの活用方法: {item.get('copilot_tip')}")
            if item.get("claude_code_relevance"):
                lines.append(f"Claude Code注目度: {item.get('claude_code_relevance')}")
            if item.get("claude_code_tip"):
                lines.append(f"Claude Codeでの活用方法: {item.get('claude_code_tip')}")
            sources = item.get("sources") or []
            if sources:
                lines.append("Source: " + " / ".join(f"{s.get('label')}: {s.get('url')}" for s in sources))
            lines.append("")
    themes = sections.get("themes") or []
    if themes:
        lines.append("🔭 THEMES")
        lines.extend(f"- {theme}" for theme in themes)
    notes = str(data.get("notes") or "").strip()
    if notes:
        lines.extend(["", "Notes", notes])
    return "\n".join(lines).strip() + "\n"


def should_send_email() -> bool:
    return os.getenv("SEND_EMAIL", "true").strip().lower() not in {"0", "false", "no", "off"}


def send_email(subject: str, html_body: str, plain_text: str) -> None:
    smtp_user = os.getenv("GMAIL_SMTP_USER", "").strip()
    smtp_password = os.getenv("GMAIL_SMTP_APP_PASSWORD", "").strip()
    to_email = os.getenv("DIGEST_TO_EMAIL", "").strip()
    missing = [
        name
        for name, value in {
            "GMAIL_SMTP_USER": smtp_user,
            "GMAIL_SMTP_APP_PASSWORD": smtp_password,
            "DIGEST_TO_EMAIL": to_email,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("Missing required environment variable(s): " + ", ".join(missing))

    message = EmailMessage()
    message["From"] = smtp_user
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(plain_text, subtype="plain", charset="utf-8")
    message.add_alternative(html_body, subtype="html", charset="utf-8")

    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as smtp:
        smtp.starttls(context=context)
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/render_digest_from_json.py inbox/YYYY-MM-DD.json", file=sys.stderr)
        return 2

    json_path = Path(sys.argv[1])
    data = read_json(json_path)
    target_date = str(data.get("target_date_jst") or json_path.stem)

    html_body = render_html(data)
    plain_text = render_text(data)
    HTML_PATH.write_text(html_body, encoding="utf-8")
    TEXT_PATH.write_text(plain_text, encoding="utf-8")
    print(f"Rendered {HTML_PATH} and {TEXT_PATH}")

    if should_send_email():
        subject = f"[AI News] {target_date} Daily Digest"
        send_email(subject, html_body, plain_text)
        print(f"HTML email sent: {subject}")
    else:
        print("SEND_EMAIL=false, skipped email delivery")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
