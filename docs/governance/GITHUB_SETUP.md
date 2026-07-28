# GitHub Setup

## Repository

Recommended name: `wcalmels/phigraph`.

Create it as **private**, without initializing README, license or `.gitignore`, because those files are included in this package.

## PowerShell bootstrap

```powershell
cd "C:\Users\wcalm\OneDrive\Escritorio\phigraph"
git init
git branch -M main
git add .
git commit -m "release: prepare TUCH PhiGraph Core v4.0.0"
gh repo create wcalmels/phigraph --private --source=. --remote=origin --push
```

## Recommended repository settings

- Protect `main`.
- Require pull requests.
- Require `CI / test` and `CodeQL` checks.
- Block force pushes and branch deletion.
- Enable secret scanning and push protection when available.
- Enable private vulnerability reporting.
- Restrict Actions to trusted actions.

## Release

After staging validation and licensing approval:

```powershell
git tag -a v4.0.0 -m "TUCH PhiGraph Core v4.0.0"
git push origin v4.0.0
```

The release workflow builds source artifacts and attaches checksums to a draft GitHub Release.
