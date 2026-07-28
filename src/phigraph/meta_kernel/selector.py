from dataclasses import dataclass, asdict
import math

@dataclass(frozen=True)
class KernelMetaDecision:
    selected_candidate:dict; score:float; exploration:bool; support:int
    contextual_similarity:float; candidate_scores:dict; reasons:tuple
    def to_dict(self): return asdict(self)

def _distance(a,b):
    keys=("nodes","edges","density","components","degree_cv","signal_variance",
          "temporal_snapshots","multiplex_layers")
    return sum(abs(float(a.get(k,0))-float(b.get(k,0)))/
               max(abs(float(a.get(k,0))),abs(float(b.get(k,0))),1.0) for k in keys)/len(keys)

def recommend_kernel_configuration(experiments,candidates,*,domain,current_context,exploration_strength=1.5):
    confirmed=[e for e in experiments if e.confirmed and e.domain==domain]
    scores={}; support={}; similarities={}
    for c in candidates:
        rows=[e for e in confirmed if e.candidate.get("name")==c.name]
        support[c.name]=len(rows)
        if not rows:
            scores[c.name]=float("inf"); similarities[c.name]=0.0; continue
        weights=[1/(1+_distance(current_context,e.context)) for e in rows]
        mean=sum(w*e.reward for w,e in zip(weights,rows))/sum(weights)
        bonus=math.sqrt(exploration_strength*math.log(max(len(confirmed),2))/len(rows))
        scores[c.name]=mean+bonus; similarities[c.name]=sum(weights)/len(weights)
    untried=[c for c in candidates if support[c.name]==0]
    if untried:
        c=untried[0]
        return KernelMetaDecision(c.to_dict(),float("inf"),True,0,0.0,scores,
            ("untested configuration selected for controlled exploration",
             "confirmed experiments only"))
    c=max(candidates,key=lambda x:scores[x.name])
    return KernelMetaDecision(c.to_dict(),float(scores[c.name]),True,support[c.name],
        similarities[c.name],{k:float(v) for k,v in scores.items()},
        ("context-weighted confirmed reward plus UCB bonus",
         "kernel family and hyperparameters selected jointly"))
