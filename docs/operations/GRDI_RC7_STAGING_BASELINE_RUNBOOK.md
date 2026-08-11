# GRDI RC7 Staging Baseline Runbook

Construir una base PostgreSQL **realmente RC7** para ejercicios de cutover RC7→RC8 en staging.

**Estado explícito:** `STAGING = NOT_PROVISIONED` hasta que un operador ejecute estos pasos en un VPS.  
**No arrancar RC8 primero:** el código RC8 aplicaría migración `002` automáticamente vía `bootstrap_postgres_scoped_schema` / `EvidenceLedger.ensure_postgres_scoped_migrations`.

| Baseline RC7 | Target RC8 |
|--------------|------------|
| `main@44ba1cc08ee007183822b629f37ce00fd6a56db8` | `main@d309c6f0d692752f2f54b912b764d71fb9de2e18` |
| Core `4.1.0-rc.7` | Core `4.1.0-rc.8` |
| Migración PostgreSQL `001_scoped_ledger_v1` solamente | Migraciones `001` → `002` |
| Datos legacy en `phigraph_core_ledger` | Cutover tooling `grdi_rc8_cutover.py` v1.2.0 |

---

## 1. Objetivo

1. Fijar código RC7 sin mover `main` local hacia atrás.
2. Aplicar **solo** migración `001`.
3. Confirmar ausencia de `002_gateway_decision_events`.
4. Cargar fixtures sintéticos representativos (cero PII / producción).
5. Verificar cadenas RC7 (pre-cutover: filas legacy, `phigraph_scoped_ledger` vacío).
6. Detener escrituras, generar backup verificable y manifiesto.

---

## 2. Precondiciones

- VPS staging aprovisionado según `GRDI_RC8_STAGING_PROVISIONING_RUNBOOK.md`.
- PostgreSQL 16 accesible vía red Docker interna o túnel SSH (`127.0.0.1` en el VPS).
- `PHIGRAPH_POSTGRES_DSN` solo en sesión del operador.
- `PHIGRAPH_ENVIRONMENT=staging`, `PHIGRAPH_RECEIPT_SIGNING_KEY` configurados.
- **No** usar datos de producción ni credenciales reales en el repositorio.

---

## 3. Fijar código RC7 (worktree detached)

No hacer `git checkout main` a `44ba1cc` en el worktree principal de operaciones RC8.

```bash
export REPO=/opt/phigraph   # placeholder VPS path
export RC7_SHA=44ba1cc08ee007183822b629f37ce00fd6a56db8
export RC7_WORKTREE=${REPO}/../phigraph-rc7-baseline

git -C "$REPO" worktree add --detach "$RC7_WORKTREE" "$RC7_SHA"
cd "$RC7_WORKTREE"
git rev-parse HEAD   # must print RC7_SHA
```

Conservar el worktree hasta completar backup; eliminar solo tras evidencia archivada.

---

## 4. Imagen / entorno RC7

Opción A — Python editable en el VPS (recomendado para baseline):

```bash
cd "$RC7_WORKTREE"
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[postgres,api]"
```

Opción B — Imagen Docker etiquetada por SHA (reproducible):

```bash
docker build -t phigraph:rc7-${RC7_SHA:0:7} "$RC7_WORKTREE"
```

Registrar la etiqueta en el manifiesto de entorno (`docs/operations/examples/grdi_rc8_staging_environment.example.json` → copia operativa).

---

## 5. Bootstrap schema RC7 (solo migración 001)

**Crítico:** en RC7, `ORDERED_POSTGRES_MIGRATIONS` contiene únicamente `001`. En RC8 existiría también `002`.

Desde el worktree RC7:

```bash
export PHIGRAPH_POSTGRES_DSN='postgresql://USER:***@127.0.0.1:5432/DBNAME'
python3.12 - <<'PY'
import os
import psycopg
from phigraph.core_v3.postgres_migrations import apply_postgres_migrations, ensure_legacy_core_ledger_table

dsn = os.environ["PHIGRAPH_POSTGRES_DSN"]
with psycopg.connect(dsn) as conn:
    applied = apply_postgres_migrations(conn)
    ensure_legacy_core_ledger_table(conn)
    conn.commit()
    print("applied:", applied)
PY
```

Verificar:

```bash
psql "$PHIGRAPH_POSTGRES_DSN" -c "SELECT version FROM phigraph_schema_migrations ORDER BY version;"
# Expected single row: 001_scoped_ledger_v1

psql "$PHIGRAPH_POSTGRES_DSN" -c "
SELECT pg_get_expr(idx.indpred, idx.indrelid)
FROM pg_class rel
JOIN pg_index idx ON idx.indrelid = rel.oid
JOIN pg_class ic ON ic.oid = idx.indexrelid
WHERE rel.relname = 'phigraph_scoped_ledger'
  AND ic.relname = 'uq_scoped_chain_sequence_linked';"
# Expected: predicate WITHOUT gateway_decision_events (002 not applied)

psql "$PHIGRAPH_POSTGRES_DSN" -c "
SELECT COUNT(*) FROM phigraph_scoped_ledger
WHERE collection = 'gateway_decision_events';"
# Expected: 0
```

