# GRDI RC7 → RC8 PostgreSQL Cutover Runbook (Staging)

Operación forward-only para actualizar una base PostgreSQL RC7 (migración `001` + datos GRDI legacy/scoped) a RC8 (`002` + gateway decision events + cutover GRDI 0.5.0).

**Core objetivo:** `main@e4e0937` — PhiGraph Core `4.1.0-rc.8`, GRDI `0.5.0`.

**Herramienta:** `scripts/grdi_rc8_cutover.py` (preflight / apply / verify).

---

## 1. Propósito y alcance

| Incluido | Excluido |
|----------|----------|
| Bootstrap schema `001 → 002` | Downgrade SQL |
| Migración legacy `phigraph_core_ledger` → scoped | Reparación automática de cadenas (`repair_chain`) |
| Backfill determinista `gateway_decision_events` | Conectores reales / webhooks / ejecución externa |
| Verificación de esquema y cadenas | Inferir simulación sin receipt verificable |
| Inventario y evidencia operativa | Tag/release `4.1.0-rc.8` (posterior a cutover staging) |

---

## 2. Precondiciones

- PostgreSQL accesible desde el operador (≥ 14 recomendado; CI valida 16).
- `PHIGRAPH_POSTGRES_DSN` configurado **solo en la sesión** (nunca en historial ni en manifiestos).
- Código desplegado o checkout en `4.1.0-rc.8` (`e4e0937` o posterior en `main`).
- Ventana de mantenimiento acordada.
- Aplicación GRDI en **modo shadow**; escrituras bloqueadas (ver §6).
- Respaldo lógico verificado (§7–8).
- Operador con acceso a `pg_dump`, Python 3.10+, dependencias `[postgres]` instaladas.

---

## 3. Variables PowerShell seguras

```powershell
# Sesión actual únicamente — no persistir en perfil ni scripts versionados
$env:PHIGRAPH_POSTGRES_DSN = 'postgresql://USER:PASSWORD@HOST:5432/DATABASE'
$env:PHIGRAPH_CUTOVER_ENV = 'staging'
$env:PHIGRAPH_CUTOVER_OPERATOR = $env:USERNAME
$BackupDir = 'D:\backups\phigraph_staging'
$ManifestPath = Join-Path $BackupDir 'grdi_rc8_cutover_manifest.json'
$ReportDir = Join-Path $BackupDir 'reports'
New-Item -ItemType Directory -Force -Path $BackupDir, $ReportDir | Out-Null
```

**Reglas:** no hacer `echo $env:PHIGRAPH_POSTGRES_DSN`; usar `-NoProfile` en scripts; redactar credenciales en tickets.

---

## 4. Revisión de capacidad y versión PostgreSQL

```powershell
psql "$env:PHIGRAPH_POSTGRES_DSN" -c "SELECT version();"
psql "$env:PHIGRAPH_POSTGRES_DSN" -c "SELECT pg_size_pretty(pg_database_size(current_database()));"
psql "$env:PHIGRAPH_POSTGRES_DSN" -c "SHOW max_connections;"
```

Confirmar espacio en disco ≥ 3× tamaño actual de la base para backup + margen.

---

## 5. Ventana de mantenimiento

1. Anunciar inicio (canal ops + stakeholders GRDI).
2. Registrar `started_at` (UTC ISO-8601) en el manifiesto.
3. Ejecutar pasos §7–20 en orden.
4. Registrar `completed_at` y `final_state` al cerrar.

---

## 6. Bloqueo de escrituras de aplicación

- Escalar/desplegar instancias GRDI con tráfico de escritura detenido (solo lecturas administrativas permitidas).
- Confirmar que no hay jobs batch escribiendo al ledger.
- Mantener bloqueo hasta `final_state: GO` o decisión de rollback (§20).

---

## 7. Respaldo obligatorio con pg_dump

```powershell
$Timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupFile = Join-Path $BackupDir "phigraph_staging_$Timestamp.dump"
pg_dump --format=custom --file $BackupFile --dbname $env:PHIGRAPH_POSTGRES_DSN
if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
```

