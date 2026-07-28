from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import sqlite3, json, uuid

@dataclass(frozen=True)
class KernelExperiment:
    experiment_id:str; created_at:str; domain:str; context:dict
    candidate:dict; metrics:dict; reward:float; confirmed:bool

class KernelExperimentStore:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS kernel_experiments(
            experiment_id TEXT PRIMARY KEY,created_at TEXT,domain TEXT,context TEXT,
            candidate TEXT,metrics TEXT,reward REAL,confirmed INTEGER)""")
    def add(self,*,domain,context,candidate,metrics,reward,confirmed):
        r=KernelExperiment(str(uuid.uuid4()),datetime.now(timezone.utc).isoformat(),
            domain,context,candidate,metrics,float(reward),bool(confirmed))
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT INTO kernel_experiments VALUES (?,?,?,?,?,?,?,?)",
                (r.experiment_id,r.created_at,r.domain,json.dumps(r.context),
                 json.dumps(r.candidate),json.dumps(r.metrics),r.reward,int(r.confirmed)))
        return r
    def list(self,*,domain=None,confirmed_only=False):
        sql="SELECT * FROM kernel_experiments"; params=[]; clauses=[]
        if domain: clauses.append("domain=?"); params.append(domain)
        if confirmed_only: clauses.append("confirmed=1")
        if clauses: sql+=" WHERE "+" AND ".join(clauses)
        with sqlite3.connect(self.path) as c: rows=c.execute(sql,params).fetchall()
        return [KernelExperiment(x[0],x[1],x[2],json.loads(x[3]),json.loads(x[4]),
            json.loads(x[5]),float(x[6]),bool(x[7])) for x in rows]
