from dataclasses import dataclass
from enum import Enum
import time
class CircuitState(str,Enum): CLOSED="closed"; OPEN="open"; HALF_OPEN="half_open"
@dataclass
class CircuitBreaker:
    failure_threshold:int=3; recovery_timeout_seconds:float=30.0
    state:CircuitState=CircuitState.CLOSED; failures:int=0; opened_at:float|None=None
    def allow(self):
        if self.state==CircuitState.OPEN:
            if self.opened_at is not None and time.monotonic()-self.opened_at>=self.recovery_timeout_seconds:
                self.state=CircuitState.HALF_OPEN; return True
            return False
        return True
    def success(self): self.state=CircuitState.CLOSED; self.failures=0; self.opened_at=None
    def failure(self):
        self.failures+=1
        if self.failures>=self.failure_threshold:
            self.state=CircuitState.OPEN; self.opened_at=time.monotonic()
