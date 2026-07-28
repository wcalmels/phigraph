from phigraph.meta.bandit import BanditArm, ucb1_select
from phigraph.meta.evaluator import choose_next_configuration
from phigraph.meta.store import ExperimentRecord

def test_ucb_explores_untried_arm():
    decision = ucb1_select(
        [
            BanditArm("a", {"x":1}, 3, 0.8),
            BanditArm("b", {"x":2}, 0, 0.0),
        ],
        total_pulls=3,
    )
    assert decision.selected_arm == "b"
    assert decision.exploration

def test_choose_next_configuration():
    records = [
        ExperimentRecord("1","t","fleet",{"engineered_signal":"a"}, {}, 0.8, True),
    ]
    decision = choose_next_configuration(
        records,
        [{"engineered_signal":"a"},{"engineered_signal":"b"}],
    )
    assert decision.selected_configuration["engineered_signal"] == "b"