---

## 8. Comprobación del archivo de respaldo

```powershell
$BackupSha = (Get-FileHash -Algorithm SHA256 $BackupFile).Hash.ToLower()
$BackupSize = (Get-Item $BackupFile).Length
if ($BackupSize -le 0) { throw 'backup file is empty' }
"backup_path=$BackupFile size=$BackupSize sha256=$BackupSha"

# Formato custom PostgreSQL obligatorio (pg_dump -Fc, cabecera PGDMP)
pg_restore --list $BackupFile
if ($LASTEXITCODE -ne 0) { throw 'pg_restore --list failed' }
```

Registrar en el manifiesto:

- `backup_path` (ruta absoluta resuelta)
- `backup_sha256`
- `backup_created_at` (UTC ISO-8601)
- `database_identity_hash` (desde `--check-only`, no incluye secretos)

**No usar** `docs/operations/examples/grdi_rc8_cutover_manifest.example.json` directamente: tiene `"placeholder": true` y hashes ficticios.

Antigüedad máxima por defecto: **24 h** (`--backup-max-age-hours`).

---

## 9. Inventario previo

La herramienta `--check-only` recopila (solo lectura):

| Artefacto | Fuente |
|-----------|--------|
| Versiones de migración + checksum | `phigraph_schema_migrations` |
| Conteos por tenant/project/collection | `phigraph_scoped_ledger` |
| Chain heads | `phigraph_chain_heads` |
| Duplicados canonical_key | agregación SQL |
| Legacy core counts | `phigraph_core_ledger` (si existe) |

```powershell
py -3 scripts/grdi_rc8_cutover.py --check-only --output (Join-Path $ReportDir '01_preflight.json')
```

**APIs públicas usadas en inventario/verificación:** `verify_postgres_schema(conn)`, `EvidenceLedger.verify_scoped_chain(...)`, `EvidenceLedger.admin_list_scoped(...)` (solo tras esquema RC8 completo).

---

## 10. Preflight de solo lectura

```powershell
py -3 scripts/grdi_rc8_cutover.py --check-only --output (Join-Path $ReportDir '02_preflight_final.json')
```

Garantías técnicas de `--check-only`:

- Transacción PostgreSQL **`READ ONLY`** (`SET TRANSACTION READ ONLY` en cada conexión de inventario).
- **No** importa ni invoca funciones mutantes (`bootstrap_*`, `cutover_*`, `backfill_*`).
- **No** construye `EvidenceLedger` hasta confirmar RC8 completo (`002` + checksum válido); evita auto-migración del constructor.
- Si RC7 solo tiene `001`, `checks.schema = NOT_EVALUATED` y verificación de cadenas se omite.

Interpretación:

- **Blockers (exit 3):** duplicados canonical, checksum de migración incorrecto.
- **Warnings:** `002` aún no aplicada — **esperado en RC7** antes del bootstrap.
- **`checks.schema: NOT_EVALUATED`** con solo `001` — **esperado** pre-cutover.
- **RC7 sin blockers:** `assessment_state: READY_FOR_CUTOVER`, `final_state: NO_GO`, **exit 2** (entorno listo para cutover, cutover aún no ejecutado).
- **RC8 totalmente verificado:** `assessment_state: VALIDATED`, `final_state: GO`, **exit 0**.
- **`final_state: GO` nunca implica que el cutover ya se completó** salvo en RC8 ya migrado y verificado.

**Filtros diagnósticos:** `--tenant-id`/`--project-id` están permitidos en `--check-only` y `--verify` únicamente. Dejan scopes no evaluados → `NOT_EVALUATED` → `NO_GO` + exit ≠ 0.

---

## 11. Bootstrap 001 → 002

**Mutación.** Ejecutar vía `--apply` (§16) o manualmente:

```powershell
py -3 -c @'
import os
from phigraph.core_v3.postgres_migrations import bootstrap_postgres_scoped_schema
applied = bootstrap_postgres_scoped_schema(os.environ["PHIGRAPH_POSTGRES_DSN"])
print({"applied_migrations": applied})
'@
```

