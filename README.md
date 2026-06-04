# Daily AI News Digest

This repository renders reviewed AI news JSON into a mobile-friendly HTML email.

Current operation model:

1. ChatGPT researches the previous day's AI news and prepares a structured JSON payload.
2. The user reviews the JSON in chat.
3. After the user replies `pushして`, the JSON is committed to `inbox/YYYY-MM-DD.json`.
4. GitHub Actions renders the JSON into HTML and sends the HTML email through SMTP.

The repository should not contain email addresses, API keys, SMTP credentials, or other secrets in digest JSON files.

## Input JSON

Reviewed digest files live under:

```text
inbox/YYYY-MM-DD.json
```

`YYYY-MM-DD` is the target news date in JST, not the generation date.

Required high-level fields:

```json
{
  "schema_version": "1.0",
  "target_date_jst": "YYYY-MM-DD",
  "generated_at_jst": "YYYY-MM-DDTHH:mm:ss+09:00",
  "edition": "Japan Edition",
  "title": "Daily Digest",
  "sections": {
    "top5": [],
    "business_picks": [],
    "watchlist": [],
    "themes": []
  },
  "notes": ""
}
```

Each news item may include these fields:

```json
{
  "num": "#1",
  "headline": "日本語の見出し",
  "why": "なぜ重要か。",
  "business_importance": "High | Medium | Low",
  "copilot_applicability": "直接使える | 間接的に有用 | 関係なし",
  "copilot_tip": "GitHub Copilotでの活用方法。",
  "claude_code_relevance": "High | Medium | Low | None",
  "claude_code_tip": "Claude Codeでの活用方法。",
  "deadline": "",
  "community": "",
  "sources": [
    {"label": "一次ソース名", "url": "https://..."}
  ]
}
```

`claude_code_relevance` and `claude_code_tip` are optional. Existing JSON without these fields still renders normally.

## GitHub Actions

Workflow:

```text
.github/workflows/daily-ai-news.yml
```

Renderer:

```text
scripts/render_digest_from_json.py
```

Triggers:

- `push` to `inbox/*.json`
- manual `workflow_dispatch`

On push, the workflow resolves the changed `inbox/*.json`, validates the minimum JSON shape, renders:

```text
out/digest.html
out/digest.txt
```

and uploads them as an artifact. If SMTP secrets are configured and `SEND_EMAIL` is true, it sends the HTML email.

Required GitHub Actions secrets:

- `GMAIL_SMTP_USER`
- `GMAIL_SMTP_APP_PASSWORD`
- `DIGEST_TO_EMAIL`

Manual run options:

- `target_date_jst`: render `inbox/YYYY-MM-DD.json`
- `send_email`: send or only render/upload artifact

## Legacy RSS generator

The old RSS-based generator is kept for reference:

```text
scripts/daily_ai_news_digest.py
```

The reviewed JSON workflow is the primary path. This keeps research and editorial judgment in ChatGPT, while GitHub Actions focuses on validation, HTML rendering, artifact upload, and SMTP delivery.
