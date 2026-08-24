#Requires -Version 5.1
<#
.SYNOPSIS
  Windows-safe G14 live drill launcher.

.DESCRIPTION
  Operator mode prompts for the local PostgreSQL password, then re-invokes this
  same file through `railway run -- powershell -File`. Secrets stay in process
  environment variables and are never placed on argv.

  This script does not enable a Railway TCP proxy and does not print DSNs.

.PARAMETER InsideRailwayEnvironment
  Internal mode for the railway-run child. Requires DATABASE_PUBLIC_URL.

.PARAMETER ExpectedBaselineCommit
  Railway-deployed G14 baseline. Local mode requires this commit to be an
  ancestor of HEAD and a clean worktree. Do not pin HEAD to the runner commit.
#>
[CmdletBinding()]
param(
    [switch]$InsideRailwayEnvironment,
    [string]$ExpectedBaselineCommit = 'e805f969421fc0392632365df998d0a248fc9d97'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:WrapperPath = Join-Path $PSScriptRoot 'railway_g14_backup_restore.ps1'
$script:ArtifactDir = Join-Path $script:RepoRoot 'output\g14'
$script:AllowedRestoreHosts = @('localhost', '127.0.0.1', '::1')
$script:PgBinCandidates = @(
    'C:\Program Files\PostgreSQL\18\bin',
    'C:\Program Files\PostgreSQL\17\bin',
    'C:\Program Files\PostgreSQL\16\bin'
)

function Stop-G14FailClosed {
    param([Parameter(Mandatory = $true)][string]$Reason)
    $host.UI.WriteErrorLine($Reason)
    exit 2
}

function Test-G14InteractiveConsole {
    if (-not [Environment]::UserInteractive) {
        return $false
    }
    $commandLine = [Environment]::GetCommandLineArgs()
    foreach ($arg in $commandLine) {
        if ($arg -eq '-NonInteractive' -or $arg -eq '-noninteractive') {
            return $false
        }
    }
    try {
        if ([Console]::IsInputRedirected) {
            return $false
        }
    }
    catch {
        return $false
    }
    return $Host.Name -eq 'ConsoleHost'
}

function Add-G14SslModeRequire {
    param([Parameter(Mandatory = $true)][string]$Dsn)
    $trimmed = $Dsn.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) {
        Stop-G14FailClosed 'source DSN is empty'
    }
    $hashIndex = $trimmed.IndexOf('#')
    $core = $trimmed
    $fragment = ''
    if ($hashIndex -ge 0) {
        $core = $trimmed.Substring(0, $hashIndex)
        $fragment = $trimmed.Substring($hashIndex)
    }
    $queryIndex = $core.IndexOf('?')
    if ($queryIndex -lt 0) {
        return ($core + '?sslmode=require' + $fragment)
    }
    $base = $core.Substring(0, $queryIndex)
    $query = $core.Substring($queryIndex + 1)
    $parts = New-Object System.Collections.Generic.List[string]
    $replaced = $false
    foreach ($part in $query.Split('&')) {
        if ([string]::IsNullOrEmpty($part)) {
            continue
        }
        $eq = $part.IndexOf('=')
        $key = if ($eq -ge 0) { $part.Substring(0, $eq) } else { $part }
        if ($key.Equals('sslmode', [StringComparison]::OrdinalIgnoreCase)) {
            [void]$parts.Add('sslmode=require')
            $replaced = $true
        }
        else {
            [void]$parts.Add($part)
        }
    }
    if (-not $replaced) {
        [void]$parts.Add('sslmode=require')
    }
    return ($base + '?' + [string]::Join('&', $parts.ToArray()) + $fragment)
}

function Get-G14DsnUri {
    param([Parameter(Mandatory = $true)][string]$Dsn)
    try {
        return New-Object Uri($Dsn)
    }
    catch {
        Stop-G14FailClosed 'DSN is not a valid URI'
    }
}

function Get-G14DsnHost {
    param([Parameter(Mandatory = $true)][string]$Dsn)
    $uri = Get-G14DsnUri -Dsn $Dsn
    return $uri.Host.Trim('[').Trim(']').ToLowerInvariant()
}

function Get-G14DsnIdentity {
    param([Parameter(Mandatory = $true)][string]$Dsn)
    $uri = Get-G14DsnUri -Dsn $Dsn
    $userInfo = $uri.UserInfo
    $user = $userInfo
    $colon = $userInfo.IndexOf(':')
    if ($colon -ge 0) {
        $user = $userInfo.Substring(0, $colon)
    }
    $user = [Uri]::UnescapeDataString($user).ToLowerInvariant()
    $hostName = $uri.Host.Trim('[').Trim(']').ToLowerInvariant()
    $port = if ($uri.IsDefaultPort -or $uri.Port -le 0) { 5432 } else { $uri.Port }
    $database = [Uri]::UnescapeDataString($uri.AbsolutePath.Trim('/'))
    return ('{0}@{1}:{2}/{3}' -f $user, $hostName, $port, $database)
}

function Assert-G14RestoreHostAllowed {
    param([Parameter(Mandatory = $true)][string]$Dsn)
    $hostName = Get-G14DsnHost -Dsn $Dsn
    if ($script:AllowedRestoreHosts -notcontains $hostName) {
        Stop-G14FailClosed 'restore host is not localhost'
    }
}

function Assert-G14SourceDiffersFromRestore {
    param(
        [Parameter(Mandatory = $true)][string]$SourceDsn,
        [Parameter(Mandatory = $true)][string]$RestoreDsn
    )
    if ((Get-G14DsnIdentity -Dsn $SourceDsn) -eq (Get-G14DsnIdentity -Dsn $RestoreDsn)) {
        Stop-G14FailClosed 'source and restore DSN must differ'
    }
}

