$ErrorActionPreference = "Stop"

$secretScript = Join-Path $PSScriptRoot "..\\.codex\\environments\\automation-mail-secrets.ps1"
$secretScript = [System.IO.Path]::GetFullPath($secretScript)

if (-not (Test-Path -LiteralPath $secretScript)) {
    throw "Automation mail secret file not found: $secretScript"
}

. $secretScript

if ([string]::IsNullOrWhiteSpace($env:GMAIL_SMTP_USER)) {
    throw "GMAIL_SMTP_USER was not set by automation-mail-secrets.ps1"
}

if ([string]::IsNullOrWhiteSpace($env:GMAIL_SMTP_APP_PASSWORD)) {
    throw "GMAIL_SMTP_APP_PASSWORD was not set by automation-mail-secrets.ps1"
}

Write-Output "Automation mail environment loaded."
