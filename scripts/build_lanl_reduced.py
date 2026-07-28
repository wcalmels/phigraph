from __future__ import annotations

import argparse
import json

from phigraph.validation.lanl import (
    LANLReductionConfig,
    reduce_lanl_dataset,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create a reproducible reduced LANL cyber1 subset "
            "by streaming windows around red-team events."
        )
    )
    parser.add_argument("raw_dir")
    parser.add_argument(
        "--output",
        default="validation_results/lanl_reduced",
    )
    parser.add_argument(
        "--profile",
        choices=["documentation-minimal", "validation-extended"],
        default="documentation-minimal",
    )
    args = parser.parse_args()

    config = (
        LANLReductionConfig.documentation_minimal()
        if args.profile == "documentation-minimal"
        else LANLReductionConfig.validation_extended()
    )
    manifest = reduce_lanl_dataset(
        args.raw_dir,
        args.output,
        config,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
