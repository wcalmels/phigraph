from phigraph.platform_general import DomainManifest,FieldContract,TableContract
from .base_tabular import TabularDomainAdapter
class CybersecurityAdapter(TabularDomainAdapter):
    def __init__(self):
        super().__init__(DomainManifest("cybersecurity","1.0.0","Identity, endpoint and network intelligence",
        ("user","credential","device","process","host","ip","alert","resource"),
        ("authenticates","executes","communicates_with","accesses","triggered"),
        (TableContract("events",(FieldContract("timestamp",nullable=False),FieldContract("user_id"),
        FieldContract("device_id"),FieldContract("event_type",nullable=False),FieldContract("risk_score",semantic_type="number"))),),
        ("risk_score","login_velocity","privilege_change","rare_process","lateral_movement_proxy"),
        ("investigate_user","investigate_device","increase_telemetry","create_security_case"),
        ("simulate_revoke_session","simulate_isolate_device","simulate_block_indicator"),
        ("delete_files","disable_critical_identity","modify_firewall_real","isolate_device_real"),
        ("normalized","heat_050","nonbacktracking","temporal_050"),
        ("precision_at_k","mean_time_to_detect","false_positive_rate","analyst_acceptance")),
        {"events":{"usuario":"user_id","equipo":"device_id","tipo_evento":"event_type","riesgo":"risk_score"}},
        {"user_id":"user","device_id":"device","event_type":"alert"},
        ({"source":"user_id","target":"device_id","edge_type":"authenticates"},))
