param(
    [string]$BackendPath = ""
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8
$PayloadPath = Join-Path $PSScriptRoot "payload"

if (-not (Test-Path $PayloadPath)) {
    throw "Payload não encontrado: $PayloadPath"
}

if ([string]::IsNullOrWhiteSpace($BackendPath)) {
    $Candidate = Split-Path $PSScriptRoot -Parent
    if (Test-Path (Join-Path $Candidate "pyproject.toml")) {
        $BackendPath = $Candidate
    }
    else {
        $BackendPath = "F:\trq_bec\LiberRotas_TRQ_BEC_Workspace_v3\backend_trq_bec"
    }
}

if (-not (Test-Path $BackendPath)) {
    throw "Backend não encontrado: $BackendPath"
}

$RequiredMarker = Join-Path $BackendPath "pyproject.toml"
if (-not (Test-Path $RequiredMarker)) {
    throw "O caminho informado não parece ser a raiz de backend_trq_bec: $BackendPath"
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupPath = Join-Path $BackendPath ".backup-api-docs-v0.5.0a2-$Timestamp"
New-Item -ItemType Directory -Force -Path $BackupPath | Out-Null

$Files = Get-ChildItem -Path $PayloadPath -Recurse -File
foreach ($File in $Files) {
    $Relative = $File.FullName.Substring($PayloadPath.Length).TrimStart('\', '/')
    $Destination = Join-Path $BackendPath $Relative
    $DestinationDirectory = Split-Path $Destination -Parent

    New-Item -ItemType Directory -Force -Path $DestinationDirectory | Out-Null

    if (Test-Path $Destination) {
        $BackupDestination = Join-Path $BackupPath $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path $BackupDestination -Parent) | Out-Null
        Copy-Item -Path $Destination -Destination $BackupDestination -Force
    }

    Copy-Item -Path $File.FullName -Destination $Destination -Force
    Write-Host "Atualizado: $Relative"
}

$ObsoleteFiles = @(
    "docs\openapi-liberrotas-v0.5.0a1.json"
)

foreach ($Relative in $ObsoleteFiles) {
    $Obsolete = Join-Path $BackendPath $Relative
    if (Test-Path $Obsolete) {
        $BackupDestination = Join-Path $BackupPath $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path $BackupDestination -Parent) | Out-Null
        Copy-Item -Path $Obsolete -Destination $BackupDestination -Force
        Remove-Item -Path $Obsolete -Force
        Write-Host "Removido contrato obsoleto: $Relative"
    }
}

Write-Host ""
Write-Host "Atualização v0.5.0-alpha.2 aplicada com sucesso." -ForegroundColor Green
Write-Host "Backup dos arquivos anteriores: $BackupPath"
Write-Host ""
Write-Host "Próximos comandos:" -ForegroundColor Cyan
Write-Host "  Set-Location `"$BackendPath`""
Write-Host "  docker compose build api"
Write-Host "  docker compose up -d api"
Write-Host "  docker compose logs --since 2m api"
Write-Host ""
Write-Host "Documentação pública:" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:8787/docs"
Write-Host "  http://127.0.0.1:8787/redoc"
Write-Host "  http://127.0.0.1:8787/openapi.json"
Write-Host ""
Write-Host "Documentação administrativa:" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:8787/internal/docs"
Write-Host "  http://127.0.0.1:8787/internal/redoc"
Write-Host "  http://127.0.0.1:8787/internal/openapi.json"
