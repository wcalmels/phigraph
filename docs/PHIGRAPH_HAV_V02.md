# TUCH PhiGraph HAV v0.2 — Universal Evidence and Claim Verification

HAV v0.2 extends the Core integration with canonical state connectors, hybrid claim extraction, factual-candidate extraction, multi-output consistency, provider abstraction, benchmark tooling and optional API-key protection.

## Security boundary

- Generated code is not executed.
- Missing authoritative state is fail-closed.
- Web search is not treated as truth by default.
- Multi-model agreement is an auxiliary signal only.
- `PHIGRAPH_HAV_API_KEY` enables API-key enforcement.

## API

- `POST /v3/hav/verify`
- `POST /v3/hav/factual/extract`
- `POST /v3/hav/consistency`
