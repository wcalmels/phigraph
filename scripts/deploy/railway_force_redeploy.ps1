#Requires -Version 5.1
<#
Force a fresh GitHub deploy of phigraph-api from the linked branch.

Before running:
  1. railway logout (optional) then set RAILWAY_API_TOKEN without leading spaces
  2. railway link  -> phigraph-private-pilot / production
  3. In Railway UI: phigraph-api -> Settings -> Deploy -> clear Pre-deploy command
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

railway whoami | Out-Null
Write-Host "Redeploying phigraph-api from latest GitHub commit..." -ForegroundColor Cyan
railway redeploy --service phigraph-api --from-source --yes
Write-Host "Watch: railway logs --service phigraph-api" -ForegroundColor Green
