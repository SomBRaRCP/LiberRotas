[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$ComposeDirectory = Join-Path $PSScriptRoot "backend_trq_bec"
$ComposeFile = Join-Path $ComposeDirectory "docker-compose.yml"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker nao foi encontrado no PATH."
}
if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
    throw "Docker Compose nao encontrado em: $ComposeFile"
}

Write-Host "Parando os conteineres sem apagar volumes, banco, imagens ou segredos..."
& docker compose --file $ComposeFile --project-directory $ComposeDirectory stop --timeout 30
if ($LASTEXITCODE -ne 0) {
    throw "Nao foi possivel parar a pilha do LiberRotas."
}

& docker compose --file $ComposeFile --project-directory $ComposeDirectory ps --all
Write-Host "Servicos parados com os dados preservados."
