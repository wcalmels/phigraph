# TUCH PhiGraph

[![CI](https://github.com/wcalmels/phigraph/actions/workflows/ci.yml/badge.svg)](https://github.com/wcalmels/phigraph/actions/workflows/ci.yml)
[![Security](https://github.com/wcalmels/phigraph/actions/workflows/security.yml/badge.svg)](https://github.com/wcalmels/phigraph/actions/workflows/security.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Release](https://img.shields.io/badge/release-4.0.0-2ea44f.svg)](RELEASE_NOTES_V4.0.0.md)

**TUCH PhiGraph Core 4.0.0** is a governed relational-intelligence platform for recording, verifying and controlling claims and actions produced by software agents and AI systems.

> Model output is not verified truth. PhiGraph treats it as a candidate claim or action proposal until evidence, policy and verification establish otherwise.

## Status

PhiGraph 4.0.0 is a stable technical MVP intended for local evaluation, controlled pilots and private deployments. It is **shadow-first**: the supplied runtime does not grant arbitrary external execution authority.

- Core version: `4.0.0`
- Protocol version: `2.0.0`
- Automated tests: `117`
- Python: `3.10+`
- Public namespaces: `phigraph.protocol`, `phigraph.core`, `phigraph.code`, `phigraph.sdk`

## Architecture

```text
AI model / deterministic agent
              │
              ▼
       PhiGraph Protocol
              │
   ┌──────────┼───────────┐
   ▼          ▼           ▼
Evidence   Verification  Policy
Ledger       Engine      Engine
   └──────────┼───────────┘
              ▼
      Shadow-first Runtime
              │
              ▼
    Outcome, audit and trace
```

PhiGraph is organized into:

- **PhiGraph Core:** protocol, evidence ledger, verification, policy, identity, persistence and governed runtime.
- **PhiGraph Code:** repository indexing, task corpora, isolated patch evaluation, security checks and model benchmarks.
- **PhiGraph Cyber:** shadow-first graph analytics and the existing CIC-IDS2017/LANL validation tooling.
- **Python SDK:** provider-neutral access to the Core API.

## Installation

### Editable development installation

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[api,benchmark,dev]"
pytest
```

### Wheel installation

```bash
pip install phigraph_causal-4.0.0-py3-none-any.whl
```

## Minimal protocol example

```python
from phigraph.protocol import Claim

claim = Claim.create(
    statement="The repository test suite passes",
    claim_type="test_run",
    subject="repository@commit",
    issuer="coding-agent",
)

print(claim.status)  # proposed
```

## Run the API

```bash
pip install -e ".[api]"
phigraph-api
```

Then inspect:

```text
GET /v3/status
GET /v3/health/live
GET /v3/health/ready
```

## Docker

```bash
cp .env.example .env
docker compose up --build
```

The included Docker configuration is a starting point for private evaluation. Review [`docs/deployment/PRODUCTION_CHECKLIST.md`](docs/deployment/PRODUCTION_CHECKLIST.md) before any production deployment.

## Safety and scientific scope

PhiGraph does not claim to:

- eliminate all LLM hallucinations;
- prove causal identification from observational data alone;
- constitute AGI;
- guarantee error-free autonomous execution;
- replace security review, testing or human authorization in critical systems.

It is designed to make unsupported claims, missing evidence and unauthorized actions easier to detect, audit and block.

## Documentation

- [Protocol 2.0](docs/protocol/PHIGRAPH_PROTOCOL_V2.md)
- [Core 4.0 architecture](docs/architecture/PHIGRAPH_CORE_V40_CANDIDATE.md)
- [Python SDK](docs/sdk/PYTHON_SDK.md)
- [Migration from 3.9](docs/migration/V39_TO_V40.md)
- [Production checklist](docs/deployment/PRODUCTION_CHECKLIST.md)
- [Roadmap](ROADMAP.md)
- [Security policy](SECURITY.md)
- [Licensing strategy](docs/governance/LICENSING_STRATEGY.md)

## Investor Overview

[Read the TUCH PhiGraph Core 4.0.0 Investor Overview](docs/papers/TUCH_PHIGRAPH_CORE_V4_INVESTOR_OVERVIEW.md)

## Repository policy

The initial GitHub repository should remain **private** until the publication checklist, secret audit and licensing decision have been completed. See [`docs/governance/PUBLICATION_CHECKLIST.md`](docs/governance/PUBLICATION_CHECKLIST.md).

## License

The current source package retains its existing MIT license while the repository remains private. Before public release, TUCH should select and obtain legal review for the final model. The recommended commercial strategy is an **AGPL-3.0 community edition plus a separate commercial license** for customers that require proprietary embedding, OEM distribution or closed-source hosted modifications.

Copyright © 2026 Walter Calmels / TUCH Systems.
