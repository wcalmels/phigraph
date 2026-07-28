from phigraph.platform_general import DomainManifest,FieldContract,TableContract
from .base_tabular import TabularDomainAdapter
class MaintenanceAdapter(TabularDomainAdapter):
    def __init__(self):
        super().__init__(DomainManifest("maintenance","1.0.0","Industrial maintenance intelligence",
        ("asset","component","sensor","work_order","failure_mode"),("contains","measured_by","serviced_by","fails_as"),
        (TableContract("measurements",(FieldContract("asset_id",nullable=False),FieldContract("timestamp",nullable=False),
        FieldContract("metric",nullable=False),FieldContract("value",semantic_type="number"))),),
        ("vibration","temperature","current","pressure","failure_frequency"),
        ("inspect_asset","create_work_order","increase_sampling"),
        ("simulate_component_isolation","simulate_sensor_replacement"),
        ("stop_critical_asset_real","change_setpoint_real"),
        ("normalized","heat_025","signal_aware","temporal_050"),
        ("early_detection_rate","false_alarm_rate","downtime_avoided")),
        {},{"asset_id":"asset","metric":"sensor"},())
