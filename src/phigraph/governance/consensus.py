from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class AgentVote:
    agent: str
    decision: str
    confidence: float
    veto: bool = False
    reasons: tuple[str, ...] = ()
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class ConsensusResult:
    decision: str
    weighted_support: float
    vetoed_by: tuple[str, ...]
    missing_required_agents: tuple[str, ...]
    votes: tuple[AgentVote, ...]
    reasons: tuple[str, ...]
    def to_dict(self): return asdict(self)

_POSITIVE={"ACCEPT","ACCEPT_WITH_REVIEW","ALLOWED","production_candidate","shadow_ready","ok"}
_NEGATIVE={"REJECT","BLOCKED","BLOCKED_BY_DATA","BLOCKED_BY_DRIFT",
           "BLOCKED_BY_EVIDENCE","INSUFFICIENT_EVIDENCE","laboratory_only","warning"}

def resolve_consensus(votes, policy, contradictions=()):
    by_agent={vote.agent:vote for vote in votes}
    required={role.name for role in policy.roles if role.required}
    missing=tuple(sorted(required-set(by_agent)))
    vetoed=[]
    weighted=0.0
    weight_total=0.0
    for role in policy.roles:
        vote=by_agent.get(role.name)
        if vote is None:
            continue
        weight_total += role.weight
        positive=vote.decision in _POSITIVE
        negative=vote.decision in _NEGATIVE
        signed=(1.0 if positive else (-1.0 if negative else 0.0))*max(0,min(1,vote.confidence))
        weighted += role.weight*signed
        if role.can_veto and (vote.veto or negative):
            vetoed.append(role.name)
    normalized=(weighted/weight_total+1.0)/2.0 if weight_total else 0.0
    reasons=[]
    if missing: reasons.append("required_agents_missing")
    if vetoed: reasons.append("veto_applied")
    if len(contradictions)>policy.max_contradictions:
        reasons.append("too_many_contradictions")
    if missing or vetoed or len(contradictions)>policy.max_contradictions:
        decision="REJECT"
    elif normalized>=policy.accept_threshold:
        decision="ACCEPT"
    elif normalized>=policy.review_threshold:
        decision="ACCEPT_WITH_REVIEW"
    else:
        decision="INSUFFICIENT_EVIDENCE"
    return ConsensusResult(decision,float(normalized),tuple(sorted(vetoed)),
                           missing,tuple(votes),tuple(reasons))
