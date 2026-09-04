#Requires -Version 5.1
<#
.SYNOPSIS
  Railway pilot block-2 validation: persistence, idempotency, auth, tenant isolation,
  GRDI shadow (NOT_EXECUTED), concurrency, and gate report (PASS/FAIL/NOT_EVALUATED).

.PARAMETER SkipRestart
  Skip G12/G13 restart checks (service restart requires Railway CLI + linked project).

.PARAMETER PromptOptionalKeys
  Prompt hidden entry for verifier and tenant-B registry keys when they are not
  already provided through the process environment.

.PARAMETER ManualRestart
  Pause after the shadow flow so an operator can restart the linked API service
  from Railway's dashboard, then verify persistence without invoking Railway CLI.

.EXAMPLE
  .\scripts\deploy\railway_pilot_validation_block2.ps1

.NOTES
  - Keys via Read-Host (hidden) or env: PHIGRAPH_API_KEY_PROPOSER, PHIGRAPH_API_KEY_VERIFIER,
    PHIGRAPH_API_KEY_TENANT_B, PHIGRAPH_API_KEY_ADMIN (never extracted via railway run).
  - Never enables PHIGRAPH_TRUSTED_IDENTITY_HEADERS. Identity comes from server-side key registry.
  - No secrets written to disk. Output is redacted.
