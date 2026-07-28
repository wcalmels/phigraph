from dataclasses import dataclass,asdict
from pathlib import Path
import shutil
@dataclass(frozen=True)
class HealthCheckResult:
    healthy:bool; checks:dict
    def to_dict(self): return asdict(self)
def run_health_checks(*,data_path="data",minimum_free_bytes=10_000_000):
    p=Path(data_path); p.mkdir(parents=True,exist_ok=True); u=shutil.disk_usage(p)
    c={"data_path_writable":p.exists() and p.is_dir(),"free_disk_bytes":u.free,
       "free_disk_ok":u.free>=minimum_free_bytes}
    return HealthCheckResult(bool(c["data_path_writable"] and c["free_disk_ok"]),c)
