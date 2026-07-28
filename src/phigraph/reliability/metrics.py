from dataclasses import dataclass,field
from collections import defaultdict
import time
@dataclass
class MetricsRegistry:
    counters:dict=field(default_factory=lambda:defaultdict(float))
    gauges:dict=field(default_factory=dict)
    timings:dict=field(default_factory=lambda:defaultdict(list))
    def increment(self,n,v=1.0): self.counters[n]+=v
    def set_gauge(self,n,v): self.gauges[n]=float(v)
    def observe(self,n,v): self.timings[n].append(float(v))
    def timer(self,n):
        r=self
        class T:
            def __enter__(self): self.s=time.perf_counter(); return self
            def __exit__(self,*_): r.observe(n,time.perf_counter()-self.s)
        return T()
    def snapshot(self):
        return {"counters":dict(self.counters),"gauges":dict(self.gauges),
        "timings":{k:{"count":len(v),"mean":sum(v)/len(v) if v else 0.0,
        "max":max(v) if v else 0.0} for k,v in self.timings.items()}}
