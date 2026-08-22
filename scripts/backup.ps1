Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backupDir = Join-Path $projectRoot 'backups'
New-Item -ItemType Directory -Force $backupDir | Out-Null
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupPath = Join-Path $backupDir "textileflow-$timestamp.sql"
Push-Location $projectRoot
try {
    docker compose exec -T db pg_dump -U textileflow --clean --if-exists --no-owner textileflow | Out-File -FilePath $backupPath -Encoding utf8
    Write-Host "Backup criado: $backupPath"
} finally { Pop-Location }
