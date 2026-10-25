"""Deterministic, illustrative demo graph used when no real graph artifact exists.

The demo graph is intentionally synthetic. Its scores and fixture markers are not
observations of real street lighting; the UI labels them as demo data.
"""
from __future__ import annotations

import math
from typing import Any

import networkx as nx

CENTER_LAT = 40.9144
CENTER_LNG = -73.1227
ROWS = 9
COLS = 9
LAT_STEP = 0.00165
LNG_STEP = 0.00215


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance between two geographic points in meters."""
    radius = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _score_for_edge(r1: int, c1: int, r2: int, c2: int) -> float:
    """Give route alternatives different scores without random run-to-run changes."""
    horizontal = r1 == r2
    corridor = r1 if horizontal else c1
    # A few main corridors are deliberately brighter, but not every edge is bright.
    base = 0.68 if corridor in (2, 4, 6) else 0.34
    # A stable small variation gives the route renderer a range of scores.
    signature = (r1 * 17 + c1 * 31 + r2 * 13 + c2 * 19) % 17
    variation = (signature - 8) * 0.025
    return round(max(0.12, min(0.96, base + variation)), 2)


def build_demo_graph() -> tuple[nx.Graph, list[dict[str, Any]]]:
    """Build a connected campus-sized grid for a no-keys-needed live demo."""
    graph = nx.Graph()
    for r in range(ROWS):
        for c in range(COLS):
            node_id = f"{r}-{c}"
            lat = CENTER_LAT + (r - (ROWS - 1) / 2) * LAT_STEP
            lng = CENTER_LNG + (c - (COLS - 1) / 2) * LNG_STEP
            graph.add_node(node_id, lat=lat, lng=lng)

    for r in range(ROWS):
        for c in range(COLS):
            for nr, nc in ((r + 1, c), (r, c + 1)):
                if nr >= ROWS or nc >= COLS:
                    continue
                # Preserve a connected grid but remove a few non-corridor links to
                # make alternatives feel like routes rather than a perfect lattice.
                if (r, c, nr, nc) in {(1, 3, 1, 4), (3, 5, 4, 5), (5, 2, 5, 3), (7, 6, 8, 6)}:
                    continue
                a = graph.nodes[f"{r}-{c}"]
                b = graph.nodes[f"{nr}-{nc}"]
                length = haversine_m(a["lat"], a["lng"], b["lat"], b["lng"])
                score = _score_for_edge(r, c, nr, nc)
                confidence = round(0.52 + ((r * 7 + c * 11 + nr * 3 + nc) % 45) / 100, 2)
                lamp_count = max(0, round((score * length) / 45))
                max_gap = round(max(12, min(110, 88 * (1 - score) + ((r + c) % 4) * 5)))
                graph.add_edge(
                    f"{r}-{c}", f"{nr}-{nc}",
                    length_m=round(length, 1), light_score=score,
                    confidence=confidence, lamp_count=lamp_count,
                    max_gap_m=max_gap, osm_lit="unknown",
                    data_sources=["illustrative demo data"],
                    geometry=[[a["lng"], a["lat"]], [b["lng"], b["lat"]]],
                )

    # Synthetic markers help demonstrate the fixture layer; never presented as real.
    lamps: list[dict[str, Any]] = []
    index = 0
    for u, v, data in graph.edges(data=True):
        p1, p2 = data["geometry"]
        for k in range(min(data["lamp_count"], 3)):
            fraction = (k + 1) / (min(data["lamp_count"], 3) + 1)
            lamps.append({
                "id": f"demo-lamp-{index}",
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [
                    p1[0] + (p2[0] - p1[0]) * fraction,
                    p1[1] + (p2[1] - p1[1]) * fraction,
                ]},
                "properties": {
                    "sources": ["illustrative demo marker"],
                    "confidence": data["confidence"],
                    "synthetic": True,
                },
            })
            index += 1
    return graph, lamps
