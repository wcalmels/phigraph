# ADR-007: Secure execution and verified identity

Status: Accepted

PhiGraph Core v3.4 exposes only a dry-run controlled execution bridge, accepts verified bearer identity through a JWT validator, records bounded runtime traces, and supplies optional PostgreSQL RLS policy SQL. No external action connector is enabled by this decision.
