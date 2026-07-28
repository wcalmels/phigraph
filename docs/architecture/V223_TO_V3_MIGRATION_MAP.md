# PhiGraph v2.2.3 to Core v3 Migration Map

| Existing package | Core v3 role | Migration strategy |
|---|---|---|
| `governance` | verification and decision evidence | adapter, then deprecate duplicate record shapes |
| `shadow` | runtime mode and outcome feedback | preserve storage; add canonical export/import |
| `execution` | explicit executor implementation | wrap behind `ActionProposal` and `PolicyDecision` |
| `advisory` | action proposal producer | emit canonical actions and rationale claims |
| `operations` | outcome and incident evidence | normalize as evidence/outcome records |
| `platform_general` | domain adapter registry | align with v3 Agent/Domain adapter contracts |
| `production` / `platform` | deployment services | consolidate after parity and API tests |
| `cyber_mvp` | first vertical package | migrate after protocol integration stabilizes |

## Deprecation policy

No v2 package is removed in 3.0.0. Deprecation starts only after:

- equivalent Core v3 behavior exists;
- migration documentation exists;
- parity tests pass;
- at least one release cycle has elapsed.