Confirmar que `phigraph_scoped_ledger` existe pero está vacío antes de fixtures:

```bash
psql "$PHIGRAPH_POSTGRES_DSN" -c "SELECT COUNT(*) FROM phigraph_scoped_ledger;"
```

---

## 6. Fixtures sintéticos RC7

Usar el script operativo (inserta filas legacy vía psycopg; **no** construye `EvidenceLedger` ni `CoreV3Service`):

Desde checkout RC8 (`d309c6f`) con baseline schema 001 + `phigraph_core_ledger` ya creado:

```bash
export PHIGRAPH_ENVIRONMENT=staging
export PHIGRAPH_RECEIPT_SIGNING_KEY='REPLACE_WITH_STAGING_KEY'
export PHIGRAPH_POSTGRES_DSN='postgresql://...'

python3.12 scripts/create_grdi_rc7_staging_fixture.py --confirm-fixture GRDI-RC7-STAGING
```

Casos mínimos insertados (legacy `phigraph_core_ledger`):

| Tenant | Project | Caso |
|--------|---------|------|
| `tenant-a` | `project-a` | Plan autorizado, **no** simulado |
| `tenant-a` | `project-b` | Plan simulado con receipt verificable |
| `tenant-b` | `project-a` | Plan `simulation_state=SIMULATED` **sin** receipt |
| `tenant-b` | `project-b` | Plan simulado con receipt (segundo tenant) |

El script es idempotente por **fallo explícito** si el marcador `requested_by=grdi-rc7-staging-fixture` ya existe.

Registrar salida JSON (conteos + `inventory_fingerprint`) en el directorio de evidencia.

---

## 7. Verificación RC7 pre-cutover

```bash
psql "$PHIGRAPH_POSTGRES_DSN" -c "
SELECT tenant_id, project_id, collection, COUNT(*) 
FROM phigraph_core_ledger 
GROUP BY 1,2,3 ORDER BY 1,2,3;"

psql "$PHIGRAPH_POSTGRES_DSN" -c "SELECT COUNT(*) FROM phigraph_scoped_ledger;"
# Expected: 0 legacy rows migrated to scoped tables
```

Preflight RC7 con tooling RC8 (solo lectura):

```bash
cd /opt/phigraph   # RC8 checkout d309c6f
py -3.12 scripts/grdi_rc8_cutover.py --check-only --output evidence/rc7_preflight.json
```

Expectativa RC7: `assessment_state=READY_FOR_CUTOVER`, `final_state=NO_GO`, **exit 2**.

---

## 8. Detener escrituras

- No iniciar API RC8 contra esta base antes del backup.
- Detener contenedores que escriban al ledger.
- Mantener PostgreSQL activo para `pg_dump`.

---

## 9. Backup verificable

```bash
export BACKUP_DIR=/var/backups/phigraph-grdi-rc8-staging   # fuera del volumen Docker activo
mkdir -p "$BACKUP_DIR"
TS=$(date -u +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/phigraph_rc7_baseline_${TS}.dump"

pg_dump --format=custom --file "$BACKUP_FILE" --dbname "$PHIGRAPH_POSTGRES_DSN"
pg_restore --list "$BACKUP_FILE"
sha256sum "$BACKUP_FILE"
```

Guardar manifiesto (derivado de `docs/operations/examples/grdi_rc8_cutover_manifest.example.json`, **sin** `placeholder: true`):

- `backup_path`, `backup_sha256`, `backup_created_at`
- `database_identity_hash` (desde `--check-only`, no incluye secretos)
- `migration_versions_before`: `[{"version":"001_scoped_ledger_v1",...}]`
- `collection_counts_before`: conteos legacy
- `source_core_version`: `4.1.0-rc.7`

---

## 10. Snapshot y conservación

- Copiar `.dump` a almacenamiento cifrado o volumen separado.
- Archivar reports JSON y manifiesto en `evidence_directory`.
- Etiquetar snapshot: `rc7-baseline-${TS}`.
- **No** ejecutar `--apply` en este runbook.

---

## 11. Riesgos evitados

| Riesgo | Control |
|--------|---------|
| Auto-upgrade a RC8 (`002`) | Bootstrap solo desde worktree RC7; script fixture rechaza `002` |
| Arrancar API RC8 antes de backup | Runbook detiene escrituras antes de `pg_dump` |
| Datos reales | Fixtures sintéticos + confirmación `--confirm-fixture` |
| Duplicado de seed | Marcador idempotente con fallo explícito |

---

## 12. Rollback de baseline

Si el baseline es inválido: restaurar volumen vacío o recrear DB desde compose y repetir §5–9. No partial-delete en `phigraph_core_ledger` manualmente.

**CUTOVER = NOT_EXECUTED** — ver `GRDI_RC7_TO_RC8_POSTGRES_CUTOVER_RUNBOOK.md` tras upgrade a RC8.
