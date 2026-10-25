# Lumen Routes

**A lighting-aware walking-route prototype.** Compare the shortest path with an alternative that gives more weight to streets with lighting evidence. The app displays street segments, estimated lighting scores, confidence, and the extra travel time/distance trade-off.

> **Important:** The first run uses an illustrative, synthetic campus graph so the app works without credentials or network data downloads. Its streets, lighting scores, and fixture markers are NOT real observations. The UI calls this out explicitly. Before presenting real route claims, build a real local graph with OpenStreetMap and—if you have a Mapillary token—add street-level imagery and run the detector. Lighting evidence is not a guarantee of safety.

## What is built

- **Frontend:** React + Vite + MapLibre; dark interactive map, start/end search, click-to-pick points, route comparison, brightness-vs-speed slider, colored line segments, fixture/coverage layers, segment inspector, responsive layout, and limitations modal.
- **Backend:** FastAPI; `/api/health`, `/api/route`, `/api/edges`, `/api/lamps`, `/api/geocode`, and `/api/report`.
- **Routing:** NetworkX shortest path plus lighting-weighted Dijkstra, estimates of travel time, well-lit route share, longest low-score stretch, nearby fixtures, low-confidence share, and a detour guardrail.
- **Data pipeline (optional):** OSM walking graph + street-lamp/lit tags; Mapillary image thumbnail fetcher; OWL-ViT zero-shot detection; image-level precision/recall/F1 validation.
- **Tests:** Core route cost, GeoJSON output, and detour-limit tests.

## Quick start (Windows / VS Code)

You need Python 3.11+ and Node.js 20+ installed. The backend and frontend run in **two separate terminals**.

### 1. Start the backend

Open a terminal in this `lumen-routes` folder:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If PowerShell blocks virtual-environment activation, you can use `\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` without activating it.

Open [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health). You should see `"status":"ok"` and a `"demo_mode":true` field on first run.

### 2. Start the frontend

Open a **second** terminal in the repository root:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL Vite prints (normally [http://127.0.0.1:5173](http://127.0.0.1:5173)). Leave both terminals running. The map tile style and web-font import need an internet connection; the demo route graph itself is local.

### 3. Try the app

Use **Library → Union** or **Staller → Sports** for a sample route. Select either route card to highlight it. Move the slider then press **Find my routes** to recompute. Turn on **Lighting coverage** or **Light markers** to inspect the data layer. Click a colored route segment to inspect its score and evidence. You can also use **Pick** and click the map to set either endpoint. Coordinates can be typed as `latitude, longitude`.

## Use real OpenStreetMap walking data

This step requires an internet connection when run. It downloads local artifacts once; route requests afterward use the local graph. OSM coverage and `lit`/`street_lamp` tags vary by area.

In a new terminal at the repository root:

```powershell
py -3.11 -m venv .venv-pipeline
.\.venv-pipeline\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r pipeline/requirements.txt
python pipeline/build_osm_graph.py
```

The script reads `config/area.geojson` (the campus-focused bounding polygon) and writes `data/processed/graph.json`. Restart the backend after the file appears; `/api/health` should show `"demo_mode":false`. The generated file is ignored by Git because it is a local data artifact.

If the live Overpass/OpenStreetMap request is rate-limited or fails, wait before retrying. Do not run many copies in parallel. You can edit `config/area.geojson` to select a different small coverage area.

## Add the optional vision component

OWL-ViT is an open-vocabulary detector that can be prompted with text labels. The script uses `google/owlvit-base-patch32` through Hugging Face Transformers. The first model run downloads weights and can be slow; a GPU helps but is not required.

1. Create a Mapillary developer access token and set it only in your local shell (never commit it):

   ```powershell
   $env:MAPILLARY_ACCESS_TOKEN = "your_token_here"
   ```

2. Ensure the OSM graph artifact exists, then request a capped batch of image thumbnails:

   ```powershell
   python pipeline/fetch_mapillary.py --max-images 80
   ```

3. Run detection and rebuild the graph so accepted detections contribute to edge scores:

   ```powershell
   python pipeline/detect_lights.py --threshold 0.15 --max-images 80
   python pipeline/build_osm_graph.py
   ```

4. Restart the backend. Its route scores now include OSM evidence and any accepted detections assigned to those image's nearest graph edge. This association is approximate; detections are bounding boxes in images, not precise light coordinates.

5. Before reporting model quality, label at least 100 varied images in `data/images/labels.csv` with columns `image_id,has_lamp` (`1` if a street-light fixture is visible, `0` otherwise). Then run:

   ```powershell
   python pipeline/validate_detections.py
   ```

   The validation script prints image-level precision, recall, and F1. Review examples of false positives (e.g. traffic lights, signs, bright reflections) and tune the threshold; do not claim accuracy without evaluating labeled examples.

**Licensing/attribution:** the frontend credits OpenStreetMap and OpenFreeMap. If you use Mapillary imagery/features, visibly attribute Mapillary and follow the current Mapillary API, image licensing, and sharing terms. Do not redistribute raw street imagery in your repo. OSM data is subject to its attribution and ODbL requirements. Review current terms before a public release.

## Run tests

```powershell
cd backend
python -m pip install -r requirements.txt
pytest -q
```

The project is designed to work first in demo mode, so you can develop the UI while real data is being prepared.

## API examples

Health check:

```text
GET http://127.0.0.1:8000/api/health
```

Route (coordinates are latitude/longitude; alpha is the lighting preference):

```text
GET http://127.0.0.1:8000/api/route?from_lat=40.9146&from_lng=-73.1232&to_lat=40.9135&to_lng=-73.1177&alpha=2.3&pace=1.4
```

- `alpha=0`: shortest-distance route
- `alpha` closer to `3`: give low lighting scores a stronger penalty (subject to the 1.6x detour cap)
- `pace=1.4`: walking speed in metres/second

## 3-minute demo flow

1. **Hook (20s):** “Maps generally optimize for time and distance; what if I also want to see the lighting evidence along my walk?”
2. **Problem (20s):** Public lighting tags are incomplete, while street imagery is inconsistent and can be out of date.
3. **Solution (20s):** Lumen Routes combines map/fixture evidence into per-segment scores and uses them as a routing cost.
4. **Live demo (60s):** select Library → Union, compare time and well-lit share, click a route segment, turn on layers, move the preference slider, and recompute.
5. **How it works (25s):** OSM graph → lighting evidence → edge score/confidence → weighted shortest-path search → GeoJSON map layers.
6. **Results (15s):** show measured detector precision/recall and route metrics only after running the live data pipeline and validation.
7. **Limitations (20s):** daytime imagery identifies visible fixtures, not actual nighttime lux; data may be stale or missing; lighting is not the only component of perceived or actual safety.

## Repository map

```text
lumen-routes/
  backend/app/            FastAPI API, graph loading, route algorithms, demo graph
  backend/tests/           route algorithm tests
  frontend/src/            React + MapLibre map interface and styles
  pipeline/                OSM graph builder, Mapillary fetch, OWL-ViT detector, validation
  config/area.geojson      target-area polygon
  data/                    generated files; not committed
  docs/                    architecture notes and demo script
```

## Current limitations

- The bundled first-run graph is synthetic and only for UI/routing demonstration.
- Real OSM graph generation and Mapillary inference are offline setup steps, not executed by the live API.
- Image detections are associated with a nearby graph edge rather than precisely geolocated from the image bounding box.
- No real-time GPS, turn-by-turn navigation, live lamp working-state checks, or guarantee of safety.
