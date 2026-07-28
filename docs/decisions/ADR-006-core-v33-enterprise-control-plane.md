# ADR-006: Core v3.3 enterprise control plane

Status: Accepted

PhiGraph Core adopts an optional PostgreSQL backend, scoped principals with explicit roles, tamper-evident per-collection hash chains, and operational health/metrics endpoints. Identity headers are trusted only when an upstream authenticated proxy is explicitly configured.
