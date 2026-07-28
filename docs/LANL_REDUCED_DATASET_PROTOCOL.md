# LANL Reduced Relational Dataset Protocol

## Purpose

This protocol creates a compact, reproducible subset of the LANL
Comprehensive Multi-Source Cyber-Security Events dataset for documenting and
testing PhiGraph's heterogeneous cybersecurity graph.

The original release contains 58 consecutive days and approximately
1.648 billion events from authentication, process, DNS, network-flow and
red-team sources. Processing all files is unnecessary for the first
relational experiment.

## Source schemas

The reducer preserves the official LANL schemas:

- Authentication:
  `time, source user, destination user, source computer, destination computer,
  authentication type, logon type, orientation, result`.
- Process:
  `time, user, computer, process name, start/end`.
- Flow:
  `time, duration, source computer, source port, destination computer,
  destination port, protocol, packet count, byte count`.
- DNS:
  `time, source computer, computer resolved`.
- Red team:
  `time, user, source computer, destination computer`.

LANL timestamps are de-identified integer offsets beginning at epoch 1 with
one-second resolution. Identifiers are consistent across sources.

## Reduction rule

The subset is event-centered rather than randomly sampled.

For each red-team event at time `t`, the reducer selects a window:

```text
[t - pre_seconds, t + post_seconds]
```

Overlapping windows are merged. The documentation profile additionally keeps
only events involving a red-team user or computer. This reduces volume while
retaining the directly connected attack neighborhood.

This selection is suitable for:

- schema and pipeline documentation;
- attack-path visualization;
- graph-construction tests;
- local anomaly-ranking experiments.

It is not suitable for estimating an enterprise-wide false-positive rate,
because most normal activity is intentionally excluded.

## Profiles

### documentation-minimal

- 30 minutes before and after each red-team event;
- authentication, process and DNS sources;
- direct red-team entity filter;
- maximum 100,000 rows per source.

Expected use: examples, diagrams, unit tests and an initial local run.

### validation-extended

- two hours before and after each red-team event;
- authentication, process, flow and DNS sources;
- no direct entity filter;
- maximum 2,000,000 rows per source.

Expected use: comparative anomaly detection and graph ablations.

## Reproducibility

Every reduced row receives `source_line_number`. The generated manifest stores:

- reduction configuration;
- SHA-256 of each source file;
- number of red-team events;
- selected windows;
- rows scanned and written;
- malformed rows;
- truncation status.

## Required local files

Download the LANL files from the official data page and place them in one
directory:

```text
auth.txt.gz
proc.txt.gz
flows.txt.gz
dns.txt.gz
redteam.txt.gz
```

The minimal profile can run without `flows.txt.gz`.

## Windows command

```powershell
cd "C:\Users\wcalm\OneDrive\Escritorio\phigraph-causal"
.\.venv\Scripts\Activate.ps1

python scripts\build_lanl_reduced.py `
  "D:\datasets\lanl-cyber1" `
  --profile documentation-minimal `
  --output "validation_results\lanl_reduced_minimal"
```

## Outputs

```text
manifest.json
windows.json
redteam_labels.csv
auth_reduced.csv
proc_reduced.csv
dns_reduced.csv
flows_reduced.csv   # extended profile
```

## Scientific limitations

1. Red-team labels identify selected authentication compromise events, not
   every malicious action surrounding them.
2. Event-centered sampling enriches attacks and changes the natural class
   distribution.
3. Entity filtering may remove supporting infrastructure not directly named
   in red-team labels.
4. The minimal profile cannot estimate production alert volume.
5. Any performance claim must be repeated on a broader chronological
   background sample.

## Citation

A. D. Kent, “Comprehensive, Multi-Source Cyber-Security Events,” Los Alamos
National Laboratory, DOI 10.17021/1179829, 2015.
