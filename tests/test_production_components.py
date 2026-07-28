import pandas as pd
from phigraph.production import *

def test_contract_drift_calibration_and_safety(tmp_path):
    ref={"t":pd.DataFrame({"id":[1,2,3],"x":[1.,2.,3.]})}
    cur={"t":pd.DataFrame({"id":[1,2,3],"x":[1.1,2.1,3.2]})}
    contract=validate_data_contracts(cur,(DataContract("t",("id","x"),unique_columns=("id",)),))
    assert contract.passed
    drift=detect_drift(ref,cur)
    assert 0<=drift.total_drift<=1
    cal=calibrate_scores([.1,.2,.9],[0,0,1])
    assert cal.brier_score is not None
    fusion=fuse_evidence(data_quality=1,ensemble_agreement=.8,robustness=.8,
                         statistical_evidence=.9,calibration_quality=.8,drift_quality=.9)
    gate=evaluate_safety_gate(contract_passed=True,drift_status="ok",
                              evidence_decision=fusion.decision,human_approval=True,
                              rollback_available=True)
    assert gate.allowed_level>=1
    shadow=ShadowModeRunner(tmp_path/"shadow.json")
    shadow.record(recommendation={"action":"inspect"})
    assert len(shadow.list())==1
