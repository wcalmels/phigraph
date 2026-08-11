#Requires -Version 5.1
<#
.SYNOPSIS
  Operator-side GRDI RC8 staging preflight (check-only, no apply).

.DESCRIPTION
  Loads PHIGRAPH_POSTGRES_DSN from the environment or SecureString prompt,
  optionally documents an SSH local forward, runs two grdi_rc8_cutover.py
  --check-only passes, compares inventory fingerprints, and verifies DSN redaction.

  STAGING = NOT_PROVISIONED until executed against a live VPS database.
  CUTOVER = NOT_EXECUTED (this script never runs --apply).

.PARAMETER RepoRoot
  PhiGraph repository root. Defaults to two levels above this script.

.PARAMETER OutputDir
  Directory for JSON reports. Created if missing.

.PARAMETER SshTunnel
  Documented optional local forward, e.g. "5433:127.0.0.1:5432".
  When set, prints guidance only; does not open the tunnel automatically.

.PARAMETER SkipRedactionProbe
  Skip the controlled redaction probe (not recommended).
#>
[CmdletBinding()]
param(
    [string] $RepoRoot = "",
    [string] $OutputDir = "",
    [string] $SshTunnel = "",
    [switch] $SkipRedactionProbe
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
}

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $RepoRoot "evidence\grdi-rc8-staging\operator-preflight"
}

$CutoverScript = Join-Path $RepoRoot "scripts\grdi_rc8_cutover.py"
if (-not (Test-Path -LiteralPath $CutoverScript)) {
    throw "missing cutover script: $CutoverScript"
}

if (-not [string]::IsNullOrWhiteSpace($SshTunnel)) {
    Write-Host "SSH tunnel (operator action, not opened by this script):"
    Write-Host "  ssh -N -L $SshTunnel OPERATOR@VPS_HOST"
    Write-Host "Ensure PHIGRAPH_POSTGRES_DSN targets the local forward endpoint."
}

function Get-Python312 {
    $candidates = @("py -3.12", "python3.12", "python")
    foreach ($candidate in $candidates) {
        try {
            $exe = $candidate.Split(" ")[0]
            if ($candidate -match "^py ") {
                & py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) { return @("py", "-3.12") }
            } elseif (Get-Command $exe -ErrorAction SilentlyContinue) {
                & $exe -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) { return @($exe) }
            }
        } catch {
            continue
        }
    }
    throw "Python 3.12 is required for operator preflight"
}

function Read-DsnSecure {
    if ($env:PHIGRAPH_POSTGRES_DSN) {
        return [string]$env:PHIGRAPH_POSTGRES_DSN
    }
    $secure = Read-Host "PHIGRAPH_POSTGRES_DSN (input hidden)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function Get-DsnFragmentForRedactionTest {
    param([string] $Dsn)
    try {
        $uri = [Uri]$Dsn
        if ($uri.UserInfo) {
            $user = $uri.UserInfo.Split(":")[0]
            if ($user) { return $user }
        }
        if ($uri.Host) { return $uri.Host }
    } catch {
        return $null
    }
    return $null
}

function Invoke-CheckOnly {
    param(
        [string[]] $Python,
        [string] $ReportPath
    )
    $args = @($CutoverScript, "--check-only", "--output", $ReportPath)
    & @Python @args 2>&1 | ForEach-Object { $_ }
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 2) {
        throw "check-only failed with exit code $LASTEXITCODE (report: $ReportPath)"
    }
    if (-not (Test-Path -LiteralPath $ReportPath)) {
        throw "check-only did not produce report: $ReportPath"
    }
    return (Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json)
}

$PythonCmd = Get-Python312
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$dsnLoaded = $false
try {
    $dsn = Read-DsnSecure
    if ([string]::IsNullOrWhiteSpace($dsn)) {
        throw "PHIGRAPH_POSTGRES_DSN is empty"
    }
    $env:PHIGRAPH_POSTGRES_DSN = $dsn
    $dsnLoaded = $true

    if ($env:PHIGRAPH_ENVIRONMENT -in @("production", "prod")) {
        throw "PHIGRAPH_ENVIRONMENT must not be production for staging preflight"
    }
    if ($env:PHIGRAPH_ENV -in @("production", "prod")) {
        throw "PHIGRAPH_ENV must not be production for staging preflight"
    }

    $reportOne = Join-Path $OutputDir "check_only_01.json"
    $reportTwo = Join-Path $OutputDir "check_only_02.json"

    $resultOne = Invoke-CheckOnly -Python $PythonCmd -ReportPath $reportOne
    Start-Sleep -Seconds 1
    $resultTwo = Invoke-CheckOnly -Python $PythonCmd -ReportPath $reportTwo

    $fpOne = $resultOne.inventory_fingerprint
    $fpTwo = $resultTwo.inventory_fingerprint
    if ([string]::IsNullOrWhiteSpace($fpOne) -or [string]::IsNullOrWhiteSpace($fpTwo)) {
        throw "inventory fingerprint missing from check-only report"
    }
    if ($fpOne -ne $fpTwo) {
        throw "inventory fingerprints differ between check-only runs"
    }
    Write-Host "inventory fingerprint stable across check-only runs"

    if (-not $SkipRedactionProbe) {
        $frag = Get-DsnFragmentForRedactionTest -Dsn $dsn
        if ($frag) {
            $combined = (Get-Content -LiteralPath $reportOne -Raw) + (Get-Content -LiteralPath $reportTwo -Raw)
            if ($combined.Contains($frag)) {
                throw "NO_GO: se detectó un fragmento sensible en el reporte."
            }
        }
        Write-Host "redaction probe passed (no DSN fragments in reports)"
    }

    Write-Host "operator preflight complete (check-only only; apply not executed)"
    Write-Host "assessment_state=$($resultTwo.assessment_state) final_state=$($resultTwo.final_state) exit=$LASTEXITCODE"
} finally {
    if ($dsnLoaded) {
        Remove-Item Env:PHIGRAPH_POSTGRES_DSN -ErrorAction SilentlyContinue
    }
}
