# TUCH PhiGraph Core v4.0 Candidate

## Product boundaries

- **PhiGraph Core**: protocol, ledger, verification, policy, runtime, identity, observability and persistence.
- **PhiGraph Code**: repository indexing, code-agent benchmarks, patch evaluation, corpus experiments and reports.
- **PhiGraph Cyber**: existing cyber MVP and domain-specific graph analytics; it consumes Core but is not part of the public Core protocol.

## Stable namespaces

```python
from phigraph.protocol import Claim, Evidence, Verification
from phigraph.core import CoreService, CoreRuntime
from phigraph.code import PatchQualityEvaluator, ReproducibleCorpus
from phigraph.sdk import PhiGraphClient
```

## Release-candidate policy

The RC freezes public import paths and serialized semantics. Breaking implementation cleanup is postponed until after compatibility tests and a real benchmark are completed.
