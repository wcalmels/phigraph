# PhiGraph v0.5 Multi-file Modeling

Version 0.5 adds a deterministic multi-file modeling pipeline.

## Pipeline

```text
FileCatalogAgent
  -> EntityResolutionAgent
  -> TableLinkingAgent
  -> TemporalAlignmentAgent
  -> HeterogeneousGraphAgent
```

## Capabilities

- profile several tables;
- infer entity and signal columns;
- normalize equipment and entity identifiers;
- infer cross-table join candidates;
- classify join cardinality;
- detect temporal columns and granularity;
- build a heterogeneous MultiGraph;
- produce a complete audit trail.

## Limitations

- join inference currently uses normalized value overlap;
- ambiguous matches require human review;
- heterogeneous graph projection to a spectral graph is planned for v0.6;
- the pipeline does not yet merge arbitrary schemas automatically.
