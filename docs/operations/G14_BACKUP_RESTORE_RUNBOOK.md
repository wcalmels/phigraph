# G14 — Isolated PostgreSQL Backup/Restore Runbook

Status: **local/CI implementation authorized**  
Railway live drill: **not authorized** unless explicitly approved  
Stable deployment baseline: `fc20fb8` / Railway `ea510837`

## Purpose

G14 validates that a PostgreSQL custom-format backup of the PhiGraph pilot schema can be:

1. Created only when G4 schema governance is `COMPATIBLE`.
2. Checksum-verified via SHA-256 manifest.
3. Restored into an **isolated ephemeral database** (never production).
4. Re-verified post-restore without breaking shadow invariants.

SHA-256 proves **integrity**, not cryptographic authenticity.

## Tools

| Tool | Purpose |
|------|---------|
| `scripts/g14_backup_restore.py` | Core Python entrypoint (testable) |
| `scripts/deploy/railway_g14_backup_restore.ps1` | Operator wrapper (redacted output) |
| `docs/operations/examples/g14_backup_manifest.example.json` | Manifest shape reference (`placeholder=true`) |

Required binaries: `pg_dump`, `pg_restore`, Python package `psycopg`.

## Environment variables

| Variable | Required | Notes |
|----------|----------|-------|
| `PHIGRAPH_POSTGRES_DSN` | Yes (backup/restore source) | Never log or commit |
| `PHIGRAPH_G14_RESTORE_DSN` | Yes (full drill) | Admin connection on same server, different database target; must not be production |
| `PHIGRAPH_G14_PRODUCTION_IDENTITY_HASH` | Optional guard | If set, restore targets matching this hash are rejected |

## Hard guards

- Source DSN and restore DSN **must differ**.
- Restore requires `-ConfirmIsolatedRestore G14-ISOLATED-RESTORE`.
- Restore targets whose host matches `*.railway.app` / `*.up.railway.app` are rejected.
- Ephemeral databases must match `phigraph_g14_<8 hex chars>`.
- Only exact ephemeral database names may be dropped during cleanup.
- Corrupted dump/manifest/checksum → non-zero exit (fail-closed).
- Never print secrets, DSNs, dump bytes, or clipboard transcripts.

## Workflow

### 1. Preflight (no secret values printed)

```powershell
cd C:\Users\wcalm\OneDrive\Escritorio\book_agent\PhiGraph
$env:PHIGRAPH_POSTGRES_DSN = '<source-dsn>'
py -3 scripts/g14_backup_restore.py backup --artifact-dir .\output\g14 --output .\output\g14\report-backup.json --force-output
```

Preflight checks:

- Tools present (`pg_dump`, `pg_restore`, `psycopg`).
- G4 governance `state=COMPATIBLE` and `catalog_valid=true` **before** backup.
- Migration fingerprint unchanged **after** backup.

Artifacts (gitignored):

- `output/g14/g14_<run_id>.dump`
- `output/g14/g14_<run_id>.manifest.json`

### 2. Manifest verification (G14b/G14f)

```powershell
py -3 scripts/g14_backup_restore.py verify-manifest `
  --manifest .\output\g14\g14_<run_id>.manifest.json `
  --output .\output\g14\report-verify.json --force-output
```

Corruption drill:

```powershell
# After tampering backup_sha256 or truncating dump:
py -3 scripts/g14_backup_restore.py verify-manifest `
  --manifest .\output\g14\g14_<run_id>.manifest.json `
  --expect-corruption-rejection
```

Expected: non-zero exit, gate `G14f=PASS` in report when using `--expect-corruption-rejection`.

### 3. Isolated restore drill (G14c–G14e)

```powershell
$env:PHIGRAPH_G14_RESTORE_DSN = '<admin-dsn-to-postgres-db>'
py -3 scripts/g14_backup_restore.py full-drill `
  --artifact-dir .\output\g14 `
  --restore-dsn $env:PHIGRAPH_G14_RESTORE_DSN `
  --confirm-isolated-restore G14-ISOLATED-RESTORE `
  --output .\output\g14\report-full-drill.json --force-output
```

Post-restore checks:

- G4 `COMPATIBLE` on restored database.
- Inventory fingerprint matches manifest snapshot.
- Collection counts and migration registry readable.
- Shadow invariants: gateway decisions remain `NOT_EXECUTED` / `SHADOW_SIMULATION` when present.

Cleanup: ephemeral database `phigraph_g14_<run_id>` dropped automatically.

### 4. PowerShell wrapper

```powershell
.\scripts\deploy\railway_g14_backup_restore.ps1 -BackupOnly -ArtifactDir .\output\g14
.\scripts\deploy\railway_g14_backup_restore.ps1 -VerifyManifest -ManifestPath .\output\g14\g14_<run_id>.manifest.json
.\scripts\deploy\railway_g14_backup_restore.ps1 -FullDrill -ArtifactDir .\output\g14 -ConfirmIsolatedRestore G14-ISOLATED-RESTORE
```

For Railway production keys, prefer `railway run` env injection or `Read-Host -AsSecureString`. Copy from Railway Variables UI only when necessary.

## Gate map

| Gate | Meaning |
|------|---------|
| G14a | Backup valid, non-empty, custom format |
| G14b | SHA-256 + manifest coherence |
| G14c | Restore target isolated and confirmed |
| G14d | Restored schema `COMPATIBLE` |
| G14e | Inventory + shadow invariants |
| G14f | Corruption rejected fail-closed |
| G14g | Redacted evidence + safe cleanup |

## Recovery notes

- Forward-only migrations: rollback is **restore-to-new-database**, not SQL downgrade.
- Production recovery requires a **new** authorized drill; do not restore over `phigraph-api` Postgres in place without explicit approval.
- Keep manifests and dumps outside Git (`output/g14/`, `backups/`).

## Railway live drill (future, not authorized)

When approved:

1. Disconnect GitHub source (if autodeploy risk exists).
2. Run backup against Railway Postgres using `railway run` env injection.
3. Restore only to isolated non-Railway or ephemeral CI database.
4. Attach redacted report to change record.

Until then: **local/CI only**.

## Limitations

- Integrity checksum only; no signing/HMAC yet.
- Inventory fingerprint is logical content hash, not row-level cryptographic proof.
- G12/G13 restart gates remain historical; not part of G14 closure.
