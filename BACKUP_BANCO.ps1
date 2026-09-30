[CmdletBinding()]
param(
    [string]$Destino = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Destino)) {
    $Destino = Join-Path $PSScriptRoot "backend_trq_bec\backups\postgresql"
}

$lrComposeFile = Join-Path $PSScriptRoot "backend_trq_bec\docker-compose.yml"
if (-not (Test-Path -LiteralPath $lrComposeFile)) {
    throw "docker-compose.yml não encontrado em backend_trq_bec."
}

New-Item -ItemType Directory -Path $Destino -Force | Out-Null
$lrDestinationDirectory = (Resolve-Path -LiteralPath $Destino).Path
$lrTimestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$lrBackupFile = Join-Path $lrDestinationDirectory "liberrotas-$lrTimestamp.dump"
$lrTemporaryFile = "/tmp/liberrotas-$lrTimestamp.dump"
$lrPostgresContainer = (
    docker compose -f $lrComposeFile ps -q postgres
).Trim()

if (-not $lrPostgresContainer) {
    throw "O contêiner PostgreSQL não está em execução. Inicie o LiberRotas antes do backup."
}

try {
    docker exec $lrPostgresContainer pg_dump `
        -U trq_bec `
        -d trq_bec `
        -Fc `
        -f $lrTemporaryFile
    if ($LASTEXITCODE -ne 0) {
        throw "O pg_dump não conseguiu gerar o backup."
    }

    docker cp "${lrPostgresContainer}:$lrTemporaryFile" $lrBackupFile | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "O Docker não conseguiu copiar o backup para o workspace."
    }
}
finally {
    docker exec $lrPostgresContainer rm -f $lrTemporaryFile 2>$null | Out-Null
}

$lrBackup = Get-Item -LiteralPath $lrBackupFile
$lrHash = (Get-FileHash -LiteralPath $lrBackupFile -Algorithm SHA256).Hash

Write-Host "BACKUP_CONCLUIDO"
Write-Host "Arquivo: $($lrBackup.FullName)"
Write-Host "Tamanho: $($lrBackup.Length) bytes"
Write-Host "SHA256: $lrHash"
