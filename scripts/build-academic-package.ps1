#Requires -Version 5.1

[CmdletBinding()]
param(
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedVersion = "0.6.0a1"
$ExpectedTestCount = 197
$ExpectedSubtestCount = 63
$ExpectedTestSummary = "$ExpectedTestCount passed, $ExpectedSubtestCount subtests passed"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $ScriptRoot))
$WorkspaceParent = [System.IO.Path]::GetFullPath((Split-Path -Parent $WorkspaceRoot))
$OutputLeaf = "LiberRotas_TRQ_BEC_Entrega_Academica_v$ExpectedVersion"
$OutputRoot = [System.IO.Path]::GetFullPath((Join-Path $WorkspaceParent $OutputLeaf))
$SourceName = "LiberRotas_TRQ_BEC_Source_v$ExpectedVersion"
$WebName = "LiberRotas_TRQ_BEC_Web_Deploy_v$ExpectedVersion"
$SourceRoot = Join-Path $OutputRoot $SourceName
$WebRoot = Join-Path $OutputRoot $WebName
$LogsRoot = Join-Path $OutputRoot "logs"
$PythonPackagesRoot = Join-Path $OutputRoot "python-packages"
$SourceZip = Join-Path $OutputRoot "$SourceName.zip"
$WebZip = Join-Path $OutputRoot "$WebName.zip"

function Assert-SafeOutputPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $parent = [System.IO.Path]::GetFullPath((Split-Path -Parent $fullPath))
    $leaf = Split-Path -Leaf $fullPath

    if ($parent -ine $WorkspaceParent -or $leaf -ine $OutputLeaf) {
        throw "Caminho de saida recusado por seguranca: $fullPath"
    }
    if ($fullPath -ieq $WorkspaceRoot -or $fullPath -ieq $WorkspaceParent) {
        throw "O caminho de saida nao pode ser o workspace nem seu diretorio pai."
    }
    $parentItem = Get-Item -LiteralPath $WorkspaceParent -Force
    if (($parentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "O diretorio pai da saida nao pode ser junction ou link simbolico: $WorkspaceParent"
    }
}

function Assert-PathInsideOutput {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $prefix = $OutputRoot.TrimEnd('\') + '\'
    if (-not $fullPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Operacao recusada fora da pasta de saida: $fullPath"
    }
}

function Remove-OutputItem {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Assert-PathInsideOutput -Path $Path
        Remove-LongPathItem -Path $Path
    }
}

function Remove-LongPathItem {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $item = Get-Item -LiteralPath $fullPath -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "A remocao recursiva recusou junction ou link simbolico: $fullPath"
    }

    if ($item.PSIsContainer) {
        # O prefixo estendido contorna o limite MAX_PATH do Windows/PowerShell 5.1.
        $extendedPath = if ($fullPath.StartsWith('\\?\')) { $fullPath } else { "\\?\$fullPath" }
        [System.IO.Directory]::Delete($extendedPath, $true)
    }
    else {
        [System.IO.File]::Delete($fullPath)
    }
}

function Get-DirectorySize {
    param([Parameter(Mandatory = $true)][string]$Path)

    $sum = [int64]0
    foreach ($file in Get-ChildItem -LiteralPath $Path -Recurse -Force -File -ErrorAction SilentlyContinue) {
        $sum += [int64]$file.Length
    }
    return $sum
}

function Get-WorkspaceSize {
    $total = [int64]0
    foreach ($item in Get-ChildItem -LiteralPath $WorkspaceRoot -Force) {
        if ($item.Name -eq ".codex_tmp") {
            continue
        }
        if ($item.PSIsContainer) {
            $total += Get-DirectorySize -Path $item.FullName
        }
        else {
            $total += [int64]$item.Length
        }
    }
    return $total
}

function Format-Megabytes {
    param([Parameter(Mandatory = $true)][int64]$Bytes)
    return [math]::Round($Bytes / 1MB, 2)
}

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$LogName
    )

    $logPath = Join-Path $LogsRoot $LogName
    Write-Host "`n> $Command $($Arguments -join ' ')"
    Push-Location -LiteralPath $WorkingDirectory
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Ferramentas como Python build, npm e Expo escrevem progresso em stderr
        # mesmo com sucesso. O codigo de saida, e nao o canal, decide a falha.
        $ErrorActionPreference = "Continue"
        $global:LASTEXITCODE = 0
        $output = @(& $Command @Arguments 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                $_.Exception.Message
            }
            else {
                $_.ToString()
            }
        })
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Pop-Location
    }

    # Inclui o comando no log e cria o arquivo mesmo quando a ferramenta não
    # produz stdout/stderr (por exemplo, `tsc --noEmit` em uma execução limpa).
    @("> $Command $($Arguments -join ' ')") + $output |
        Set-Content -LiteralPath $logPath -Encoding UTF8
    foreach ($line in $output) {
        Write-Host $line
    }
    if ($exitCode -ne 0) {
        throw "Comando falhou com codigo $exitCode. Consulte $logPath"
    }
    return $output
}

