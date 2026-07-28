# PhiGraph v0.6 Analytical Multi-Agent Pipeline

Version 0.6 extends the multi-file model with a complete analytical layer.

## Pipeline

```text
FileCatalogAgent
  -> EntityResolutionAgent
  -> TableLinkingAgent
  -> TemporalAlignmentAgent
  -> HeterogeneousGraphAgent
  -> ProjectionAgent
  -> SignalEngineeringAgent
  -> ModelSelectionAgent
  -> ProjectedRootCauseAgent
  -> NullControlAgent
  -> AdversarialValidationAgent
```

## New capabilities

- automatic projection of a heterogeneous graph;
- deterministic signal engineering;
- automatic Laplacian and spectral-mode selection;
- localized root-cause candidates on the projection;
- degree-preserving rewiring controls;
- empirical p-values and z-scores;
- robustness checks against:
  - Laplacian choice;
  - number of modes;
  - random edge dropout.

## Interpretation

The result is an analytical hypothesis with model-based controls. It is not
proof of real-world causality. Operational validation remains necessary.
