param(
    [string]$Repository = "wcalmels/phigraph",
    [switch]$Public
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git no está instalado o no está disponible en PATH."
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) no está instalado o no está disponible en PATH."
}

python .\scripts\publication_audit.py
python -m compileall -q src tests
$env:PYTHONPATH = "src"
python -m pytest -q
Remove-Item Env:\PYTHONPATH

if (-not (Test-Path .git)) {
    git init
}
git branch -M main
git add .
git commit -m "release: prepare TUCH PhiGraph Core v4.0.0"

$visibility = if ($Public) { "--public" } else { "--private" }
gh repo create $Repository $visibility --source=. --remote=origin --push

Write-Host "Repositorio creado: https://github.com/$Repository"
Write-Host "Manténgalo privado hasta aprobar docs/governance/PUBLICATION_CHECKLIST.md"
