# Architecture

## Request path

1. The React UI sends start/end latitude and longitude plus `alpha` and walking pace to `GET /api/route`.
2. FastAPI snaps both points to the nearest graph nodes, rejecting points far outside coverage.
3. NetworkX calculates a distance-only shortest path and a lighting-weighted path. If the latter exceeds 1.6 times the baseline distance, the engine reduces its lighting preference until it fits the detour guardrail.
4. The API returns summary metrics plus one GeoJSON line feature per street edge. Each feature includes a score, confidence, nearby lamp count, data sources, and longest-gap estimate.
5. MapLibre draws the routes with the same dim/mixed/more-evidence palette and lets the user inspect a segment.

## Edge scoring

For edge length `L`, initial graph scoring uses the project-plan heuristic:

```text
density_term = min(lamp_density / 3 lamps_per_100m, 1)
gap_term = 1 - min(max_gap_m / 60m, 1)
lit_bonus = +0.15 for lit=yes; -0.20 for lit=no; otherwise 0
light_score = clamp(0.5*density_term + 0.5*gap_term + lit_bonus, 0, 1)
```

The real-data pipeline uses street-light features and `lit` tags when present. OWL-ViT detections can add approximate edge evidence from associated Mapillary images. It does not estimate lux, confirm that lights work, or derive a precise map position for each bounding box.

## Routing cost

```python
cost = length_m * (1 + alpha * ((1 - light_score) + unknown_penalty))
unknown_penalty = 0.1 if confidence < 0.3 else 0
```

Alpha zero is distance-only; higher alpha applies stronger weight to low scores. The bright route is kept within 1.6x the fastest route distance.

## Evidence states

- **More evidence:** score >= 0.6.
- **Mixed evidence:** 0.3 <= score < 0.6.
- **Low evidence:** score < 0.3.
- **Unknown/low confidence:** confidence < 0.3 is separately measured and is not synonymous with darkness.

The no-credentials fallback graph is synthetic and should never be used as evidence about actual campus lighting. The application intentionally labels demo mode.
