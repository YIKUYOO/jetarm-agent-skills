"""Capture one frame from the RDK X5 CSI camera.

The default path uses the board-verified ``hobot_vio.libsrcampy`` CSI API.
An older ROS ``mipi_cam`` path remains available for diagnostics, but it can
fail when the lower-level camera service already owns the sensor.
"""

from __future__ import annotations

from jetarm_connection import add_connection_arguments, connect, connection_cli, require_driver, preview_motion

import argparse
import json
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


def image_to_bgr(msg):
    if msg.encoding not in ("bgr8", "rgb8", "mono8", "8UC1"):
        raise RuntimeError(f"unsupported encoding: {msg.encoding}")
    if msg.encoding in ("bgr8", "rgb8"):
        arr = np.frombuffer(msg.data, dtype=np.uint8)
        arr = arr.reshape((msg.height, msg.step // 3, 3))[:, :msg.width, :].copy()
        if msg.encoding == "rgb8":
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return arr
    arr = np.frombuffer(msg.data, dtype=np.uint8)
    arr = arr.reshape((msg.height, msg.step))[:, :msg.width].copy()
    return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="/image_raw")
    parser.add_argument("--camera-info-topic", default="/camera_info")
    parser.add_argument("--output", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()

    rclpy.init()
    node = rclpy.create_node("codex_one_shot_csi_capture")
    state = {"image": None, "info": None}

    def on_image(msg):
        if state["image"] is None:
            state["image"] = msg

    def on_info(msg):
        if state["info"] is None:
            state["info"] = msg

    node.create_subscription(Image, args.topic, on_image, qos_profile_sensor_data)
    node.create_subscription(CameraInfo, args.camera_info_topic, on_info, qos_profile_sensor_data)

    deadline = time.time() + args.timeout
    while time.time() < deadline and state["image"] is None:
        rclpy.spin_once(node, timeout_sec=0.1)
    msg = state["image"]
    if msg is None:
        raise RuntimeError(f"timed out waiting for {args.topic}")

    image = image_to_bgr(msg)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(args.output, image)

    camera_info = None
    if state["info"] is not None:
        info = state["info"]
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

    meta = {
        "topic": args.topic,
        "camera_info_topic": args.camera_info_topic,
        "encoding": msg.encoding,
        "height": msg.height,
        "width": msg.width,
        "step": msg.step,
        "camera_info": camera_info,
    }
    Path(args.meta).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
'''


REMOTE_SRCAMPY_CAPTURE = r'''
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np


def nv12_to_bgr(raw, width, height):
    data = np.frombuffer(raw, dtype=np.uint8)
    expected = width * height * 3 // 2
    if data.size < expected:
        raise RuntimeError(f"NV12 buffer is too small: got {data.size}, need {expected}")
    nv12 = data[:expected].reshape((height * 3 // 2, width))
    return cv2.cvtColor(nv12, cv2.COLOR_YUV2BGR_NV12)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--sensor-width", type=int, default=1920)
    parser.add_argument("--sensor-height", type=int, default=1080)
    parser.add_argument("--channel", type=int, default=2)
    parser.add_argument("--warmup", type=int, default=2)
    args = parser.parse_args()

    try:
        from hobot_vio import libsrcampy as srcampy
        module_name = "hobot_vio.libsrcampy"
    except ImportError:
        from hobot_vio_rdkx5 import libsrcampy as srcampy
        module_name = "hobot_vio_rdkx5.libsrcampy"

    cam = srcampy.Camera()
    opened_at = time.time()
    try:
        cam.open_cam(
            0,
            -1,
            -1,
            [args.width, args.sensor_width],
            [args.height, args.sensor_height],
            args.sensor_height,
            args.sensor_width,
        )
        raw = None
        for _ in range(max(1, args.warmup + 1)):
            raw = cam.get_img(args.channel, args.width, args.height)
        image = nv12_to_bgr(raw, args.width, args.height)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(args.output, image)
        meta = {
            "backend": "srcampy",
            "module": module_name,
            "encoding": "nv12",
            "output_encoding": "bgr8",
            "width": args.width,
            "height": args.height,
            "sensor_width": args.sensor_width,
            "sensor_height": args.sensor_height,
            "channel": args.channel,
            "warmup": args.warmup,
            "opened_at": opened_at,
            "captured_at": time.time(),
        }
        Path(args.meta).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    finally:
        cam.close_cam()


if __name__ == "__main__":
    main()
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_connection_arguments(parser)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--backend", choices=["srcampy", "mipi_ros"], default="srcampy")
    parser.add_argument("--topic", default="/image_raw")
    parser.add_argument("--camera-info-topic", default="/camera_info")
    parser.add_argument("--video-device", default="F37")
    parser.add_argument("--width", default="640")
    parser.add_argument("--height", default="480")
    parser.add_argument("--sensor-width", default="1920")
    parser.add_argument("--sensor-height", default="1080")
    parser.add_argument("--srcampy-channel", default="2")
    return parser.parse_args()


def run(client: paramiko.SSHClient, command: str, timeout: int = 30) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")


def detect_red(rgb_bgr: np.ndarray) -> tuple[dict | None, np.ndarray]:
    hsv = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 80, 40]), np.array([12, 255, 255]))
    mask |= cv2.inRange(hsv, np.array([170, 70, 40]), np.array([179, 255, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= 80.0]
    if not contours:
        return None, mask
    contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(contour)
    m = cv2.moments(contour)
    if abs(m["m00"]) > 1e-6:
        center = [float(m["m10"] / m["m00"]), float(m["m01"] / m["m00"])]
    else:
        center = [x + w / 2.0, y + h / 2.0]
    rect = cv2.minAreaRect(contour)
    return {
        "bbox": [int(x), int(y), int(w), int(h)],
        "center_px": center,
        "area": float(cv2.contourArea(contour)),
        "min_area_rect": {
            "center": [float(rect[0][0]), float(rect[0][1])],
            "size": [float(rect[1][0]), float(rect[1][1])],
            "angle": float(rect[2]),
            "box": cv2.boxPoints(rect).astype(int).tolist(),
        },
    }, mask


def annotate(output_dir: Path, prefix: str) -> None:
    image_path = output_dir / f"{prefix}_csi_rgb.png"
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("downloaded CSI image could not be read")
    candidate, mask = detect_red(image)
    annotated = image.copy()
    if candidate:
        x, y, w, h = candidate["bbox"]
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 255), 2)
        cx, cy = candidate["center_px"]
        cv2.drawMarker(annotated, (int(round(cx)), int(round(cy))), (0, 255, 255), cv2.MARKER_CROSS, 16, 2)
        cv2.putText(annotated, "red", (x, max(16, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    cv2.imwrite(str(output_dir / f"{prefix}_csi_rgb_annotated.png"), annotated)
    cv2.imwrite(str(output_dir / f"{prefix}_csi_red_mask.png"), mask)

    meta_path = output_dir / f"{prefix}_csi_capture_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta["red_candidate"] = candidate
    meta["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (output_dir / f"{prefix}_csi_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = connect(args.host, args.username, args.key_file)
    try:
        stamp = int(time.time())
        remote_dir = f"/tmp/codex_csi_{args.prefix}_{stamp}"
        remote_image = posixpath.join(remote_dir, "csi_rgb.png")
        remote_meta = posixpath.join(remote_dir, "csi_capture_meta.json")

        if args.backend == "srcampy":
            remote_script = f"/tmp/codex_capture_csi_srcampy_{stamp}.py"
            sftp = client.open_sftp()
            with sftp.open(remote_script, "w") as fh:
                fh.write(REMOTE_SRCAMPY_CAPTURE)
            sftp.close()

            capture_cmd = (
                f"python3 {shlex.quote(remote_script)} "
                f"--output {shlex.quote(remote_image)} "
                f"--meta {shlex.quote(remote_meta)} "
                f"--width {shlex.quote(args.width)} "
                f"--height {shlex.quote(args.height)} "
                f"--sensor-width {shlex.quote(args.sensor_width)} "
                f"--sensor-height {shlex.quote(args.sensor_height)} "
                f"--channel {shlex.quote(args.srcampy_channel)}"
            )
            shell = f"mkdir -p {shlex.quote(remote_dir)}; {capture_cmd}"
            code, stdout, stderr = run(client, "bash -lc " + shlex.quote(shell), timeout=int(args.timeout + 20))
            if code != 0:
                print(stdout, end="")
                print(stderr, end="", file=sys.stderr)
                return code

            sftp = client.open_sftp()
            sftp.get(remote_image, str(output_dir / f"{args.prefix}_csi_rgb.png"))
            sftp.get(remote_meta, str(output_dir / f"{args.prefix}_csi_capture_meta.json"))
            sftp.close()
            annotate(output_dir, args.prefix)
            print(json.dumps({"ok": True, "backend": args.backend, "output_dir": str(output_dir), "prefix": args.prefix}, ensure_ascii=False))
            return 0

        remote_script = f"/tmp/codex_capture_csi_{stamp}.py"
        remote_log = f"/tmp/codex_mipi_{args.prefix}_{stamp}.log"

        sftp = client.open_sftp()
        with sftp.open(remote_script, "w") as fh:
            fh.write(REMOTE_CAPTURE)
        sftp.close()

        launch_cmd = (
            "ros2 launch mipi_cam mipi_cam_640x480_bgr8.launch.py "
            f"mipi_video_device:={shlex.quote(args.video_device)} "
            f"mipi_image_width:={shlex.quote(args.width)} "
            f"mipi_image_height:={shlex.quote(args.height)}"
        )
        capture_cmd = (
            f"python3 {shlex.quote(remote_script)} "
            f"--topic {shlex.quote(args.topic)} "
            f"--camera-info-topic {shlex.quote(args.camera_info_topic)} "
            f"--output {shlex.quote(remote_image)} "
            f"--meta {shlex.quote(remote_meta)} "
            f"--timeout {args.timeout}"
        )
        shell = (
            "source /opt/ros/humble/setup.bash; "
            "source /opt/tros/humble/setup.bash; "
            f"mkdir -p {shlex.quote(remote_dir)}; "
            f"{launch_cmd} >{shlex.quote(remote_log)} 2>&1 & "
            "MIPI_PID=$!; "
            "sleep 2.5; "
            f"{capture_cmd}; "
            "CAPTURE_RC=$?; "
            "kill $MIPI_PID 2>/dev/null || true; "
            "wait $MIPI_PID 2>/dev/null || true; "
            "exit $CAPTURE_RC"
        )
        code, stdout, stderr = run(client, "bash -lc " + shlex.quote(shell), timeout=int(args.timeout + 25))
        if code != 0:
            print(stdout, end="")
            print(stderr, end="", file=sys.stderr)
            log_code, log_out, _ = run(client, f"tail -120 {shlex.quote(remote_log)}", timeout=10)
            if log_code == 0:
                print(log_out, file=sys.stderr)
            return code

        sftp = client.open_sftp()
        sftp.get(remote_image, str(output_dir / f"{args.prefix}_csi_rgb.png"))
        sftp.get(remote_meta, str(output_dir / f"{args.prefix}_csi_capture_meta.json"))
        sftp.close()
        annotate(output_dir, args.prefix)
        print(json.dumps({"ok": True, "output_dir": str(output_dir), "prefix": args.prefix}, ensure_ascii=False))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
