# Daily AI News Digest

This workspace contains both:

- a local SMTP mail transport for manual tests
- a GitHub Actions workflow for scheduled delivery while the PC is off

## HTML mail delivery

The automation should send HTML mail through the local PowerShell script:

- `scripts/send_html_email.ps1`

Required environment variables:

- `GMAIL_SMTP_USER`
- `GMAIL_SMTP_APP_PASSWORD`

For detached worktree automations that must run while the PC is off:

- setup config: `.codex/environments/automation-mail.toml`
- setup script: `scripts/setup_automation_env.ps1`
- secrets file: `.codex/environments/automation-mail-secrets.ps1`

Expected behavior:

1. Render the digest HTML to a local UTF-8 `.html` file.
2. Send it with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\send_html_email.ps1 `
  -To "fact.facter@gmail.com" `
  -Subject "[AI News] YYYY-MM-DD Daily Digest" `
  -HtmlFilePath ".\out\digest.html"
```

Notes:

- Use a Gmail App Password, not the normal account password.
- The script sends a multipart message with both `text/plain` and `text/html`.
- The secrets file is gitignored and is intended for the automation setup path.

## GitHub Actions

Workflow:

- `.github/workflows/daily-ai-news.yml`

Digest generator:

- `scripts/daily_ai_news_digest.py`

Schedule:

- `0 23 * * *` UTC = `08:00 JST`

Required GitHub Actions secrets:

- `GMAIL_SMTP_USER`
- `GMAIL_SMTP_APP_PASSWORD`
- `DIGEST_TO_EMAIL`
- `OPENAI_API_KEY` (recommended for source-grounded summaries)

Optional GitHub Actions variable:

- `OPENAI_MODEL` default: `gpt-5.2`

What it does:

1. Fetches yesterday's AI-related items from a set of RSS/Atom feeds.
2. Filters by JST date.
3. Fetches article excerpts and, when `OPENAI_API_KEY` is present, generates source-grounded Japanese summaries.
4. Scores and groups items into `Top 5`, `Business Picks`, `Watchlist`, and `Themes`.
5. Renders the mobile HTML digest template.
6. Sends the digest by Gmail SMTP.

Manual run:

- Use `workflow_dispatch`
- Optionally set `target_date_jst`
- Optionally disable send with `send_email=false`

Caveat:

- Feed coverage depends on the upstream RSS/Atom sources. The workflow intentionally prefers high-confidence feeds and sends a shorter digest rather than padding weak items.
- Without `OPENAI_API_KEY`, the workflow falls back to deterministic template summaries, which are less accurate than source-grounded AI summaries.
