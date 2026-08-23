#Requires -Version 5.1
<#
.SYNOPSIS
  Factory-reset phigraph-api on the existing phigraph-private-pilot project.

  Keeps Postgres. Deletes the broken phigraph-api service and creates a fresh one
  from deploy/railway-private-pilot (railway.toml controls pre-deploy + healthcheck).

.PREREQUISITE
  railway login
  railway link   # choose project phigraph-private-pilot, service phigraph-api

.EXAMPLE
  cd C:\Users\wcalm\OneDrive\Escritorio\book_agent\PhiGraph
  .\scripts\deploy\railway_reset_api.ps1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ServiceName = 'phigraph-api'
$Branch = 'deploy/railway-private-pilot'
$Repo = 'wcalmels/phigraph'

function Assert-RailwayCli {
    if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
        throw "Railway CLI not found. Install: npm install -g @railway/cli"
    }
    $null = railway whoami 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Not logged in. Run: railway login"
    }
}

function Invoke-Railway {
    param([Parameter(Mandatory = $true)][string[]]$CommandArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & railway @CommandArgs
    $exit = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($exit -ne 0) {
        throw "railway $($CommandArgs -join ' ') failed (exit $exit)"
    }
}

function New-RandomSecret {
    [Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }))
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $RepoRoot

Write-Host "== PhiGraph Railway API reset ==" -ForegroundColor Cyan
Write-Host "Project must be linked: phigraph-private-pilot"
Write-Host "Postgres is NOT deleted.`n"
Assert-RailwayCli

$null = railway status 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Not linked to a project. Run: railway link  (choose phigraph-private-pilot)"
}

Write-Host "[1/4] Deleting broken service '$ServiceName'..." -ForegroundColor Yellow
Write-Host "  If Railway asks to select a service, choose phigraph-api and press Enter." -ForegroundColor DarkGray
try {
    Invoke-Railway -CommandArgs @('service', 'delete', '-s', $ServiceName, '-y')
} catch {
    Write-Host "  Delete step: $($_.Exception.Message) (continuing if service already gone)" -ForegroundColor DarkYellow
}

Write-Host "[2/4] Creating fresh '$ServiceName' from GitHub..." -ForegroundColor Yellow
Invoke-Railway -CommandArgs @(
    'add',
    '--repo', $Repo,
    '--branch', $Branch,
    '--service', $ServiceName,
    '--json'
)

$apiKey = New-RandomSecret
$proposerKey = New-RandomSecret
$verifierKey = New-RandomSecret
$tenantBKey = New-RandomSecret
$receiptKey = New-RandomSecret

Write-Host "[3/4] Setting variables..." -ForegroundColor Yellow
$vars = @(
    'PHIGRAPH_ENV=staging',
    'PHIGRAPH_BACKEND=postgresql',
    'PHIGRAPH_POSTGRES_DSN=${{Postgres.DATABASE_URL}}',
    'PHIGRAPH_SHADOW_ONLY=true',
    'PHIGRAPH_REAL_CONNECTORS_ENABLED=false',
    'PHIGRAPH_DATA_DIR=/app/data',
    'PHIGRAPH_LOG_LEVEL=INFO'
)
foreach ($pair in $vars) {
    Invoke-Railway -CommandArgs @('variable', 'set', $pair, '--service', $ServiceName, '--skip-deploys')
}
$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$apiKey | railway variable set PHIGRAPH_API_KEY --stdin --service $ServiceName --skip-deploys
if ($LASTEXITCODE -ne 0) { throw 'PHIGRAPH_API_KEY set failed' }
$proposerKey | railway variable set PHIGRAPH_API_KEY_PROPOSER --stdin --service $ServiceName --skip-deploys
if ($LASTEXITCODE -ne 0) { throw 'PHIGRAPH_API_KEY_PROPOSER set failed' }
$verifierKey | railway variable set PHIGRAPH_API_KEY_VERIFIER --stdin --service $ServiceName --skip-deploys
if ($LASTEXITCODE -ne 0) { throw 'PHIGRAPH_API_KEY_VERIFIER set failed' }
$tenantBKey | railway variable set PHIGRAPH_API_KEY_TENANT_B --stdin --service $ServiceName --skip-deploys
if ($LASTEXITCODE -ne 0) { throw 'PHIGRAPH_API_KEY_TENANT_B set failed' }
$receiptKey | railway variable set PHIGRAPH_RECEIPT_SIGNING_KEY --stdin --service $ServiceName --skip-deploys
if ($LASTEXITCODE -ne 0) { throw 'PHIGRAPH_RECEIPT_SIGNING_KEY set failed' }
$ErrorActionPreference = $prev

Write-Host "[4/4] Deploying from latest commit..." -ForegroundColor Yellow
Invoke-Railway -CommandArgs @('redeploy', '--service', $ServiceName, '--from-source', '--yes')

Write-Host "`n== DONE. Secrets were sent to Railway only (not printed). ==" -ForegroundColor Green
Write-Host 'PHIGRAPH_API_KEY configured'
Write-Host 'PHIGRAPH_API_KEY_PROPOSER configured'
Write-Host 'PHIGRAPH_API_KEY_VERIFIER configured'
Write-Host 'PHIGRAPH_API_KEY_TENANT_B configured'
Write-Host 'PHIGRAPH_RECEIPT_SIGNING_KEY configured'
Write-Host 'Retrieve values from Railway Variables UI. Never paste secrets in chat, logs, or transcripts.' -ForegroundColor Yellow
Write-Host "`nWait 5-10 min. Dashboard should show Online (not Building 24h)."
Write-Host "Logs: railway logs --service $ServiceName --deployment --latest --lines 30"

$apiKey = $null
$proposerKey = $null
$verifierKey = $null
$tenantBKey = $null
$receiptKey = $null
