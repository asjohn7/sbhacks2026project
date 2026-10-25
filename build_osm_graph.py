"""Build the local walking graph and street-light evidence from OpenStreetMap.

Run from the repository root after installing pipeline/requirements.txt.
The resulting graph.json is read automatically by the FastAPI backend.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
from shapely.geometry import LineString, Point, shape

ROOT = Path(__file__).resolve().parents[1]
AREA_FILE = ROOT / "config" / "area.geojson"
OUTPUT = ROOT / "data" / "processed" / "graph.json"
DETECTIONS_FILE = ROOT / "data" / "processed" / "detections.json"


def normalize_lit(value) -> str:
    value = str(value or "unknown").strip().lower()
    if value in {"yes", "no", "automatic", "24/7", "disused"}:
        return value
    return "unknown"


def edge_identity(u, v) -> str:
    return "|".join(sorted((str(u), str(v))))


def clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def load_detection_votes() -> dict[str, list[dict]]:
    if not DETECTIONS_FILE.exists():
        return {}
    try:
        rows = json.loads(DETECTIONS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    grouped = defaultdict(list)
    for row in rows:
        edge_id = row.get("edge_id")
        for detection in row.get("detections", []):
            if float(detection.get("score", 0)) >= 0.15:
                grouped[edge_id].append(detection)
    return dict(grouped)


def main() -> None:
    area = json.loads(AREA_FILE.read_text(encoding="utf-8"))
    polygon = shape(area["features"][0]["geometry"])
    print("Downloading the walking network from OpenStreetMap…")
    graph = ox.graph_from_polygon(polygon, network_type="walk", simplify=True)
    projected = ox.project_graph(graph)

    print("Querying mapped street lamps…")
    try:
        lamps = ox.features_from_polygon(polygon, tags={"highway": "street_lamp"})
        lamps = lamps[~lamps.geometry.is_empty].copy()
        if len(lamps):
            lamps_projected = lamps.to_crs(projected.graph["crs"])
            lamp_points = lamps_projected.geometry.centroid
            lamp_points = gpd.GeoSeries(lamp_points, crs=projected.graph["crs"])
            lamp_points_wgs84 = lamp_points.to_crs("EPSG:4326")
        else:
            lamps_projected = gpd.GeoDataFrame(geometry=[], crs=projected.graph["crs"])
            lamp_points = gpd.GeoSeries([], crs=projected.graph["crs"])
            lamp_points_wgs84 = gpd.GeoSeries([], crs="EPSG:4326")
    except Exception as exc:
        print(f"Lamp query unavailable ({exc}); continuing with lit tags only.")
        lamps_projected = gpd.GeoDataFrame(geometry=[], crs=projected.graph["crs"])
        lamp_points = gpd.GeoSeries([], crs=projected.graph["crs"])
        lamp_points_wgs84 = gpd.GeoSeries([], crs="EPSG:4326")

    detector_votes = load_detection_votes()
    nodes = []
    for node_id, attrs in graph.nodes(data=True):
        nodes.append({"id": str(node_id), "lat": float(attrs["y"]), "lng": float(attrs["x"])})

    node_lookup = {str(n["id"]): n for n in nodes}
    # Collapse OSM's two directed edges into one walkable undirected edge.
    edge_choices = {}
    for u, v, key, attrs in graph.edges(keys=True, data=True):
        u_s, v_s = str(u), str(v)
        if u_s == v_s:
            continue
        identity = edge_identity(u_s, v_s)
        geom = attrs.get("geometry")
        if geom is None:
            geom = LineString([
                (node_lookup[u_s]["lng"], node_lookup[u_s]["lat"]),
                (node_lookup[v_s]["lng"], node_lookup[v_s]["lat"]),
            ])
        candidate = {
            "u": u_s, "v": v_s, "length_m": float(attrs.get("length", geom.length * 85000)),
            "geometry": [[float(x), float(y)] for x, y in geom.coords],
            "osm_lit": normalize_lit(attrs.get("lit")),
            "road_type": str(attrs.get("highway", "unknown")),
            "edge_id": identity,
        }
        if identity not in edge_choices or candidate["length_m"] < edge_choices[identity]["length_m"]:
            edge_choices[identity] = candidate

    lamp_geometries = list(lamp_points) if len(lamp_points) else []
    lamp_sindex = lamps_projected.sindex if len(lamps_projected) else None
    projected_edge_lookup = {}
    for u, v, key, attrs in projected.edges(keys=True, data=True):
        identity = edge_identity(u, v)
        if identity not in projected_edge_lookup:
            geom = attrs.get("geometry")
            if geom is None:
                a, b = projected.nodes[u], projected.nodes[v]
                geom = LineString([(a["x"], a["y"]), (b["x"], b["y"])])
            projected_edge_lookup[identity] = geom

    edges = []
    uses_mapillary = False
    for identity, edge in edge_choices.items():
        geom = projected_edge_lookup.get(identity)
        length = max(1.0, float(edge["length_m"]))
        nearby = []
        if geom is not None and lamp_sindex is not None:
            try:
                candidate_indexes = lamp_sindex.query(geom.buffer(20), predicate="intersects")
                nearby = [lamp_geometries[int(i)] for i in candidate_indexes if geom.distance(lamp_geometries[int(i)]) <= 20]
            except Exception:
                nearby = [point for point in lamp_geometries if geom.distance(point) <= 20]
        lamp_count_osm = len(nearby)
        projected_positions = sorted(geom.project(point) for point in nearby) if geom is not None else []
        if projected_positions:
            stops = [0.0] + projected_positions + [min(length, float(geom.length))]
            max_gap = max((b - a for a, b in zip(stops, stops[1:])), default=length)
        else:
            max_gap = min(length, 120.0)
        max_gap = max(0.0, max_gap)
        density = lamp_count_osm / length * 100
        density_term = min(density / 3.0, 1.0)
        gap_term = 1 - min(max_gap / 60.0, 1.0)
        lit = edge["osm_lit"]
        bonus = 0.15 if lit in {"yes", "24/7", "automatic"} else (-0.2 if lit == "no" else 0.0)
        base_score = clip(0.5 * density_term + 0.5 * gap_term + bonus)

        votes = detector_votes.get(identity, [])
        detector_count = len(votes)
        total_count = lamp_count_osm + detector_count
        if detector_count:
            uses_mapillary = True
            # Fixture detections are attributed to the nearest route edge; they are
            # not claimed to be precisely geolocated lamp positions.
            density_total = total_count / length * 100
            density_term_total = min(density_total / 3.0, 1.0)
            score = clip(0.5 * density_term_total + 0.5 * gap_term + bonus)
        else:
            score = base_score
        if lit != "unknown":
            confidence = 0.78 if lit == "yes" else 0.74
        elif lamp_count_osm:
            confidence = 0.62
        else:
            confidence = 0.42
        if detector_count:
            confidence = min(0.92, confidence + min(0.08, detector_count * 0.02))
        sources = []
        if lamp_count_osm:
            sources.append("OpenStreetMap street lamps")
        if lit != "unknown":
            sources.append("OpenStreetMap lit tag")
        if detector_count:
            sources.append("Mapillary imagery + OWL-ViT detection")
        if not sources:
            sources.append("OpenStreetMap walking network; lighting unknown")
        edge.update({
            "lamp_count": int(total_count),
            "max_gap_m": round(float(max_gap), 1),
            "light_score": round(float(score), 3),
            "confidence": round(float(confidence), 2),
            "data_sources": sources,
        })
        edges.append(edge)

    # Mapillary imagery remains optional. OSM lamp features are exported as actual points.
    lamp_features = []
    for index, point in enumerate(lamp_points_wgs84):
        original_feature = lamps.iloc[index]
        coord = [float(point.x), float(point.y)]
        lamp_features.append({
            "id": f"osm-lamp-{index}", "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coord},
            "properties": {
                "sources": ["OpenStreetMap highway=street_lamp"],
                "confidence": 0.82,
                "synthetic": False,
                "osm_id": str(original_feature.name),
            },
        })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "demo_mode": False,
        "uses_mapillary": uses_mapillary,
        "area_name": area["features"][0].get("properties", {}).get("name", "OSM area"),
        "nodes": nodes,
        "edges": edges,
        "lamps": lamp_features,
        "metadata": {
            "road_graph": "OpenStreetMap via OSMnx",
            "street_lamp_features": len(lamp_features),
            "edges_with_vision_evidence": sum(1 for edge in edges if any("OWL-ViT" in s for s in edge["data_sources"])),
            "lighting_score_note": "Heuristic from OSM lamp points, lit tags, and optional image detections; not measured lux.",
        },
    }
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {len(nodes)} nodes and {len(edges)} edges to {OUTPUT}")
    print(f"OpenStreetMap lamp points: {len(lamp_features)}; detector votes integrated: {sum(len(v) for v in detector_votes.values())}")
    print("Restart the backend so it reloads the artifact.")


if __name__ == "__main__":
    main()
