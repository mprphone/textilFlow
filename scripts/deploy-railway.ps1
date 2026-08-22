Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $railway = Get-Command railway -ErrorAction SilentlyContinue
    if (-not $railway) {
        Write-Host 'A instalar Railway CLI...'
        npm install -g @railway/cli
        $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')
        $railway = Get-Command railway -ErrorAction SilentlyContinue
    }
    if (-not $railway) {
        throw 'Railway CLI nao ficou no PATH. Feche e reabra o PowerShell e volte a correr .\scripts\deploy-railway.ps1'
    }
    railway login
    railway init
    railway add --database postgres
    $secret = -join ((1..40) | ForEach-Object { Get-Random -InputObject ([char[]]((48..57) + (65..90) + (97..122))) })
    railway variable set "APP_SECRET=$secret"
    railway variable set "APP_ALLOW_WEAK_SECRET=0"
    railway variable set 'DATABASE_URL=${{Postgres.DATABASE_URL}}'
    railway up
    railway domain
    Write-Host 'Quando o deploy terminar, abra o dominio HTTPS. Login: admin / admin123'
} finally {
    Pop-Location
}