function Assert-G14BaselineAndWorktree {
    param(
        [string]$RepoRoot = $script:RepoRoot,
        [string]$BaselineCommit = $ExpectedBaselineCommit
    )
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        Stop-G14FailClosed 'git is required'
    }
    if ([string]::IsNullOrWhiteSpace($RepoRoot) -or -not (Test-Path -LiteralPath $RepoRoot)) {
        Stop-G14FailClosed 'git repository is required'
    }
    if ([string]::IsNullOrWhiteSpace($BaselineCommit)) {
        Stop-G14FailClosed 'baseline commit is required'
    }
    $head = & git -C $RepoRoot rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($head)) {
        Stop-G14FailClosed 'unable to resolve worktree HEAD'
    }
    & git -C $RepoRoot merge-base --is-ancestor $BaselineCommit HEAD
    if ($LASTEXITCODE -ne 0) {
        Stop-G14FailClosed 'HEAD does not descend from the G14 Railway baseline commit'
    }
    $status = & git -C $RepoRoot status --porcelain
    if ($LASTEXITCODE -ne 0) {
        Stop-G14FailClosed 'unable to determine worktree status'
    }
    $statusText = if ($null -eq $status) { '' } else { [string]$status }
    if (-not [string]::IsNullOrWhiteSpace($statusText)) {
        Stop-G14FailClosed 'worktree is not clean'
    }
}

function Assert-G14PgTools {
    foreach ($candidate in $script:PgBinCandidates) {
        if (Test-Path -LiteralPath $candidate) {
            $env:Path = $candidate + [IO.Path]::PathSeparator + $env:Path
            break
        }
    }
    foreach ($tool in @('pg_dump', 'pg_restore')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            Stop-G14FailClosed ("required tool missing: " + $tool)
        }
    }
}

function Invoke-G14InsideRailwayEnvironment {
    try {
        $publicUrl = [Environment]::GetEnvironmentVariable('DATABASE_PUBLIC_URL')
        if ([string]::IsNullOrWhiteSpace($publicUrl)) {
            Stop-G14FailClosed 'DATABASE_PUBLIC_URL is required'
        }
        $restoreDsn = [Environment]::GetEnvironmentVariable('PHIGRAPH_G14_RESTORE_DSN')
        if ([string]::IsNullOrWhiteSpace($restoreDsn)) {
            Stop-G14FailClosed 'PHIGRAPH_G14_RESTORE_DSN is required'
        }
        Assert-G14RestoreHostAllowed -Dsn $restoreDsn
        $sourceDsn = Add-G14SslModeRequire -Dsn $publicUrl
        Assert-G14SourceDiffersFromRestore -SourceDsn $sourceDsn -RestoreDsn $restoreDsn
        Assert-G14PgTools
        $env:PHIGRAPH_POSTGRES_DSN = $sourceDsn
        if (-not (Test-Path -LiteralPath $script:WrapperPath)) {
            Stop-G14FailClosed 'G14 backup wrapper is missing'
        }
        & $script:WrapperPath -FullDrill -ArtifactDir $script:ArtifactDir -ConfirmIsolatedRestore 'G14-ISOLATED-RESTORE'
        $code = $LASTEXITCODE
        if ($null -eq $code) {
            $code = 0
        }
        exit $code
    }
    finally {
        Remove-Item Env:PHIGRAPH_POSTGRES_DSN -ErrorAction SilentlyContinue
    }
}

function Invoke-G14OperatorLocal {
    if (-not (Test-G14InteractiveConsole)) {
        Stop-G14FailClosed 'interactive PowerShell console is required'
    }
    Assert-G14BaselineAndWorktree
    Assert-G14PgTools
    if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
        Stop-G14FailClosed 'railway CLI is required'
    }

    $secure = $null
    $bstr = [IntPtr]::Zero
    $plain = $null
    $encoded = $null
    try {
        $secure = Read-Host -AsSecureString 'Local PostgreSQL postgres password'
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        if ([string]::IsNullOrEmpty($plain)) {
            Stop-G14FailClosed 'password is empty'
        }
        $encoded = [uri]::EscapeDataString($plain)
        $env:PHIGRAPH_G14_RESTORE_DSN = 'postgresql://postgres:' + $encoded + '@127.0.0.1:5432/postgres'
        Assert-G14RestoreHostAllowed -Dsn $env:PHIGRAPH_G14_RESTORE_DSN
        $plain = $null
        $encoded = $null

        $childArgs = @(
            'run',
            '--service', 'Postgres',
            '--',
            'powershell',
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-File', $PSCommandPath,
            '-InsideRailwayEnvironment'
        )
        & railway @childArgs
        $code = $LASTEXITCODE
        if ($null -eq $code) {
            $code = 0
        }
        exit $code
    }
    finally {
        Remove-Item Env:PHIGRAPH_G14_RESTORE_DSN -ErrorAction SilentlyContinue
        Remove-Item Env:PHIGRAPH_POSTGRES_DSN -ErrorAction SilentlyContinue
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        $plain = $null
        $encoded = $null
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
            $bstr = [IntPtr]::Zero
        }
        if ($null -ne $secure) {
            $secure.Dispose()
            $secure = $null
        }
    }
}

if ($InsideRailwayEnvironment) {
    Invoke-G14InsideRailwayEnvironment
}
else {
    Invoke-G14OperatorLocal
}
