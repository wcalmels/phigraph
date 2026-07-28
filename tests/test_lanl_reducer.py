from pathlib import Path

from phigraph.validation.lanl import (
    LANLReductionConfig,
    reduce_lanl_dataset,
)


def test_lanl_fixture_reduction(tmp_path):
    fixture = (
        Path(__file__).parents[1]
        / "data"
        / "lanl_reduced_fixture"
    )
    manifest = reduce_lanl_dataset(
        fixture,
        tmp_path / "output",
        LANLReductionConfig.documentation_minimal(),
    )
    assert manifest["redteam_events"] == 3
    assert manifest["attack_windows"] >= 1
    assert (tmp_path / "output" / "auth_reduced.csv").exists()
    assert (tmp_path / "output" / "proc_reduced.csv").exists()
    assert (tmp_path / "output" / "dns_reduced.csv").exists()
