"""Lumen Routes API."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .routing import all_edges_geojson, calculate_routes, generated_demo_lamps, load_graph_artifact

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH_PATH = ROOT / "data" / "processed" / "graph.json"
GRAPH_PATH = Path(os.getenv("LUMEN_GRAPH_PATH", str(DEFAULT_GRAPH_PATH)))
GRAPH, LAMPS, DEMO_MODE = load_graph_artifact(GRAPH_PATH)
try:
    USES_MAPILLARY = bool(json.loads(GRAPH_PATH.read_text(encoding="utf-8")).get("uses_mapillary", False)) if GRAPH_PATH.exists() else False
except (OSError, json.JSONDecodeError):
    USES_MAPILLARY = False
if not LAMPS:
    LAMPS = generated_demo_lamps(GRAPH)

app = FastAPI(
    title="Lumen Routes API",
    description="Lighting-aware walking routes. Lighting estimates are not a guarantee of safety.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
_GEOCODE_CACHE: dict[str, list[dict[str, Any]]] = {}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "graph_nodes": GRAPH.number_of_nodes(),
        "graph_edges": GRAPH.number_of_edges(),
        "demo_mode": DEMO_MODE,
        "graph_source": "illustrative demo graph" if DEMO_MODE else str(GRAPH_PATH),
        "uses_mapillary": USES_MAPILLARY,
    }


@app.get("/api/route")
def get_route(
    from_lat: float = Query(..., ge=-90, le=90),
    from_lng: float = Query(..., ge=-180, le=180),
    to_lat: float = Query(..., ge=-90, le=90),
    to_lng: float = Query(..., ge=-180, le=180),
    alpha: float = Query(2.0, ge=0, le=3),
    pace: float = Query(1.4, gt=0.2, le=3.0),
) -> dict[str, Any]:
    try:
        result = calculate_routes(GRAPH, from_lat, from_lng, to_lat, to_lng, alpha, pace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result["demo_mode"] = DEMO_MODE
    result["uses_mapillary"] = USES_MAPILLARY
    return result


@app.get("/api/edges")
def get_edges() -> dict[str, Any]:
    return all_edges_geojson(GRAPH)


@app.get("/api/lamps")
def get_lamps(
    bbox: str | None = Query(default=None, description="Optional minLng,minLat,maxLng,maxLat"),
) -> dict[str, Any]:
    rows = LAMPS
    if bbox:
        try:
            min_lng, min_lat, max_lng, max_lat = [float(v.strip()) for v in bbox.split(",")]
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="bbox must be minLng,minLat,maxLng,maxLat") from exc
        filtered = []
        for row in rows:
            coords = row.get("geometry", {}).get("coordinates", [])
            if len(coords) >= 2 and min_lng <= coords[0] <= max_lng and min_lat <= coords[1] <= max_lat:
                filtered.append(row)
        rows = filtered
    return {"type": "FeatureCollection", "features": rows, "demo_mode": DEMO_MODE, "uses_mapillary": USES_MAPILLARY}


@app.get("/api/geocode")
def geocode(q: str = Query(..., min_length=2, max_length=160)) -> dict[str, Any]:
    """Small, cached proxy to Nominatim; use only for the focused demo area."""
    normalized = q.strip().lower()
    if normalized in _GEOCODE_CACHE:
        return {"results": _GEOCODE_CACHE[normalized]}
    # Useful offline aliases for the default campus demo.
    aliases = {
        "melville library": {"label": "Melville Library (demo point)", "lat": 40.9146, "lon": -73.1232},
        "stony brook union": {"label": "Stony Brook Union (demo point)", "lat": 40.9135, "lon": -73.1177},
        "staller center": {"label": "Staller Center (demo point)", "lat": 40.9149, "lon": -73.1201},
        "sports complex": {"label": "Sports Complex (demo point)", "lat": 40.9121, "lon": -73.1166},
    }
    if normalized in aliases:
        result = [aliases[normalized]]
        _GEOCODE_CACHE[normalized] = result
        return {"results": result}
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "jsonv2", "limit": 5, "countrycodes": "us"},
            headers={"User-Agent": "LumenRoutesHackathon/0.1 (local student demo)"},
            timeout=3.5,
        )
        response.raise_for_status()
        results = [
            {"label": item.get("display_name", q), "lat": float(item["lat"]), "lon": float(item["lon"])}
            for item in response.json()
        ]
        _GEOCODE_CACHE[normalized] = results
        return {"results": results}
    except (requests.RequestException, ValueError, KeyError):
        raise HTTPException(status_code=503, detail="Search is unavailable. Try a campus preset, click the map, or enter latitude, longitude.")


@app.post("/api/report")
def create_report(report: dict[str, Any]) -> dict[str, Any]:
    """Save a simple lighting report locally (stretch feature)."""
    try:
        lat, lng = float(report["lat"]), float(report["lng"])
        report_type = str(report["type"])
        if report_type not in {"missing", "broken"}:
            raise ValueError("type must be 'missing' or 'broken'")
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("invalid coordinates")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    folder = ROOT / "data" / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / "lighting_reports.jsonl"
    safe_report = {"lat": lat, "lng": lng, "type": report_type, "note": str(report.get("note", ""))[:400]}
    with file_path.open("a", encoding="utf-8") as output:
        import json
        output.write(json.dumps(safe_report) + "\n")
    return {"status": "saved", "report": safe_report}
