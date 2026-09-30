param(
    [string]$BackendPath = ""
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($BackendPath)) {
    $BackendPath = Split-Path $PSScriptRoot -Parent
}
$PayloadPath = Join-Path $PSScriptRoot "payload"

if (-not (Test-Path $PayloadPath)) {
    throw "Payload não encontrado: $PayloadPath"
}

if (-not (Test-Path $BackendPath)) {
    throw "Backend não encontrado: $BackendPath"
}

$RequiredMarker = Join-Path $BackendPath "pyproject.toml"
if (-not (Test-Path $RequiredMarker)) {
    throw "O caminho informado não parece ser a raiz de backend_trq_bec: $BackendPath"
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupPath = Join-Path $BackendPath ".backup-api-docs-$Timestamp"
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

Write-Host ""
Write-Host "Atualização aplicada com sucesso." -ForegroundColor Green
Write-Host "Backup dos arquivos anteriores: $BackupPath"
Write-Host ""
Write-Host "Próximos comandos:" -ForegroundColor Cyan
Write-Host "  Set-Location `"$BackendPath`""
Write-Host "  docker compose build api"
Write-Host "  docker compose up -d api"
Write-Host "  docker compose logs --since 2m api"
Write-Host ""
Write-Host "Abra:" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:8787/docs"
Write-Host "  http://127.0.0.1:8787/redoc"
