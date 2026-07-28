from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    app = Path(__file__).with_name("run_webapp.py")
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "streamlit", "run", str(app)]
        )
    )
