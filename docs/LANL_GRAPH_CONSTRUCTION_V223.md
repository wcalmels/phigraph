# LANL Heterogeneous Graph Construction — PhiGraph v2.2.3

This stage converts reduced LANL files into a heterogeneous temporal graph.

Node types: user, computer, process.

Relations: uses, authenticates_to, authenticates_as, executes, resolves,
communicates_with.

Outputs: GraphML, nodes.csv, edges.csv, graph_summary.json, anomalies.json,
attack_paths.json and report.json.

The current score combines relationship rarity, edge-type rarity, remote
authentication relevance, process/network context and centrality. Official
red-team labels are currently used to annotate and boost demonstrative scores,
so this stage validates graph construction and path documentation, not an
unbiased benchmark. A later benchmark must calculate scores label-free.

Run:

```powershell
python scripts\build_lanl_graph.py `
  "validation_results\lanl_reduced_minimal" `
  --output "validation_results\lanl_graph_minimal"
```

A fixture result validates software only. Real LANL conclusions require the
official source files.
