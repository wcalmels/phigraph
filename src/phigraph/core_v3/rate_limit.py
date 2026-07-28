from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import RLock


@dataclass
class SlidingWindowRateLimiter:
    limit: int = 120
    window_seconds: int = 60
    _events: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _lock: RLock = field(default_factory=RLock)

    def check(self, key: str, *, now: float | None = None) -> tuple[bool, int, int]:
        timestamp = time.time() if now is None else now
        cutoff = timestamp - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (timestamp - events[0])))
                return False, 0, retry_after
            events.append(timestamp)
            return True, self.limit - len(events), 0
