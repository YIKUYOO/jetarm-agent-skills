"""Capture one RGB-D observation from the JetArm RDK X5 ROS topics.

The script connects over the fixed SSH channel, runs a short ROS2 subscriber on
the board, downloads the captured files, then writes local annotated evidence.
It intentionally keeps the target detector simple; higher-level skills may swap
the red mask for VLM or open-vocabulary detection.
"""

from __future__ import annotations

from jetarm_connection import add_connection_arguments, connect, connection_cli, require_driver, preview_motion

import argparse
import json
import math
import posixpath
import shlex
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import paramiko


REMOTE_CAPTURE = r'''
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image


def image_to_array(msg):
    dtype = np.uint8
    channels = 1
    if msg.encoding in ("rgb8", "bgr8"):
        channels = 3
    elif msg.encoding in ("rgba8", "bgra8"):
        channels = 4
    elif msg.encoding in ("mono8", "8UC1"):
        channels = 1
    elif msg.encoding in ("16UC1", "mono16"):
        dtype = np.uint16
        channels = 1
    elif msg.encoding == "32FC1":
        dtype = np.float32
        channels = 1
    else:
        raise RuntimeError(f"unsupported encoding: {msg.encoding}")

    arr = np.frombuffer(msg.data, dtype=dtype)
    if channels == 1:
        arr = arr.reshape((msg.height, msg.step // np.dtype(dtype).itemsize))[:, :msg.width]
    else:
        arr = arr.reshape((msg.height, msg.step // np.dtype(dtype).itemsize // channels, channels))
        arr = arr[:, :msg.width, :]
    return arr.copy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--color-topic", default="/depth_cam/color/image_raw")
    parser.add_argument("--depth-topic", default="/depth_cam/depth/image_raw")
    parser.add_argument("--camera-info-topic", default="/depth_cam/color/camera_info")
    parser.add_argument("--depth-camera-info-topic", default="/depth_cam/depth/camera_info")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    rclpy.init()
    node = rclpy.create_node("codex_one_shot_rgbd_capture")
    state = {"color": None, "depth": None, "info": None, "depth_info": None}

    def on_color(msg):
        if state["color"] is None:
            state["color"] = msg

    def on_depth(msg):
        if state["depth"] is None:
            state["depth"] = msg

    def on_info(msg):
        if state["info"] is None:
            state["info"] = msg

    def on_depth_info(msg):
        if state["depth_info"] is None:
            state["depth_info"] = msg

    node.create_subscription(Image, args.color_topic, on_color, qos_profile_sensor_data)
    node.create_subscription(Image, args.depth_topic, on_depth, qos_profile_sensor_data)
    node.create_subscription(CameraInfo, args.camera_info_topic, on_info, qos_profile_sensor_data)
    node.create_subscription(CameraInfo, args.depth_camera_info_topic, on_depth_info, qos_profile_sensor_data)

    deadline = time.time() + args.timeout
    while time.time() < deadline and (state["color"] is None or state["depth"] is None or state["info"] is None):
        rclpy.spin_once(node, timeout_sec=0.1)

    if state["color"] is None or state["depth"] is None:
        raise RuntimeError("timed out waiting for RGB-D frames")

    color_msg = state["color"]
    depth_msg = state["depth"]
    color = image_to_array(color_msg)
    depth = image_to_array(depth_msg)

    if color_msg.encoding == "rgb8":
        color_bgr = cv2.cvtColor(color, cv2.COLOR_RGB2BGR)
    elif color_msg.encoding == "rgba8":
        color_bgr = cv2.cvtColor(color, cv2.COLOR_RGBA2BGR)
    elif color_msg.encoding == "bgra8":
        color_bgr = cv2.cvtColor(color, cv2.COLOR_BGRA2BGR)
    else:
        color_bgr = color

    cv2.imwrite(str(out / "rgb.png"), color_bgr)
    if depth.dtype == np.float32:
        depth_mm = np.nan_to_num(depth * 1000.0, nan=0.0, posinf=0.0, neginf=0.0).astype(np.uint16)
    else:
        depth_mm = depth.astype(np.uint16)
    cv2.imwrite(str(out / "depth_raw.png"), depth_mm)

    info = state["info"]
    camera_info = None
    if info is not None:
        camera_info = {
            "width": info.width,
            "height": info.height,
            "distortion_model": info.distortion_model,
            "d": list(info.d),
            "k": list(info.k),
            "r": list(info.r),
            "p": list(info.p),
            "frame_id": info.header.frame_id,
        }
        (out / "camera_info.json").write_text(json.dumps(camera_info, indent=2), encoding="utf-8")

    depth_camera_info = None
    depth_info = state["depth_info"]
    if depth_info is not None:
        depth_camera_info = {
            "width": depth_info.width,
            "height": depth_info.height,
            "distortion_model": depth_info.distortion_model,
            "d": list(depth_info.d),
            "k": list(depth_info.k),
            "r": list(depth_info.r),
            "p": list(depth_info.p),
            "frame_id": depth_info.header.frame_id,
        }
        (out / "depth_camera_info.json").write_text(json.dumps(depth_camera_info, indent=2), encoding="utf-8")

    meta = {
        "color_topic": args.color_topic,
        "depth_topic": args.depth_topic,
        "camera_info_topic": args.camera_info_topic,
        "depth_camera_info_topic": args.depth_camera_info_topic,
        "color_encoding": color_msg.encoding,
        "depth_encoding": depth_msg.encoding,
        "color_shape": list(color.shape),
        "depth_shape": list(depth.shape),
        "camera_info": camera_info,
        "depth_camera_info": depth_camera_info,
    }
    (out / "capture_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_connection_arguments(parser)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    return parser.parse_args()


def run(client: paramiko.SSHClient, command: str, timeout: int = 30) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")


def scaled_depth_roi(depth: np.ndarray, rgb_shape: tuple[int, int, int], bbox: list[int]) -> np.ndarray:
    """Return depth ROI for an RGB bbox, with only conservative shape scaling.

    The JetArm depth camera currently publishes RGB as 640x480 and depth as
    640x400. This is not a true registration step; it only avoids sampling the
    wrong row when the two images differ in height.
    """
    x, y, w, h = bbox
    rgb_h, rgb_w = rgb_shape[:2]
    depth_h, depth_w = depth.shape[:2]
    sx = depth_w / float(rgb_w)
    sy = depth_h / float(rgb_h)
    dx0 = max(0, min(depth_w - 1, int(round(x * sx))))
    dx1 = max(dx0 + 1, min(depth_w, int(round((x + w) * sx))))
    dy0 = max(0, min(depth_h - 1, int(round(y * sy))))
    dy1 = max(dy0 + 1, min(depth_h, int(round((y + h) * sy))))
    return depth[dy0:dy1, dx0:dx1]


def summarize_depth_roi(roi: np.ndarray) -> dict:
    valid = roi[np.isfinite(roi) & (roi > 0)]
    total = int(roi.size)
    valid_count = int(valid.size)
    result = {
        "valid_count": valid_count,
        "total_count": total,
        "valid_ratio": float(valid_count / total) if total else 0.0,
        "median_mm": math.nan,
        "iqr_mm": math.nan,
        "reliable": False,
    }
    if valid_count:
        q25, q50, q75 = np.percentile(valid.astype(np.float32), [25, 50, 75])
        result["median_mm"] = float(q50)
        result["iqr_mm"] = float(q75 - q25)
        result["reliable"] = result["valid_ratio"] >= 0.15 and result["iqr_mm"] <= 120.0
    return result


def detect_red(rgb_bgr: np.ndarray, depth: np.ndarray) -> dict | None:
    hsv = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2HSV)
    lower1 = np.array([0, 80, 40], dtype=np.uint8)
    upper1 = np.array([12, 255, 255], dtype=np.uint8)
    lower2 = np.array([170, 70, 40], dtype=np.uint8)
    upper2 = np.array([179, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower1, upper1) | cv2.inRange(hsv, lower2, upper2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= 80.0]
    if not contours:
        return None, mask

    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    x, y, w, h = cv2.boundingRect(contour)
    m = cv2.moments(contour)
    if abs(m["m00"]) > 1e-6:
        cx = float(m["m10"] / m["m00"])
        cy = float(m["m01"] / m["m00"])
    else:
        cx = x + w / 2.0
        cy = y + h / 2.0

    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect).astype(int).tolist()
    depth_roi = scaled_depth_roi(depth, rgb_bgr.shape, [int(x), int(y), int(w), int(h)])
    depth_summary = summarize_depth_roi(depth_roi)
    depth_median = depth_summary["median_mm"]
    candidate = {
        "bbox": [int(x), int(y), int(w), int(h)],
        "center_px": [cx, cy],
        "area": area,
        "depth_median_at_center": depth_median,
        "depth_quality": depth_summary,
        "depth_registration": {
            "rgb_shape": [int(rgb_bgr.shape[0]), int(rgb_bgr.shape[1])],
            "depth_shape": [int(depth.shape[0]), int(depth.shape[1])],
            "is_same_shape": bool(depth.shape[:2] == rgb_bgr.shape[:2]),
            "note": "Depth is shape-scaled only; treat as weak evidence unless calibrated registration is added.",
        },
        "min_area_rect": {
            "center": [float(rect[0][0]), float(rect[0][1])],
            "size": [float(rect[1][0]), float(rect[1][1])],
            "angle": float(rect[2]),
            "box": box,
        },
    }
    return candidate, mask


def write_evidence(output_dir: Path, prefix: str) -> None:
    rgb_path = output_dir / f"{prefix}_rgb.png"
    depth_path = output_dir / f"{prefix}_depth_raw.png"
    rgb = cv2.imread(str(rgb_path), cv2.IMREAD_COLOR)
    depth = cv2.imread(str(depth_path), cv2.IMREAD_UNCHANGED)
    if rgb is None or depth is None:
        raise RuntimeError("failed to read downloaded RGB-D files")

    candidate, mask = detect_red(rgb, depth)
    annotated = rgb.copy()
    if candidate:
        x, y, w, h = candidate["bbox"]
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 255), 2)
        cx, cy = candidate["center_px"]
        cv2.drawMarker(annotated, (int(round(cx)), int(round(cy))), (0, 255, 255), cv2.MARKER_CROSS, 16, 2)
        cv2.putText(
            annotated,
            f"red {candidate['depth_median_at_center']:.0f} weak-depth",
            (x, max(16, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )

    depth_nonzero = depth[depth > 0]
    if depth_nonzero.size:
        lo, hi = np.percentile(depth_nonzero, [2, 98])
        depth_vis = np.clip((depth.astype(np.float32) - lo) * 255.0 / max(1.0, hi - lo), 0, 255).astype(np.uint8)
    else:
        depth_vis = np.zeros(depth.shape[:2], dtype=np.uint8)
    depth_vis = cv2.applyColorMap(depth_vis, cv2.COLORMAP_TURBO)

    cv2.imwrite(str(output_dir / f"{prefix}_rgb_annotated.png"), annotated)
    cv2.imwrite(str(output_dir / f"{prefix}_red_mask.png"), mask)
    cv2.imwrite(str(output_dir / f"{prefix}_depth_vis.png"), depth_vis)

    capture_meta_path = output_dir / f"{prefix}_capture_meta.json"
    camera_info_path = output_dir / f"{prefix}_camera_info.json"
    depth_camera_info_path = output_dir / f"{prefix}_depth_camera_info.json"
    def load_json_or_none(path: Path) -> dict | None:
        if not path.exists() or path.stat().st_size <= 0:
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    capture_meta = load_json_or_none(capture_meta_path) or {}
    camera_info = load_json_or_none(camera_info_path)
    depth_camera_info = load_json_or_none(depth_camera_info_path)
    meta = {
        "prefix": prefix,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "red_candidate": candidate,
        "camera_info": camera_info,
        "depth_camera_info": depth_camera_info,
        "capture_meta": capture_meta,
    }
    (output_dir / f"{prefix}_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = connect(args.host, args.username, args.key_file)
    try:
        remote_dir = f"/tmp/jetarm_obs_{args.prefix}_{int(time.time())}"
        remote_script = f"/tmp/jetarm_capture_{int(time.time())}.py"
        sftp = client.open_sftp()
        with sftp.open(remote_script, "w") as fh:
            fh.write(REMOTE_CAPTURE)
        sftp.close()

        command = (
            "bash -lc "
            + shlex.quote(
                "source /opt/ros/humble/setup.bash; "
                "source ~/jetarm_ros2_ws/install/setup.bash; "
                f"python3 {shlex.quote(remote_script)} --output {shlex.quote(remote_dir)} --timeout {args.timeout}"
            )
        )
        code, stdout, stderr = run(client, command, timeout=int(args.timeout + 20))
        if code != 0:
            print(stdout, end="")
            print(stderr, end="", file=sys.stderr)
            return code

        sftp = client.open_sftp()
        mapping = {
            "rgb.png": output_dir / f"{args.prefix}_rgb.png",
            "depth_raw.png": output_dir / f"{args.prefix}_depth_raw.png",
            "capture_meta.json": output_dir / f"{args.prefix}_capture_meta.json",
            "camera_info.json": output_dir / f"{args.prefix}_camera_info.json",
            "depth_camera_info.json": output_dir / f"{args.prefix}_depth_camera_info.json",
        }
        for remote_name, local_path in mapping.items():
            try:
                sftp.get(posixpath.join(remote_dir, remote_name), str(local_path))
            except FileNotFoundError:
                if remote_name not in {"camera_info.json", "depth_camera_info.json"}:
                    raise
        sftp.close()

        write_evidence(output_dir, args.prefix)
        print(json.dumps({"ok": True, "output_dir": str(output_dir), "prefix": args.prefix}, ensure_ascii=False))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
