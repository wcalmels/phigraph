from phigraph.advisory import *

def test_queue_permissions_simulation_and_promotion(tmp_path):
    queue=AdvisoryQueue(tmp_path/"queue.json")
    action=AdvisoryAction("inspect","truck:118",True,.5,.1,{})
    case=queue.enqueue(recommendation={"x":1},action=action.to_dict(),
        governance_decision="ACCEPT_WITH_REVIEW",readiness_grade="shadow_ready")
    auth=authorize_action(action,requested_level=2,policy=PermissionPolicy(),human_approved=True)
    assert auth["authorized"]
    sim=simulate_reversible_action(action,confidence=.8,readiness_score=.8)
    assert sim.recommended
    queue.decide(case.case_id,reviewer="ops",decision="approved",authorized_level=2)
    assert queue.list_cases()[0].status=="approved"
    promo=evaluate_promotion(MaturityState(1,20,10,.8,.2,.7,.85,1.0))
    assert promo.promoted