Comportamiento real:

- `pg_advisory_xact_lock` global (namespace `phigraph:scoped-migration:v1`).
- Re-lectura de checksums tras el lock.
- `apply → verify_postgres_schema → commit` atómico.
- Idempotente: segunda ejecución devuelve `[]` si `002` ya está aplicada.

---

## 12. Verificación de esquema

```powershell
py -3 -c @'
import os, psycopg
from phigraph.core_v3.postgres_migrations import verify_postgres_schema
with psycopg.connect(os.environ["PHIGRAPH_POSTGRES_DSN"]) as conn:
    verify_postgres_schema(conn)
print("schema OK")
'@
```

Fallos típicos (`TransactionUnavailable`): tabla/columna/index ausente, checksum mismatch, `002` faltante.

---

## 13. Migración legacy a scoped

API: `migrate_grdi_scoped_ledger(ledger)` → en PostgreSQL llama `ledger.ensure_postgres_scoped_migrations()` + `ledger.migrate_legacy_scoped_postgres()`.

| Propiedad | Valor |
|-----------|-------|
| Alcance | **Global** (todas las filas en `phigraph_core_ledger` de colecciones migrables) |
| Escritura | Sí — inserta en `phigraph_scoped_ledger` / chain heads |
| Idempotencia | Omite filas ya presentes con mismo hash; falla en conflicto de hash |
| Excepciones | `DuplicateCanonicalKey`, `TransactionUnavailable` |

Colecciones migrables: todas en `LEGACY_MIGRATABLE_SCOPED_COLLECTIONS` (excluye `gateway_decision_events`).

---

## 14. Backfill determinista de gateway events

API: `backfill_gateway_decision_events(ledger, tenant_id=..., project_id=...)`

| Propiedad | Valor |
|-----------|-------|
| Filtros opcionales | `tenant_id`, `project_id` |
| Escritura | Sí — append a `gateway_decision_events` |
| Idempotencia | `append_scoped_once`; eventos existentes se cuentan como `skipped_events` |
| Simulación | `SIMULATION_RECORDED` **solo** si existe receipt scoped verificable |
| Atomicidad | Por plan (transacción scoped); error en un plan no revierte planes anteriores ya confirmados |
| Cierre | Llama `ledger.verify_scoped_chain(tenant_id=..., project_id=...)` |

Excepciones: `DuplicateCanonicalKey`, `TransactionUnavailable`, `ScopedRecordNotFound` (contado como `simulation_not_evaluated`, no aborta el plan).

---

## 15. Verificación de cadenas

API: `ledger.verify_scoped_chain(tenant_id=..., project_id=..., collection=...)`

| Propiedad | Valor |
|-----------|-------|
| Filtros opcionales | `tenant_id`, `project_id`, `collection` |
| Escritura | **No** — solo lectura |
| Retorno | `{"valid": true, "checked": N, "heads": {...}}` o `TransactionUnavailable` |

---

## 16. Cutover completo (apply)

**Cutover RC7→RC8 v1 es GLOBAL.** No existe `--apply` parcial.

| Flag / campo | Propósito |
|--------------|-----------|
| `--backup-manifest` | Manifiesto real (no example/placeholder) |
| `--confirm-cutover GRDI-RC8` | Confirmación explícita |
| `--acknowledge-global-migration` | Aceptar migración legacy + backfill + verificación **GLOBAL** |

**Prohibido en `--apply`:** `--tenant-id`, `--project-id`. Si aparecen, la herramienta aborta con **exit 2** antes de cualquier DDL/DML.

Los filtros `--tenant-id`/`--project-id` solo están disponibles en `--check-only` y `--verify` para diagnóstico acotado. Un backfill parcial futuro requerirá **otro comando/protocolo**; no está soportado en v1.

```powershell
py -3 scripts/grdi_rc8_cutover.py `
  --apply `
  --backup-manifest $ManifestPath `
  --confirm-cutover GRDI-RC8 `
  --acknowledge-global-migration `
  --output (Join-Path $ReportDir '03_apply.json')
