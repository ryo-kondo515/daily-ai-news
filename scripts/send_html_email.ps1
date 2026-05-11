param(
    [Parameter(Mandatory = $true)]
    [string]$To,

    [Parameter(Mandatory = $true)]
    [string]$Subject,

    [Parameter(Mandatory = $true)]
    [string]$HtmlFilePath,

    [string]$PlainText = "This message requires an HTML-capable mail client."
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $HtmlFilePath)) {
    throw "HTML file not found: $HtmlFilePath"
}

$smtpUser = $env:GMAIL_SMTP_USER
$smtpPassword = $env:GMAIL_SMTP_APP_PASSWORD

if ([string]::IsNullOrWhiteSpace($smtpUser)) {
    throw "Missing environment variable: GMAIL_SMTP_USER"
}

if ([string]::IsNullOrWhiteSpace($smtpPassword)) {
    throw "Missing environment variable: GMAIL_SMTP_APP_PASSWORD"
}

$htmlBody = Get-Content -LiteralPath $HtmlFilePath -Raw -Encoding UTF8

$message = New-Object System.Net.Mail.MailMessage
$message.From = $smtpUser
$message.To.Add($To)
$message.Subject = $Subject
$message.SubjectEncoding = [System.Text.Encoding]::UTF8
$message.BodyEncoding = [System.Text.Encoding]::UTF8
$message.HeadersEncoding = [System.Text.Encoding]::UTF8

$plainView = [System.Net.Mail.AlternateView]::CreateAlternateViewFromString(
    $PlainText,
    [System.Text.Encoding]::UTF8,
    "text/plain"
)
$htmlView = [System.Net.Mail.AlternateView]::CreateAlternateViewFromString(
    $htmlBody,
    [System.Text.Encoding]::UTF8,
    "text/html"
)

$message.AlternateViews.Add($plainView)
$message.AlternateViews.Add($htmlView)
$message.IsBodyHtml = $true
$message.Body = $htmlBody

$smtpClient = New-Object System.Net.Mail.SmtpClient("smtp.gmail.com", 587)
$smtpClient.EnableSsl = $true
$smtpClient.UseDefaultCredentials = $false
$smtpClient.Credentials = New-Object System.Net.NetworkCredential($smtpUser, $smtpPassword)

try {
    $smtpClient.Send($message)
    Write-Output "HTML email sent successfully to $To"
}
catch {
    $errorMessage = $_.Exception.Message
    if ($_.Exception.InnerException) {
        $errorMessage = "$errorMessage :: $($_.Exception.InnerException.Message)"
    }
    throw $errorMessage
}
finally {
    $message.Dispose()
    $smtpClient.Dispose()
}
