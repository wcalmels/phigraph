# PhiGraph v2.2 Cybersecurity Shadow MVP

This release converts the platform architecture into a demonstrable
cybersecurity workflow.

## User workflow

1. Load CSV or JSON security events, or use the included demo.
2. Validate the event contract.
3. Build a heterogeneous security graph.
4. score users and devices using event risk, event semantics, relationship
   rarity, process rarity, destination rarity and graph structure.
5. Review the highest-ranked alerts.
6. Record analyst verdicts.
7. Measure cumulative precision and false-positive rate.

## Minimum schema

- `timestamp`
- `user_id`
- `device_id`
- `event_type`
- `source_ip`
- `risk_score` in the range `[0, 1]`

Optional fields include destination IP, process, resource, alert identifier,
privilege and known outcome.

## Scope

The MVP is a shadow evaluation system, not a replacement for a SIEM, EDR or
SOAR. It does not revoke sessions, isolate endpoints, modify firewalls or
execute any external action.

## Run

```bash
pip install -e ".[mvp,dev]"
phigraph-cyber-mvp
```

The included demo contains a synthetic sequence representing unusual device
use, privilege escalation and lateral movement.
