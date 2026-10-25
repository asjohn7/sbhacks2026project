# Data notes and responsible messaging

## Sources used by the optional real-data pipeline

- **OpenStreetMap:** pedestrian graph, `highway=street_lamp` features, and `lit` tags where mapped.
- **Mapillary (optional):** street-level image thumbnails and metadata, queried with a personal developer token. The fetch script caps image count and caches files locally.
- **OWL-ViT (optional):** zero-shot object detection prompted with candidate fixture labels; image detections are attached to a nearby route edge using the image metadata.

## What a score does—and does not—mean

The lighting score is a routing heuristic that combines fixture density, gaps, and explicit `lit` tags. It is not a measurement of lux, current lamp status, crime, or personal safety. Daytime imagery can show a fixture but cannot establish whether it illuminates the street at night. A high score is evidence of more mapped/detected lighting signals, not a guarantee that a path is safe.

## Unknown data

Missing lighting tags or imagery should not be interpreted as proof of darkness. The app surfaces confidence separately. The pipeline starts with a neutral prior/low confidence where data is absent, so users can distinguish low evidence from a directly observed dim street.

## Validation recommendation

Before presenting measured outcomes, label at least 100 images with variety in light, shade, camera direction, and road type. Compute image-level precision, recall, and F1; inspect false positives; tune threshold; compare edge ranks with `lit` tags and a few streets checked on the ground. Do not present metrics from synthetic demo fixtures as measurements.

## Privacy and licensing checklist

- Keep downloaded images and API tokens out of Git.
- Do not redistribute raw street imagery from this repo.
- Retain image IDs and capture timestamps where needed to assess freshness.
- Follow the current OpenStreetMap/ODbL, Mapillary, model, dataset, and basemap terms. Keep visible attribution in the app if Mapillary data is included.
- Avoid logging route endpoints or user location histories in this MVP.
