from __future__ import annotations

import argparse

from .benchmark import (
    BenchmarkConfig,
    make_synthetic_fleet,
    make_synthetic_fraud,
    run_benchmark,
    save_benchmark_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="phigraph-benchmark")
    parser.add_argument(
        "--dataset",
        choices=["fleet", "fraud"],
        default="fleet",
    )
    parser.add_argument("--output", default="results/benchmark")
    parser.add_argument("--seed", type=int, default=47)
    parser.add_argument("--null-controls", type=int, default=10)
    args = parser.parse_args()

    dataset = (
        make_synthetic_fleet(seed=args.seed)
        if args.dataset == "fleet"
        else make_synthetic_fraud(seed=args.seed)
    )
    result = run_benchmark(
        dataset,
        BenchmarkConfig(
            seed=args.seed,
            n_null_controls=args.null_controls,
        ),
    )
    paths = save_benchmark_report(result, args.output)
    print(f"Ranking: {', '.join(result.ranking)}")
    for kind, path in paths.items():
        print(f"{kind}: {path}")
