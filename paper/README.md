# PhiGraph Scientific Paper

## Versions

| Version | Branch / commit | Zenodo | Scope |
|---------|-----------------|--------|-------|
| **v1** | `docs/scientific-paper-zenodo@9c891d3` | [10.5281/zenodo.21689514](https://doi.org/10.5281/zenodo.21689514) | Core 4.0.0, HAV v0.2, 5 TikZ figures |
| **v2 (in progress)** | `docs/paper-v2` on `main@a5a7187` | TBD (new version of same DOI) | Core 4.1.0-rc.6, GRDI 0.4.0, transactional ledger |

**Planning doc:** [`PAPER_V2_OUTLINE.md`](PAPER_V2_OUTLINE.md) — section map, figures, allowed claims, Zenodo workflow.

---

## v1 reference (published)

**Title:** PhiGraph Core 4.0: A Shadow-First Evidence Ledger and Policy-Gated Runtime for Software-Agent Operations

**Author:** Walter Calmels von Dem Knesebeck  
**Affiliation:** TUCH Systems  
**Contact:** wcalmels@phi47.cl  
**Paper license:** CC BY 4.0

v1 includes Section 4.5 (HAV v0.2), Section 5.3 (HAV scenarios), and five vector figures (TikZ/pgfplots, no external images):

1. Architecture diagram (agent → protocol → core service → deployment boundary).
2. Protocol lifecycle (Claim / Evidence / Verification / ActionProposal / PolicyDecision / Outcome).
3. HAV v0.2 verification pipeline.
4. HAV fail-closed policy flowchart.
5. CIC-IDS2017 PR-AUC / P@10% bar chart.

All figures use `\begin{figure}[H]` so they stay with the introducing paragraph.

---

## Build

From this directory:

```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

Output: `main.pdf`.

On Windows with MiKTeX/TeX Live installed, the same commands apply from PowerShell.

### DOCX export (Zenodo supplementary)

Pandoc converts prose and bibliography; **TikZ figures appear only in the PDF**:

```powershell
pandoc main.tex -o main.docx --bibliography=references.bib --citeproc --standalone
```

Or run `.\build.ps1` to rebuild PDF and DOCX together.

### Zenodo deposit files

Upload at minimum:

| File | Role |
|------|------|
| `main.pdf` | Primary publication (vector figures) |
| `main.docx` | Accessible text export |
| `main.tex` | Reproducible LaTeX source |
| `references.bib` | Bibliography source |
| `LICENSE.md` | Paper license (CC BY 4.0) |

Metadata draft: `zenodo_metadata.json` (v2 update pending).

### Zenodo upload folder

Ready-to-publish copies: [`zenodo/`](zenodo/) (`PhiGraph_Paper_v2_draft.pdf`, `.docx`, source, license).

---

## v2 workflow (draft)

1. Follow [`PAPER_V2_OUTLINE.md`](PAPER_V2_OUTLINE.md) section order.
2. Run the full test suite from the repository root on the pinned commit.
3. Build the paper and inspect figures and tables visually.
4. Confirm every metric in the PDF matches CI / release notes.
5. Update `zenodo_metadata.json` and publish a **new version** on Zenodo (linked to v1 DOI).
6. Update `CITATION.cff` and root `README.md` with the new version metadata.
7. Tag the repository (e.g. `paper-v2.0`).

Do not claim state-of-the-art anomaly performance. Do not claim production PostgreSQL transactional semantics until implemented.

`zenodo_metadata.json` is an API-style helper; uploading it does not auto-fill the Zenodo web form.
