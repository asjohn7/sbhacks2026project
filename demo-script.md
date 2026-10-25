# Three-minute demo script

**0:00–0:20 — Hook**
“Think about leaving a late club meeting or the library. The fastest walk isn't always the path with the most lighting evidence. Lumen Routes makes that trade-off visible.”

**0:20–0:40 — Problem**
“Typical walking routes optimize distance and time. Lighting data is incomplete, and an absent tag doesn't automatically mean a street is dark.”

**0:40–1:00 — Solution**
“We combine the walkable street graph with tagged or detected fixtures, estimate an evidence score and confidence for each segment, and return a fastest route and a brighter alternative.”

**1:00–2:00 — Live demo**
- Choose Library → Union.
- Compare the travel-time and well-lit-share estimates.
- Select each route and explain that the user remains in control.
- Turn on coverage and fixture layers.
- Click a segment to show the score, nearby fixture estimate, gap, sources, and confidence.
- Raise the preference slider and recalculate; explain the detour cap.

**2:00–2:25 — How it works**
“OSMnx builds the walk graph, evidence is merged on each edge, a weighted shortest-path search selects a candidate route, and the backend sends GeoJSON to MapLibre.”

**2:25–2:40 — Results**
Show detector precision/recall, labeled sample size, and an example route comparison only after running the real-data pipeline and validation. Do not quote sample/demo scores as real measurements.

**2:40–3:00 — Limitations and next steps**
“Daytime images show fixtures, not current nighttime brightness. Data can be old or missing. This doesn't guarantee safety. Next we'd add night imagery, community reports with review, and broader validated coverage.”
