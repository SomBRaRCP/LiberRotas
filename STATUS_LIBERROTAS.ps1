[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$ComposeDirectory = Join-Path $PSScriptRoot "backend_trq_bec"
$ComposeFile = Join-Path $ComposeDirectory "docker-compose.yml"
$Services = @("postgres", "redis", "secrets-init", "api", "web")
$HasFailure = $false

function Write-Result {
    param([string]$Label, [bool]$Success, [string]$Detail)
    if ($Success) {
        Write-Host "[OK]    $Label - $Detail" -ForegroundColor Green
    }
    else {
        Write-Host "[FALHA] $Label - $Detail" -ForegroundColor Red
        $script:HasFailure = $true
    }
}

function Test-Endpoint {
    param([string]$Label, [string]$Url, [int]$Attempts = 3)

    $lastError = "falha desconhecida"
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15
            if ($response.StatusCode -eq 200) {
                Write-Result $Label $true "HTTP 200 em $Url"
                return
            }
            $lastError = "HTTP $($response.StatusCode)"
        }
        catch {
            $lastError = $_.Exception.Message
        }

        # Alguns Windows resolvem primeiro o IPv6 do Cloudflare mesmo quando a
        # rota IPv6 local não está operacional. O curl em IPv4 evita esse falso
        # negativo sem mudar a URL pública testada.
        if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
            $curlStatus = (& curl.exe -4 --silent --show-error --output NUL --write-out "%{http_code}" --max-time 15 $Url).Trim()
            if ($LASTEXITCODE -eq 0 -and $curlStatus -eq "200") {
                Write-Result $Label $true "HTTP 200 em $Url (curl IPv4)"
                return
            }
            if ($curlStatus) {
                $lastError = "curl HTTP $curlStatus"
            }
        }

        if ($attempt -lt $Attempts) {
            Start-Sleep -Seconds 2
        }
    }

    Write-Result $Label $false "sem resposta valida apos $Attempts tentativas em $Url ($lastError)"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Result "Docker" $false "comando nao encontrado no PATH"
    exit 1
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Result "Docker Desktop" $false "daemon indisponivel"
    exit 1
}
Write-Result "Docker Desktop" $true "daemon disponivel"

Write-Host "`nEstado do Docker Compose:"
& docker compose --file $ComposeFile --project-directory $ComposeDirectory ps --all
if ($LASTEXITCODE -ne 0) {
    Write-Result "Docker Compose" $false "nao foi possivel consultar os servicos"
}

Write-Host "`nHealth dos servicos:"
foreach ($service in $Services) {
    $containerId = (& docker compose --file $ComposeFile --project-directory $ComposeDirectory ps -q --all $service).Trim()
    if (-not $containerId) {
        Write-Result $service $false "conteiner nao encontrado"
        continue
    }

    $state = (& docker inspect --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}sem-healthcheck{{end}}|{{.State.ExitCode}}' $containerId).Trim()
    if ($service -eq "secrets-init") {
        $ok = $state -match '^exited\|sem-healthcheck\|0$'
    }
    else {
        $ok = $state -match '^running\|healthy\|0$'
    }
    Write-Result $service $ok $state
}

Write-Host "`nTestes HTTP:"
Test-Endpoint "Web local" "http://127.0.0.1:8081/"
Test-Endpoint "API local" "http://127.0.0.1:8787/health/"
Test-Endpoint "API publica" "https://api.liberrotas.com.br/health/"

if ($HasFailure) {
    Write-Host "`nHa falhas. Revise as linhas marcadas acima." -ForegroundColor Yellow
    exit 1
}

Write-Host "`nTodos os testes de status foram aprovados." -ForegroundColor Green
exit 0
