Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$baseUrl = 'http://localhost:8000'
$login = Invoke-RestMethod -Method Post -Uri "$baseUrl/auth/login" -ContentType 'application/json' -Body '{"username":"admin","password":"admin123"}'
$headers = @{ Authorization = "Bearer $($login.token)" }
$companyId = $login.companies[0].id
$paths = @(
    '/health',
    "/dashboard/$companyId",
    "/production/$companyId/live",
    "/production/$companyId/capacity",
    "/reports/$companyId/employees",
    "/reports/$companyId/machines",
    "/reports/$companyId/costs",
    "/costing/$companyId/sheets",
    "/costing/$companyId/controls",
    "/costing/$companyId/wizard-catalog",
    "/confection/$companyId/overview?weeks=8",
    "/configuration/$companyId/style",
    "/crud/styles?company_id=$companyId",
    "/crud/materials?company_id=$companyId",
    "/crud/subcontract-services?company_id=$companyId",
    "/crud/subcontract-jobs?company_id=$companyId",
    "/crud/capacity-days?company_id=$companyId",
    "/crud/capacity-events?company_id=$companyId",
    "/crud/employee-skills?company_id=$companyId",
    "/crud/sewing-plans?company_id=$companyId",
    "/crud/external-capacities?company_id=$companyId",
    "/crud/work-shifts?company_id=$companyId",
    "/crud/production-orders?company_id=$companyId"
)
foreach ($path in $paths) {
    Invoke-RestMethod -Uri "$baseUrl$path" -Headers $headers | Out-Null
    Write-Host "PASS $path"
}
$styles = Invoke-RestMethod -Uri "$baseUrl/crud/styles?company_id=$companyId&limit=1" -Headers $headers
$checkBody = @{
    company_id = $companyId
    style_id = $styles[0].id
    quantity = 1000
    requested_date = (Get-Date).AddDays(60).ToString('yyyy-MM-dd')
} | ConvertTo-Json
$capacityCheck = Invoke-RestMethod -Method Post -Uri "$baseUrl/confection/capacity-check" -Headers $headers -ContentType 'application/json' -Body $checkBody
if (-not $capacityCheck.scenarios -or $capacityCheck.sam_minutes -le 0) { throw 'A simulação de capacidade não devolveu cenários válidos.' }
Write-Host 'PASS simulador de capacidade'
$web = Invoke-WebRequest -UseBasicParsing 'http://localhost:8080'
if ($web.StatusCode -ne 200) { throw 'A interface web não respondeu com HTTP 200.' }
Write-Host 'PASS interface web'
