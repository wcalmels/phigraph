# TUCH PhiGraph Core v3.9.0

PhiGraph Code v3.9 adds reproducible corpora, provider-neutral model adapters, read-only GitHub commit archive acquisition, deterministic security and dependency evidence, patch quality gates, repeated experiments, and scientific JSON/Markdown reporting.

## Safety posture

- Repository sources are not modified.
- GitHub acquisition is read-only.
- Archives reject traversal paths and links.
- Patches run in temporary copies.
- High/critical deterministic findings introduced by a patch block acceptance.
- No remote commits, merges, deployments, or arbitrary shell commands are enabled.