#>
[CmdletBinding()]
param(
    [switch]$SkipRestart,
    [switch]$PromptOptionalKeys,
    [switch]$ManualRestart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Base = if ($env:PHIGRAPH_BASE_URL) { $env:PHIGRAPH_BASE_URL.TrimEnd('/') } else { 'https://phigraph-api-production.up.railway.app' }
$RunId = [guid]::NewGuid().ToString('n').Substring(0, 8)
$TenantA = 'pilot-b2-tenant-a'
$TenantB = 'pilot-b2-tenant-b'
$Project = 'pilot-b2-project'
$ProposedAction = @{ type = 'promote'; target = 'staging' }
$GateResults = [ordered]@{}
$EvidenceLog = [System.Collections.Generic.List[string]]::new()
$flow = [pscustomobject]@{ Ok = $false }
$replayId = $null
$DualIdentityReady = $false
$AdminKey = $null

function Read-SecretKey {
    param([string]$Prompt)
    Write-Host "$Prompt (hidden; not stored on disk):" -ForegroundColor Yellow
    $secure = Read-Host $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringAuto($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Get-OptionalSecretKey {
    param([string]$EnvVar, [string]$Prompt)
    $value = [Environment]::GetEnvironmentVariable($EnvVar)
    if ($value) { return $value }
    return $null
}

function Get-Block2Keys {
    param([switch]$PromptOptionalKeys)
    $proposer = Get-OptionalSecretKey 'PHIGRAPH_API_KEY_PROPOSER' 'PHIGRAPH_API_KEY_PROPOSER'
    if (-not $proposer) {
        $proposer = Get-OptionalSecretKey 'PHIGRAPH_API_KEY' 'PHIGRAPH_API_KEY'
    }
    if (-not $proposer) {
        $proposer = Read-SecretKey 'PHIGRAPH_API_KEY_PROPOSER'
    }
    $verifier = Get-OptionalSecretKey 'PHIGRAPH_API_KEY_VERIFIER' 'PHIGRAPH_API_KEY_VERIFIER'
    $tenantB = Get-OptionalSecretKey 'PHIGRAPH_API_KEY_TENANT_B' 'PHIGRAPH_API_KEY_TENANT_B'
    if ($PromptOptionalKeys -and -not $verifier) {
        $verifier = Read-SecretKey 'PHIGRAPH_API_KEY_VERIFIER'
    }
    if ($PromptOptionalKeys -and -not $tenantB) {
        $tenantB = Read-SecretKey 'PHIGRAPH_API_KEY_TENANT_B'
    }
    if (-not $proposer) { throw 'PHIGRAPH_API_KEY_PROPOSER (or PHIGRAPH_API_KEY) is required' }
    return [pscustomobject]@{
        Proposer = $proposer
        Verifier = $verifier
        TenantB  = $tenantB
    }
}

function Resolve-AdminKey {
    $value = Get-OptionalSecretKey 'PHIGRAPH_API_KEY_ADMIN' 'PHIGRAPH_API_KEY_ADMIN'
    if ($value) { return $value }
    return Read-SecretKey 'PHIGRAPH_API_KEY_ADMIN'
}

function Get-GrdiIdentity {
    param([string]$ApiKey)
    return Invoke-PilotApi -Path '/v4/grdi/health' -Headers (New-Headers -ApiKey $ApiKey -TenantId $TenantA -ProjectId $Project -Subject 'identity-probe' -Role 'verifier') -ExpectStatus @(200)
}

function Redact-Text {
    param([string]$Text)
    if (-not $Text) { return $Text }
    $redacted = $Text
    $redacted = [regex]::Replace($redacted, '(?i)(x-api-key["\s:=]+)[^"\s,}]+', '$1[REDACTED]')
    $redacted = [regex]::Replace($redacted, '(?i)("(?:value|signature|key|token|receipt_signing_key)"\s*:\s*")[^"]+(")', '$1[REDACTED]$2')
    $redacted = [regex]::Replace($redacted, '(?i)(PHIGRAPH_API_KEY(?:_(?:PROPOSER|VERIFIER|TENANT_B|ADMIN))?=)\S+', '$1[REDACTED]')
    return $redacted
}

function Get-JsonStringProperty {
    param(
        [object]$Json,
        [string]$Name
    )
    if ($null -eq $Json) { return $null }
    $property = $Json.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) { return $null }
    return [string]$property.Value
}

function Write-Evidence {
    param([string]$Line)
    $safe = Redact-Text $Line
    $EvidenceLog.Add($safe) | Out-Null
    Write-Host $safe
}

function Set-Gate {
    param(
        [string]$Gate,
        [ValidateSet('PASS', 'FAIL', 'NOT_EVALUATED')]
        [string]$Status,
        [string]$Note = ''
    )
    if ($GateResults.Contains($Gate)) {
        throw "Duplicate gate registration: $Gate"
    }
    $GateResults[$Gate] = @{ Status = $Status; Note = $Note }
}

function New-Headers {
    param(
        [string]$ApiKey,
        [string]$TenantId,
        [string]$ProjectId,
        [string]$Subject,
        [string]$Role,
        [hashtable]$Extra = @{}
    )
    $h = @{
        'X-API-Key'    = $ApiKey
        'X-Tenant-ID'  = $TenantId
        'X-Project-ID' = $ProjectId
        'X-Subject'    = $Subject
        'X-Role'       = $Role
    }
    foreach ($k in $Extra.Keys) { $h[$k] = $Extra[$k] }
    return $h
}

function Invoke-PilotApi {
    param(
        [string]$Method = 'Get',
        [string]$Path,
        [hashtable]$Headers = @{},
        [string]$Body = $null,
        [int[]]$ExpectStatus = @(200)
    )
    $uri = if ($Path.StartsWith('http')) { $Path } else { "$Base$Path" }
    try {
        $params = @{
            Uri             = $uri
            Method          = $Method
            Headers         = $Headers
            UseBasicParsing = $true
        }
        if ($Body) {
            $params['Body'] = $Body
            if (-not $Headers.ContainsKey('Content-Type')) {
                $params['Headers'] = $Headers + @{ 'Content-Type' = 'application/json' }
            }
        }
        $resp = Invoke-WebRequest @params
        $code = [int]$resp.StatusCode
        $text = $resp.Content
    } catch {
        $code = [int]$_.Exception.Response.StatusCode.value__
        $text = $_.ErrorDetails.Message
        if (-not $text -and $_.Exception.Response) {
            $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
            $text = $reader.ReadToEnd()
            $reader.Close()
        }
    }
    $ok = $ExpectStatus -contains $code
    return [pscustomobject]@{
        Ok       = $ok
        Status   = $code
        BodyText = $text
        Json     = if ($text) { try { $text | ConvertFrom-Json } catch { $null } } else { $null }
    }
}

function Get-HavPassPayload {
    return (@{
        candidate_output  = 'CodeQL status: passed'
        source_system     = 'github-actions'
        state_available   = $true
        evidence          = @(
            @{
                source     = 'github-actions'
                subject    = 'repository'
                predicate  = 'codeql_status'
                value      = 'passed'
                confidence = 1.0
                scope      = 'current'
                metadata   = @{ required = $true }
            }
        )
        agent_id          = 'release-agent'
    } | ConvertTo-Json -Depth 6 -Compress)
}

function Invoke-HavVerify {
    param(
        [string]$ApiKey,
        [string]$TenantId,
        [string]$ProjectId,
        [string]$IdempotencyKey
    )
    $headers = New-Headers -ApiKey $ApiKey -TenantId $TenantId -ProjectId $ProjectId -Subject 'hav-verifier' -Role 'verifier' -Extra @{
        'Idempotency-Key' = $IdempotencyKey
        'Content-Type'    = 'application/json'
    }
    return Invoke-PilotApi -Method Post -Path '/v3/hav/verify' -Headers $headers -Body (Get-HavPassPayload) -ExpectStatus @(200)
}

function New-GrdiEnvelopeBody {
    param([object]$HavReceipt)
    return (@{
        domain             = 'software'
        decision_type      = 'promote_release'
        subject            = 'phigraph@candidate'
        proposed_action    = $ProposedAction
        hav_receipt        = $HavReceipt
        required_authority = 'verifier'
        risk_level         = 'medium'
    } | ConvertTo-Json -Depth 12 -Compress)
}

function Invoke-GrdiEnvelopeCreate {
    param(
        [string]$ProposerKey,
        [string]$VerifierKey,
        [string]$TenantId,
        [string]$ProjectId,
        [string]$Suffix
    )
    $hav = Invoke-HavVerify -ApiKey $VerifierKey -TenantId $TenantId -ProjectId $ProjectId -IdempotencyKey "b2-hav-$Suffix"
    if (-not $hav.Ok) {
        return [pscustomobject]@{ Ok = $false; Step = 'hav'; Status = $hav.Status; Detail = $hav.Json.detail }
    }

    $createHeaders = New-Headers -ApiKey $ProposerKey -TenantId $TenantId -ProjectId $ProjectId -Subject 'release-agent' -Role 'operator'
    $createHeaders['Idempotency-Key'] = "b2-env-$Suffix"
    $createHeaders['Content-Type'] = 'application/json'
    $create = Invoke-PilotApi -Method Post -Path '/v4/grdi/envelopes' -Headers $createHeaders -Body (New-GrdiEnvelopeBody -HavReceipt $hav.Json.receipt) -ExpectStatus @(201)
    if (-not $create.Ok) {
        return [pscustomobject]@{ Ok = $false; Step = 'envelope'; Status = $create.Status; Detail = $create.Json.detail }
    }

    return [pscustomobject]@{
        Ok         = $true
        EnvelopeId = $create.Json.envelope_id
        Envelope   = $create.Json
        Receipt    = $hav.Json.receipt
    }
}

function Invoke-GrdiShadowFlow {
    param(
        [string]$ProposerKey,
        [string]$VerifierKey,
        [string]$TenantId,
        [string]$ProjectId,
        [string]$Suffix
    )

    $created = Invoke-GrdiEnvelopeCreate -ProposerKey $ProposerKey -VerifierKey $VerifierKey -TenantId $TenantId -ProjectId $ProjectId -Suffix $Suffix
    if (-not $created.Ok) {
        return [pscustomobject]@{ Ok = $false; Step = $created.Step; Status = $created.Status; Detail = $created.Detail }
    }
    $envelope = $created.Envelope

    $authHeaders = New-Headers -ApiKey $VerifierKey -TenantId $TenantId -ProjectId $ProjectId -Subject 'human-verifier' -Role 'verifier'
    $authHeaders['Idempotency-Key'] = "b2-auth-$Suffix"
    $authHeaders['Content-Type'] = 'application/json'
    $auth = Invoke-PilotApi -Method Post -Path "/v4/grdi/envelopes/$($envelope.envelope_id)/authorize" -Headers $authHeaders -Body '{"approved":true}' -ExpectStatus @(201)
    if (-not $auth.Ok) {
        return [pscustomobject]@{ Ok = $false; Step = 'authorize'; Status = $auth.Status; Detail = $auth.Json.detail; EnvelopeId = $envelope.envelope_id }
    }
    $decision = $auth.Json
    if ($decision.authorization_state -ne 'AUTHORIZED' -or $decision.verification_state -ne 'VERIFIED') {
        $reasons = @($decision.reasons) -join ','
        return [pscustomobject]@{
            Ok = $false; Step = 'authorize'; Status = 409
            Detail = "authorization_state=$($decision.authorization_state) verification_state=$($decision.verification_state) reasons=$reasons"
            EnvelopeId = $envelope.envelope_id; Decision = $decision
        }
    }

    $planBody = (@{
        envelope_id           = $envelope.envelope_id
        authority_decision_id = $decision.authority_decision_id
        requested_action      = $ProposedAction
        expected_effects      = @('staging promotion recorded (shadow only)')
        rollback_strategy     = @{ type = 'revert_release' }
    } | ConvertTo-Json -Depth 6 -Compress)

    $planHeaders = New-Headers -ApiKey $ProposerKey -TenantId $TenantId -ProjectId $ProjectId -Subject 'release-agent' -Role 'operator'
    $planHeaders['Idempotency-Key'] = "b2-plan-$Suffix"
    $planHeaders['Content-Type'] = 'application/json'
    $plan = Invoke-PilotApi -Method Post -Path '/v4/grdi/execution-plans' -Headers $planHeaders -Body $planBody -ExpectStatus @(201)
    if (-not $plan.Ok) {
        return [pscustomobject]@{ Ok = $false; Step = 'plan'; Status = $plan.Status; Detail = $plan.Json.detail; EnvelopeId = $envelope.envelope_id; Decision = $decision }
    }
    if ($plan.Json.gateway_decision.eligibility -ne 'ELIGIBLE_FOR_SHADOW') {
        $reasons = @($plan.Json.gateway_decision.reasons) -join ','
        return [pscustomobject]@{
            Ok = $false; Step = 'plan'; Status = 409
            Detail = "eligibility=$($plan.Json.gateway_decision.eligibility) reasons=$reasons"
            EnvelopeId = $envelope.envelope_id; Decision = $decision; Plan = $plan.Json; PlanId = $plan.Json.plan_id
        }
    }

    $simHeaders = New-Headers -ApiKey $VerifierKey -TenantId $TenantId -ProjectId $ProjectId -Subject 'human-verifier' -Role 'verifier'
    $simHeaders['Idempotency-Key'] = "b2-sim-$Suffix"
    $sim = Invoke-PilotApi -Method Post -Path "/v4/grdi/execution-plans/$($plan.Json.plan_id)/simulate" -Headers $simHeaders -ExpectStatus @(201)
    if (-not $sim.Ok) {
        return [pscustomobject]@{
            Ok = $false; Step = 'simulate'; Status = $sim.Status; Detail = $sim.Json.detail
            EnvelopeId = $envelope.envelope_id; Decision = $decision; Plan = $plan.Json; PlanId = $plan.Json.plan_id
        }
    }

    return [pscustomobject]@{
        Ok         = $true
        EnvelopeId = $envelope.envelope_id
        PlanId     = $plan.Json.plan_id
        Decision   = $decision
        Plan       = $plan.Json
        Simulate   = $sim.Json
        Receipt    = $created.Receipt
    }
}

Write-Host '== PhiGraph Railway pilot - block 2 validation ==' -ForegroundColor Cyan
Write-Host "Base: $Base | RunId: $RunId"
Write-Evidence "$(Get-Date -Format o) | block2 start"

$Keys = Get-Block2Keys -PromptOptionalKeys:$PromptOptionalKeys
$ProposerKey = $Keys.Proposer
$VerifierKey = $Keys.Verifier
$TenantBKey = $Keys.TenantB

try {
    $spoofTenant = "spoof-$RunId"
    $headerProbe = Invoke-PilotApi -Path '/v4/grdi/health' -Headers (New-Headers -ApiKey $ProposerKey -TenantId $spoofTenant -ProjectId $Project -Subject 'attacker' -Role 'admin') -ExpectStatus @(200)
    $resolvedTenant = Get-JsonStringProperty -Json $headerProbe.Json -Name 'tenant_id'
    $probeDetail = Get-JsonStringProperty -Json $headerProbe.Json -Name 'detail'
    $headersIgnored = $headerProbe.Ok -and $null -ne $resolvedTenant -and ($resolvedTenant -ne $spoofTenant)
    Write-Evidence "$(Get-Date -Format o) | header spoof HTTP $($headerProbe.Status) tenant=$spoofTenant resolved=$resolvedTenant detail=$probeDetail ignored=$headersIgnored"
    if ($headersIgnored) {
        Set-Gate 'G6b' 'PASS' 'untrusted X-Tenant-ID ignored; server-side identity used'
    } else {
        Set-Gate 'G6b' 'FAIL' 'client tenant header was honored without verified identity'
    }

    $proposerIdentity = Get-GrdiIdentity -ApiKey $ProposerKey
    if ($VerifierKey) {
        $verifierIdentity = Get-GrdiIdentity -ApiKey $VerifierKey
        $DualIdentityReady = $proposerIdentity.Ok -and $verifierIdentity.Ok -and ($ProposerKey -ne $VerifierKey)
        $proposerTenant = Get-JsonStringProperty -Json $proposerIdentity.Json -Name 'tenant_id'
        $verifierTenant = Get-JsonStringProperty -Json $verifierIdentity.Json -Name 'tenant_id'
        Write-Evidence "$(Get-Date -Format o) | proposer HTTP $($proposerIdentity.Status) tenant=$proposerTenant verifier HTTP $($verifierIdentity.Status) tenant=$verifierTenant dual=$DualIdentityReady"
    } else {
        Write-Evidence "$(Get-Date -Format o) | verifier key not supplied; dual-identity gates NOT_EVALUATED"
    }

    # G3 / G5 - postgres via /ready
    $ready = Invoke-PilotApi -Path '/ready' -ExpectStatus @(200, 503)
    $pgOk = $ready.Json.checks.postgres.status -eq 'ok'
    Write-Evidence "$(Get-Date -Format o) | /ready HTTP $($ready.Status) postgres=$($ready.Json.checks.postgres.status)"
    if ($pgOk) {
        Set-Gate 'G3' 'PASS' 'checks.postgres.status=ok'
    } else {
        Set-Gate 'G3' 'FAIL' "postgres status=$($ready.Json.checks.postgres.status)"
    }

    $live = Invoke-PilotApi -Path '/health/live' -ExpectStatus @(200)
    if ($live.Ok -and $live.Json.status -eq 'alive') {
        Set-Gate 'G5' 'PASS' '/health/live alive; /ready postgres checked above'
    } else {
        Set-Gate 'G5' 'FAIL' "health/live HTTP $($live.Status)"
    }

    # G4 - schema governance admin endpoint (requires server-side admin identity)
    if (-not $AdminKey) {
        try {
            $AdminKey = Resolve-AdminKey
        } catch {
            $AdminKey = $null
        }
    }
    if (-not $AdminKey) {
        Set-Gate 'G4' 'NOT_EVALUATED' 'requires PHIGRAPH_API_KEY_ADMIN on server (schema:read)'
    } else {
        $g4Headers = New-Headers -ApiKey $AdminKey -TenantId $TenantA -ProjectId $Project -Subject 'schema-admin' -Role 'admin'
        $g4 = Invoke-PilotApi -Path '/v3/admin/schema-governance' -Headers $g4Headers -ExpectStatus @(200)
        $g4State = Get-JsonStringProperty -Json $g4.Json -Name 'state'
        $g4CatalogValid = $null -ne $g4.Json -and $null -ne $g4.Json.PSObject.Properties['catalog_valid'] -and $g4.Json.PSObject.Properties['catalog_valid'].Value -eq $true
        $g4Detail = Get-JsonStringProperty -Json $g4.Json -Name 'detail'
        Write-Evidence "$(Get-Date -Format o) | schema_governance HTTP $($g4.Status) state=$g4State catalog_valid=$g4CatalogValid detail=$g4Detail"
        if ($g4.Ok -and $g4State -eq 'COMPATIBLE' -and $g4CatalogValid) {
            Set-Gate 'G4' 'PASS' 'schema governance COMPATIBLE; migration registry verified'
        } elseif ($g4.Ok) {
            Set-Gate 'G4' 'FAIL' "schema governance state=$g4State"
        } else {
            Set-Gate 'G4' 'FAIL' "schema governance HTTP $($g4.Status)"
        }
    }

    # G6 - auth negative
    $noKey = Invoke-PilotApi -Method Post -Path '/v3/hav/verify' -Headers @{
        'Content-Type' = 'application/json'
        'X-Tenant-ID'  = $TenantA
        'X-Project-ID' = $Project
        'X-Subject'    = 'anon'
        'X-Role'       = 'verifier'
    } -Body (Get-HavPassPayload) -ExpectStatus @(401)
    $badHeaders = New-Headers -ApiKey 'invalid-key-block2' -TenantId $TenantA -ProjectId $Project -Subject 'anon' -Role 'verifier'
    $badHeaders['Content-Type'] = 'application/json'
    $badKey = Invoke-PilotApi -Method Post -Path '/v3/hav/verify' -Headers $badHeaders -Body (Get-HavPassPayload) -ExpectStatus @(401)
    Write-Evidence "$(Get-Date -Format o) | auth missing HTTP $($noKey.Status) detail=$($noKey.Json.detail)"
    Write-Evidence "$(Get-Date -Format o) | auth invalid HTTP $($badKey.Status) detail=$($badKey.Json.detail)"
    if ($noKey.Ok -and $badKey.Ok) {
        Set-Gate 'G6' 'PASS' 'missing/invalid API key -> 401'
    } else {
        Set-Gate 'G6' 'FAIL' "noKey=$($noKey.Status) badKey=$($badKey.Status)"
    }

    # G7 - idempotency
    $idemKey = "b2-idem-$RunId"
    $h1 = Invoke-HavVerify -ApiKey $VerifierKey -TenantId $TenantA -ProjectId $Project -IdempotencyKey $idemKey
    $h2 = Invoke-HavVerify -ApiKey $VerifierKey -TenantId $TenantA -ProjectId $Project -IdempotencyKey $idemKey
    $idemPass = $h1.Ok -and $h2.Ok -and ($h1.Json.receipt.receipt_id -eq $h2.Json.receipt.receipt_id)
    Write-Evidence "$(Get-Date -Format o) | idempotency receipt1=$($h1.Json.receipt.receipt_id) receipt2=$($h2.Json.receipt.receipt_id)"
    if ($idemPass) { Set-Gate 'G7' 'PASS' 'duplicate Idempotency-Key returns same HAV receipt_id' }
    else { Set-Gate 'G7' 'FAIL' 'idempotency mismatch' }

    # G7b - authenticated tenant isolation (requires server-side tenant-B key)
    if (-not $DualIdentityReady -or -not $TenantBKey) {
        Set-Gate 'G7b' 'NOT_EVALUATED' 'requires PHIGRAPH_API_KEY_PROPOSER + PHIGRAPH_API_KEY_TENANT_B registry on server'
    } else {
        $isoSuffix = "iso-$RunId"
        $isoEnv = Invoke-GrdiEnvelopeCreate -ProposerKey $ProposerKey -VerifierKey $VerifierKey -TenantId $TenantA -ProjectId $Project -Suffix $isoSuffix
        if (-not $isoEnv.Ok) {
            Set-Gate 'G7b' 'FAIL' "envelope create failed step=$($isoEnv.Step) HTTP $($isoEnv.Status)"
        } else {
            $cross = Invoke-PilotApi -Path "/v4/grdi/envelopes/$($isoEnv.EnvelopeId)" -Headers (New-Headers -ApiKey $TenantBKey -TenantId $TenantB -ProjectId $Project -Subject 'tenant-b-viewer' -Role 'verifier') -ExpectStatus @(404)
            Write-Evidence "$(Get-Date -Format o) | tenant isolation cross-tenant GET HTTP $($cross.Status) envelope_id=$($isoEnv.EnvelopeId)"
            if ($cross.Ok) {
                Set-Gate 'G7b' 'PASS' 'tenant B identity cannot read tenant A envelope (404)'
            } else {
                Set-Gate 'G7b' 'FAIL' "expected 404 got $($cross.Status)"
            }
        }
    }

    # G10s - self-authorization must remain blocked for proposer identity
    $selfSuffix = "self-$RunId"
    $selfEnv = Invoke-GrdiEnvelopeCreate -ProposerKey $ProposerKey -VerifierKey $VerifierKey -TenantId $TenantA -ProjectId $Project -Suffix $selfSuffix
    if (-not $selfEnv.Ok) {
        Set-Gate 'G10s' 'FAIL' "envelope create failed step=$($selfEnv.Step) HTTP $($selfEnv.Status)"
    } else {
        $selfAuthHeaders = New-Headers -ApiKey $ProposerKey -TenantId $TenantA -ProjectId $Project -Subject 'release-agent' -Role 'operator'
        $selfAuthHeaders['Idempotency-Key'] = "b2-self-auth-$RunId"
        $selfAuthHeaders['Content-Type'] = 'application/json'
        $selfAuth = Invoke-PilotApi -Method Post -Path "/v4/grdi/envelopes/$($selfEnv.EnvelopeId)/authorize" -Headers $selfAuthHeaders -Body '{"approved":true}' -ExpectStatus @(201, 403)
        $reasons = if ($null -ne $selfAuth.Json -and $null -ne $selfAuth.Json.PSObject.Properties['reasons']) {
            @($selfAuth.Json.reasons) -join ','
        } else {
            ''
        }
        $authState = if ($null -ne $selfAuth.Json -and $null -ne $selfAuth.Json.PSObject.Properties['authorization_state']) {
            $selfAuth.Json.authorization_state
        } else {
            'n/a'
        }
        $authDetail = if ($null -ne $selfAuth.Json -and $null -ne $selfAuth.Json.PSObject.Properties['detail']) {
            $selfAuth.Json.detail
        } else {
            ''
        }
        Write-Evidence "$(Get-Date -Format o) | self-authorize HTTP $($selfAuth.Status) auth=$authState detail=$authDetail reasons=$reasons"
        if (
            ($selfAuth.Status -eq 403 -and "$($selfAuth.Json.detail)" -match 'missing_permission:grdi:authorize') -or
            ($selfAuth.Ok -and ($selfAuth.Json.authorization_state -ne 'AUTHORIZED') -and ($reasons -match 'self_authorization_forbidden'))
        ) {
            Set-Gate 'G10s' 'PASS' 'proposer cannot self-authorize (RBAC or self_authorization_forbidden)'
        } else {
            Set-Gate 'G10s' 'FAIL' "expected self-authorization block got HTTP $($selfAuth.Status) auth=$($selfAuth.Json.authorization_state)"
        }
    }

    # G8 - HAV verify operational
    if ($h1.Ok) { Set-Gate 'G8' 'PASS' "HAV verify HTTP 200 verdict=$($h1.Json.receipt.verdict)" }
    else { Set-Gate 'G8' 'FAIL' "HAV verify HTTP $($h1.Status)" }

    # G9/G10/G11 - GRDI envelope + authorize + shadow simulate
    $mainSuffix = "main-$RunId"
    if (-not $DualIdentityReady) {
        Set-Gate 'G9' 'NOT_EVALUATED' 'requires server-side proposer + verifier API keys'
        Set-Gate 'G10' 'NOT_EVALUATED' 'requires separate authenticated verifier identity'
        Set-Gate 'G11' 'NOT_EVALUATED' 'requires verifier identity for shadow simulate'
        Set-Gate 'G9b' 'NOT_EVALUATED' 'requires completed GRDI flow'
    } else {
    $flow = Invoke-GrdiShadowFlow -ProposerKey $ProposerKey -VerifierKey $VerifierKey -TenantId $TenantA -ProjectId $Project -Suffix $mainSuffix
    $replayId = $null
    $outcomeId = $null
    if (-not $flow.Ok) {
        Write-Evidence "$(Get-Date -Format o) | grdi flow failed step=$($flow.Step) HTTP $($flow.Status) detail=$($flow.Detail)"
        Set-Gate 'G9' 'FAIL' "GRDI flow failed at $($flow.Step)"
        Set-Gate 'G10' 'FAIL' 'blocked by GRDI flow failure'
        Set-Gate 'G11' 'FAIL' 'blocked by GRDI flow failure'
        Set-Gate 'G9b' 'FAIL' 'blocked by GRDI flow failure'
    } else {
        $decision = $flow.Decision
        $sim = $flow.Simulate

        Write-Evidence "$(Get-Date -Format o) | envelope_id=$($flow.EnvelopeId) auth=$($decision.authorization_state) exec=$($decision.execution_state)"
        Set-Gate 'G9' 'PASS' "envelope registered id=$($flow.EnvelopeId)"

        if ($decision.authorization_state -eq 'AUTHORIZED') {
            Set-Gate 'G10' 'PASS' 'authority step AUTHORIZED'
        } else {
            Set-Gate 'G10' 'FAIL' "authorization_state=$($decision.authorization_state)"
        }

        $shadowOk = ($decision.execution_state -eq 'NOT_EXECUTED') -and
            ($flow.Plan.gateway_decision.eligibility -eq 'ELIGIBLE_FOR_SHADOW') -and
            ($sim.shadow_receipt.executed -eq $false) -and
            ($sim.shadow_receipt.connector_invoked -eq $false)
        Write-Evidence "$(Get-Date -Format o) | shadow executed=$($sim.shadow_receipt.executed) connector=$($sim.shadow_receipt.connector_invoked) decision_exec=$($decision.execution_state)"
        if ($shadowOk) { Set-Gate 'G11' 'PASS' 'GRDI shadow simulate; NOT_EXECUTED; no connector' }
        else { Set-Gate 'G11' 'FAIL' 'shadow invariants violated' }

        $getEnv = Invoke-PilotApi -Path "/v4/grdi/envelopes/$($flow.EnvelopeId)" -Headers (New-Headers -ApiKey $ProposerKey -TenantId $TenantA -ProjectId $Project -Subject 'viewer' -Role 'verifier') -ExpectStatus @(200)
        $getPlan = Invoke-PilotApi -Path "/v4/grdi/execution-plans/$($flow.PlanId)" -Headers (New-Headers -ApiKey $ProposerKey -TenantId $TenantA -ProjectId $Project -Subject 'viewer' -Role 'verifier') -ExpectStatus @(200)
        if ($getEnv.Ok -and $getPlan.Ok) {
            Set-Gate 'G9b' 'PASS' 'GET envelope + execution plan after write'
        } else {
            Set-Gate 'G9b' 'FAIL' "GET envelope=$($getEnv.Status) plan=$($getPlan.Status)"
        }

        $replayHeaders = New-Headers -ApiKey $VerifierKey -TenantId $TenantA -ProjectId $Project -Subject 'replay-auditor' -Role 'verifier'
        $replayHeaders['Idempotency-Key'] = "b2-replay-$RunId"
        $replay = Invoke-PilotApi -Method Post -Path "/v4/grdi/execution-plans/$($flow.PlanId)/replays" -Headers $replayHeaders -ExpectStatus @(201)
        $replayId = $replay.Json.replay_id
        Write-Evidence "$(Get-Date -Format o) | replay_id=$replayId"

        $outcomeHeaders = New-Headers -ApiKey $VerifierKey -TenantId $TenantA -ProjectId $Project -Subject 'outcome-auditor' -Role 'verifier'
        $outcomeHeaders['Idempotency-Key'] = "b2-outcome-$RunId"
        $outcomeHeaders['Content-Type'] = 'application/json'
        $outcomeBody = @{
            effect_assessments = @(
                @{
                    expected_effect = 'staging promotion recorded'
                    simulated_observation = 'observed in shadow'
                    state = 'MATCHED'
                }
            )
            metrics = @{ latency_ms = 0 }
            limitations = @('shadow only')
        } | ConvertTo-Json -Depth 8 -Compress
        $outcome = Invoke-PilotApi -Method Post -Path "/v4/grdi/execution-plans/$($flow.PlanId)/outcomes" -Headers $outcomeHeaders -Body $outcomeBody -ExpectStatus @(201)
        if ($outcome.Ok -and $outcome.Json -and $null -ne $outcome.Json.PSObject.Properties['outcome_id']) {
            $outcomeId = $outcome.Json.outcome_id
            Write-Evidence "$(Get-Date -Format o) | outcome_id=$outcomeId state=$($outcome.Json.outcome_state)"
        } else {
            $outcomeId = $null
            Write-Evidence "$(Get-Date -Format o) | outcome create failed HTTP $($outcome.Status) detail=$($outcome.Json.detail)"
        }
    }
    }

    # Concurrency - parallel HAV verifies (PowerShell 5.1 Start-Job)
    $concPayload = Get-HavPassPayload
    $concScript = {
        param($BaseUrl, $Key, $Tenant, $ProjectId, $IdemKey, $Body)
        $headers = @{
            'X-API-Key'       = $Key
            'X-Tenant-ID'     = $Tenant
            'X-Project-ID'    = $ProjectId
            'X-Subject'       = 'conc-verifier'
            'X-Role'          = 'verifier'
            'Idempotency-Key' = $IdemKey
            'Content-Type'    = 'application/json'
        }
        try {
            $r = Invoke-WebRequest -Uri "$BaseUrl/v3/hav/verify" -Method Post -Headers $headers -Body $Body -UseBasicParsing
            return [pscustomobject]@{ Ok = ($r.StatusCode -eq 200); Status = [int]$r.StatusCode }
        } catch {
            return [pscustomobject]@{ Ok = $false; Status = [int]$_.Exception.Response.StatusCode.value__ }
        }
    }
    $jobA = Start-Job -ScriptBlock $concScript -ArgumentList $Base, $VerifierKey, $TenantA, $Project, "b2-conc-a-$RunId", $concPayload
    $jobB = Start-Job -ScriptBlock $concScript -ArgumentList $Base, $VerifierKey, $TenantA, $Project, "b2-conc-b-$RunId", $concPayload
    $concResults = @($jobA, $jobB | Wait-Job | Receive-Job)
    $jobA, $jobB | Remove-Job -Force
    $concFail = @($concResults | Where-Object { -not $_.Ok })
    $concPass = $concFail.Count -eq 0
    Write-Evidence "$(Get-Date -Format o) | concurrency statuses=$(($concResults.Status -join ','))"
    if ($concPass) { Set-Gate 'G7c' 'PASS' 'two parallel HAV verifies returned 200' }
    else { Set-Gate 'G7c' 'FAIL' 'concurrent HAV verify failed' }

    # G12/G13 - service lifecycle persistence (restart or redeploy)
    if ($SkipRestart) {
        Set-Gate 'G12' 'NOT_EVALUATED' '-SkipRestart'
        Set-Gate 'G13' 'NOT_EVALUATED' '-SkipRestart'
    } elseif (-not $DualIdentityReady) {
        Set-Gate 'G12' 'NOT_EVALUATED' 'requires completed GRDI flow with dual server-side identities'
        Set-Gate 'G13' 'NOT_EVALUATED' 'requires completed GRDI flow with dual server-side identities'
    } elseif ((-not $ManualRestart) -and (-not (Get-Command railway -ErrorAction SilentlyContinue))) {
        Set-Gate 'G12' 'NOT_EVALUATED' 'Railway CLI not available'
        Set-Gate 'G13' 'NOT_EVALUATED' 'Railway CLI not available'
    } else {
        if ($ManualRestart) {
            Write-Evidence "$(Get-Date -Format o) | manual reload required for G12/G13"
            Read-Host 'Restart or redeploy phigraph-api, wait until it is Online, then press Enter to verify persistence' | Out-Null
            $restartExitCode = 0
        } else {
            Write-Evidence "$(Get-Date -Format o) | restarting phigraph-api via Railway CLI"
            $previousErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $restartOutput = & railway restart --service phigraph-api --yes 2>&1
                $restartExitCode = $LASTEXITCODE
            } finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
        }
        if ($restartExitCode -ne 0) {
            $restartSummary = (($restartOutput | Out-String).Trim() -replace '[\r\n]+', ' ')
            Write-Evidence "$(Get-Date -Format o) | Railway restart failed exit=$restartExitCode detail=$restartSummary"
            Set-Gate 'G12' 'NOT_EVALUATED' "Railway restart failed (exit $restartExitCode)"
            Set-Gate 'G13' 'NOT_EVALUATED' "Railway restart failed (exit $restartExitCode)"
        } else {
            if (-not $ManualRestart) { Start-Sleep -Seconds 45 }
            $live2 = Invoke-PilotApi -Path '/health/live' -ExpectStatus @(200)
            if (-not $flow.Ok) {
                Set-Gate 'G12' 'NOT_EVALUATED' 'GRDI main flow failed'
                Set-Gate 'G13' 'NOT_EVALUATED' 'GRDI main flow failed'
            } else {
                if (-not $outcomeId) {
                    Set-Gate 'G12' 'FAIL' 'outcome no fue creado antes del lifecycle'
                } else {
                    $outcomeGet = Invoke-PilotApi -Path "/v4/grdi/outcomes/$outcomeId" -Headers (New-Headers -ApiKey $VerifierKey -TenantId $TenantA -ProjectId $Project -Subject 'outcome-viewer' -Role 'verifier') -ExpectStatus @(200)
                    $persistedOutcomeId = if ($outcomeGet.Ok -and $outcomeGet.Json -and $null -ne $outcomeGet.Json.PSObject.Properties['outcome_id']) { $outcomeGet.Json.outcome_id } else { $null }
                    $persistedOutcomeState = if ($outcomeGet.Ok -and $outcomeGet.Json -and $null -ne $outcomeGet.Json.PSObject.Properties['outcome_state']) { $outcomeGet.Json.outcome_state } else { $null }
                    if ($live2.Ok -and $outcomeGet.Ok -and $persistedOutcomeId -eq $outcomeId) {
                        Set-Gate 'G12' 'PASS' "Outcome Ledger persisted across service lifecycle; outcome_id=$persistedOutcomeId state=$persistedOutcomeState"
                    } else {
                        Set-Gate 'G12' 'FAIL' "post-lifecycle live=$($live2.Status) outcome=$($outcomeGet.Status)"
                    }
                }

                if ($replayId) {
                    $getReplay = Invoke-PilotApi -Path "/v4/grdi/replays/$replayId" -Headers (New-Headers -ApiKey $VerifierKey -TenantId $TenantA -ProjectId $Project -Subject 'viewer' -Role 'verifier') -ExpectStatus @(200)

                    if ($getReplay.Ok) {
                        $replayJson = $getReplay.Json
                        $replayIdMatch = $null -ne $replayJson -and $null -ne $replayJson.PSObject.Properties['replay_id'] -and [string]$replayJson.replay_id -eq $replayId
                        $executionState = if ($null -ne $replayJson -and $null -ne $replayJson.PSObject.Properties['execution_state']) { [string]$replayJson.execution_state } else { $null }

                        if ($replayIdMatch -and $executionState -eq 'NOT_EXECUTED') {
                            Set-Gate 'G13' 'PASS' 'replay persisted and semantically valid; execution_state NOT_EXECUTED'
                        } else {
                            Set-Gate 'G13' 'FAIL' "replay persisted but did not satisfy valid replay contract: replay_id_match=$replayIdMatch execution_state=$executionState"
                        }
                    } elseif ($getReplay.Status -eq 409) {
                        $replayDetail = $null
                        $replayReason = $null
                        $replayCode = $null
                        $replayStatus = $null

                        if ($null -ne $getReplay.Json) {
                            $replayDetail = if ($null -ne $getReplay.Json.PSObject.Properties['detail']) { [string]$getReplay.Json.detail } else { $null }
                            $replayReason = if ($null -ne $getReplay.Json.PSObject.Properties['reason']) { [string]$getReplay.Json.reason } else { $null }
                            $replayCode = if ($null -ne $getReplay.Json.PSObject.Properties['code']) { [string]$getReplay.Json.code } else { $null }
                            $replayStatus = if ($null -ne $getReplay.Json.PSObject.Properties['status']) { [string]$getReplay.Json.status } else { $null }
                        }

                        if (-not $replayDetail -and $null -ne $getReplay.Json -and $null -ne $getReplay.Json.PSObject.Properties['error']) {
                            $replayDetail = [string]$getReplay.Json.error
                        }
                        if (-not $replayReason -and $null -ne $getReplay.Json -and $null -ne $getReplay.Json.PSObject.Properties['message']) {
                            $replayReason = [string]$getReplay.Json.message
                        }

                        if ($replayDetail -and $replayDetail.StartsWith('replay_source_drift:')) {
                            Write-Evidence "$(Get-Date -Format o) | replay GET HTTP 409 detail=$replayDetail"
                            Set-Gate 'G13' 'PASS' 'replay persisted; source drift detected by fail-closed revalidation'
                        } else {
                            Write-Evidence "$(Get-Date -Format o) | replay GET failed HTTP $($getReplay.Status) code=$replayCode reason=$replayReason detail=$replayDetail status=$replayStatus"
                            Set-Gate 'G13' 'FAIL' "GET replay HTTP $($getReplay.Status) code=$replayCode reason=$replayReason detail=$replayDetail status=$replayStatus"
                        }
                    } elseif ($getReplay.Status -eq 404) {
                        Set-Gate 'G13' 'FAIL' 'replay not found after service lifecycle'
                    } else {
                        $replayDetail = $null
                        $replayReason = $null
                        $replayCode = $null
                        $replayStatus = $null

                        if ($null -ne $getReplay.Json) {
                            $replayDetail = if ($null -ne $getReplay.Json.PSObject.Properties['detail']) { [string]$getReplay.Json.detail } else { $null }
                            $replayReason = if ($null -ne $getReplay.Json.PSObject.Properties['reason']) { [string]$getReplay.Json.reason } else { $null }
                            $replayCode = if ($null -ne $getReplay.Json.PSObject.Properties['code']) { [string]$getReplay.Json.code } else { $null }
                            $replayStatus = if ($null -ne $getReplay.Json.PSObject.Properties['status']) { [string]$getReplay.Json.status } else { $null }
                        }

                        if (-not $replayDetail -and $null -ne $getReplay.Json -and $null -ne $getReplay.Json.PSObject.Properties['error']) {
                            $replayDetail = [string]$getReplay.Json.error
                        }
                        if (-not $replayReason -and $null -ne $getReplay.Json -and $null -ne $getReplay.Json.PSObject.Properties['message']) {
                            $replayReason = [string]$getReplay.Json.message
                        }

                        Write-Evidence "$(Get-Date -Format o) | replay GET failed HTTP $($getReplay.Status) code=$replayCode reason=$replayReason detail=$replayDetail status=$replayStatus"
                        Set-Gate 'G13' 'FAIL' "GET replay HTTP $($getReplay.Status) code=$replayCode reason=$replayReason detail=$replayDetail status=$replayStatus"
                    }
                } else {
                    Set-Gate 'G13' 'FAIL' 'replay report not created'
                }
            }
        }
    }

    Set-Gate 'G14' 'NOT_EVALUATED' 'backup/restore runbook manual gate'

    # G8 - CI evidence artifact (stdout only, redacted)
    Set-Gate 'G8b' 'PASS' 'block2 script emitted redacted gate report for CI capture'

} finally {
    Remove-Item Env:PHIGRAPH_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:PHIGRAPH_API_KEY_PROPOSER -ErrorAction SilentlyContinue
    Remove-Item Env:PHIGRAPH_API_KEY_VERIFIER -ErrorAction SilentlyContinue
    Remove-Item Env:PHIGRAPH_API_KEY_TENANT_B -ErrorAction SilentlyContinue
    Remove-Item Env:PHIGRAPH_API_KEY_ADMIN -ErrorAction SilentlyContinue
    $ProposerKey = $null
    $VerifierKey = $null
    $TenantBKey = $null
    $AdminKey = $null
}

Write-Host "`n== GATE REPORT (block 2) ==" -ForegroundColor Cyan
$failCount = 0
foreach ($entry in $GateResults.GetEnumerator()) {
    $color = switch ($entry.Value.Status) {
        'PASS' { 'Green' }
        'FAIL' { 'Red'; $failCount++ }
        default { 'DarkYellow' }
    }
    $note = if ($entry.Value.Note) { " - $($entry.Value.Note)" } else { '' }
    Write-Host ("{0}: {1}{2}" -f $entry.Key, $entry.Value.Status, $note) -ForegroundColor $color
}

Write-Host "`n== REDACTED EVIDENCE ==" -ForegroundColor DarkGray
$EvidenceLog | ForEach-Object { Write-Host $_ }

Write-Host "`n== SECURITY RECLASSIFICATION ==" -ForegroundColor Cyan
Write-Host 'Headers no confiables ignorados: ' -NoNewline; Write-Host $GateResults['G6b'].Status -ForegroundColor Green
Write-Host 'Self-authorization bloqueada: ' -NoNewline; Write-Host $GateResults['G10s'].Status -ForegroundColor Green
Write-Host 'Aislamiento entre identidades autenticadas: ' -NoNewline; Write-Host $GateResults['G7b'].Status -ForegroundColor DarkYellow
Write-Host 'Autorizacion por autoridad separada: ' -NoNewline; Write-Host $GateResults['G10'].Status -ForegroundColor DarkYellow

if ($failCount -gt 0) {
    Write-Host "`nBLOCK 2: FAIL ($failCount gates failed). Pilot NOT stable." -ForegroundColor Red
    exit 1
}

$notEval = @($GateResults.Values | Where-Object { $_.Status -eq 'NOT_EVALUATED' }).Count
Write-Host "`nBLOCK 2: PASS (functional gates). NOT_EVALUATED=$notEval. Pilot NOT declared production-ready." -ForegroundColor Green
exit 0
