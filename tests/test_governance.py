from phigraph.governance import *

def test_consensus_veto_and_dossier(tmp_path):
    policy=default_governance_policy()
    votes=[
        AgentVote("data_contract","ok",1.0),
        AgentVote("drift_detection","ok",0.9),
        AgentVote("kernel_critic","ok",0.8),
        AgentVote("calibration","ok",0.8),
        AgentVote("evidence_fusion","ACCEPT",0.9),
        AgentVote("safety_gate","ALLOWED",1.0),
        AgentVote("production_readiness","production_candidate",0.9),
    ]
    result=resolve_consensus(votes,policy)
    assert result.decision=="ACCEPT"
    dossier=build_review_dossier(case_id="x",consensus=result,contradictions=(),
        artifacts={},proposed_action={"action":"inspect"})
    store=DecisionAuditStore(tmp_path/"audit.json")
    store.append(case_id="x",decision=result.decision,dossier=dossier.to_dict())
    assert len(store.list())==1

def test_contradiction_detection():
    rows=detect_contradictions({
        "data_contract":{"passed":True},
        "drift":{"status":"blocked"},
    })
    assert rows
