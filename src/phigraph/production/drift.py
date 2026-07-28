from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class DriftResult:
    feature_drift: float
    missingness_drift: float
    graph_proxy_drift: float
    total_drift: float
    status: str
    details: dict
    def to_dict(self): return asdict(self)

def _numeric_summary(frame: pd.DataFrame) -> dict[str,tuple[float,float]]:
    out={}
    for col in frame.select_dtypes(include="number").columns:
        series=frame[col].dropna().astype(float)
        if len(series):
            out[str(col)]=(float(series.mean()),float(series.std(ddof=0)))
    return out

def detect_drift(reference: dict[str,pd.DataFrame], current: dict[str,pd.DataFrame]) -> DriftResult:
    distances=[]
    missing=[]
    graph_proxy=[]
    details={}
    for name, cur in current.items():
        ref=reference.get(name)
        if ref is None:
            distances.append(1.0); missing.append(1.0); graph_proxy.append(1.0)
            details[name]={"status":"new_table"}
            continue
        rsum=_numeric_summary(ref); csum=_numeric_summary(cur)
        table_dist=[]
        for col in set(rsum)&set(csum):
            rm,rs=rsum[col]; cm,cs=csum[col]
            scale=max(abs(rm),abs(cm),rs,cs,1.0)
            table_dist.append(min(1.0,(abs(cm-rm)+abs(cs-rs))/scale))
        distances.append(float(np.mean(table_dist)) if table_dist else 0.0)
        rmiss=float(ref.isna().sum().sum()/max(ref.size,1))
        cmiss=float(cur.isna().sum().sum()/max(cur.size,1))
        missing.append(min(1.0,abs(cmiss-rmiss)))
        rcard=sum(ref[col].nunique(dropna=True) for col in ref.columns)/max(len(ref.columns),1)
        ccard=sum(cur[col].nunique(dropna=True) for col in cur.columns)/max(len(cur.columns),1)
        graph_proxy.append(min(1.0,abs(ccard-rcard)/max(rcard,1.0)))
        details[name]={"feature_drift":distances[-1],"missingness_drift":missing[-1],
                       "graph_proxy_drift":graph_proxy[-1]}
    fd=float(np.mean(distances)) if distances else 0.0
    md=float(np.mean(missing)) if missing else 0.0
    gd=float(np.mean(graph_proxy)) if graph_proxy else 0.0
    total=0.5*fd+0.2*md+0.3*gd
    status="ok" if total<0.20 else ("review_required" if total<0.40 else "blocked")
    return DriftResult(fd,md,gd,float(total),status,details)
