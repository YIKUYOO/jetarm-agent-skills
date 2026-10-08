"""Analyze red-block pick geometry from local webcam and wrist RGB-D evidence.

This helper keeps the tabletop pick skill data-driven: it reports local-camera
red-block pixels, wrist RGB-D pixels/depth, the board calibration's estimated
JetArm XY, and deltas against the first successful red-block grasp template.
"""

from __future__ import annotations

from jetarm_connection import add_connection_arguments, connect, connection_cli, require_driver, preview_motion

import argparse
import json
import math
import shlex
from pathlib import Path

import cv2
import numpy as np
import paramiko
import yaml


def detect_local_red(image_path: Path) -> dict:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"failed to read image: {image_path}")
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 65, 60]), np.array([12, 255, 255]))
    mask |= cv2.inRange(hsv, np.array([168, 65, 60]), np.array([179, 255, 255]))
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {"found": False}
    contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(contour)
    moments = cv2.moments(contour)
    if abs(moments["m00"]) < 1e-6:
        cx, cy = x + w / 2.0, y + h / 2.0
    else:
        cx = moments["m10"] / moments["m00"]
        cy = moments["m01"] / moments["m00"]
    return {
        "found": True,
        "area": float(cv2.contourArea(contour)),
        "bbox": [int(x), int(y), int(w), int(h)],
        "center_px": [float(cx), float(cy)],
    }


def board_pixels_to_xy(wrist_meta: dict, args) -> dict | None:
    if not wrist_meta.get("red_candidate") or not wrist_meta.get("camera_info"):
        return None
    from jetarm_tabletop_motion import REMOTE_SCRIPT
    import ast
    # Reuse only the calibration adapter; no Commander and no motion code run.
    tree = ast.parse(REMOTE_SCRIPT)
    adapter = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "compute_pose_xy")
    code = "import json, numpy as np, yaml\nfrom pathlib import Path\nfrom sdk.common import pixels_to_world, extristric_plane_shift\nCONFIG_PATH = Path.home() / 'jetarm_ros2_ws/src/bringup/config/config.yaml'\n" + ast.unparse(adapter)
    code += "\nprint(json.dumps(compute_pose_xy(json.loads(" + repr(json.dumps(wrist_meta)) + "))))"
    client = connect(args.host, args.username, args.key_file)
    try:
        command = "source /opt/ros/humble/setup.bash; source ~/jetarm_ros2_ws/install/setup.bash; python3 -c " + shlex.quote(code)
        _, out, err = client.exec_command("bash -lc " + shlex.quote(command), timeout=20)
        status = out.channel.recv_exit_status()
        data = out.read().decode("utf-8", "replace")
        if status:
            raise RuntimeError(err.read().decode("utf-8", "replace"))
        result = json.loads(data)
    finally:
        client.close()
    candidate = wrist_meta["red_candidate"]
    depth = candidate.get("depth_median_at_center")
    depth_m = float(depth) / 1000.0 if depth is not None and math.isfinite(float(depth)) and float(depth) > 0 else None
    return {"center_px": result["center_px"], "depth_m": depth_m,
            "camera_metric_xyz_m": None, "board_calibrated_xy_m": result["pose_xy"],
            "raw_plane_xyz": result["raw_plane_xyz"]}


def vector_delta(a: dict | None, b: dict | None) -> list[float] | None:
    if not a or not b or not a.get("found") or not b.get("found"):
        return None
    ac = a["center_px"]
    bc = b["center_px"]
    return [float(ac[0] - bc[0]), float(ac[1] - bc[1])]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-image", required=True, type=Path)
    parser.add_argument("--wrist-meta", required=True, type=Path)
    parser.add_argument("--success-local", default=None, type=Path)
    parser.add_argument("--success-wrist", default=None, type=Path)
    add_connection_arguments(parser)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    local_red = detect_local_red(args.local_image)
    success_local_red = detect_local_red(args.success_local) if args.success_local and args.success_local.exists() else None
    wrist_meta = json.loads(args.wrist_meta.read_text(encoding="utf-8"))
    success_wrist_meta = (
        json.loads(args.success_wrist.read_text(encoding="utf-8")) if args.success_wrist and args.success_wrist.exists() else {}
    )

    wrist_pose = board_pixels_to_xy(wrist_meta, args)
    success_wrist_pose = board_pixels_to_xy(success_wrist_meta, args) if success_wrist_meta else None
    local_delta_from_success = vector_delta(local_red, success_local_red)
    wrist_delta_from_success = None
    if wrist_pose and success_wrist_pose:
        wrist_delta_from_success = [
            wrist_pose["center_px"][0] - success_wrist_pose["center_px"][0],
            wrist_pose["center_px"][1] - success_wrist_pose["center_px"][1],
        ]

    candidate = wrist_meta.get("red_candidate") or {}
    rect = candidate.get("min_area_rect") or {}
    angle = float(rect.get("angle", 0.0))
    angle_norm = angle % 90.0
    if angle_norm > 45.0:
        angle_norm -= 90.0
    # Red wooden blocks in this workspace benefited from a larger wrist yaw
    # than the original formula produced, so report an evidence-backed sweep.
    servo5_sweep = [560, 600, 640, 650]
    if abs(angle_norm) < 10:
        servo5_sweep = [520, 560, 600, 640]

    recommendation = {
        "base_xy_m": wrist_pose["board_calibrated_xy_m"] if wrist_pose else None,
        "servo5_sweep": servo5_sweep,
        "needs_fresh_probe": True,
        "notes": [
            "Use wrist RGB-D calibrated XY only when red depth is finite and the target is not cut off by the image border.",
            "Use local delta from the success template to detect pushing/drift before counting a trial.",
            "Close only after a low local image matches the success morphology: red block visible between the two vertical fingers, not under the wrist crossbar.",
        ],
    }

    result = {
        "local": {
            "image": str(args.local_image),
            "red": local_red,
            "success_template_red": success_local_red,
            "delta_px_from_success_template": local_delta_from_success,
        },
        "wrist_rgbd": {
            "meta": str(args.wrist_meta),
            "red": candidate or None,
            "pose_estimate": wrist_pose,
            "success_template_pose_estimate": success_wrist_pose,
            "delta_px_from_success_probe": wrist_delta_from_success,
        },
        "recommendation": recommendation,
    }

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
