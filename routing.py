"""Graph loading, lighting-aware route search, and GeoJSON serialization."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import networkx as nx

from .demo_data import build_demo_graph, haversine_m


def load_graph_artifact(path: Path) -> tuple[nx.Graph, list[dict[str, Any]], bool]:
    """Load a pipeline-produced graph artifact; fall back to the demo graph."""
    if not path.exists():
        graph, lamps = build_demo_graph()
        return graph, lamps, True

    payload = json.loads(path.read_text(encoding="utf-8"))
    graph = nx.Graph()
    for node in payload.get("nodes", []):
        graph.add_node(str(node["id"]), lat=float(node["lat"]), lng=float(node["lng"]))
    for edge in payload.get("edges", []):
        u, v = str(edge["u"]), str(edge["v"])
        if u not in graph or v not in graph:
            continue
        graph.add_edge(
            u, v,
            length_m=float(edge.get("length_m", 1)),
            light_score=float(edge.get("light_score", 0.4)),
            confidence=float(edge.get("confidence", 0.0)),
            lamp_count=int(edge.get("lamp_count", 0)),
            max_gap_m=float(edge.get("max_gap_m", 60)),
            osm_lit=edge.get("osm_lit", "unknown"),
            data_sources=edge.get("data_sources", ["OpenStreetMap"]),
            geometry=edge.get("geometry") or [
                [graph.nodes[u]["lng"], graph.nodes[u]["lat"]],
                [graph.nodes[v]["lng"], graph.nodes[v]["lat"]],
            ],
        )
    if graph.number_of_nodes() < 2 or graph.number_of_edges() < 1:
        raise ValueError(f"Graph artifact {path} contains too few nodes/edges.")
    return graph, payload.get("lamps", []), bool(payload.get("demo_mode", False))


def edge_cost(data: dict[str, Any], alpha: float) -> float:
    """Distance-weighted cost; alpha=0 means pure shortest distance."""
    score = float(data.get("light_score", 0.4))
    confidence = float(data.get("confidence", 0))
    unknown_penalty = 0.1 if confidence < 0.3 else 0.0
    return float(data.get("length_m", 1)) * (1 + alpha * ((1 - score) + unknown_penalty))


def nearest_node(graph: nx.Graph, lat: float, lng: float) -> str:
    best_node, best_dist = None, float("inf")
    for node, data in graph.nodes(data=True):
        dist = haversine_m(lat, lng, data["lat"], data["lng"])
        if dist < best_dist:
            best_node, best_dist = node, dist
    if best_node is None:
        raise ValueError("The routing graph is empty.")
    if best_dist > 500:
        raise ValueError("This location is outside the current demo coverage area. Pick a point closer to the campus map.")
    return best_node


def _path_edges(graph: nx.Graph, path: list[str]) -> list[dict[str, Any]]:
    rows = []
    for u, v in zip(path, path[1:]):
        rows.append({"u": u, "v": v, **graph[u][v]})
    return rows


def _path_length(edges: list[dict[str, Any]]) -> float:
    return sum(float(edge.get("length_m", 0)) for edge in edges)


def _longest_dark_stretch(edges: list[dict[str, Any]]) -> float:
    best = current = 0.0
    for edge in edges:
        if float(edge.get("light_score", 0.4)) < 0.3:
            current += float(edge.get("length_m", 0))
            best = max(best, current)
        else:
            current = 0.0
    return round(best, 1)


def route_summary(edges: list[dict[str, Any]], pace_mps: float) -> dict[str, Any]:
    distance = _path_length(edges)
    lit_distance = sum(e["length_m"] for e in edges if e["light_score"] >= 0.6)
    low_conf_distance = sum(e["length_m"] for e in edges if e["confidence"] < 0.3)
    return {
        "distance_m": round(distance),
        "duration_s": round(distance / max(pace_mps, 0.1)),
        "pct_well_lit": round(lit_distance / distance, 3) if distance else 0,
        "longest_dark_m": _longest_dark_stretch(edges),
        "lamp_count": sum(int(e.get("lamp_count", 0)) for e in edges),
        "pct_low_confidence": round(low_conf_distance / distance, 3) if distance else 0,
        "geometry": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": edge["geometry"]},
                    "properties": {
                        "u": edge["u"], "v": edge["v"],
                        "light_score": edge["light_score"],
                        "confidence": edge["confidence"],
                        "lamp_count": edge.get("lamp_count", 0),
                        "max_gap_m": edge.get("max_gap_m", 0),
                        "length_m": edge["length_m"],
                        "data_sources": edge.get("data_sources", []),
                        "osm_lit": edge.get("osm_lit", "unknown"),
                    },
                }
                for edge in edges
            ],
        },
    }


def calculate_routes(
    graph: nx.Graph,
    from_lat: float, from_lng: float, to_lat: float, to_lng: float,
    alpha: float = 2.0, pace: float = 1.4,
) -> dict[str, Any]:
    """Return fastest and lighting-weighted routes with a detour limit."""
    source = nearest_node(graph, from_lat, from_lng)
    target = nearest_node(graph, to_lat, to_lng)
    if source == target:
        raise ValueError("Start and destination are too close together. Pick two different points.")

    try:
        shortest_path = nx.shortest_path(graph, source, target, weight="length_m")
        shortest_edges = _path_edges(graph, shortest_path)
    except nx.NetworkXNoPath as exc:
        raise LookupError("No walking route connects those locations.") from exc

    baseline_length = _path_length(shortest_edges)
    best_path = shortest_path
    used_alpha = 0.0
    # Reduce alpha if the lighting preference exceeds the plan's 1.6x detour guardrail.
    trial_alphas = sorted({max(0.0, min(3.0, alpha)), 2.0, 1.5, 1.0, 0.5, 0.0}, reverse=True)
    for candidate_alpha in trial_alphas:
        try:
            candidate_path = nx.shortest_path(
                graph, source, target,
                weight=lambda u, v, d: edge_cost(d, candidate_alpha),
            )
            candidate_edges = _path_edges(graph, candidate_path)
            if _path_length(candidate_edges) <= baseline_length * 1.6 + 1:
                best_path, used_alpha = candidate_path, candidate_alpha
                break
        except nx.NetworkXNoPath:
            continue

    bright_edges = _path_edges(graph, best_path)
    fastest = route_summary(shortest_edges, pace)
    brightest = route_summary(bright_edges, pace)
    return {
        "fastest": fastest,
        "brightest": brightest,
        "delta": {
            "extra_time_s": max(0, brightest["duration_s"] - fastest["duration_s"]),
            "extra_distance_m": max(0, brightest["distance_m"] - fastest["distance_m"]),
        },
        "routing_alpha_used": used_alpha,
        "start_node": source,
        "destination_node": target,
    }


def all_edges_geojson(graph: nx.Graph) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": data["geometry"]},
                "properties": {
                    "light_score": data["light_score"],
                    "confidence": data["confidence"],
                    "lamp_count": data.get("lamp_count", 0),
                    "max_gap_m": data.get("max_gap_m", 0),
                    "length_m": data["length_m"],
                    "data_sources": data.get("data_sources", []),
                },
            }
            for _, _, data in graph.edges(data=True)
        ],
    }


def generated_demo_lamps(graph: nx.Graph) -> list[dict[str, Any]]:
    """Create clearly marked illustrative fixture markers for graph artifacts lacking lamps."""
    rows = []
    index = 0
    for _, _, data in graph.edges(data=True):
        coords = data["geometry"]
        count = min(int(data.get("lamp_count", 0)), 3)
        for k in range(count):
            fraction = (k + 1) / (count + 1)
            rows.append({
                "id": f"fixture-{index}", "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [
                    coords[0][0] + (coords[-1][0] - coords[0][0]) * fraction,
                    coords[0][1] + (coords[-1][1] - coords[0][1]) * fraction,
                ]},
                "properties": {"sources": ["estimated edge count"], "confidence": data.get("confidence", 0), "synthetic": True},
            })
            index += 1
    return rows
