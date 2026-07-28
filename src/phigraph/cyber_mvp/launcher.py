from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def main() -> None:
    dashboard = Path(__file__).with_name("dashboard.py")
    raise SystemExit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(dashboard),
            ]
        )
    )
