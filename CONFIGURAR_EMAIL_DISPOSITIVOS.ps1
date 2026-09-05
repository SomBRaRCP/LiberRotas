[CmdletBinding()]
param(
    [switch]$NaoReiniciar
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$ProjectRoot = $PSScriptRoot
$BackendDirectory = Join-Path $ProjectRoot "backend_trq_bec"
$EnvironmentFile = Join-Path $BackendDirectory ".env.backend"
$SecretsDirectory = Join-Path $BackendDirectory "secrets"
$SmtpSecretFile = Join-Path $SecretsDirectory "smtp-password"
$ComposeFile = Join-Path $BackendDirectory "docker-compose.yml"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $content = [System.IO.File]::ReadAllText($EnvironmentFile)
    $pattern = "(?m)^[ \t]*" + [regex]::Escape($Name) + "=.*$"
    $replacement = "$Name=$Value"
    if ([regex]::IsMatch($content, $pattern)) {
        $content = [regex]::Replace($content, $pattern, $replacement)
    }
    else {
        if ($content.Length -gt 0 -and -not $content.EndsWith("`n")) {
            $content += [Environment]::NewLine
        }
        $content += $replacement + [Environment]::NewLine
    }
    [System.IO.File]::WriteAllText($EnvironmentFile, $content, $Utf8NoBom)
}

if (-not (Test-Path -LiteralPath $EnvironmentFile -PathType Leaf)) {
    throw "Arquivo de configuração não encontrado: $EnvironmentFile"
}
if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
    throw "Docker Compose não encontrado: $ComposeFile"
}

Write-Host "Configuração segura do e-mail de confirmação de dispositivos"
Write-Host "Use o login SMTP e a chave SMTP mostrados pela Brevo. Não use a chave de API."

$smtpUsername = (Read-Host "Login SMTP da Brevo").Trim()
if (
    [string]::IsNullOrWhiteSpace($smtpUsername) -or
    $smtpUsername -match "[`r`n=]" -or
    $smtpUsername.ToLowerInvariant() -in @(
        "change_me",
        "seu-usuario-brevo",
        "conta-smtp"
    )
) {
    throw "O login SMTP informado está vazio ou é inválido."
}

$securePassword = Read-Host "Chave SMTP da Brevo" -AsSecureString
$passwordPointer = [IntPtr]::Zero
$plainPassword = $null
try {
    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
        $securePassword
    )
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
        $passwordPointer
    )
    if (
        [string]::IsNullOrWhiteSpace($plainPassword) -or
        $plainPassword -match "[`r`n]"
    ) {
        throw "A chave SMTP está vazia ou contém uma quebra de linha inválida."
    }

    New-Item -ItemType Directory -Path $SecretsDirectory -Force | Out-Null
    [System.IO.File]::WriteAllText(
        $SmtpSecretFile,
        $plainPassword,
        $Utf8NoBom
    )
}
finally {
    if ($passwordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
    $plainPassword = $null
    $securePassword = $null
}

Copy-Item -LiteralPath $EnvironmentFile -Destination "$EnvironmentFile.smtp-backup" -Force
Set-DotEnvValue -Name "TRQ_BEC_SMTP_HOST" -Value "smtp-relay.brevo.com"
Set-DotEnvValue -Name "TRQ_BEC_SMTP_PORT" -Value "587"
Set-DotEnvValue -Name "TRQ_BEC_SMTP_USERNAME" -Value $smtpUsername
Set-DotEnvValue -Name "TRQ_BEC_SMTP_PASSWORD_PATH" -Value "/run/secrets/smtp-password"
Set-DotEnvValue -Name "TRQ_BEC_SMTP_STARTTLS" -Value "true"
Set-DotEnvValue -Name "TRQ_BEC_SMTP_SSL" -Value "false"
Set-DotEnvValue -Name "TRQ_BEC_SMTP_TIMEOUT_SECONDS" -Value "10"

Write-Host "Credenciais gravadas sem exibir a chave SMTP."

if ($NaoReiniciar) {
    Write-Host "Configuração salva. Reinicie a API antes de testar o envio."
    exit 0
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker não foi encontrado no PATH."
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "O Docker Desktop não está disponível."
}

Write-Host "Copiando o segredo para o volume protegido..."
& docker compose `
    --file $ComposeFile `
    --project-directory $BackendDirectory `
    up --force-recreate secrets-init
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível preparar o segredo SMTP no Docker."
}

Write-Host "Recriando somente a API..."
& docker compose `
    --file $ComposeFile `
    --project-directory $BackendDirectory `
    up -d --force-recreate api
if ($LASTEXITCODE -ne 0) {
    throw "Não foi possível reiniciar a API."
}

$deadline = (Get-Date).AddSeconds(120)
do {
    $containerState = (& docker inspect `
        --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' `
        backend_trq_bec-api-1).Trim()
    if ($containerState -eq "running|healthy") {
        break
    }
    Start-Sleep -Seconds 3
} while ((Get-Date) -lt $deadline)

if ($containerState -ne "running|healthy") {
    throw "A API não ficou saudável após configurar o SMTP: $containerState"
}

Write-Host "Validando configuração e autenticação SMTP..."
$smtpProbe = @'
import smtplib
import ssl
from pathlib import Path
from trq_bec.server.config import ServerSettings

settings = ServerSettings()
required = (
    settings.smtp_host,
    settings.email_from,
    settings.smtp_username,
    settings.smtp_password_path,
)
if not all(required):
    raise SystemExit("SMTP_CONFIGURATION_INCOMPLETE")
password = Path(settings.smtp_password_path).read_text(
    encoding="utf-8"
).rstrip("\r\n")
if not password:
    raise SystemExit("SMTP_PASSWORD_EMPTY")
if settings.smtp_ssl:
    smtp = smtplib.SMTP_SSL(
        settings.smtp_host,
        settings.smtp_port,
        timeout=settings.smtp_timeout_seconds,
        context=ssl.create_default_context(),
    )
else:
    smtp = smtplib.SMTP(
        settings.smtp_host,
        settings.smtp_port,
        timeout=settings.smtp_timeout_seconds,
    )
with smtp:
    smtp.ehlo()
    if settings.smtp_starttls:
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
    smtp.login(settings.smtp_username, password)
print("SMTP_AUTHENTICATION_OK")
'@

& docker exec backend_trq_bec-api-1 python -c $smtpProbe
if ($LASTEXITCODE -ne 0) {
    throw "A Brevo recusou a autenticação SMTP. Confira o login e a chave SMTP."
}

Write-Host "E-mail de dispositivos configurado com sucesso."
Write-Host "Na tela Segurança da minha conta, clique em Reenviar e-mail."
