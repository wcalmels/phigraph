# PhiGraph v1.9 Deployment Packaging

Version 1.9 packages PhiGraph as a shadow-only service.

## Included

- FastAPI application;
- `/health` and `/ready`;
- `/config` with secret masking;
- `/v1/shadow/analyze`;
- environment-based configuration;
- API-key support;
- request-size limits;
- Dockerfile and Docker Compose;
- non-root container;
- read-only root filesystem;
- GitHub Actions test and image-build workflow.

## Safety boundary

The configuration validator rejects:

- `PHIGRAPH_SHADOW_ONLY=false`;
- `PHIGRAPH_REAL_CONNECTORS_ENABLED=true`.

The API response always reports `executed=false`. This release does not contain
a real connector endpoint.
