from phigraph.platform_general import DomainManifest,FieldContract,TableContract
from .base_tabular import TabularDomainAdapter
class FleetAdapter(TabularDomainAdapter):
    def __init__(self):
        super().__init__(DomainManifest("fleet","1.0.0","Fleet and logistics intelligence",
        ("truck","driver","route","shift","fuel_station","maintenance_event"),
        ("assigned_to","operates_on","refuels_at","has_maintenance"),
        (TableContract("fuel",(FieldContract("truck_id",nullable=False),FieldContract("liters",semantic_type="number"))),
         TableContract("trips",(FieldContract("truck_id",nullable=False),FieldContract("route_id"),FieldContract("tons",semantic_type="number")))),
        ("fuel_per_ton","cycle_time","idle_time","downtime"),
        ("inspect_truck","review_route","create_maintenance_case"),
        ("simulate_remove_truck","simulate_route_reassignment","simulate_increase_monitoring"),
        ("stop_truck_real","disciplinary_action"),
        ("normalized","heat_050","signal_aware","temporal_050"),
        ("precision_at_k","fuel_saving_potential","downtime_reduction")),
        {"fuel":{"camion":"truck_id","litros":"liters"},"trips":{"equipo":"truck_id","ruta":"route_id","toneladas":"tons"}},
        {"truck_id":"truck","route_id":"route"},
        ({"source":"truck_id","target":"route_id","edge_type":"operates_on"},))
