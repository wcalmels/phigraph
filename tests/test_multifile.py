import pandas as pd

from phigraph.multifile import (
    EntityResolver,
    build_heterogeneous_graph,
    infer_join_candidates,
    profile_tables,
)


def sample_tables():
    fuel = pd.DataFrame(
        {
            "camion": ["KLG-118", "KLG-119", "KLG-118"],
            "fecha": ["2026-07-01", "2026-07-01", "2026-07-02"],
            "litros": [500.0, 420.0, 510.0],
        }
    )
    trips = pd.DataFrame(
        {
            "equipo": ["118", "119"],
            "ruta": ["CMC-TMP", "CMC-TMP"],
            "toneladas": [140.0, 112.0],
        }
    )
    return {"fuel": fuel, "trips": trips}


def test_catalog_and_join_candidates():
    tables = sample_tables()
    catalog = profile_tables(tables)
    assert len(catalog.tables) == 2

    joins = infer_join_candidates(tables, min_overlap=0.5)
    assert joins
    assert joins[0].overlap_ratio >= 0.5


def test_entity_resolver_normalizes_equipment_ids():
    resolver = EntityResolver()
    registry = resolver.build_registry(["KLG-118", "Equipo 118", "118"])
    assert "118" in registry
    assert len(registry["118"]) == 3


def test_build_heterogeneous_graph():
    tables = sample_tables()
    joins = infer_join_candidates(tables, min_overlap=0.5)
    graph = build_heterogeneous_graph(tables, joins)
    assert graph.graph.number_of_nodes() > 0
    assert graph.graph.number_of_edges() > 0
