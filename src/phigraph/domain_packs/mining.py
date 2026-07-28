from phigraph.platform_general import DomainManifest,FieldContract,TableContract
from .base_tabular import TabularDomainAdapter
class MiningAdapter(TabularDomainAdapter):
    def __init__(self):
        super().__init__(DomainManifest("mining","1.0.0","Mining equipment and process intelligence",
        ("equipment","sensor","process_stage","material_stream","operator"),
        ("feeds","drives","measures","recirculates","operated_by"),
        (TableContract("process",(FieldContract("equipment_id",nullable=False),FieldContract("timestamp",nullable=False),
        FieldContract("throughput",semantic_type="number"))),),
        ("throughput","vibration","temperature","current","particle_size"),
        ("inspect_equipment","review_feed","create_process_case"),
        ("simulate_equipment_isolation","simulate_feed_change"),
        ("stop_equipment_real","change_process_setpoint_real"),
        ("normalized","heat_050","signal_aware","temporal_050"),
        ("throughput_stability","downtime_avoided","false_alarm_rate")),
        {},{"equipment_id":"equipment"},())
