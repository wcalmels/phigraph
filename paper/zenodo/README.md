# Zenodo publication folder (v2 draft)

Ready-to-upload artifacts for a **new version** of [10.5281/zenodo.21689514](https://doi.org/10.5281/zenodo.21689514).

## Files

| File | Use |
|------|-----|
| `PhiGraph_Paper_v2_draft.pdf` | **Primary** publication (all TikZ figures, incl. Fig. 6 scoped transaction) |
| `PhiGraph_Paper_v2_draft.docx` | Accessible text export (figures PDF-only) |
| `main.tex` | LaTeX source |
| `references.bib` | Bibliography |
| `LICENSE.md` | CC BY 4.0 |
| `zenodo_metadata.json` | Metadata helper (v2 title, keywords, git pin `a5a7187`) |

## What changed in this draft

- **§4.3** Transactional scoped ledger (Core 4.1.0-rc.6) + **Figure 6**
- **Figure 7** Chain-linked GRDI vs mutable Core collections
- **§4.6** GRDI shadow decision chain (GRDI 0.4.0) + **Figure 8**
- **§5.4** Transactional ledger integrity (57 contract tests)
- **§5.5** GRDI replay audit scenarios
- Software verification updated to **319 tests** (`main@a5a7187`)

## Rebuild

From repository root:

```powershell
powershell -ExecutionPolicy Bypass -File paper/build.ps1
Copy-Item paper/main.pdf paper/zenodo/PhiGraph_Paper_v2_draft.pdf -Force
Copy-Item paper/main.docx paper/zenodo/PhiGraph_Paper_v2_draft.docx -Force
```

## Upload checklist

1. Open Zenodo → existing record → **New version**
2. Upload files from this folder
3. Paste title/description/keywords from `zenodo_metadata.json` (or upload the JSON as supplementary)
4. Publish version → update root `README.md` / `CITATION.cff` if metadata changes
