# Automatic Modeling Assistant

The modeling assistant converts ordinary operational tables into graph-ready data.

It performs:

1. column-role inference;
2. domain inference;
3. entity detection;
4. relation proposal;
5. signal detection;
6. edge-table generation;
7. warning generation.

## Supported initial domains

- fleet
- mining
- supply chain
- cybersecurity
- fraud
- energy
- telecom

## Important limitation

The assistant proposes a model. It does not prove that the inferred graph is the
correct causal representation of the process. The user should review entity,
relation, weight, and signal choices before analysis.
