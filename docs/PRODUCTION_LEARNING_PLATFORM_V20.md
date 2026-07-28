# PhiGraph v2.0 Production Learning Platform

Version 2.0 introduces platform services around the governed shadow pipeline.

## Included

- relational persistence abstraction;
- versioned database migrations;
- model, kernel, workflow and dataset registry;
- persistent job queue and worker;
- role-based access control;
- platform audit events;
- governed promotion from experimental to shadow and staging;
- staging Docker Compose configuration;
- v2 registry and job API.

## Database scope

The built-in runtime directly supports SQLite for local and staging validation.
`PHIGRAPH_DATABASE_URL` is designed for PostgreSQL deployment configuration,
but a PostgreSQL driver and operational database must be provisioned separately
before production use.

## Safety boundary

- real connectors remain disabled;
- the worker handles shadow jobs only;
- promotion to `production` is explicitly blocked;
- all deployment settings still require `shadow_only=true`.
