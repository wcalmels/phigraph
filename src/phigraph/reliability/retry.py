from dataclasses import dataclass
import time
@dataclass(frozen=True)
class RetryPolicy:
    max_attempts:int=3; initial_delay_seconds:float=.01; backoff_multiplier:float=2.0; max_delay_seconds:float=1.0
def run_with_retry(fn,*,policy=RetryPolicy(),retry_on=(Exception,)):
    delay=policy.initial_delay_seconds; last=None
    for a in range(1,policy.max_attempts+1):
        try: return fn(),a
        except retry_on as e:
            last=e
            if a>=policy.max_attempts: break
            time.sleep(delay); delay=min(policy.max_delay_seconds,delay*policy.backoff_multiplier)
    raise last
