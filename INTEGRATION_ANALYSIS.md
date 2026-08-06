# Análisis de integración — PhiGraph Core 4.1.0-rc.1 + HAV v0.2

**Fecha:** 2026-08-06  
**Rama:** `integration/v4.1-grdi-foundation`  
**Base:** `main@74d15e2`  
**Estado:** cambios locales listos para revisión (sin commit ni push en el momento del empaquetado)

---

## 1. Resumen ejecutivo

Se integró **HAV v0.2** como componente canónico de PhiGraph Core sobre la línea **4.1.0-rc.1** (`development candidate`), preservando:

- Shadow-first (sin ejecución externa por defecto)
- Fail-closed
- Aislamiento multitenant vía identidad Core
- Protocol 2.0.0 **sin cambios**
- Receipts firmados y trazables

HAV **verifica** claims frente a evidencia y políticas; **no autoriza ejecución** por sí solo. Un `PASS` registra `ALLOW` en el ledger pero `execution_authorized: false` en el receipt.

---

## 2. Qué contiene este paquete

| Área | Contenido |
|------|-----------|
| Código HAV | `src/phigraph/hav/` |
| Auth compartida | `src/phigraph/core_v3/auth_deps.py` |
| API montada | `/v3/hav/*` en `deployment/app.py` |
| Tests | 146 passing (128 Core+HAV base + 18 canonical) |
| Documentación | `CANONICAL_INVENTORY.md`, `PROJECT_STATUS.md`, `CONFORMANCE_REPORT.md`, ADR-014/015, etc. |

---

## 3. Commits HAV incorporados

| Original | En rama |
|----------|---------|
| `1f23491` feat(hav): integrate PhiGraph HAV v0.2 | `538056c` |
| `c7bf335` fix(security): Bandit Verdict.PASS | `fb17d13` |

Endurecimiento adicional (auth, idempotencia, versionado) está en **cambios locales sin commit**.

---

## 4. Validación ejecutada en esta sesión

| Control | Resultado |
|---------|-----------|
| `pytest -q` | **146 passed**, 0 failed, 0 skipped |
| `compileall src tests` | OK |
| `python -m build` | OK (`phigraph_causal-4.1.0rc1`) |
| `ruff` (HAV + auth_deps + tests nuevos) | OK |
| `ruff` (repo completo) | No evaluado (697 hallazgos previos) |
| Docker build/config | No evaluado (CLI ausente en host) |

---

## 5. Cambios arquitectónicos clave

### 5.1 Identidad y multitenancy
- **Antes:** `tenant_id` / `project_id` en el body de `/v3/hav/verify` (spoofable).
- **Ahora:** tenant/proyecto/rol desde `Principal` (headers, JWT, OIDC o API key Core).
- `PHIGRAPH_HAV_API_KEY` solo como fallback de desarrollo si Core auth no está configurado.

### 5.2 Idempotencia
- Header `Idempotency-Key` en `/v3/hav/verify`.
- Misma clave + mismo payload → misma respuesta, sin duplicar ledger.
- Misma clave + payload distinto → HTTP 409.

### 5.3 Versionado centralizado (`src/phigraph/version.py`)
```
CORE_VERSION = 4.1.0-rc.1
PROTOCOL_VERSION = 2.0.0
HAV_VERSION = 0.2.0
HAV_VERIFIER_ID = phigraph-hav-v0.2
HAV_POLICY_ID = PHIGRAPH_HAV_FAIL_CLOSED_V1
```

### 5.4 Mapeo de políticas

| HAV | Core | Ejecuta |
|-----|------|---------|
| PASS | ALLOW | No |
| WARN | WARN | No |
| HUMAN_REVIEW | REQUIRE_APPROVAL | No |
| REJECT | BLOCK | No |
| SOURCE_UNAVAILABLE | BLOCK | No |

### 5.5 Frontera GRDI (conceptual)
Receipt incluye `grdi_boundary.stage = verification_only` para consumo futuro por Decision Envelope, Authority Engine, Execution Gateway y Outcome Ledger. **GRDI completo no está implementado.**

---

## 6. Clasificación por componente

| Componente | Estado |
|------------|--------|
| HAV engine + policy | IMPLEMENTED |
| HAV API + Core auth | VALIDATED |
| Idempotencia HAV | VALIDATED |
| Receipts firmados | VALIDATED |
| GRDI Foundation | CONCEPTUAL |
| Release estable 4.1.0 | PENDIENTE |
| Piloto DonWeb (PR #6) | PENDIENTE (rama aparte) |

---

## 7. Limitaciones conocidas

1. **Hybrid extractor:** puede emitir `WARN` si el texto incluye spans factuales no anclados (consenso entre modelos no es verdad).
2. **4.1.0-rc.1** no debe presentarse como release estable hasta completar GRDI Foundation y CI completa.
3. **Dos PRs abiertos** en GitHub sin merge: #5 (HAV feature), #6 (deploy piloto).
4. Este paquete puede incluir cambios **staged y unstaged**; revisar con `git status` si restauras el repo Git original.

---

## 8. Opciones para avanzar

### Opción A — Merge canónico (recomendada a mediano plazo)
1. Revisar diff en `integration/v4.1-grdi-foundation`
2. Commit local
3. Push + PR → `main`
4. Cerrar/superseder PR #5 si esta rama lo reemplaza

### Opción B — Piloto VPS primero
1. Mergear PR #6 (`feature/pilot-deploy-artifacts`) o cherry-pick deploy
2. Combinar con esta integración HAV
3. Seguir `docs/deployment/DONWEB_PILOT_RUNBOOK.md`

### Opción C — GRDI Foundation (v4.1 siguiente hito)
1. Decision Envelope (schema + ledger)
2. Authority Engine stub
3. Execution Gateway (sigue shadow-first)
4. Outcome Ledger

### Opción D — Publicación
- Paper ya en Zenodo: https://doi.org/10.5281/zenodo.21689514
- Tag/release **solo** cuando 4.1.0 sea estable

---

## 9. Comandos útiles tras descomprimir

```powershell
cd PhiGraph_v4.1_HAV_Integration
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[api,benchmark,auth,dev]"
py -3 -m pytest -q
pip install -e ".[api]" ; phigraph-api
```

Probar HAV verify (dev, headers confiables):

```powershell
curl -X POST http://127.0.0.1:8000/v3/hav/verify `
  -H "X-Role: verifier" `
  -H "X-Tenant-ID: tuch" `
  -H "Content-Type: application/json" `
  -d '{"candidate_output":"Todos los controles pasaron.","source_system":"manual","evidence":[]}'
```

---

## 10. Recomendación

**REVIEW_REQUIRED** → revisar este paquete, decidir commit/PR, y solo entonces merge a `main`.

No declarar 4.1.0 estable ni afirmar cobertura Docker/CI remota sin ejecutar esos controles en tu entorno.

---

## 11. Documentos relacionados en el paquete

- `CONFORMANCE_REPORT.md` — matriz de conformidad
- `PROJECT_STATUS.md` — estado del proyecto
- `CANONICAL_INVENTORY.md` — inventario de módulos
- `RELEASE_NOTES_V4.1.0.md` — notas de release candidate
- `docs/architecture/PHIGRAPH_HAV_INTEGRATION.md` — arquitectura
- `docs/decisions/ADR-014-*.md`, `ADR-015-*.md` — decisiones

---

*Generado para revisión offline por Walter Calmels / TUCH Systems.*
