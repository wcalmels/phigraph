from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from collections import Counter, defaultdict
import json, math
import networkx as nx
import pandas as pd

@dataclass(frozen=True)
class LANLGraphSummary:
    nodes:int; edges:int; node_types:dict; edge_types:dict
    time_min:int|None; time_max:int|None
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class LANLAnomaly:
    entity:str; entity_type:str; score:float; severity:str
    evidence:tuple[str,...]; redteam_related:bool
    def to_dict(self): return asdict(self)

def _node(kind,value): return f"{kind}:{value}"
def _read(path):
    path=Path(path)
    return pd.read_csv(path) if path.exists() else pd.DataFrame()

def build_lanl_graph(reduced_dir):
    d=Path(reduced_dir); g=nx.MultiDiGraph(dataset="LANL cyber1 reduced")
    auth=_read(d/"auth_reduced.csv"); proc=_read(d/"proc_reduced.csv")
    dns=_read(d/"dns_reduced.csv"); flows=_read(d/"flows_reduced.csv")
    labels=_read(d/"redteam_labels.csv")
    rt={(str(r.user),str(r.source_computer),str(r.destination_computer),int(r.time))
        for r in labels.itertuples(index=False)}
    for r in auth.itertuples(index=False):
        t=int(r.time); su=_node("user",r.source_user); du=_node("user",r.destination_user)
        sc=_node("computer",r.source_computer); dc=_node("computer",r.destination_computer)
        for n,k in ((su,"user"),(du,"user"),(sc,"computer"),(dc,"computer")):
            g.add_node(n,node_type=k)
        red=(str(r.source_user),str(r.source_computer),str(r.destination_computer),t) in rt
        g.add_edge(su,sc,edge_type="uses",time=t,source="auth",redteam=red,result=str(r.result))
        g.add_edge(sc,dc,edge_type="authenticates_to",time=t,source="auth",redteam=red,
                   authentication_type=str(r.authentication_type),logon_type=str(r.logon_type))
        g.add_edge(su,du,edge_type="authenticates_as",time=t,source="auth",redteam=red)
    for r in proc.itertuples(index=False):
        t=int(r.time); u=_node("user",r.user); c=_node("computer",r.computer); p=_node("process",r.process_name)
        g.add_node(u,node_type="user"); g.add_node(c,node_type="computer"); g.add_node(p,node_type="process")
        g.add_edge(u,c,edge_type="uses",time=t,source="proc",redteam=False)
        g.add_edge(c,p,edge_type="executes",time=t,source="proc",redteam=False,lifecycle=str(r.start_end))
    for r in dns.itertuples(index=False):
        t=int(r.time); s=_node("computer",r.source_computer); q=_node("computer",r.resolved_computer)
        g.add_node(s,node_type="computer"); g.add_node(q,node_type="computer")
        g.add_edge(s,q,edge_type="resolves",time=t,source="dns",redteam=False)
    for r in flows.itertuples(index=False):
        t=int(r.time); s=_node("computer",r.source_computer); q=_node("computer",r.destination_computer)
        g.add_node(s,node_type="computer"); g.add_node(q,node_type="computer")
        g.add_edge(s,q,edge_type="communicates_with",time=t,source="flows",redteam=False,
                   protocol=str(r.protocol),byte_count=float(r.byte_count),packet_count=float(r.packet_count))
    return g

def summarize_graph(g):
    nt=Counter(d.get("node_type","unknown") for _,d in g.nodes(data=True))
    et=Counter(d.get("edge_type","unknown") for *_,d in g.edges(data=True))
    times=[int(d["time"]) for *_,d in g.edges(data=True) if "time" in d]
    return LANLGraphSummary(g.number_of_nodes(),g.number_of_edges(),dict(nt),dict(et),
                            min(times) if times else None,max(times) if times else None)

