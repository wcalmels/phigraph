# PhiGraph v2.1 General Relational Intelligence Platform

The analytical, meta-learning, governance, shadow, advisory, sandbox,
observability and deployment layers are now shared core services.

Each sector is introduced as a domain pack defining ontology, table contracts,
normalization, entity and relation mappings, signals, recommended kernels,
allowed advisory/sandbox actions, prohibited actions and success metrics.

Included packs: cybersecurity, fleet, maintenance, fraud and mining.

New domains implement `DomainAdapter` and register with `DomainRegistry`;
the core engine is not duplicated.
