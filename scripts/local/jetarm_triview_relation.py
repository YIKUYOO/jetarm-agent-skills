"""Estimate gripper-to-block relation from local, CSI, and wrist RGB-D views.

The output is intentionally conservative. It treats RGB/CSI image geometry as
the primary evidence and only uses depth when the capture metadata marks the
red-block depth as reliable enough. This avoids turning a noisy or unregistered
depth frame into a bad grasp command.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def read_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"failed to read image: {path}")
    return image


def red_mask(image: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 65, 45]), np.array([12, 255, 255]))
    mask |= cv2.inRange(hsv, np.array([168, 65, 45]), np.array([179, 255, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    return mask


def contour_record(contour: np.ndarray, image_shape: tuple[int, int, int]) -> dict:
    x, y, w, h = cv2.boundingRect(contour)
    moments = cv2.moments(contour)
    if abs(moments["m00"]) > 1e-6:
        cx = float(moments["m10"] / moments["m00"])
        cy = float(moments["m01"] / moments["m00"])
    else:
        cx = float(x + w / 2)
        cy = float(y + h / 2)
    rect = cv2.minAreaRect(contour)
    return {
        "bbox": [int(x), int(y), int(w), int(h)],
        "center_px": [cx, cy],
        "area": float(cv2.contourArea(contour)),
        "image_shape": [int(image_shape[1]), int(image_shape[0])],
        "min_area_rect": {
            "center": [float(rect[0][0]), float(rect[0][1])],
            "size": [float(rect[1][0]), float(rect[1][1])],
            "angle": float(rect[2]),
            "box": cv2.boxPoints(rect).astype(int).tolist(),
        },
    }


def detect_red(image: np.ndarray, prefer_lower: bool) -> dict | None:
    mask = red_mask(image)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    h_img, w_img = image.shape[:2]
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 80:
            continue
        rec = contour_record(contour, image.shape)
        x, y, w, h = rec["bbox"]
        fill = area / float(max(1, w * h))
        aspect = w / float(max(1, h))
        lower_bonus = (rec["center_px"][1] / max(1.0, h_img)) ** 3 if prefer_lower else 0.0
        blockish = 1.0 / (1.0 + abs(math.log(max(0.2, min(5.0, aspect)))))
        score = area * (0.65 + lower_bonus) * (0.5 + blockish) * max(0.2, fill)
        rec["score"] = float(score)
        rec["fill_ratio"] = float(fill)
        candidates.append(rec)
    if not candidates:
        return None
    if prefer_lower:
        lower = [item for item in candidates if item["center_px"][1] >= 0.55 * h_img]
        if lower:
            candidates = lower
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[0]


def detect_dark_gripper(image: np.ndarray, red: dict | None) -> dict | None:
    if not red:
        return None
    x, y, w, h = red["bbox"]
    img_h, img_w = image.shape[:2]
    rx0 = max(0, x - int(1.6 * w) - 60)
    rx1 = min(img_w, x + int(2.0 * w) + 90)
    ry0 = max(0, y - int(1.8 * h) - 100)
    ry1 = min(img_h, y + int(0.45 * h))
    roi = image[ry0:ry1, rx0:rx1]
    if roi.size == 0:
        return None

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # Black fingers and brackets are low value. Keep the threshold broad because
    # the CSI view can darken the green arm and black finger differently.
    mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([179, 255, 95]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    red_cx, red_cy = red["center_px"]
    records = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 120:
            continue
        x0, y0, ww, hh = cv2.boundingRect(contour)
        gx, gy = x0 + rx0, y0 + ry0
        if hh < 18 or ww < 4:
            continue
        if ww > 1.25 * w or hh > 3.2 * h:
            continue
        cx = gx + ww / 2.0
        cy = gy + hh / 2.0
        # Prefer long dark pieces close to the red block, especially above or
        # beside it. This catches the finger rather than far background shadows.
        dx = abs(cx - red_cx) / max(1.0, w)
        dy = max(0.0, (red_cy - cy) / max(1.0, h))
        if dx > 1.65:
            continue
        verticality = hh / max(1.0, ww)
        if verticality < 0.8:
            continue
        score = area * (1.0 + min(verticality, 8.0)) / (1.0 + dx + 0.35 * dy)
        records.append(
            {
                "bbox": [int(gx), int(gy), int(ww), int(hh)],
                "center_px": [float(cx), float(cy)],
                "area": float(area),
                "score": float(score),
                "verticality": float(verticality),
            }
        )
    if not records:
        return None
    records.sort(key=lambda item: item["score"], reverse=True)
    return records[0]


def overlap_1d(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def relation_from_view(red: dict | None, grip: dict | None) -> dict:
    if not red:
        return {"usable": False, "reason": "red block not detected"}
    if not grip:
        return {"usable": False, "reason": "gripper candidate not detected", "red": red}

    rx, ry, rw, rh = red["bbox"]
    gx, gy, gw, gh = grip["bbox"]
    red_cx, red_cy = red["center_px"]
    grip_cx, grip_cy = grip["center_px"]
    x_overlap = overlap_1d(rx, rx + rw, gx, gx + gw) / max(1.0, min(rw, gw))
    y_overlap = overlap_1d(ry, ry + rh, gy, gy + gh) / max(1.0, min(rh, gh))
    dx_norm = (grip_cx - red_cx) / max(1.0, rw)
    dy_norm = (grip_cy - red_cy) / max(1.0, rh)

    if dx_norm > 0.45:
        horizontal = "image_right_of_block"
    elif dx_norm < -0.45:
        horizontal = "image_left_of_block"
    else:
        horizontal = "horizontally_near_block"

    if dy_norm < -0.45:
        vertical = "above_block"
    elif dy_norm > 0.45:
        vertical = "below_block"
    else:
        vertical = "same_height_band"

    return {
        "usable": True,
        "red": red,
        "gripper": grip,
        "dx_norm": float(dx_norm),
        "dy_norm": float(dy_norm),
        "x_overlap_ratio": float(x_overlap),
        "y_overlap_ratio": float(y_overlap),
        "horizontal_relation": horizontal,
        "vertical_relation": vertical,
        "enclosure_likelihood": (
            "low" if x_overlap < 0.25 or y_overlap < 0.15 or abs(dx_norm) > 0.65 else "possible"
        ),
    }


def red_target_quality(red: dict | None, view_name: str) -> dict:
    if not red:
        return {"usable_for_close": False, "reason": "red not found"}
    x, y, w, h = red["bbox"]
    image_shape = red.get("image_shape") or [0, 0]
    img_w = max(1, int(image_shape[0]))
    img_h = max(1, int(image_shape[1]))
    area_ratio = (w * h) / float(img_w * img_h)
    aspect = max(w / float(max(1, h)), h / float(max(1, w)))
    touches_border = x <= 2 or y <= 2 or (x + w) >= img_w - 2 or (y + h) >= img_h - 2

    close_view = view_name in {"csi", "wrist_rgb"}
    min_width = 20 if close_view else 18
    max_aspect = 3.5 if close_view else 2.3
    max_area_ratio = 0.35 if close_view else 0.08
    reasons = []
    if w < min_width or h < 20:
        reasons.append("red bbox too small or too thin")
    if aspect > max_aspect:
        reasons.append("red bbox shape is not block-like")
    if area_ratio > max_area_ratio:
        reasons.append("red bbox is too large for this view; likely merged with background or occluder")
    if view_name == "csi" and touches_border and w < 40:
        reasons.append("CSI red target is border-clipped into a narrow strip")

    return {
        "usable_for_close": not reasons,
        "reason": "; ".join(reasons) if reasons else "ok",
        "area_ratio": float(area_ratio),
        "aspect": float(aspect),
        "touches_border": bool(touches_border),
    }


def bbox_record(raw: str | None) -> dict | None:
    if not raw:
        return None
    parts = [int(float(v.strip())) for v in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("--csi-gripper-bbox must be x,y,w,h")
    x, y, w, h = parts
    return {
        "bbox": [x, y, w, h],
        "center_px": [float(x + w / 2), float(y + h / 2)],
        "area": float(w * h),
        "source": "manual",
    }


def depth_quality_from_meta(path: Path | None) -> dict:
    if not path or not path.exists():
        return {"available": False, "use_for_decision": False, "reason": "no wrist RGB-D metadata"}
    meta = json.loads(path.read_text(encoding="utf-8"))
    candidate = meta.get("red_candidate") or {}
    quality = candidate.get("depth_quality") or {}
    registration = candidate.get("depth_registration") or {}
    reliable = bool(quality.get("reliable")) and bool(registration.get("is_same_shape"))
    reason = "ok"
    if not quality:
        reason = "capture does not include depth quality"
    elif not quality.get("reliable"):
        reason = "low valid ratio or noisy depth ROI"
    elif not registration.get("is_same_shape"):
        reason = "RGB and depth frames are not registered to the same shape"
    return {
        "available": True,
        "use_for_decision": reliable,
        "reason": reason,
        "red_candidate_depth_quality": quality,
        "depth_registration": registration,
        "red_depth_median_mm": candidate.get("depth_median_at_center"),
    }


def red_from_meta(path: Path | None, image_shape: tuple[int, int, int]) -> dict | None:
    if not path or not path.exists():
        return None
    meta = json.loads(path.read_text(encoding="utf-8"))
    candidate = meta.get("red_candidate")
    if not candidate:
        return None
    result = dict(candidate)
    result.setdefault("image_shape", [int(image_shape[1]), int(image_shape[0])])
    result["source"] = str(path)
    return result


def annotate(image: np.ndarray, red: dict | None, grip: dict | None, output: Path) -> None:
    canvas = image.copy()
    if red:
        x, y, w, h = red["bbox"]
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (0, 255, 255), 2)
        cx, cy = red["center_px"]
        cv2.drawMarker(canvas, (int(cx), int(cy)), (0, 255, 255), cv2.MARKER_CROSS, 16, 2)
        cv2.putText(canvas, "red", (x, max(16, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    if grip:
        x, y, w, h = grip["bbox"]
        cv2.rectangle(canvas, (x, y), (x + w, y + h), (255, 180, 0), 2)
        cx, cy = grip["center_px"]
        cv2.drawMarker(canvas, (int(cx), int(cy)), (255, 180, 0), cv2.MARKER_CROSS, 16, 2)
        cv2.putText(canvas, "grip", (x, max(16, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 180, 0), 1)
    cv2.imwrite(str(output), canvas)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-image", type=Path)
    parser.add_argument("--csi-image", type=Path, required=True)
    parser.add_argument("--csi-meta", type=Path)
    parser.add_argument("--csi-gripper-bbox", help="Manual CSI gripper bbox as x,y,w,h.")
    parser.add_argument("--wrist-image", type=Path)
    parser.add_argument("--wrist-meta", type=Path)
    parser.add_argument("--servo-state-json", type=Path)
    parser.add_argument("--servo-state", help="Servo state as comma-separated ID:PULSE pairs.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--annotated-dir", type=Path)
    args = parser.parse_args()

    views = {}
    for name, path, prefer_lower, meta_path in [
        ("local", args.local_image, True, None),
        ("csi", args.csi_image, False, args.csi_meta),
        ("wrist_rgb", args.wrist_image, False, args.wrist_meta),
    ]:
        if not path:
            continue
        image = read_image(path)
        red = red_from_meta(meta_path, image.shape) or detect_red(image, prefer_lower=prefer_lower)
        manual_grip = bbox_record(args.csi_gripper_bbox) if name == "csi" else None
        grip = manual_grip or detect_dark_gripper(image, red)
        relation = relation_from_view(red, grip)
        views[name] = {
            "image": str(path),
            "red": red,
            "red_quality": red_target_quality(red, name),
            "gripper": grip,
            "relation": relation,
        }
        if args.annotated_dir:
            args.annotated_dir.mkdir(parents=True, exist_ok=True)
            annotate(image, red, grip, args.annotated_dir / f"{args.output.stem}_{name}_annotated.png")

    csi_rel = views.get("csi", {}).get("relation", {})
    local_rel = views.get("local", {}).get("relation", {})
    depth_quality = depth_quality_from_meta(args.wrist_meta)
    servo_state = None
    if args.servo_state_json and args.servo_state_json.exists():
        servo_state = json.loads(args.servo_state_json.read_text(encoding="utf-8"))
    elif args.servo_state:
        servo_state = {}
        for pair in args.servo_state.split(","):
            if not pair.strip():
                continue
            servo_id, pulse = pair.split(":", 1)
            servo_state[servo_id.strip()] = int(float(pulse.strip()))

    blockers = []
    csi_quality = views.get("csi", {}).get("red_quality", {})
    if csi_quality and not csi_quality.get("usable_for_close", False):
        blockers.append(f"CSI red target is not reliable: {csi_quality.get('reason')}")
    if not csi_rel.get("usable"):
        blockers.append("CSI view did not find both red block and gripper")
    elif csi_rel.get("enclosure_likelihood") == "low":
        blockers.append("CSI geometry says the gripper is not enclosing the block volume")
    if depth_quality["available"] and not depth_quality["use_for_decision"]:
        blockers.append(f"depth downgraded: {depth_quality['reason']}")

    if csi_rel.get("usable") and csi_rel.get("horizontal_relation") == "image_right_of_block":
        direction = "move gripper inward/left in the CSI view before closing"
    elif csi_rel.get("usable") and csi_rel.get("horizontal_relation") == "image_left_of_block":
        direction = "move gripper outward/right in the CSI view before closing"
    else:
        direction = "use a small approach sweep and re-capture before closing"

    result = {
        "schema": "jetarm_triview_relation.v1",
        "servo_state": servo_state,
        "views": views,
        "depth_quality": depth_quality,
        "phase_space_model": {
            "primary_view": "csi",
            "supporting_views": ["local", "wrist_rgb"],
            "depth_policy": "use only as weak support unless RGB and depth are registered and ROI quality is reliable",
            "relation_summary": {
                "csi": {
                    "horizontal": csi_rel.get("horizontal_relation"),
                    "vertical": csi_rel.get("vertical_relation"),
                    "x_overlap_ratio": csi_rel.get("x_overlap_ratio"),
                    "enclosure_likelihood": csi_rel.get("enclosure_likelihood"),
                },
                "local": {
                    "horizontal": local_rel.get("horizontal_relation"),
                    "vertical": local_rel.get("vertical_relation"),
                    "x_overlap_ratio": local_rel.get("x_overlap_ratio"),
                    "enclosure_likelihood": local_rel.get("enclosure_likelihood"),
                },
            },
        },
        "action_gate": {
            "close_gripper": len([b for b in blockers if not b.startswith("depth downgraded")]) == 0,
            "blockers": blockers,
            "next_motion_hint": direction,
            "servo_hint": {
                "keep_open": "servo10=200",
                "current_good_wrist_yaw_band": "servo5 around 420-460 looked more natural than 500-520 in CSI",
                "test_before_close": "capture again after each servo4/servo5 change; do not close until CSI x-overlap improves",
            },
        },
    }

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
