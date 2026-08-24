# G14 — Isolated PostgreSQL Backup/Restore Runbook

Status: **local/CI implementation authorized**
Railway live drill: **paused / not executed** — waiting for an authorized interactive operator after the explicit-target runner is reviewed. Do not treat this document as G14 PASS.
Railway deployed baseline: `e805f96` / Railway `f1dd97c9` (commit currently running in `phigraph-api`)
Windows runner commit: any **clean descendant** of that baseline (the runner SHA changes with each fix; do not pin `HEAD` to the runner commit)

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
| `scripts/deploy/railway_g14_live_runner.ps1` | Windows-safe Railway live drill launcher (`-File` only) |
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
- Restore targets must be on the **positive allowlist**: `localhost`, `127.0.0.1`, `::1`, `postgres`, plus optional `PHIGRAPH_G14_ALLOWED_RESTORE_HOSTS`.
- Restore requires `-ConfirmIsolatedRestore G14-ISOLATED-RESTORE`.
- Ephemeral databases must match `phigraph_g14_<8 hex chars>`.
- Only exact ephemeral database names may be dropped during cleanup.
- Corrupted dump/manifest/checksum → non-zero exit (fail-closed).
- Never print secrets, DSNs, dump bytes, or clipboard transcripts.
- `pg_dump` / `pg_restore` use libpq env vars only (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`, `PGSSLMODE`); DSNs never appear in process argv.
- Manifest stores `backup_filename` (for example `g14_<run_id>.dump`) relative to the manifest directory; filename, manifest name, and `run_id` must match.
- Existing dump/manifest for the same `run_id` is rejected (collision guard).

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

## Windows Railway live drill

Use a **normal interactive PowerShell window**, not an agent, Cursor task, or nested `-Command` string. Nested `powershell -Command`, `python -c`, and `cmd /c` quoting is forbidden: it dropped DSN quotes on Windows and failed before `pg_dump`.

Railway baseline (`ExpectedBaselineCommit`): `e805f969421fc0392632365df998d0a248fc9d97`.
The live runner must run from a **clean** worktree whose `HEAD` **descends from** that baseline (`git merge-base --is-ancestor`). The runner's own commit is not the Railway deployment pin.

The runner selects Railway with internal fail-closed constants and CLI flags (`--project`, `--environment production`, `--service Postgres`) placed before `--`. A linked local Railway directory or `.railway` folder is neither required nor used. Do not associate this worktree with Railway, and do not pass project, environment, or service parameters to the runner.

```powershell
cd C:\Users\wcalm\phigraph-g14-e805f96
.\scripts\deploy\railway_g14_live_runner.ps1
```

Operator flow:

1. Confirm Railway freeze (no `phigraph-api` source, no unplanned deploy).
2. Enable the Postgres TCP Proxy **manually** in Railway only for the duration of the drill.
3. Run `railway_g14_live_runner.ps1` in interactive PowerShell. It prompts for the **local** PostgreSQL password via `Read-Host -AsSecureString`, then re-invokes itself with:
   `railway run --project <phigraph-private-pilot-id> --environment production --service Postgres -- powershell -NoProfile -ExecutionPolicy Bypass -File <this-script> -InsideRailwayEnvironment`
4. Restore target is local only: `127.0.0.1:5432` ephemeral `phigraph_g14_<8hex>`.
5. **Always remove the TCP Proxy after the drill, including on failure**: Postgres → Settings → Networking → delete `:5432` → Deploy Changes. Confirm `DATABASE_PUBLIC_URL` is gone.
6. Do not start a second drill until the proxy is absent and health/live plus ready remain HTTP 200.

The runner fail-closes without an interactive console, without `DATABASE_PUBLIC_URL` in the child, if restore host is not `localhost` / `127.0.0.1` / `::1`, if the password is empty, if source equals restore, if `pg_dump`/`pg_restore` are missing, if the worktree is dirty, or if `HEAD` does not descend from the Railway baseline.

Do not pass DSNs on argv. Do not copy secrets to clipboard, transcript, or files. Until this runner is used by an authorized operator: **local/CI only**.

## Limitations

- Integrity checksum only; no signing/HMAC yet.
- Inventory fingerprint is logical content hash, not row-level cryptographic proof.
- G12/G13 restart gates remain historical; not part of G14 closure.
