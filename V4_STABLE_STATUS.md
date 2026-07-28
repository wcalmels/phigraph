# PhiGraph Core 4.0.0 — Stable Status

## Verified

- Full repository test suite passes.
- Python sources and tests compile.
- Wheel builds without network access using the installed build backend.
- Clean wheel installation and public-import smoke test pass.
- FastAPI status/liveness smoke test reports Core 4.0.0 and Protocol 2.0.0.
- Ledger remains tamper-evident after evidence verification transitions.
- Legacy chain repair is covered by regression tests.
- No hardcoded credential assignment patterns were found in the Python source scan.
- No `shell=True`, direct `eval`, or direct `exec` primitives were found in the Python source scan.

## Production boundary

This release is stable at the software/API level. Production deployment still requires environment-specific validation of PostgreSQL, OIDC/JWKS, secrets, networking, backups, monitoring, capacity and disaster recovery.

## Authority boundary

External side effects remain disabled by default and in the supplied sandbox. PhiGraph 4.0.0 is shadow-first.
