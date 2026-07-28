import pandas as pd
from phigraph.platform_general import GeneralPlatformRuntime,default_domain_registry
def test_domains_and_fleet_normalization():
    names={x["name"] for x in default_domain_registry().list()}
    assert {"cybersecurity","fleet","maintenance","fraud","mining"}.issubset(names)
    r=GeneralPlatformRuntime().prepare(domain="fleet",tables={
      "fuel":pd.DataFrame({"camion":["KLG-118"],"litros":[520.]}),
      "trips":pd.DataFrame({"equipo":["KLG-118"],"ruta":["R1"],"toneladas":[100.]})},
      requested_action="inspect_truck",mode="advisory")
    assert r.ready_for_core_pipeline
    assert r.adapter_output["normalized_tables"]["fuel"][0]["truck_id"]=="KLG-118"
def test_cyber_real_action_prohibited():
    r=GeneralPlatformRuntime().prepare(domain="cybersecurity",tables={"events":pd.DataFrame({
      "timestamp":["2026-07-24T00:00:00Z"],"user_id":["u1"],"device_id":["d1"],
      "event_type":["login"],"risk_score":[.9]})},requested_action="isolate_device_real",mode="sandbox")
    assert not r.ready_for_core_pipeline
