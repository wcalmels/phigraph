# Rebuild PhiGraph paper artifacts for Zenodo (PDF + DOCX).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot

Write-Host "Building PDF..."
pdflatex -interaction=nonstopmode main.tex | Out-Null
bibtex main | Out-Null
pdflatex -interaction=nonstopmode main.tex | Out-Null
pdflatex -interaction=nonstopmode main.tex | Out-Null

Write-Host "Building DOCX (pandoc; figures remain PDF-only)..."
pandoc main.tex -o main.docx --bibliography=references.bib --citeproc --standalone

Write-Host "Done: main.pdf, main.docx"
if (Test-Path "$PSScriptRoot/zenodo") {
  Copy-Item "$PSScriptRoot/main.pdf" "$PSScriptRoot/zenodo/PhiGraph_Paper_v2_draft.pdf" -Force
  Copy-Item "$PSScriptRoot/main.docx" "$PSScriptRoot/zenodo/PhiGraph_Paper_v2_draft.docx" -Force
  Copy-Item "$PSScriptRoot/main.tex" "$PSScriptRoot/zenodo/" -Force
  Copy-Item "$PSScriptRoot/references.bib" "$PSScriptRoot/zenodo/" -Force
  Copy-Item "$PSScriptRoot/LICENSE.md" "$PSScriptRoot/zenodo/" -Force
  Write-Host "Synced paper/zenodo/ publish folder"
}
Pop-Location
