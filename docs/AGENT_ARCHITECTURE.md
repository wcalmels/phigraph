# PhiGraph Agentic Architecture

## Design rule

Language models orchestrate tools and explain outputs. They do not replace the deterministic graph and spectral engine.

## Layers

1. `phigraph`: graph, spectral, localization, ablation, controls and corridors.
2. `phigraph.agents`: deterministic agent workflow and audit trail.
3. `phigraph.domains`: sector-specific node types, signals and intervention policies.
4. `phigraph.local`: optional local-model and allow-listed tool adapters.

## Default workflow

```text
DataQualityAgent
  -> GraphBuilderAgent
  -> RootCauseAgent
  -> SimulationAgent
  -> ValidationAgent
```

Every step writes an audit entry. A blocked step stops the workflow.

## Safety

- No arbitrary shell tool.
- Read-only analysis by default.
- Explicit approval for write tools.
- Model-based causal language is kept separate from confirmed causality.
- Sensitive datasets should remain outside the public repository.
