from phigraph.domains import get_domain_profile


def test_domain_profiles():
    fleet = get_domain_profile("fleet")
    assert "truck" in fleet.node_types
    assert "change_real_assignment" in fleet.required_human_approval
