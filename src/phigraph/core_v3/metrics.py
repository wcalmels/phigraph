from __future__ import annotations

from collections import Counter
from threading import RLock
from typing import Any


class CoreMetrics:
    def __init__(self) -> None:
        self._counter: Counter[str] = Counter()
        self._lock = RLock()

    def inc(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counter[name] += value

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"counters": dict(sorted(self._counter.items()))}

    def prometheus(self) -> str:
        with self._lock:
            lines = ["# TYPE phigraph_core_counter counter"]
            for name, value in sorted(self._counter.items()):
                safe = name.replace(".", "_").replace("-", "_")
                lines.append(f'phigraph_core_{safe} {value}')
            return "\n".join(lines) + "\n"