function Test-IsForbiddenSourcePath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $normalized = $RelativePath.Replace('\', '/').TrimStart('/')
    $segments = @($normalized.Split('/'))
    $forbiddenDirectories = @(
        "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", ".expo", ".expo-shared", "coverage",
        "build", "dist", ".git", ".agents", ".codex", ".codex_tmp",
        "backups", "secrets"
    )

    foreach ($segment in $segments) {
        if ($forbiddenDirectories -contains $segment -or
            $segment -like "*.egg-info" -or
            $segment -like ".backup-*") {
            return $true
        }
    }

    $leaf = $segments[$segments.Count - 1]
    if ($leaf -in @(".env.example", ".env.backend.example")) {
        return $false
    }
    if ($leaf -eq ".env" -or $leaf -like ".env.*") {
        return $true
    }
    if ($leaf -in @(
            "firebase-service-account.json", "google-services.json",
            "GoogleService-Info.plist", "credentials.json", ".npmrc", ".pypirc"
        )) {
        return $true
    }
    foreach ($pattern in @(
            "*.zip", "*.whl", "*.tar.gz", "*.pyc", "*.pyo", "*.pem",
            "*.key", "*.p8", "*.p12", "*.pfx", "*.crt", "*.jks", "*.keystore",
            "*service-account*.json"
        )) {
        if ($leaf -like $pattern) {
            return $true
        }
    }
    return $false
}

function Copy-AllowedFile {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    if (Test-IsForbiddenSourcePath -RelativePath $RelativePath) {
        throw "A allowlist tentou copiar um item proibido: $RelativePath"
    }
    $source = Join-Path $WorkspaceRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Arquivo obrigatorio ausente: $source"
    }
    $destination = Join-Path $SourceRoot $RelativePath
    $destinationParent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

