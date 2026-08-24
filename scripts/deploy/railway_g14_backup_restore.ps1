#Requires -Version 5.1
<#
.SYNOPSIS
  G14 isolated PostgreSQL backup/restore drill wrapper.

.DESCRIPTION
  Delegates to scripts/g14_backup_restore.py. Secrets are read from environment or
  Read-Host -AsSecureString only. Never prints DSN values, API keys, or dump contents.

.PARAMETER BackupOnly
  Create pg_dump backup + manifest after G4 COMPATIBLE checks.

.PARAMETER VerifyManifest
  Validate manifest/checksum coherence (G14b/G14f).

.PARAMETER FullDrill
  Backup, restore to ephemeral database, verify, cleanup.

.PARAMETER ExpectCorruptionRejection
  Use with -VerifyManifest to assert corrupted manifests fail closed.

.PARAMETER ConfirmIsolatedRestore
  Required token for restore/full-drill: G14-ISOLATED-RESTORE

.EXAMPLE
  $env:PHIGRAPH_POSTGRES_DSN = 'postgresql://...'
  .\scripts\deploy\railway_g14_backup_restore.ps1 -BackupOnly -ArtifactDir .\output\g14

.EXAMPLE
  $env:PHIGRAPH_POSTGRES_DSN = 'postgresql://...'
  $env:PHIGRAPH_G14_RESTORE_DSN = 'postgresql://.../postgres'
  .\scripts\deploy\railway_g14_backup_restore.ps1 -FullDrill -ArtifactDir .\output\g14 -ConfirmIsolatedRestore G14-ISOLATED-RESTORE
#>
[CmdletBinding(DefaultParameterSetName = 'BackupOnly')]
param(
    [Parameter(ParameterSetName = 'BackupOnly')]
    [switch]$BackupOnly,

    [Parameter(ParameterSetName = 'VerifyManifest')]
    [switch]$VerifyManifest,

    [Parameter(ParameterSetName = 'FullDrill')]
    [switch]$FullDrill,

    [Parameter(ParameterSetName = 'BackupOnly')]
    [Parameter(ParameterSetName = 'FullDrill')]
    [string]$ArtifactDir = (Join-Path $PSScriptRoot '..\..\output\g14'),

    [Parameter(Mandatory = $true, ParameterSetName = 'VerifyManifest')]
    [string]$ManifestPath,

    [Parameter(ParameterSetName = 'FullDrill')]
    [string]$ConfirmIsolatedRestore,

    [Parameter(ParameterSetName = 'VerifyManifest')]
    [switch]$ExpectCorruptionRejection,

    [string]$RunId,
    [string]$ReportPath,
    [switch]$ForceReport
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$PythonScript = Join-Path $RepoRoot 'scripts\g14_backup_restore.py'
$ConfirmToken = 'G14-ISOLATED-RESTORE'

function Stop-G14FailClosed {
    param(
        [Parameter(Mandatory = $true)][string]$Reason,
        [int]$Code = 2
    )
    $host.UI.WriteErrorLine($Reason)
    exit $Code
}

function Complete-G14Python {
    param([Parameter(Mandatory = $true)][string]$Action)
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Stop-G14FailClosed -Reason ("G14 $Action failed (exit $code)") -Code $code
    }
}

