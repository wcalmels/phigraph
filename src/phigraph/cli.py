from __future__ import annotations

import argparse

from .agent_demo import run_agent_demo
from .demo import run_demo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phigraph")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Run the synthetic fleet demo.")
    demo.add_argument("--output", default="results/demo")

    agent_demo = subparsers.add_parser(
        "agent-demo",
        help="Run the deterministic local multi-agent fleet workflow.",
    )
    agent_demo.add_argument("--output", default="results/agent-demo")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "demo":
        path = run_demo(args.output)
    elif args.command == "agent-demo":
        path = run_agent_demo(args.output)
    else:
        raise RuntimeError(f"Unsupported command: {args.command}")
    print(f"Report written to {path}")