function Copy-AllowedTree {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $sourceBase = Join-Path $WorkspaceRoot $RelativePath
    if (-not (Test-Path -LiteralPath $sourceBase -PathType Container)) {
        throw "Diretorio obrigatorio ausente: $sourceBase"
    }
    foreach ($file in Get-ChildItem -LiteralPath $sourceBase -Recurse -Force -File) {
        $workspaceRelative = $file.FullName.Substring($WorkspaceRoot.Length).TrimStart('\')
        if (Test-IsForbiddenSourcePath -RelativePath $workspaceRelative) {
            continue
        }
        $destination = Join-Path $SourceRoot $workspaceRelative
        $destinationParent = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    }
}

function Copy-TreeContents {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    foreach ($file in Get-ChildItem -LiteralPath $Source -Recurse -Force -File) {
        $relative = $file.FullName.Substring($Source.Length).TrimStart('\')
        $target = Join-Path $Destination $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    }
}

function Normalize-ExpoWebAssets {
    param([Parameter(Mandatory = $true)][string]$WebDist)

    $nodeModulesAssets = Join-Path $WebDist "assets\node_modules"
    if (-not (Test-Path -LiteralPath $nodeModulesAssets -PathType Container)) {
        return
    }

    $vendorAssets = Join-Path $WebDist "assets\vendor"
    if (Test-Path -LiteralPath $vendorAssets) {
        throw "A normalizacao Web encontrou destino existente: $vendorAssets"
    }
    [System.IO.Directory]::Move($nodeModulesAssets, $vendorAssets)

    $oldReference = "/assets/node_modules/"
    $newReference = "/assets/vendor/"
    $updatedFiles = 0
    foreach ($file in Get-ChildItem -LiteralPath $WebDist -Recurse -Force -File) {
        if ($file.Extension -notin @(".js", ".css", ".html", ".json", ".map")) {
            continue
        }
        $content = [System.IO.File]::ReadAllText($file.FullName)
        if ($content.Contains($oldReference)) {
            $content = $content.Replace($oldReference, $newReference)
            [System.IO.File]::WriteAllText(
                $file.FullName,
                $content,
                (New-Object System.Text.UTF8Encoding($false))
            )
            $updatedFiles++
        }
    }
    if ($updatedFiles -lt 1) {
        throw "A pasta Web foi movida para vendor, mas nenhuma referencia foi atualizada."
    }
}

function Assert-CleanSourcePackage {
    foreach ($file in Get-ChildItem -LiteralPath $SourceRoot -Recurse -Force -File) {
        $relative = $file.FullName.Substring($SourceRoot.Length).TrimStart('\')
        if (Test-IsForbiddenSourcePath -RelativePath $relative) {
            throw "Artefato proibido detectado no pacote Source: $relative"
        }
    }
}

function Assert-CleanWebPackage {
    $forbiddenSegments = @(
        "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
        ".expo", ".expo-shared", ".git", "secrets", "backups"
    )
    foreach ($file in Get-ChildItem -LiteralPath $WebRoot -Recurse -Force -File) {
        $relative = $file.FullName.Substring($WebRoot.Length).TrimStart('\')
        $normalized = $relative.Replace('\', '/')
        $segments = @($normalized.Split('/'))
        foreach ($segment in $segments) {
            if ($forbiddenSegments -contains $segment -or
                $segment -like ".backup-*" -or
                $segment -like "*.egg-info") {
                throw "Artefato proibido detectado no pacote Web: $relative"
            }
        }
        $leaf = $segments[$segments.Count - 1]
        if ($leaf -eq ".env" -or $leaf -like ".env.*" -or
            $leaf -in @(
                "firebase-service-account.json", "google-services.json",
                "GoogleService-Info.plist", "credentials.json", ".npmrc", ".pypirc"
            )) {
            throw "Configuracao sensivel detectada no pacote Web: $relative"
        }
        foreach ($pattern in @(
                "*.zip", "*.whl", "*.pem", "*.key", "*.p8", "*.p12", "*.pfx",
                "*.crt", "*.jks", "*.keystore", "*service-account*.json"
            )) {
            if ($leaf -like $pattern) {
                throw "Arquivo sensivel ou pacote aninhado detectado no Web: $relative"
            }
        }
    }
}

function Copy-PublicExpoEnvironmentForBuild {
    param([Parameter(Mandatory = $true)][string]$DestinationDirectory)

    $sourceEnv = Join-Path $WorkspaceRoot "mobile_app\.env.local"
    if (-not (Test-Path -LiteralPath $sourceEnv -PathType Leaf)) {
        Write-Host "Nenhum .env.local encontrado; o export Web sera gerado sem configuracao local."
        return $false
    }

    foreach ($line in Get-Content -LiteralPath $sourceEnv) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed -notmatch '^([A-Za-z_][A-Za-z0-9_]*)=') {
            throw "Linha invalida encontrada em mobile_app/.env.local. O valor nao foi exibido."
        }
        $name = $Matches[1]
        if (-not $name.StartsWith("EXPO_PUBLIC_", [System.StringComparison]::Ordinal)) {
            throw "Variavel nao publica recusada no build Expo: $name"
        }
        if ($name -match '(SECRET|PRIVATE|PASSWORD|TOKEN|CREDENTIAL|SERVICE_ACCOUNT)') {
            throw "Variavel potencialmente secreta recusada no build Expo: $name"
        }
    }

    $destination = Join-Path $DestinationDirectory ".env.local"
    Copy-Item -LiteralPath $sourceEnv -Destination $destination -Force
    Write-Host "Configuracao EXPO_PUBLIC copiada temporariamente para o build; o arquivo nao entrara nos ZIPs."
    return $true
}

function New-PackageManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$ManifestPath
    )

    $records = foreach ($file in Get-ChildItem -LiteralPath $Root -Recurse -Force -File |
        Where-Object { $_.FullName -ine $ManifestPath } |
        Sort-Object FullName) {
        [PSCustomObject]@{
            Path = $file.FullName.Substring($Root.Length).TrimStart('\').Replace('\', '/')
            SizeBytes = $file.Length
            SHA256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    $records | Export-Csv -LiteralPath $ManifestPath -NoTypeInformation -Encoding UTF8
}

Assert-SafeOutputPath -Path $OutputRoot
if (Test-Path -LiteralPath $OutputRoot) {
    if (-not $Force) {
        throw "A saida ja existe: $OutputRoot. Revise-a e execute novamente com -Force para substitui-la."
    }
    $outputItem = Get-Item -LiteralPath $OutputRoot -Force
    if (($outputItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "A saida existente nao pode ser junction ou link simbolico: $OutputRoot"
    }
    Remove-LongPathItem -Path $OutputRoot
}

foreach ($command in @("node.exe", "npm.cmd", "npx.cmd")) {
    if ($null -eq (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Comando obrigatorio nao encontrado no PATH: $command"
    }
}

# No Windows, usar os executaveis .cmd evita que o PowerShell escolha os
# wrappers npm.ps1/npx.ps1. Esses wrappers podem falhar sob StrictMode.
$NodeCommand = (Get-Command "node.exe" -ErrorAction Stop).Source
$NpmCommand = (Get-Command "npm.cmd" -ErrorAction Stop).Source
$NpxCommand = (Get-Command "npx.cmd" -ErrorAction Stop).Source

$basePythonCandidates = @(
    (Join-Path $WorkspaceRoot "backend_trq_bec\.venv\Scripts\python.exe"),
    (Join-Path $WorkspaceRoot ".venv\Scripts\python.exe")
)
$BasePython = $basePythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $BasePython) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "Python nao encontrado. Instale Python 3.11 ou superior."
    }
    $BasePython = $pythonCommand.Source
}

$WorkspaceSize = Get-WorkspaceSize
New-Item -ItemType Directory -Path $SourceRoot, $WebRoot, $LogsRoot, $PythonPackagesRoot -Force | Out-Null

$versionCode = "import pathlib,sys,tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))['project']['version'])"
$versionOutput = Invoke-LoggedCommand -Command $BasePython -Arguments @(
    "-c", $versionCode, (Join-Path $WorkspaceRoot "backend_trq_bec\pyproject.toml")
) -WorkingDirectory $WorkspaceRoot -LogName "01-backend-version.log"
$AuthoritativeVersion = ($versionOutput | Select-Object -Last 1).Trim()
if ($AuthoritativeVersion -ne $ExpectedVersion) {
    throw "Versao autoritativa inesperada: $AuthoritativeVersion. Esperado: $ExpectedVersion"
}

$mobileRoot = Join-Path $WorkspaceRoot "mobile_app"
if (-not (Test-Path -LiteralPath (Join-Path $mobileRoot "package-lock.json") -PathType Leaf)) {
    throw "mobile_app/package-lock.json e obrigatorio."
}
foreach ($conflictingLock in @("yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json")) {
    if (Test-Path -LiteralPath (Join-Path $mobileRoot $conflictingLock)) {
        throw "Lock conflitante encontrado em mobile_app: $conflictingLock"
    }
}
$lockCheckCode = "const fs=require('fs'); const p=JSON.parse(fs.readFileSync(process.argv[1],'utf8')); const l=JSON.parse(fs.readFileSync(process.argv[2],'utf8')); if(p.name!==l.name || p.version!==l.version || l.lockfileVersion!==3){process.exit(2)} console.log(p.name+' '+p.version+' lockfileVersion='+l.lockfileVersion);"
Invoke-LoggedCommand -Command $NodeCommand -Arguments @(
    "-e", $lockCheckCode, (Join-Path $mobileRoot "package.json"), (Join-Path $mobileRoot "package-lock.json")
) -WorkingDirectory $mobileRoot -LogName "02-npm-lock.log" | Out-Null

$rootFiles = @(
    ".gitignore",
    "LiberRotas.code-workspace",
    "INICIAR_LIBERROTAS.ps1",
    "PARAR_LIBERROTAS.ps1",
    "STATUS_LIBERROTAS.ps1",
    "BACKUP_BANCO.ps1",
    "MAPA_DE_COMANDOS.md",
    "README.md",
    "scripts\proteger-ambiente-local.ps1",
    "scripts\build-academic-package.ps1"
)
$rootTrees = @(
    ".vscode"
)
$backendFiles = @(
    "backend_trq_bec\.dockerignore",
    "backend_trq_bec\.env.backend.example",
    "backend_trq_bec\.gitignore",
    "backend_trq_bec\docker-compose.yml",
    "backend_trq_bec\Dockerfile",
    "backend_trq_bec\NOTICE.md",
    "backend_trq_bec\pyproject.toml",
    "backend_trq_bec\pytest.ini",
    "backend_trq_bec\README.md",
    "backend_trq_bec\SECURITY.md",
    "backend_trq_bec\VALIDATION.md"
)
$backendTrees = @(
    "backend_trq_bec\config",
    "backend_trq_bec\docs",
    "backend_trq_bec\examples",
    "backend_trq_bec\integrations",
    "backend_trq_bec\migrations",
    "backend_trq_bec\schemas",
    "backend_trq_bec\src",
    "backend_trq_bec\tests"
)
$mobileFiles = @(
    "mobile_app\.dockerignore",
    "mobile_app\.env.example",
    "mobile_app\.firebaserc",
    "mobile_app\.gitignore",
    "mobile_app\app.json",
    "mobile_app\CHECKLIST_ENTREGA_LIMPA.md",
    "mobile_app\Dockerfile.web",
    "mobile_app\eas.json",
    "mobile_app\eslint.config.js",
    "mobile_app\FEITUR_V3_ROTEIRO.md",
    "mobile_app\FIREBASE_AUTH_SETUP.md",
    "mobile_app\firebase.json",
    "mobile_app\firestore.rules",
    "mobile_app\LICENSE",
    "mobile_app\nginx.conf",
    "mobile_app\package.json",
    "mobile_app\package-lock.json",
    "mobile_app\README.md",
    "mobile_app\BUILD_MOBILE.md",
    "mobile_app\TRQ_BEC_INTEGRATION.md",
    "mobile_app\tsconfig.json",
    "mobile_app\vitest.config.mts",
    "mobile_app\VALIDACAO_TRQ_BEC.md",
    "mobile_app\WEB_DEPLOYMENT.md"
)
$mobileTrees = @(
    "mobile_app\assets",
    "mobile_app\scripts",
    "mobile_app\src",
    "mobile_app\tests"
)

foreach ($file in $rootFiles + $backendFiles + $mobileFiles) {
    Copy-AllowedFile -RelativePath $file
}
foreach ($tree in $rootTrees + $backendTrees + $mobileTrees) {
    Copy-AllowedTree -RelativePath $tree
}

$backendStage = Join-Path $SourceRoot "backend_trq_bec"
$mobileStage = Join-Path $SourceRoot "mobile_app"

$validationPythonRoot = Join-Path $OutputRoot ".validation-python"
Invoke-LoggedCommand -Command $BasePython -Arguments @(
    "-m", "venv", $validationPythonRoot
) -WorkingDirectory $OutputRoot -LogName "03-validation-venv.log" | Out-Null
$ValidationPython = Join-Path $validationPythonRoot "Scripts\python.exe"
Invoke-LoggedCommand -Command $ValidationPython -Arguments @(
    "-m", "pip", "install", "--upgrade", "pip", "build"
) -WorkingDirectory $OutputRoot -LogName "04-validation-tools.log" | Out-Null
Invoke-LoggedCommand -Command $ValidationPython -Arguments @(
    "-m", "pip", "install", "-e", "${backendStage}[test]"
) -WorkingDirectory $OutputRoot -LogName "05-validation-backend.log" | Out-Null

Invoke-LoggedCommand -Command $ValidationPython -Arguments @(
    "-m", "build", "--outdir", $PythonPackagesRoot
) -WorkingDirectory $backendStage -LogName "06-python-build.log" | Out-Null

$oldVersionArtifacts = @(Get-ChildItem -LiteralPath $PythonPackagesRoot -File |
    Where-Object { $_.Name -match '0\.5\.0a1|0\.5\.0a2' })
if ($oldVersionArtifacts.Count -gt 0) {
    throw "O build atual gerou ou misturou artefatos com versao antiga."
}
$wheels = @(Get-ChildItem -LiteralPath $PythonPackagesRoot -Filter "trq_bec-$ExpectedVersion-*.whl" -File)
$sdists = @(Get-ChildItem -LiteralPath $PythonPackagesRoot -Filter "trq_bec-$ExpectedVersion.tar.gz" -File)
if ($wheels.Count -ne 1 -or $sdists.Count -ne 1) {
    throw "O build deve gerar exatamente um wheel e um sdist da versao $ExpectedVersion."
}

$metadataCode = "import email,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); n=next(x for x in z.namelist() if x.endswith('.dist-info/METADATA')); print(email.message_from_bytes(z.read(n))['Version'])"
$metadataOutput = Invoke-LoggedCommand -Command $ValidationPython -Arguments @(
    "-c", $metadataCode, $wheels[0].FullName
) -WorkingDirectory $backendStage -LogName "07-wheel-metadata.log"
if (($metadataOutput | Select-Object -Last 1).Trim() -ne $ExpectedVersion) {
    throw "O METADATA do wheel nao anuncia $ExpectedVersion."
}

$sdistMetadataCode = "import email,sys,tarfile; t=tarfile.open(sys.argv[1], 'r:gz'); n=next(x for x in t.getnames() if x.endswith('/PKG-INFO')); print(email.message_from_bytes(t.extractfile(n).read())['Version'])"
$sdistMetadataOutput = Invoke-LoggedCommand -Command $ValidationPython -Arguments @(
    "-c", $sdistMetadataCode, $sdists[0].FullName
) -WorkingDirectory $backendStage -LogName "07b-sdist-metadata.log"
if (($sdistMetadataOutput | Select-Object -Last 1).Trim() -ne $ExpectedVersion) {
    throw "O PKG-INFO do pacote fonte nao anuncia $ExpectedVersion."
}

$wheelCheckRoot = Join-Path $OutputRoot ".wheel-check"
Invoke-LoggedCommand -Command $BasePython -Arguments @(
    "-m", "venv", $wheelCheckRoot
) -WorkingDirectory $OutputRoot -LogName "08-wheel-venv.log" | Out-Null
$wheelPython = Join-Path $wheelCheckRoot "Scripts\python.exe"
Invoke-LoggedCommand -Command $wheelPython -Arguments @(
    "-m", "pip", "install", "--no-deps", "--force-reinstall", $wheels[0].FullName
) -WorkingDirectory $OutputRoot -LogName "09-wheel-install.log" | Out-Null
$installedVersionOutput = Invoke-LoggedCommand -Command $wheelPython -Arguments @(
    "-c", "import importlib.metadata,trq_bec; print(importlib.metadata.version('trq-bec')+'|'+trq_bec.__version__)"
) -WorkingDirectory $OutputRoot -LogName "10-wheel-installed-version.log"
if (($installedVersionOutput | Select-Object -Last 1).Trim() -ne "$ExpectedVersion|$ExpectedVersion") {
    throw "A instalacao isolada do wheel nao retornou $ExpectedVersion."
}
Remove-OutputItem -Path $wheelCheckRoot

$hadPythonPath = Test-Path Env:PYTHONPATH
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = (Join-Path $backendStage "src") + [System.IO.Path]::PathSeparator + (Join-Path $backendStage "tests")
try {
    $testOutput = Invoke-LoggedCommand -Command $ValidationPython -Arguments @(
        "-m", "pytest", ".\tests", "-q",
        "-W", "error::starlette.exceptions.StarletteDeprecationWarning"
    ) -WorkingDirectory $backendStage -LogName "11-pytest.log"
}
finally {
    if ($hadPythonPath) {
        $env:PYTHONPATH = $previousPythonPath
    }
    else {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
}
$testSummaryMatch = [regex]::Match(
    ($testOutput -join "`n"),
    '(?m)^(?<count>\d+) passed,\s+(?<subtests>\d+) subtests passed(?:,.*)? in .+$'
)
if (-not $testSummaryMatch.Success -or
    [int]$testSummaryMatch.Groups['count'].Value -ne $ExpectedTestCount -or
    [int]$testSummaryMatch.Groups['subtests'].Value -ne $ExpectedSubtestCount) {
    throw "A suite nao confirmou o resultado esperado: $ExpectedTestSummary"
}
Remove-OutputItem -Path $validationPythonRoot

$generatedDist = Join-Path $mobileStage "dist"
$GeneratedRoutes = 0
$temporaryEnvPath = Join-Path $mobileStage ".env.local"
try {
    Copy-PublicExpoEnvironmentForBuild -DestinationDirectory $mobileStage | Out-Null
    Invoke-LoggedCommand -Command $NpmCommand -Arguments @("ci") -WorkingDirectory $mobileStage -LogName "12-npm-ci.log" | Out-Null
    Invoke-LoggedCommand -Command $NpxCommand -Arguments @("expo", "install", "--check") -WorkingDirectory $mobileStage -LogName "13-expo-check.log" | Out-Null
    Invoke-LoggedCommand -Command $NpmCommand -Arguments @("test") -WorkingDirectory $mobileStage -LogName "14-mobile-tests.log" | Out-Null
    Invoke-LoggedCommand -Command $NpmCommand -Arguments @("run", "test:firestore") -WorkingDirectory $mobileStage -LogName "14b-firestore-tests.log" | Out-Null
    Invoke-LoggedCommand -Command $NpmCommand -Arguments @("run", "typecheck") -WorkingDirectory $mobileStage -LogName "14c-typescript.log" | Out-Null
    Invoke-LoggedCommand -Command $NpmCommand -Arguments @("run", "lint") -WorkingDirectory $mobileStage -LogName "15-eslint.log" | Out-Null
    Invoke-LoggedCommand -Command $NpmCommand -Arguments @("audit", "--omit=dev", "--audit-level=high") -WorkingDirectory $mobileStage -LogName "15b-npm-audit.log" | Out-Null
    Invoke-LoggedCommand -Command $NpxCommand -Arguments @("expo", "export", "--platform", "web") -WorkingDirectory $mobileStage -LogName "16-expo-web-export.log" | Out-Null

    if (-not (Test-Path -LiteralPath $generatedDist -PathType Container)) {
        throw "O Expo nao gerou mobile_app/dist."
    }
    $GeneratedRoutes = @(Get-ChildItem -LiteralPath $generatedDist -Recurse -File -Filter "*.html").Count
    if ($GeneratedRoutes -lt 1) {
        throw "Nenhuma rota HTML foi encontrada no export Web."
    }
    $webDist = Join-Path $WebRoot "dist"
    Copy-TreeContents -Source $generatedDist -Destination $webDist
    Normalize-ExpoWebAssets -WebDist $webDist
    Copy-Item -LiteralPath (Join-Path $mobileStage "WEB_DEPLOYMENT.md") -Destination (Join-Path $WebRoot "WEB_DEPLOYMENT.md") -Force
}
finally {
    if (Test-Path -LiteralPath $temporaryEnvPath) {
        Remove-OutputItem -Path $temporaryEnvPath
    }
}
foreach ($generatedPath in @(
        (Join-Path $backendStage "build"),
        (Join-Path $backendStage "dist"),
        (Join-Path $backendStage "src\trq_bec.egg-info"),
        (Join-Path $backendStage ".pytest_cache"),
        (Join-Path $backendStage ".mypy_cache"),
        (Join-Path $backendStage ".ruff_cache"),
        (Join-Path $backendStage ".coverage"),
        (Join-Path $backendStage "coverage"),
        (Join-Path $mobileStage "node_modules"),
        (Join-Path $mobileStage ".expo"),
        (Join-Path $mobileStage ".expo-shared"),
        (Join-Path $mobileStage "dist"),
        (Join-Path $mobileStage "coverage"),
        (Join-Path $mobileStage "expo-env.d.ts")
    )) {
    Remove-OutputItem -Path $generatedPath
}
foreach ($pythonCache in @(Get-ChildItem -LiteralPath $backendStage -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Sort-Object { $_.FullName.Length } -Descending)) {
    Remove-OutputItem -Path $pythonCache.FullName
}
foreach ($tsBuildInfo in Get-ChildItem -LiteralPath $mobileStage -Recurse -Force -File -Filter "*.tsbuildinfo" -ErrorAction SilentlyContinue) {
    Remove-OutputItem -Path $tsBuildInfo.FullName
}

$validationReport = @"
# Validacao da entrega academica

- Versao autoritativa: $AuthoritativeVersion
- Wheel: $($wheels[0].Name)
- Pacote fonte Python: $($sdists[0].Name)
- Testes do backend: $ExpectedTestSummary
- npm ci: aprovado
- Testes mobile: aprovados
- Testes das regras Firestore: aprovados
- npm audit de producao: aprovado com audit-level=high; alertas moderados nao bloqueiam
- Expo install check: aprovado
- ESLint: aprovado
- TypeScript: aprovado
- Export Web: aprovado
- Rotas HTML geradas: $GeneratedRoutes

Os logs completos estao na pasta `logs` externa aos ZIPs.
"@
$validationReport | Set-Content -LiteralPath (Join-Path $SourceRoot "VALIDATION_ACADEMIC_PACKAGE.md") -Encoding UTF8

Assert-CleanSourcePackage
Assert-CleanWebPackage

New-PackageManifest -Root $SourceRoot -ManifestPath (Join-Path $SourceRoot "PACKAGE_MANIFEST.csv")
New-PackageManifest -Root $WebRoot -ManifestPath (Join-Path $WebRoot "PACKAGE_MANIFEST.csv")
Assert-CleanSourcePackage
Assert-CleanWebPackage

$SourceUncompressedSize = Get-DirectorySize -Path $SourceRoot
$WebUncompressedSize = Get-DirectorySize -Path $WebRoot

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $SourceRoot,
    $SourceZip,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false
)
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $WebRoot,
    $WebZip,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false
)

$sourceZipItem = Get-Item -LiteralPath $SourceZip
$webZipItem = Get-Item -LiteralPath $WebZip
$sourceHash = (Get-FileHash -LiteralPath $SourceZip -Algorithm SHA256).Hash.ToLowerInvariant()
$webHash = (Get-FileHash -LiteralPath $WebZip -Algorithm SHA256).Hash.ToLowerInvariant()
@(
    "$sourceHash  $($sourceZipItem.Name)",
    "$webHash  $($webZipItem.Name)"
) | Set-Content -LiteralPath (Join-Path $OutputRoot "SHA256SUMS.txt") -Encoding ASCII

$ReductionBytes = $WorkspaceSize - $SourceUncompressedSize
if ($WorkspaceSize -gt 0) {
    $ReductionPercent = [math]::Round(($ReductionBytes / [double]$WorkspaceSize) * 100, 2)
}
else {
    $ReductionPercent = 0
}

$finalReport = @"
# Relatorio de empacotamento academico

- Workspace sem .codex_tmp: $(Format-Megabytes -Bytes $WorkspaceSize) MiB
- Source descompactado: $(Format-Megabytes -Bytes $SourceUncompressedSize) MiB
- Source ZIP: $(Format-Megabytes -Bytes $sourceZipItem.Length) MiB
- Web descompactado: $(Format-Megabytes -Bytes $WebUncompressedSize) MiB
- Web ZIP: $(Format-Megabytes -Bytes $webZipItem.Length) MiB
- Reducao absoluta do Source: $(Format-Megabytes -Bytes $ReductionBytes) MiB
- Reducao percentual do Source: $ReductionPercent%
- Rotas HTML geradas: $GeneratedRoutes
- npm audit de producao: aprovado com audit-level=high; alertas moderados nao bloqueiam
- SHA-256 Source: $sourceHash
- SHA-256 Web: $webHash

Os pacotes nao contem node_modules, ambientes virtuais, caches, arquivos .env,
segredos do backend, wheels antigos nem ZIPs aninhados.
"@
$finalReport | Set-Content -LiteralPath (Join-Path $OutputRoot "PACKAGE_REPORT.md") -Encoding UTF8

Write-Host "`nEntrega concluida em: $OutputRoot"
Write-Host "Source ZIP: $($sourceZipItem.Name) - $(Format-Megabytes -Bytes $sourceZipItem.Length) MiB"
Write-Host "Web ZIP: $($webZipItem.Name) - $(Format-Megabytes -Bytes $webZipItem.Length) MiB"
Write-Host "Hashes: $(Join-Path $OutputRoot 'SHA256SUMS.txt')"
