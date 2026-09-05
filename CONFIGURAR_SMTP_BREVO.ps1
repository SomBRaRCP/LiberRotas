param(
    [string]$SmtpUsername
)

$ErrorActionPreference = "Stop"

$WorkspaceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDirectory = Join-Path $WorkspaceRoot "backend_trq_bec"
$EnvironmentPath = Join-Path $BackendDirectory ".env.backend"
$SecretsDirectory = Join-Path $BackendDirectory "secrets"
$SecretPath = Join-Path $SecretsDirectory "smtp-password"

if (-not (Test-Path -LiteralPath $EnvironmentPath -PathType Leaf)) {
    throw "Arquivo não encontrado: $EnvironmentPath"
}

if ([string]::IsNullOrWhiteSpace($SmtpUsername)) {
    $SmtpUsername = Read-Host "Cole o Login SMTP mostrado pela Brevo (não é a chave)"
}

$SmtpUsername = $SmtpUsername.Trim()
if (
    $SmtpUsername -notmatch "^[^@\s]+@[^@\s]+$" -or
    $SmtpUsername -match "[\r\n]"
) {
    throw "Login SMTP inválido. Copie o campo Login da página Configurações > SMTP e API da Brevo."
}

Write-Host ""
Write-Host "A próxima entrada ficará oculta. Cole a CHAVE SMTP da Brevo e pressione Enter." -ForegroundColor Yellow
$SecurePassword = Read-Host "Chave SMTP" -AsSecureString
$PasswordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
$PlainPassword = $null

try {
    $PlainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($PasswordPointer)
    if (
        [string]::IsNullOrWhiteSpace($PlainPassword) -or
        $PlainPassword.Length -lt 15 -or
        $PlainPassword -match "[\r\n]"
    ) {
        throw "A chave SMTP está vazia ou possui formato inválido."
    }

    New-Item -ItemType Directory -Force -Path $SecretsDirectory | Out-Null
    $Utf8WithoutBom = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText($SecretPath, $PlainPassword, $Utf8WithoutBom)

    $EnvironmentText = [IO.File]::ReadAllText($EnvironmentPath)
    $EnvironmentText = [regex]::Replace(
        $EnvironmentText,
        "(?m)^TRQ_BEC_SMTP_USERNAME=.*$",
        "TRQ_BEC_SMTP_USERNAME=$SmtpUsername"
    )
    $EnvironmentText = [regex]::Replace(
        $EnvironmentText,
        "(?m)^TRQ_BEC_SMTP_PASSWORD_PATH=.*$",
        "TRQ_BEC_SMTP_PASSWORD_PATH=/run/secrets/smtp-password"
    )
    [IO.File]::WriteAllText($EnvironmentPath, $EnvironmentText, $Utf8WithoutBom)
}
finally {
    if ($PasswordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($PasswordPointer)
    }
    $PlainPassword = $null
    $SecurePassword = $null
}

Write-Host ""
Write-Host "SMTP Brevo configurado sem exibir a chave." -ForegroundColor Green
Write-Host "O segredo foi salvo em backend_trq_bec\secrets\smtp-password."
Write-Host "Agora reconstrua a API com:"
Write-Host "powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\INICIAR_LIBERROTAS.ps1 -Rebuild" -ForegroundColor Cyan
