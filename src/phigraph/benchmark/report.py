from __future__ import annotations

from pathlib import Path
import json
import pandas as pd


def save_benchmark_report(result, output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    json_path = output / "benchmark_report.json"
    json_path.write_text(
        json.dumps(result.to_dict(), indent=2, default=float),
        encoding="utf-8",
    )

    rows = []
    for method, payload in result.methods.items():
        row = {"method": method, **payload["metrics"]}
        rows.append(row)
    csv_path = output / "benchmark_metrics.csv"
    pd.DataFrame(rows).sort_values(
        ["f1", "localization_recall_at_k", "auprc"],
        ascending=False,
    ).to_csv(csv_path, index=False)

    markdown_path = output / "BENCHMARK_REPORT.md"
    lines = [
        "# PhiGraph Benchmark Report",
        "",
        f"Dataset: `{result.dataset['name']}`",
        "",
        "## Ranking",
        "",
    ]
    for index, method in enumerate(result.ranking, start=1):
        metrics = result.methods[method]["metrics"]
        lines.append(
            f"{index}. **{method}** — F1={metrics['f1']:.3f}, "
            f"AUPRC={metrics['auprc']:.3f}, "
            f"Localization recall@k={metrics['localization_recall_at_k']:.3f}, "
            f"Runtime={metrics['runtime_seconds']:.3f}s"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "json": json_path,
        "csv": csv_path,
        "markdown": markdown_path,
    }