function Read-SecretEnv {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Prompt
    )
    $existing = [Environment]::GetEnvironmentVariable($Name)
    if ($existing) { return $existing }
    $label = if ($Prompt) { $Prompt } else { $Name }
    Write-Host "$label (hidden; not stored on disk):" -ForegroundColor Yellow
    $secure = Read-Host $label -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringAuto($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Resolve-Python {
    $candidates = @('py -3', 'python3', 'python')
    foreach ($candidate in $candidates) {
        $parts = $candidate.Split(' ')
        if (Get-Command $parts[0] -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }
    Stop-G14FailClosed 'Python runtime not found'
}

function Build-ReportArgs {
    if (-not $ReportPath) { return @() }
    $args = @('--output', $ReportPath)
    if ($ForceReport) { $args += '--force-output' }
    return $args
}

Set-Location $RepoRoot

if (-not (Test-Path -LiteralPath $PythonScript)) {
    Stop-G14FailClosed "G14 python entrypoint not found: $PythonScript"
}

if (-not $env:PHIGRAPH_POSTGRES_DSN) {
    $env:PHIGRAPH_POSTGRES_DSN = Read-SecretEnv -Name 'PHIGRAPH_POSTGRES_DSN'
}
if (-not $env:PHIGRAPH_POSTGRES_DSN) {
    Stop-G14FailClosed 'PHIGRAPH_POSTGRES_DSN is required'
}

$python = Resolve-Python
$reportArgs = Build-ReportArgs

Write-Host '== G14 backup/restore drill ==' -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host 'Secrets/DSN values are never printed.' -ForegroundColor Yellow

if ($BackupOnly) {
    $artifact = (Resolve-Path -LiteralPath $ArtifactDir -ErrorAction SilentlyContinue)
    if (-not $artifact) {
        New-Item -ItemType Directory -Path $ArtifactDir -Force | Out-Null
        $artifact = Resolve-Path -LiteralPath $ArtifactDir
    }
    $args = @($PythonScript, 'backup', '--artifact-dir', $artifact.Path) + $reportArgs
    if ($RunId) { $args += @('--run-id', $RunId) }
    if ($python -eq 'py -3') {
        & py -3 @args
    } else {
        & $python @args
    }
    Complete-G14Python 'backup'
    Write-Host 'G14 backup complete. Inspect redacted report only.' -ForegroundColor Green
    exit 0
}

if ($VerifyManifest) {
    $manifest = Resolve-Path -LiteralPath $ManifestPath
    $args = @($PythonScript, 'verify-manifest', '--manifest', $manifest.Path) + $reportArgs
    if ($ExpectCorruptionRejection) { $args += '--expect-corruption-rejection' }
    if ($python -eq 'py -3') {
        & py -3 @args
    } else {
        & $python @args
    }
    Complete-G14Python 'manifest verification'
    Write-Host 'G14 manifest verification complete.' -ForegroundColor Green
    exit 0
}

if ($FullDrill) {
    if ($ConfirmIsolatedRestore -ne $ConfirmToken) {
        Stop-G14FailClosed "-ConfirmIsolatedRestore $ConfirmToken is required for -FullDrill"
    }
    if (-not $env:PHIGRAPH_G14_RESTORE_DSN) {
        $env:PHIGRAPH_G14_RESTORE_DSN = Read-SecretEnv -Name 'PHIGRAPH_G14_RESTORE_DSN' -Prompt 'PHIGRAPH_G14_RESTORE_DSN (admin connection target, not production)'
    }
    if (-not $env:PHIGRAPH_G14_RESTORE_DSN) {
        Stop-G14FailClosed 'PHIGRAPH_G14_RESTORE_DSN is required for -FullDrill'
    }
    $artifact = (Resolve-Path -LiteralPath $ArtifactDir -ErrorAction SilentlyContinue)
    if (-not $artifact) {
        New-Item -ItemType Directory -Path $ArtifactDir -Force | Out-Null
        $artifact = Resolve-Path -LiteralPath $ArtifactDir
    }
    $args = @(
        $PythonScript,
        'full-drill',
        '--artifact-dir', $artifact.Path,
        '--confirm-isolated-restore', $ConfirmToken
    ) + $reportArgs
    if ($RunId) { $args += @('--run-id', $RunId) }
    if ($python -eq 'py -3') {
        & py -3 @args
    } else {
        & $python @args
    }
    Complete-G14Python 'full drill'
    Write-Host 'G14 full drill complete. Ephemeral restore database dropped.' -ForegroundColor Green
    exit 0
}

Stop-G14FailClosed 'Specify -BackupOnly, -VerifyManifest, or -FullDrill'
