from __future__ import annotations

import argparse
import json

from phigraph.validation import (
    CICIDSValidationConfig,
    run_cicids2017_validation,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument(
        "--output",
        default="validation_results/cicids2017_friday_ddos",
    )
    parser.add_argument("--seed", type=int, default=47)
    args = parser.parse_args()

    report = run_cicids2017_validation(
        args.csv_path,
        args.output,
        CICIDSValidationConfig(seed=args.seed),
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
