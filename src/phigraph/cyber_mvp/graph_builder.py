from __future__ import annotations

import networkx as nx
import pandas as pd


def _node(kind: str, value: object) -> str:
    return f"{kind}:{value}"


def build_security_graph(events: pd.DataFrame) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(domain="cybersecurity")

    for index, row in events.iterrows():
        event_id = (
            str(row.get("alert_id"))
            if pd.notna(row.get("alert_id"))
            else f"event-{index}"
        )
        event_node = _node("event", event_id)
        user_node = _node("user", row["user_id"])
        device_node = _node("device", row["device_id"])
        source_node = _node("ip", row["source_ip"])

        graph.add_node(
            event_node,
            node_type="event",
            event_type=row["event_type"],
            timestamp=row["timestamp"].isoformat(),
            risk_score=float(row["risk_score"]),
        )
        graph.add_node(user_node, node_type="user")
        graph.add_node(device_node, node_type="device")
        graph.add_node(source_node, node_type="ip")

        graph.add_edge(
            user_node,
            device_node,
            key=event_id,
            edge_type="authenticates",
            event_node=event_node,
            risk_score=float(row["risk_score"]),
        )
        graph.add_edge(
            source_node,
            device_node,
            key=event_id,
            edge_type="connects_to",
            event_node=event_node,
            risk_score=float(row["risk_score"]),
        )
        graph.add_edge(
            event_node,
            user_node,
            edge_type="involves",
        )
        graph.add_edge(
            event_node,
            device_node,
            edge_type="involves",
        )

        destination = row.get("destination_ip")
        if pd.notna(destination) and str(destination).strip():
            destination_node = _node("ip", destination)
            graph.add_node(destination_node, node_type="ip")
            graph.add_edge(
                device_node,
                destination_node,
                key=event_id,
                edge_type="communicates_with",
                event_node=event_node,
                risk_score=float(row["risk_score"]),
            )

        process = row.get("process_name")
        if pd.notna(process) and str(process).strip():
            process_node = _node("process", process)
            graph.add_node(process_node, node_type="process")
            graph.add_edge(
                device_node,
                process_node,
                key=event_id,
                edge_type="executes",
                event_node=event_node,
                risk_score=float(row["risk_score"]),
            )

        resource = row.get("resource_id")
        if pd.notna(resource) and str(resource).strip():
            resource_node = _node("resource", resource)
            graph.add_node(resource_node, node_type="resource")
            graph.add_edge(
                user_node,
                resource_node,
                key=event_id,
                edge_type="accesses",
                event_node=event_node,
                risk_score=float(row["risk_score"]),
            )

    return graph
