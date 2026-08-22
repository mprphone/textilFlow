param([Parameter(Mandatory=$true)][string]$BackupPath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$resolvedBackup = (Resolve-Path -LiteralPath $BackupPath).Path
$projectRoot = Split-Path -Parent $PSScriptRoot
$confirmation = Read-Host "A reposição substitui os dados atuais. Escreva RESTAURAR para continuar"
if ($confirmation -ne 'RESTAURAR') { Write-Host 'Operação cancelada.'; exit 1 }
Push-Location $projectRoot
try {
    Get-Content -LiteralPath $resolvedBackup -Raw | docker compose exec -T db psql -U textileflow -d textileflow
    Write-Host 'Base de dados restaurada.'
} finally { Pop-Location }
