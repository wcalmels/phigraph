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
Pop-Location
