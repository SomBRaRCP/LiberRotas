#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$relativePaths = @(
    "backend_trq_bec\.env",
    "backend_trq_bec\.env.backend",
    "mobile_app\.env.local"
)
$backupDirectory = Join-Path $workspaceRoot "backend_trq_bec\backups\windows-acl"
New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
$backupPath = Join-Path $backupDirectory ("env-acl-{0}.clixml" -f (Get-Date -Format "yyyyMMdd-HHmmss-fff"))

# Guarda somente as permissoes anteriores; nunca copia o conteudo dos arquivos.
$existingFiles = @($relativePaths | ForEach-Object {
    $path = Join-Path $workspaceRoot $_
    if (Test-Path -LiteralPath $path -PathType Leaf) { $path }
})
if ($existingFiles.Count -eq 0) {
    throw "Nenhum arquivo de ambiente encontrado neste workspace."
}
$existingFiles | ForEach-Object {
    [PSCustomObject]@{ Path = $_; Sddl = (Get-Acl -LiteralPath $_).Sddl }
} | Export-Clixml -LiteralPath $backupPath

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$allowedSids = @(
    $currentUser,
    [System.Security.Principal.SecurityIdentifier]::new("S-1-5-18"),
    [System.Security.Principal.SecurityIdentifier]::new("S-1-5-32-544")
)
foreach ($path in $existingFiles) {
    $acl = Get-Acl -LiteralPath $path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) { $acl.RemoveAccessRuleSpecific($rule) }
    foreach ($sid in $allowedSids) {
        $acl.AddAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new(
            $sid, "FullControl", "Allow"
        ))
    }
    Set-Acl -LiteralPath $path -AclObject $acl

    $verifiedAcl = Get-Acl -LiteralPath $path
    if (-not $verifiedAcl.AreAccessRulesProtected) {
        throw "A heranca de permissoes continua ativa em $path."
    }
    foreach ($rule in $verifiedAcl.Access) {
        $sid = $rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier])
        if ($sid.Value -notin $allowedSids.Value -or $rule.AccessControlType -ne "Allow") {
            throw "Permissao inesperada depois da protecao de $path."
        }
    }
    Write-Host "Protegido: $path"
}
Write-Host "ACL anterior salva em: $backupPath"
Write-Host "Acesso restrito ao usuario atual, Administradores e SYSTEM."
