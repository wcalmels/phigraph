# Benchmark Protocol

Run the complete benchmark:

```bash
phigraph-benchmark --dataset fleet --output results/benchmark/fleet
phigraph-benchmark --dataset fraud --output results/benchmark/fraud
```

The report produces JSON, CSV, and Markdown outputs.

## Reproducibility

Use the same seed, package versions, and benchmark configuration. Do not tune a
method on the test labels. New datasets and methods must include tests.
