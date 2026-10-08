"""Evaluate red-block state in a local webcam image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def detect_red(image: np.ndarray) -> dict:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, np.array([0, 65, 60]), np.array([12, 255, 255]))
    mask2 = cv2.inRange(hsv, np.array([168, 65, 60]), np.array([179, 255, 255]))
    mask = cv2.bitwise_or(mask1, mask2)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {"found": False}
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    x, y, w, h = cv2.boundingRect(contour)
    moments = cv2.moments(contour)
    if moments["m00"] == 0:
        cx, cy = x + w / 2.0, y + h / 2.0
    else:
        cx = moments["m10"] / moments["m00"]
        cy = moments["m01"] / moments["m00"]
    return {
        "found": True,
        "area": area,
        "bbox": [int(x), int(y), int(w), int(h)],
        "center_px": [float(cx), float(cy)],
    }


def classify(candidate: dict) -> str:
    if not candidate.get("found") or candidate.get("area", 0) < 400:
        return "not_found"
    _, y, _, h = candidate["bbox"]
    cy = candidate["center_px"][1]
    bottom = y + h
    # This threshold is calibrated for the current local HD Webcam view:
    # table objects sit low in the frame, while a lifted block is held around
    # the gripper above the table surface.
    if cy < 520 and bottom < 610:
        return "lifted"
    return "on_table"


def annotate(image: np.ndarray, candidate: dict, state: str) -> np.ndarray:
    out = image.copy()
    if candidate.get("found"):
        x, y, w, h = candidate["bbox"]
        cx, cy = candidate["center_px"]
        color = (0, 255, 0) if state == "lifted" else (0, 255, 255)
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
        cv2.drawMarker(out, (int(cx), int(cy)), color, cv2.MARKER_CROSS, 18, 2)
    cv2.putText(out, state, (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--annotated", type=Path)
    args = parser.parse_args()

    image = cv2.imread(str(args.image))
    if image is None:
        raise SystemExit(f"failed to read image: {args.image}")
    candidate = detect_red(image)
    state = classify(candidate)
    result = {"image": str(args.image), "state": state, "red_candidate": candidate}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.annotated:
        args.annotated.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(args.annotated), annotate(image, candidate, state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
