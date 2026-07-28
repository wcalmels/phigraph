from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class ResourceLimits:
    max_nodes:int=10000; max_edges:int=100000; max_tables:int=50; max_total_rows:int=1_000_000
@dataclass(frozen=True)
class LimitCheckResult:
    passed:bool; violations:tuple[str,...]; observed:dict
    def to_dict(self): return asdict(self)
def check_resource_limits(*,tables=None,dataset=None,limits=ResourceLimits()):
    tables=tables or {}; rows=sum(len(f) for f in tables.values()); v=[]
    o={"tables":len(tables),"total_rows":rows,"nodes":dataset.size if dataset else 0,
       "edges":dataset.graph.number_of_edges() if dataset else 0}
    if o["tables"]>limits.max_tables:v.append("max_tables_exceeded")
    if rows>limits.max_total_rows:v.append("max_total_rows_exceeded")
    if dataset and o["nodes"]>limits.max_nodes:v.append("max_nodes_exceeded")
    if dataset and o["edges"]>limits.max_edges:v.append("max_edges_exceeded")
    return LimitCheckResult(not v,tuple(v),o)
