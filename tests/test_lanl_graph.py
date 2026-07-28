from pathlib import Path
from phigraph.validation.lanl.graph import build_lanl_graph,summarize_graph,score_lanl_entities,export_graph_bundle
def test_fixture_graph(tmp_path):
    reduced=Path(__file__).parents[1]/"validation_results"/"lanl_reduced_fixture"
    g=build_lanl_graph(reduced); s=summarize_graph(g)
    assert s.nodes>0 and s.edges>0
    assert s.node_types["user"]>0 and s.node_types["computer"]>0
    assert any(x.redteam_related for x in score_lanl_entities(g))
    r=export_graph_bundle(reduced,tmp_path/"bundle")
    assert r["executed"] is False
    assert (tmp_path/"bundle"/"lanl_graph.graphml").exists()
