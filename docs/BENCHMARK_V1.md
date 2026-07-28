# PhiGraph Causal v1.0 Formal Benchmark

Version 1.0 introduces a reproducible comparison framework.

## Included datasets

- Synthetic fleet anomaly with coordinated truck-driver-shift-station effects.
- Synthetic fraud ring with coordinated device-merchant-beneficiary effects.

Each dataset includes:

- tabular files for PhiGraph;
- numerical feature matrix for baseline methods;
- entity-level anomaly labels;
- known causal entities;
- reproducible random seed.

## Baselines

- Robust multivariate z-score.
- Isolation Forest.
- Local Outlier Factor.
- One-Class SVM.
- PhiGraph v1 adapter.

## Metrics

Detection:

- precision;
- recall;
- F1;
- AUROC;
- AUPRC.

Localization:

- precision@k;
- recall@k;
- mean causal-entity rank.

Operational:

- runtime;
- adversarial stability when available.

## Scientific status

Synthetic benchmark superiority does not establish superiority on industrial
data. Real competitiveness requires external datasets, incident labels,
prospective testing, and cost-benefit measurement.
