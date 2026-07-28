# PhiGraph External Validation Report — CIC-IDS2017

## Scope

This is the first executed external benchmark for the PhiGraph Cybersecurity
Shadow MVP. It uses the CIC-IDS2017 Friday afternoon DDoS flow file.

## Dataset

- Total rows: 225,745
- Benign: 97,718
- DDoS: 128,027
- Benign-only reference set: 12,000
- Test set: 6,000 benign + 6,000 DDoS
- Random seed: 47
- Alert budget: top 10%

## Results

| Method | ROC-AUC | PR-AUC | Precision@budget | Recall@budget | F1@budget | Runtime (s) |
|---|---:|---:|---:|---:|---:|---:|
| local_outlier_factor | 0.9757 | 0.9506 | 0.9617 | 0.1923 | 0.3206 | 0.322 |
| phigraph_relational | 0.7295 | 0.7316 | 0.8400 | 0.1680 | 0.2800 | 0.165 |
| isolation_forest | 0.7403 | 0.6840 | 0.7817 | 0.1563 | 0.2606 | 0.321 |
| robust_z | 0.5771 | 0.5540 | 0.4117 | 0.0823 | 0.1372 | 0.006 |

## Main finding

Local Outlier Factor produced the strongest ranking on this particular
tabular benchmark. PhiGraph Relational ranked second by PR-AUC and achieved
84.0% precision among the top 10% alerts, outperforming Isolation Forest
(78.2%) and the robust deviation baseline (41.2%).

This is useful evidence that the current PhiGraph scoring is functional and
competitive against basic unsupervised baselines. It is not evidence of
state-of-the-art superiority.

## Interpretation boundary

The MachineLearningCSV file omits source IP, destination IP, timestamp,
identity, device and process identifiers. The graph used here is therefore a
feature-similarity graph, not the heterogeneous operational graph for which
PhiGraph was designed.

The result cannot validate lateral movement localization, identity-device
paths or causal attribution. Those require GeneratedLabelledFlows, corrected
CIC flows, LANL multi-source events or customer telemetry.

## Dataset-quality caveat

Published research has identified flow-construction, feature-extraction and
labeling problems in CIC-IDS2017. The benchmark should be treated as an
initial engineering validation rather than definitive production evidence.

## Next experiment

1. Repeat on corrected CIC-IDS2017 flows.
2. Add a chronological attack-budget evaluation.
3. Validate heterogeneous paths on a LANL subset.
4. Compare against LOF, Isolation Forest, one-class SVM and supervised
   classifiers under leakage-safe splits.
