# CIC-IDS2017 Validation Protocol

## Dataset

The initial external validation uses the CIC-IDS2017
`Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv` file.

The official UNB documentation states that CIC-IDS2017 contains labeled flows
generated with CICFlowMeter and includes benign traffic plus DDoS and other
attack scenarios. The official download currently requires a form; for
reproducibility, the validation may use a public byte-level mirror while
retaining the UNB documentation and citation as the authoritative source.

## Protocol

- Clean column whitespace and numeric invalid values.
- Draw a reproducible benign-only reference set.
- Build a balanced unseen test set containing benign and DDoS flows.
- Select variable numeric features using the benign reference only.
- Fit preprocessing on benign data only.
- Compare:
  - robust feature-deviation score;
  - Isolation Forest;
  - Local Outlier Factor;
  - PhiGraph relational score using robust deviation plus k-nearest-neighbor
    graph distance and kernel disagreement.
- Report ROC-AUC, PR-AUC, precision, recall and F1 at the top 10% alert budget.

## Interpretation boundary

This CSV does not contain source/destination IPs, timestamps, users, devices or
processes. Therefore, the experiment validates flow-level ranking and a graph
of feature similarity. It does not validate the full heterogeneous
identity-device-process graph implemented in the Cyber Shadow MVP.

## Reproduction

```powershell
python scripts\validate_cicids2017.py `
  "C:\ruta\Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv"
```

## Dataset caveat

Published research has reported substantial flow-construction, feature and
labeling problems in CIC-IDS2017. The dataset is useful as an initial benchmark
but not as sufficient evidence for production claims. A subsequent experiment
should use corrected CIC-IDS2017 flows and a relational LANL subset.
