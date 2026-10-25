"""Evaluate image-level fixture detection against a hand-labeled CSV.

Required labels file: data/images/labels.csv with columns image_id,has_lamp.
has_lamp must be 1 if a street-light fixture is visible and 0 otherwise.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "images" / "labels.csv"
DETECTIONS = ROOT / "data" / "processed" / "detections.json"


def main() -> None:
    if not LABELS.exists() or not DETECTIONS.exists():
        raise SystemExit("Need both data/images/labels.csv and data/processed/detections.json.")
    with LABELS.open(newline="", encoding="utf-8") as file:
        labels = {row["image_id"]: int(row["has_lamp"]) for row in csv.DictReader(file)}
    predictions = json.loads(DETECTIONS.read_text(encoding="utf-8"))
    pred_by_id = {row["image_id"]: int(any(float(d.get("score", 0)) >= 0.15 for d in row.get("detections", []))) for row in predictions}
    ids = sorted(set(labels) & set(pred_by_id))
    if not ids:
        raise SystemExit("No image_id values overlap between labels.csv and detections.json.")
    tp = sum(labels[i] == 1 and pred_by_id[i] == 1 for i in ids)
    fp = sum(labels[i] == 0 and pred_by_id[i] == 1 for i in ids)
    fn = sum(labels[i] == 1 and pred_by_id[i] == 0 for i in ids)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    print(f"Labeled images evaluated: {len(ids)}")
    print(f"Precision: {precision:.3f}  Recall: {recall:.3f}  F1: {f1:.3f}")
    print(f"TP={tp} FP={fp} FN={fn}")


if __name__ == "__main__":
    main()
