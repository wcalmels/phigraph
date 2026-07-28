from .base import DomainProfile


DOMAIN_PROFILES = {
    "fleet": DomainProfile(
        name="fleet",
        node_types=("truck", "driver", "route", "shift", "fuel_station"),
        edge_types=("assigned_to", "operates_on", "loads_at", "shares_shift"),
        recommended_signals=(
            "fuel_per_ton",
            "cycle_time",
            "idle_time",
            "downtime",
            "maintenance_events",
        ),
        allowed_interventions=(
            "simulate_shift_reassignment",
            "simulate_route_reassignment",
            "simulate_equipment_removal",
        ),
        required_human_approval=(
            "change_real_assignment",
            "send_disciplinary_alert",
        ),
    ),
    "mining": DomainProfile(
        name="mining",
        node_types=("equipment", "sensor", "process_stage", "material_stream"),
        edge_types=("feeds", "drives", "measures", "recirculates"),
        recommended_signals=(
            "vibration",
            "temperature",
            "current",
            "throughput",
            "particle_size",
        ),
        allowed_interventions=(
            "simulate_component_isolation",
            "simulate_feed_change",
        ),
        required_human_approval=("stop_equipment", "change_process_setpoint"),
    ),
    "supply_chain": DomainProfile(
        name="supply_chain",
        node_types=("supplier", "plant", "warehouse", "carrier", "port"),
        edge_types=("supplies", "ships_to", "depends_on"),
        recommended_signals=("lead_time", "inventory", "delay", "failure_rate"),
        allowed_interventions=("simulate_supplier_removal", "simulate_route_change"),
        required_human_approval=("cancel_supplier", "reroute_real_shipment"),
    ),
    "cybersecurity": DomainProfile(
        name="cybersecurity",
        node_types=("user", "credential", "device", "server", "process"),
        edge_types=("logs_into", "communicates_with", "executes", "accesses"),
        recommended_signals=("login_risk", "traffic_volume", "privilege_change"),
        allowed_interventions=("simulate_block_credential", "simulate_isolate_device"),
        required_human_approval=("block_real_account", "isolate_real_device"),
    ),
    "fraud": DomainProfile(
        name="fraud",
        node_types=("account", "person", "device", "merchant", "beneficiary"),
        edge_types=("transfers_to", "uses", "owns", "pays"),
        recommended_signals=("transaction_value", "velocity", "risk_score"),
        allowed_interventions=("simulate_freeze_account", "simulate_remove_transfer"),
        required_human_approval=("freeze_real_account", "report_customer"),
    ),
    "energy": DomainProfile(
        name="energy",
        node_types=("generator", "substation", "transformer", "feeder", "load"),
        edge_types=("transmits_to", "feeds", "measures"),
        recommended_signals=("voltage", "current", "frequency", "loss"),
        allowed_interventions=("simulate_disconnect_feeder",),
        required_human_approval=("disconnect_real_feeder",),
    ),
    "telecom": DomainProfile(
        name="telecom",
        node_types=("cell", "router", "link", "customer_segment", "service"),
        edge_types=("routes_to", "serves", "depends_on"),
        recommended_signals=("latency", "packet_loss", "traffic", "drop_rate"),
        allowed_interventions=("simulate_remove_link", "simulate_rebalance_traffic"),
        required_human_approval=("disable_real_link",),
    ),
}
