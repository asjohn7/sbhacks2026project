"""Run a zero-shot OWL-ViT detector on locally cached street-level images.

Hugging Face documents the same task/model pattern at:
https://huggingface.co/docs/transformers/tasks/zero_shot_object_detection
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from PIL import Image, ImageFile
from transformers import pipeline

ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "data" / "images"
METADATA_FILE = IMAGE_DIR / "metadata.csv"
OUTPUT = ROOT / "data" / "processed" / "detections.json"
CANDIDATE_LABELS = ["street lamp", "street light fixture", "light pole", "wall-mounted outdoor light", "pedestrian bollard light"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.15, help="Minimum detector score to keep (default: 0.15).")
    parser.add_argument("--max-images", type=int, default=300, help="Maximum number of images to process.")
    parser.add_argument("--model", default="google/owlvit-base-patch32", help="Hugging Face zero-shot object detector model.")
    args = parser.parse_args()
    if not METADATA_FILE.exists():
        raise SystemExit("Missing data/images/metadata.csv. Run pipeline/fetch_mapillary.py first, or create the same CSV for your local images.")
    with METADATA_FILE.open(newline="", encoding="utf-8") as source:
        metadata = list(csv.DictReader(source))[:max(0, args.max_images)]
    if not metadata:
        raise SystemExit("No images listed in data/images/metadata.csv.")

    print(f"Loading {args.model}. First run downloads model weights and may take several minutes.")
    detector = pipeline(task="zero-shot-object-detection", model=args.model)
    results = []
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    for index, item in enumerate(metadata, start=1):
        image_path = IMAGE_DIR / item["filename"]
        row = {"image_id": item.get("image_id", image_path.stem), "edge_id": item.get("edge_id", ""), "detections": []}
        try:
            with Image.open(image_path) as image:
                image = image.convert("RGB")
                predictions = detector(image, candidate_labels=CANDIDATE_LABELS)
            for pred in predictions:
                score = float(pred.get("score", 0))
                if score < args.threshold:
                    continue
                box = pred.get("box", {})
                row["detections"].append({
                    "label": pred.get("label", "street light"),
                    "score": round(score, 4),
                    "box": {key: int(value) for key, value in box.items()},
                })
        except Exception as exc:
            row["error"] = str(exc)
        results.append(row)
        if index % 10 == 0 or index == len(metadata):
            print(f"Processed {index}/{len(metadata)} images; {sum(len(r['detections']) for r in results)} candidate detections")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote detections to {OUTPUT}")
    print("Review false positives before relying on these counts. Daytime imagery detects fixtures, not whether they are currently illuminated.")


if __name__ == "__main__":
    main()
