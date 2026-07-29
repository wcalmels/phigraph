# PhiGraph Scientific Paper

**Title:** PhiGraph Core 4.0: A Shadow-First Evidence Ledger and Policy-Gated Runtime for Software-Agent Operations

**Author:** Walter Calmels von Dem Knesebeck  
**Affiliation:** TUCH Systems  
**Contact:** wcalmels@phi47.cl  
**Paper license:** CC BY 4.0

This revision adds Section 4.5 (HAV v0.2 architecture and fail-closed policy),
Section 5.3 (HAV verification scenarios), an "HAV validity" limitations
paragraph, and the corresponding related-work, keyword, and reproducibility
updates, so the paper covers the HAV v0.2 module integrated into the
repository alongside PhiGraph Core 4.0.0.

It also adds five vector figures generated from TikZ/pgfplots source (no
external image files, fully reproducible from `main.tex`):

1. Architecture diagram (agent -> protocol -> core service -> deployment boundary).
2. Protocol lifecycle diagram (Claim/Evidence/Verification/ActionProposal/PolicyDecision/Outcome).
3. HAV v0.2 verification pipeline (candidate output -> extractor -> verifier -> policy -> ledger).
4. HAV fail-closed policy decision flowchart.
5. CIC-IDS2017 PR-AUC / P@10% bar chart (companion to Table 2).

All figures use `\begin{figure}[H]` (via the `float` package) so they render
immediately after the paragraph that introduces them instead of drifting to
the end of the document.

## Build

From this directory:

```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

The output is `main.pdf`.

## Verification before a Zenodo release

1. Run the complete software test suite from the repository root.
2. Build the paper and inspect the PDF visually.
3. Confirm that all reported metrics match the committed validation artifact.
4. Enter the values from `zenodo_metadata.json` in the Zenodo form, or use the
   file as the metadata payload for the deposit API. Upload `main.pdf`,
   `main.tex`, `references.bib`, and `LICENSE.md` as record files.
5. Reserve or publish the Zenodo DOI.
6. Add the DOI to the paper, `CITATION.cff`, and the repository README.
7. Rebuild the final PDF and publish a versioned repository release.

Do not claim that the CIC-IDS2017 result establishes state-of-the-art
performance. The paper deliberately reports the stronger LOF baseline and the
dataset limitations.

`zenodo_metadata.json` is an API-style helper document; uploading it as a file
does not make the Zenodo web form ingest its values automatically.
