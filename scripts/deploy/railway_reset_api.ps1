#Requires -Version 5.1
<#
.SYNOPSIS
  Configure phigraph-api registry variables on the existing phigraph-private-pilot project.

  Default: provision only PHIGRAPH_API_KEY_ADMIN without rotating existing registry or legacy secrets.
  -RotateRegistryKeys: rotate proposer, verifier, tenant-B and admin registry keys.
  -ConfirmServiceRecreation: destructive factory reset plus legacy/signing rotation.

.PREREQUISITE
  railway login
  railway link   # choose project phigraph-private-pilot, service phigraph-api

.EXAMPLE
  cd C:\Users\wcalm\OneDrive\Escritorio\book_agent\PhiGraph
  .\scripts\deploy\railway_reset_api.ps1

.EXAMPLE
  .\scripts\deploy\railway_reset_api.ps1 -RotateRegistryKeys

.EXAMPLE
  .\scripts\deploy\railway_reset_api.ps1 -ConfirmServiceRecreation
#>
[CmdletBinding()]
param(
    [switch]$ConfirmServiceRecreation,
    [switch]$RotateRegistryKeys
)

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
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes)
    }
    finally {
        $rng.Dispose()
    }
}

function Set-RailwaySecretVariable {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )
    $Value | railway variable set $Name --stdin --service $ServiceName --skip-deploys
    if ($LASTEXITCODE -ne 0) {
        throw "$Name set failed"
    }
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $RepoRoot

Write-Host "== PhiGraph Railway API variable setup ==" -ForegroundColor Cyan
Write-Host "Project must be linked: phigraph-private-pilot"
Write-Host "Postgres is NOT deleted.`n"
Assert-RailwayCli

$null = railway status 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Not linked to a project. Run: railway link  (choose phigraph-private-pilot)"
}

if ($ConfirmServiceRecreation -and $RotateRegistryKeys) {
    throw 'Use -ConfirmServiceRecreation for factory reset, or -RotateRegistryKeys for non-destructive registry rotation.'
}

if ($ConfirmServiceRecreation) {
    Write-Host "[1/4] Deleting service '$ServiceName' (destructive)..." -ForegroundColor Yellow
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
    $stepPrefix = '[3/4]'
    $finalStep = '[4/4]'
} else {
    if ($RotateRegistryKeys) {
        Write-Host "Rotating registry keys on existing '$ServiceName' (legacy secrets preserved)." -ForegroundColor Green
    } else {
        Write-Host "Provisioning PHIGRAPH_API_KEY_ADMIN on existing '$ServiceName' (all other secrets preserved)." -ForegroundColor Green
    }
    $stepPrefix = '[1/2]'
    $finalStep = '[2/2]'
}

$proposerKey = $null
$verifierKey = $null
$tenantBKey = $null
$adminKey = $null
$apiKey = $null
$receiptKey = $null

if ($ConfirmServiceRecreation -or $RotateRegistryKeys) {
    $proposerKey = New-RandomSecret
    $verifierKey = New-RandomSecret
    $tenantBKey = New-RandomSecret
    $adminKey = New-RandomSecret
} else {
    $adminKey = New-RandomSecret
}

if ($ConfirmServiceRecreation) {
    $apiKey = New-RandomSecret
    $receiptKey = New-RandomSecret
}

Write-Host "$stepPrefix Setting variables..." -ForegroundColor Yellow
if ($ConfirmServiceRecreation) {
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
}

$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    if ($ConfirmServiceRecreation -or $RotateRegistryKeys) {
        Set-RailwaySecretVariable -Name 'PHIGRAPH_API_KEY_PROPOSER' -Value $proposerKey
        Set-RailwaySecretVariable -Name 'PHIGRAPH_API_KEY_VERIFIER' -Value $verifierKey
        Set-RailwaySecretVariable -Name 'PHIGRAPH_API_KEY_TENANT_B' -Value $tenantBKey
        Set-RailwaySecretVariable -Name 'PHIGRAPH_API_KEY_ADMIN' -Value $adminKey
    } else {
        Set-RailwaySecretVariable -Name 'PHIGRAPH_API_KEY_ADMIN' -Value $adminKey
    }

    if ($ConfirmServiceRecreation) {
        Set-RailwaySecretVariable -Name 'PHIGRAPH_API_KEY' -Value $apiKey
        Set-RailwaySecretVariable -Name 'PHIGRAPH_RECEIPT_SIGNING_KEY' -Value $receiptKey
    }
}
finally {
    $ErrorActionPreference = $prev
}

if ($ConfirmServiceRecreation) {
    Write-Host "$finalStep Deploying from latest commit..." -ForegroundColor Yellow
    Invoke-Railway -CommandArgs @('redeploy', '--service', $ServiceName, '--from-source', '--yes')
} else {
    Write-Host "$finalStep Registry variables set with --skip-deploys." -ForegroundColor Yellow
}

Write-Host "`n== DONE. Secrets were sent to Railway only (not printed). ==" -ForegroundColor Green
if ($ConfirmServiceRecreation -or $RotateRegistryKeys) {
    Write-Host 'PHIGRAPH_API_KEY_PROPOSER configured'
    Write-Host 'PHIGRAPH_API_KEY_VERIFIER configured'
    Write-Host 'PHIGRAPH_API_KEY_TENANT_B configured'
    Write-Host 'PHIGRAPH_API_KEY_ADMIN configured'
} else {
    Write-Host 'PHIGRAPH_API_KEY_ADMIN configured'
    Write-Host 'PHIGRAPH_API_KEY_PROPOSER unchanged'
    Write-Host 'PHIGRAPH_API_KEY_VERIFIER unchanged'
    Write-Host 'PHIGRAPH_API_KEY_TENANT_B unchanged'
}
if ($ConfirmServiceRecreation) {
    Write-Host 'PHIGRAPH_API_KEY configured'
    Write-Host 'PHIGRAPH_RECEIPT_SIGNING_KEY configured'
} else {
    Write-Host 'PHIGRAPH_API_KEY unchanged'
    Write-Host 'PHIGRAPH_RECEIPT_SIGNING_KEY unchanged'
}
Write-Host 'Retrieve values from Railway Variables UI. Never paste secrets in chat, logs, or transcripts.' -ForegroundColor Yellow
if ($ConfirmServiceRecreation) {
    Write-Host "`nWait 5-10 min. Dashboard should show Online (not Building 24h)."
    Write-Host "Logs: railway logs --service $ServiceName --deployment --latest --lines 30"
} elseif ($RotateRegistryKeys) {
    Write-Host 'Service was not deleted. Use -ConfirmServiceRecreation only for destructive factory reset and legacy secret rotation.' -ForegroundColor DarkYellow
} else {
    Write-Host 'Use -RotateRegistryKeys to rotate proposer, verifier, tenant-B and admin keys explicitly.' -ForegroundColor DarkYellow
}

$apiKey = $null
$proposerKey = $null
$verifierKey = $null
$tenantBKey = $null
$adminKey = $null
$receiptKey = $null