def score_lanl_entities(g,top_k=20):
    rel=Counter((s,t,d.get("edge_type","unknown")) for s,t,d in g.edges(data=True))
    et=Counter(d.get("edge_type","unknown") for *_,d in g.edges(data=True))
    scores=defaultdict(float); ev=defaultdict(set); rt=set()
    for s,t,d in g.edges(data=True):
        typ=d.get("edge_type","unknown"); c=0.45/max(rel[(s,t,typ)],1)+0.15*math.sqrt(1/max(et[typ],1))
        if d.get("redteam"):
            c+=1.0; rt.update({s,t}); ev[s].add("official_redteam_edge"); ev[t].add("official_redteam_edge")
        if typ=="authenticates_to":
            c+=0.2; ev[s].add("remote_authentication_path"); ev[t].add("remote_authentication_path")
        if typ=="executes": c+=0.1; ev[s].add("process_execution")
        if typ=="communicates_with": c+=0.08; ev[s].add("network_flow"); ev[t].add("network_flow")
        scores[s]+=c; scores[t]+=c
    ug=g.to_undirected()
    deg=nx.degree_centrality(ug) if g.number_of_nodes()>1 else {}
    btw=nx.betweenness_centrality(ug) if g.number_of_nodes()<=5000 else {}
    for n in g.nodes:
        if deg.get(n,0)>0.15: scores[n]+=0.3*deg[n]; ev[n].add("high_degree_centrality")
        if btw.get(n,0)>0.05: scores[n]+=0.4*btw[n]; ev[n].add("bridge_entity")
    m=max(scores.values(),default=1.0) or 1.0; out=[]
    for n,v in scores.items():
        z=min(1.0,v/m); sev="critical" if z>=.8 else "high" if z>=.6 else "medium" if z>=.4 else "low"
        out.append(LANLAnomaly(n.split(":",1)[1],g.nodes[n].get("node_type","unknown"),
                               round(z,6),sev,tuple(sorted(ev[n])),n in rt))
    return sorted(out,key=lambda x:x.score,reverse=True)[:top_k]

def extract_attack_paths(g,cutoff=4):
    red=[(s,t,d) for s,t,d in g.edges(data=True) if d.get("redteam")]
    uniq={}
    for s,t,d in red:
        cand={s,t}
        for n in list(cand):
            cand.update(g.predecessors(n)); cand.update(g.successors(n))
        sub=g.subgraph(cand).to_undirected()
        for a in cand:
            for b in cand:
                if a==b: continue
                try: p=nx.shortest_path(sub,a,b)
                except nx.NetworkXNoPath: continue
                if 2<=len(p)<=cutoff+1:
                    uniq[tuple(p)]={"anchor_time":int(d.get("time",0)),"path":p,
                                    "node_types":[g.nodes[n].get("node_type","unknown") for n in p]}
    return list(uniq.values())

def export_graph_bundle(reduced_dir,output_dir,top_k=20):
    o=Path(output_dir); o.mkdir(parents=True,exist_ok=True)
    g=build_lanl_graph(reduced_dir); s=summarize_graph(g)
    a=score_lanl_entities(g,top_k); p=extract_attack_paths(g)
    nx.write_graphml(g,o/"lanl_graph.graphml")
    pd.DataFrame([{"node_id":n,**d} for n,d in g.nodes(data=True)]).to_csv(o/"nodes.csv",index=False)
    pd.DataFrame([{"source":s0,"target":t0,**d} for s0,t0,d in g.edges(data=True)]).to_csv(o/"edges.csv",index=False)
    (o/"graph_summary.json").write_text(json.dumps(s.to_dict(),indent=2),encoding="utf-8")
    (o/"anomalies.json").write_text(json.dumps([x.to_dict() for x in a],indent=2),encoding="utf-8")
    (o/"attack_paths.json").write_text(json.dumps(p,indent=2),encoding="utf-8")
    r={"summary":s.to_dict(),"top_anomalies":[x.to_dict() for x in a],"attack_paths":p,
       "executed":False,"interpretation":"Relational graph construction and ranking only; no real action executed."}
    (o/"report.json").write_text(json.dumps(r,indent=2),encoding="utf-8")
    return r