```

Secuencia interna `--apply`:

1. Rechazar filtros tenant/project (exit 2).
2. Validar manifiesto (rechaza `placeholder: true`), identidad de base, backup regular `PGDMP`, SHA-256, antigüedad, `pg_restore --list`.
3. `bootstrap_postgres_scoped_schema(dsn)`.
4. `cutover_grdi_scoped_ledger(ledger)` — migración legacy + backfill **GLOBAL**.
5. `--verify` embebido (global); exit `4` si falla.

Salida JSON: `migration_scope=GLOBAL`, `backfill_scope=GLOBAL`, `verification_scope=GLOBAL`. Escritura **atómica** (`*.tmp` + replace). No sobrescribir reportes existentes salvo `--force-output`.

---

## 17. Conteos y hashes antes/después

Conservar en manifiesto/reportes JSON:

- `migration_versions_before/after`
- `collection_counts_before/after`
- `chain_heads_before/after`
- `inventory_fingerprint_before` (SHA-256 del inventario JSON)

---

## 18. Smoke funcional shadow-only

Tras `final_state: GO`:

1. **Lectura de plan** — API GRDI GET plan existente; confirmar `signed_gateway_decision`, `gateway_events`.
2. **Simulación idempotente** — repetir simulate sobre plan ya simulado; sin duplicar eventos (skipped).
3. **Outcome/replay** — solo si staging tiene fixtures; confirmar lectura, no ejecución real.
4. **Cero conectores** — confirmar flags shadow; sin webhooks ni HAV connectors activos.

Registrar resultados en `smoke_results` del manifiesto.

---

## 19. Criterios GO / NO-GO

| GO (`final_state: GO`, exit 0) | NO-GO (exit ≠ 0) |
|----|-------|
| Modo ejecutado validado satisfactoriamente | Cualquier check `NOT_EVALUATED` (salvo `NOT_APPLICABLE`) |
| RC8: `002` + schema + chains verificados | RC7 pre-cutover: `READY_FOR_CUTOVER` + exit 2 |
| `--apply`/`--verify` global sin issues | Duplicados canonical o checksum mismatch (exit 3) |
| Backup verificado pre-apply | Migración/verificación fallida (exit 4) |
| Smoke shadow OK post-GO | `--apply` con filtros tenant/project (exit 2, sin mutación) |

**Reglas contractuales:**

- `exit 0` **solo** si `final_state: GO`.
- `final_state: NO_GO` **nunca** produce `exit 0`.
- `assessment_state: READY_FOR_CUTOVER` indica inventario RC7 válido pendiente de `--apply`; **no** significa cutover completado.

---

## 20. Recuperación ante fallo

1. **Detener** apply si exit ≠ 0.
2. **No** ejecutar `repair_chain()`.
3. Documentar error en manifiesto (`final_state: NO_GO`).
4. Mantener aplicación en lectura/bloqueo.

### Rollback operativo (forward-only)

No existe downgrade SQL. Rollback = **restaurar backup en base nueva**:

```powershell
$RestoreDb = 'phigraph_staging_restore'
createdb $RestoreDb  # o equivalente en el servidor
pg_restore --dbname "postgresql://USER:PASSWORD@HOST:5432/$RestoreDb" $BackupFile
```

Reapuntar staging al DSN restaurado solo tras validación del operador. La base original mutada permanece como evidencia forense hasta retención cumplida.

**Significado de rollback en migración forward-only:** transacciones abortadas durante bootstrap/cutover revierten DDL/DML de esa transacción; planes ya commitados en backfill secuencial **no** se revierten automáticamente.

---

## 21. Evidencia a conservar

- Dump `pg_dump` + SHA-256.
- Manifiesto JSON completo.
- Reportes `--check-only`, `--apply`, `--verify`.
- Logs de aplicación (sin DSN).
- Checklist firmado (§22).
- Timestamp UTC inicio/fin.

---

## 22. Checklist de aprobación y firma

| # | Item | OK | Operador | Fecha UTC |
|---|------|----|----------|-----------|
| 1 | Backup pg_dump verificado | ☐ | | |
| 2 | Preflight `--check-only` sin blockers | ☐ | | |
| 3 | Escrituras de app bloqueadas | ☐ | | |
| 4 | `--apply` exit 0 | ☐ | | |
| 5 | `--verify` exit 0 | ☐ | | |
| 6 | Smoke shadow OK | ☐ | | |
| 7 | GO autorizado por platform + GRDI owner | ☐ | | |

---

## 23. Limitaciones

- Migraciones PostgreSQL **forward-only** (`001` → `002`); sin script de downgrade.
- Sin `repair_chain()` en el procedimiento ni en la herramienta.
- Sin conectores reales ni side effects externos.
- `SIMULATION_RECORDED` requiere `shadow_execution_receipts` verificable; estados legacy simulados sin receipt quedan en `simulation_not_evaluated`.
- `migrate_grdi_scoped_ledger` es global; **no hay `--apply` parcial** en v1.
- Filtros tenant/project: solo `--check-only` / `--verify` (diagnóstico); backfill parcial futuro = otro comando.
- `EvidenceLedger(...)` en PostgreSQL aplica migraciones pendientes al conectar — evitar en preflight manual fuera de `--check-only`.

---

## Inventario de APIs (referencia técnica)

| Función | Global | tenant/project | Escritura | Idempotente | Excepciones principales |
|---------|--------|----------------|-----------|-------------|-------------------------|
| `bootstrap_postgres_scoped_schema(dsn)` | Sí | — | Sí (DDL+migration rows) | Sí | `TransactionUnavailable` |
| `apply_postgres_migrations(conn, verify=True)` | Sí | — | Sí | Sí | `TransactionUnavailable` |
| `verify_postgres_schema(conn)` | Sí | — | No | N/A | `TransactionUnavailable` |
| `migrate_grdi_scoped_ledger(ledger)` | Sí | — | Sí | Parcial | `DuplicateCanonicalKey`, `TransactionUnavailable` |
| `backfill_gateway_decision_events(ledger, tenant_id=, project_id=)` | No* | Opcional | Sí | Parcial | `DuplicateCanonicalKey`, `TransactionUnavailable` |
| `cutover_grdi_scoped_ledger(ledger)` | Sí | — | Sí | Parcial | Igual que migrate+backfill |
| `verify_scoped_chain(ledger, tenant_id=, project_id=, collection=)` | No* | Opcional | No | N/A | `TransactionUnavailable` |

\*Filtros opcionales acotan verificación/backfill, no la migración legacy.

---

## Códigos de salida (`grdi_rc8_cutover.py`)

| Código | Significado |
|--------|-------------|
| 0 | Modo ejecutado validado (`final_state: GO`, `assessment_state: VALIDATED`) |
| 2 | Precondición / entorno no listo (`READY_FOR_CUTOVER` en RC7, flags, manifiesto, backup, reporte existente, filtros en `--apply`) |
| 3 | Conflicto de datos (duplicados, checksum backup incorrecto) |
| 4 | Migración o verificación fallida; verificación incompleta (`NOT_EVALUATED`); interrupción; error inesperado redactado |

**Reglas fail-closed:**

- `exit 0` **únicamente** si `final_state: GO`.
- `final_state: NO_GO` **nunca** devuelve `exit 0`.
- RC7 `--check-only` sin blockers: `assessment_state: READY_FOR_CUTOVER`, `final_state: NO_GO`, **exit 2**.
- RC8 `--check-only` completo: `assessment_state: VALIDATED`, `final_state: GO`, **exit 0**.
- `--apply` con `--tenant-id`/`--project-id` → **exit 2** antes de mutaciones.
- Verificación diagnóstica con filtros deja `global_scope_verification = NOT_EVALUATED` → exit `4`.
- Errores inesperados e interrupciones (`KeyboardInterrupt`) → exit `4`, mensaje redactado.
- Nunca invoca `repair_chain()`.
