[CmdletBinding()]
param(
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$ComposeDirectory = Join-Path $PSScriptRoot "backend_trq_bec"
$ComposeFile = Join-Path $ComposeDirectory "docker-compose.yml"
$WebImage = "liberrotas-web:local"
$RequiredServices = @("postgres", "redis", "api", "web")

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$ComposeArguments)
    & docker compose --file $ComposeFile --project-directory $ComposeDirectory @ComposeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falha em: docker compose $($ComposeArguments -join ' ')"
    }
}

function Import-FirebaseBuildEnvironment {
    $envFile = Join-Path $PSScriptRoot "mobile_app\.env.local"
    $requiredNames = @(
        "EXPO_PUBLIC_FIREBASE_API_KEY",
        "EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN",
        "EXPO_PUBLIC_FIREBASE_PROJECT_ID",
        "EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET",
        "EXPO_PUBLIC_FIREBASE_MESSAGING_SENDER_ID",
        "EXPO_PUBLIC_FIREBASE_APP_ID"
    )

    if (Test-Path -LiteralPath $envFile -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath $envFile) {
            if ($line -notmatch '^\s*(?<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?<value>.*)\s*$') {
                continue
            }

            $name = $Matches.name
            if ($name -notin $requiredNames) {
                continue
            }

            $value = $Matches.value.Trim()
            if ($value.Length -ge 2 -and (
                ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))
            )) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }

    $missingNames = @($requiredNames | Where-Object {
        [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_, "Process"))
    })
    if ($missingNames.Count -gt 0) {
        throw "Configuracao Firebase incompleta para o build Web. Preencha $envFile com as variaveis EXPO_PUBLIC_FIREBASE_*."
    }
}

function Test-Http200 {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Wait-ForServices {
    param([int]$TimeoutSeconds = 240)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $pending = @()
        foreach ($service in $RequiredServices) {
            $containerId = (& docker compose --file $ComposeFile --project-directory $ComposeDirectory ps -q $service).Trim()
            if (-not $containerId) {
                $pending += "$service (sem conteiner)"
                continue
            }

            $state = (& docker inspect --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $containerId).Trim()
            if ($LASTEXITCODE -ne 0 -or $state -notmatch '^running\|(?:healthy|none)$') {
                $pending += "$service ($state)"
            }
        }

        if ($pending.Count -eq 0) {
            return
        }

        Write-Host "Aguardando: $($pending -join ', ')"
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)

    throw "Os servicos nao ficaram saudaveis em $TimeoutSeconds segundos."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker nao foi encontrado no PATH. Instale ou inicie o Docker Desktop."
}
if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
    throw "Docker Compose nao encontrado em: $ComposeFile"
}

Write-Host "Verificando o Docker Desktop..."
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "O Docker Desktop nao esta disponivel. Abra-o e aguarde aparecer 'Engine running'."
}

Invoke-Compose -ComposeArguments @("config", "--quiet")

$imageExists = $false
& cmd.exe /d /c "docker image inspect `"$WebImage`" >nul 2>&1"
if ($LASTEXITCODE -eq 0) {
    $imageExists = $true
}

if ($Rebuild -or -not $imageExists) {
    Import-FirebaseBuildEnvironment
}

if ($Rebuild) {
    Write-Host "Reconstruindo as imagens da API e da Web..."
    Invoke-Compose -ComposeArguments @("build", "api", "web")
}
elseif (-not $imageExists) {
    Write-Host "Construindo a imagem web de producao..."
    Invoke-Compose -ComposeArguments @("build", "web")
}
else {
    Write-Host "Imagens existentes encontradas. Use -Rebuild depois de alterar o frontend ou o backend."
}

Write-Host "Iniciando a pilha sem remover volumes..."
Invoke-Compose -ComposeArguments @("up", "-d")
Wait-ForServices

Write-Host "Testando os endpoints locais..."
if (-not (Test-Http200 "http://127.0.0.1:8081/")) {
    throw "O site nao respondeu HTTP 200 em http://127.0.0.1:8081/."
}
if (-not (Test-Http200 "http://127.0.0.1:8787/health/")) {
    throw "A API nao respondeu HTTP 200 em http://127.0.0.1:8787/health/."
}

Invoke-Compose -ComposeArguments @("ps")
Write-Host "LiberRotas iniciado com sucesso."
Write-Host "Web local: http://127.0.0.1:8081"
Write-Host "API local: http://127.0.0.1:8787"

