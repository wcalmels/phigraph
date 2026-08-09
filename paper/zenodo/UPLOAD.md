# Zenodo v2 upload

**Record:** [10.5281/zenodo.21689514](https://doi.org/10.5281/zenodo.21689514)  
**Concept DOI:** [10.5281/zenodo.21689513](https://doi.org/10.5281/zenodo.21689513)

## Option A — API (recommended)

1. Create a personal access token at [Zenodo → Applications](https://zenodo.org/account/settings/applications/new/) with scopes `deposit:write` and `deposit:actions`.
2. Rebuild artifacts if needed:

```powershell
powershell -ExecutionPolicy Bypass -File paper/build.ps1
```

3. Upload (draft only):

```powershell
$env:ZENODO_ACCESS_TOKEN = "YOUR_TOKEN"
py -3 scripts/upload_zenodo_paper_v2.py
```

4. Review the draft URL printed by the script, then publish:

```powershell
py -3 scripts/upload_zenodo_paper_v2.py --publish
```

## Option B — Web UI

1. Open [Zenodo record 21689514](https://zenodo.org/records/21689514).
2. Click **New version** (must be logged in as owner).
3. Remove the v1 PDF and upload all files from this folder.
4. Set **Preview** to `PhiGraph_Paper_v2_draft.pdf`.
5. Paste title, description, and keywords from `zenodo_metadata.json`.
6. **Publish** the new version.

## After publish

- Note the **new version DOI** (concept DOI stays `10.5281/zenodo.21689513`).
- Update `CITATION.cff` and root `README.md` with the v2 title and version DOI.
