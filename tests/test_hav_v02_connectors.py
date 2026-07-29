from phigraph.hav.connectors import CodeRepositoryConnector, GenericStateConnector


def test_generic_connector_builds_state():
    result = GenericStateConnector(source_system="test", facts=[{"subject":"system","predicate":"status","value":"passed"}]).collect()
    assert result.state.available is True
    assert result.state.evidence[0].value == "passed"

def test_generic_connector_fail_closed():
    result = GenericStateConnector(source_system="test", facts=[], available=False).collect()
    assert result.state.available is False
    assert not result.state.evidence

def test_code_connector_marks_required_checks():
    result = CodeRepositoryConnector(
        tests_passed=10, tests_total=10, ci_status="passed", codeql_status="failed",
        package_status="passed", docker_status="passed", release_gate_status="blocked",
    ).collect()
    assert len([e for e in result.state.evidence if e.metadata.get("required")]) == 5
