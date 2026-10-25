"""Fetch a capped selection of Mapillary thumbnails along graph edges.

Set MAPILLARY_ACCESS_TOKEN in your environment before running this script.
Mapillary imagery must be attributed and used under the current Mapillary terms.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
GRAPH_FILE = ROOT / "data" / "processed" / "graph.json"
IMAGE_DIR = ROOT / "data" / "images"
METADATA_FILE = IMAGE_DIR / "metadata.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-images", type=int, default=80, help="Hard cap to keep the demo small (default: 80).")
    parser.add_argument("--per-edge", type=int, default=3, help="Maximum results requested for each edge midpoint.")
    args = parser.parse_args()
    token = os.getenv("MAPILLARY_ACCESS_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing MAPILLARY_ACCESS_TOKEN. Create a Mapillary developer token and set it in your shell first.")
    if not GRAPH_FILE.exists():
        raise SystemExit("Missing data/processed/graph.json. Run pipeline/build_osm_graph.py first.")
    graph = json.loads(GRAPH_FILE.read_text(encoding="utf-8"))
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "LumenRoutesHackathon/0.1"})
    seen: set[str] = set()
    rows = []

    for edge in graph["edges"]:
        if len(rows) >= max(1, args.max_images):
            break
        coords = edge["geometry"]
        mid_lng = sum(coord[0] for coord in coords) / len(coords)
        mid_lat = sum(coord[1] for coord in coords) / len(coords)
        # Small bounding box: street-level images close to an edge's midpoint.
        delta_lat, delta_lng = 0.00022, 0.00028
        bbox = f"{mid_lng-delta_lng},{mid_lat-delta_lat},{mid_lng+delta_lng},{mid_lat+delta_lat}"
        params = {
            "access_token": token,
            "fields": "id,geometry,thumb_1024_url,captured_at,compass_angle",
            "bbox": bbox,
            "limit": min(10, max(1, args.per_edge)),
        }
        try:
            response = session.get("https://graph.mapillary.com/images", params=params, timeout=12)
            response.raise_for_status()
            candidates = response.json().get("data", [])
        except (requests.RequestException, ValueError) as exc:
            print(f"Skipping edge {edge.get('edge_id', '?')}: {exc}")
            time.sleep(0.25)
            continue
        for item in candidates:
            image_id = str(item.get("id", ""))
            image_url = item.get("thumb_1024_url")
            coords = item.get("geometry", {}).get("coordinates", [])
            if not image_id or image_id in seen or not image_url or len(coords) < 2:
                continue
            seen.add(image_id)
            filename = f"{image_id}.jpg"
            path = IMAGE_DIR / filename
            try:
                if not path.exists():
                    image_response = session.get(image_url, timeout=15)
                    image_response.raise_for_status()
                    path.write_bytes(image_response.content)
            except requests.RequestException as exc:
                print(f"Thumbnail download failed for {image_id}: {exc}")
                continue
            rows.append({
                "image_id": image_id,
                "filename": filename,
                "lat": coords[1],
                "lon": coords[0],
                "edge_id": edge.get("edge_id", ""),
                "captured_at": item.get("captured_at", ""),
                "compass_angle": item.get("compass_angle", ""),
                "source": "Mapillary",
            })
            if len(rows) >= args.max_images:
                break
        print(f"Images saved: {len(rows)}/{args.max_images}")
        time.sleep(0.25)  # Be considerate of service limits.

    with METADATA_FILE.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["image_id", "filename", "lat", "lon", "edge_id", "captured_at", "compass_angle", "source"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved metadata to {METADATA_FILE}")
    print("Attribute Mapillary in the app and pitch. Check current API terms before use.")


if __name__ == "__main__":
    main()
