"""Scan tabletop target visibility from multiple JetArm poses.

This script is a local orchestration helper for physical grasp experiments. It
moves through a small set of direct-pulse observation poses, captures local
webcam and wrist RGB-D evidence at each pose, optionally tries the CSI view, and
stores the servo state that produced every image.
"""

from __future__ import annotations

from jetarm_connection import add_connection_arguments, connect, connection_cli, require_driver, preview_motion

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import paramiko



ROS_SETUP = (
    "source /opt/ros/humble/setup.bash; "
    "source ~/jetarm_ros2_ws/install/setup.bash; "
)


@dataclass(frozen=True)
class ScanPose:
    name: str
    goals: list[tuple[int, int]]
    duration: float
    settle: float
    note: str


SCAN_PRESETS: dict[str, list[ScanPose]] = {
    "near_red_block": [
        ScanPose(
            "safe_high_center",
            [(1, 500), (2, 560), (3, 130), (4, 115), (5, 500), (10, 200)],
            1.2,
            0.5,
            "High, centered overview; useful before any low sweep.",
        ),
        ScanPose(
            "look_left_high",
            [(1, 560), (2, 545), (3, 135), (4, 120), (5, 540), (10, 200)],
            1.0,
            0.45,
            "Yaw left from a high posture to expose the near-table area.",
        ),
        ScanPose(
            "look_right_high",
            [(1, 440), (2, 545), (3, 135), (4, 120), (5, 460), (10, 200)],
            1.0,
            0.45,
            "Yaw right from a high posture to expose the opposite side.",
        ),
        ScanPose(
            "near_scoop_prepose",
            [(1, 475), (2, 500), (3, 35), (4, 225), (5, 600), (10, 200)],
            1.0,
            0.45,
            "Low pre-scoop view for blocks close to the robot body.",
        ),
        ScanPose(
            "inside_scoop_probe_view",
            [(1, 500), (2, 500), (3, 0), (4, 255), (5, 620), (10, 200)],
            0.9,
            0.45,
            "More inward servo-3/4 geometry; only observes, does not close.",
        ),
    ],
    "wide_table": [
        ScanPose(
            "safe_high_center",
            [(1, 500), (2, 560), (3, 130), (4, 115), (5, 500), (10, 200)],
            1.2,
            0.5,
            "High centered overview.",
        ),
        ScanPose(
            "wide_left",
            [(1, 620), (2, 545), (3, 135), (4, 120), (5, 560), (10, 200)],
            1.1,
            0.45,
            "Large left sweep for target search.",
        ),
        ScanPose(
            "wide_right",
            [(1, 380), (2, 545), (3, 135), (4, 120), (5, 440), (10, 200)],
            1.1,
            0.45,
            "Large right sweep for target search.",
        ),
        ScanPose(
            "forward_low_open",
            [(1, 500), (2, 505), (3, 40), (4, 215), (5, 580), (10, 200)],
            1.0,
            0.45,
            "Lower forward view while keeping the gripper open.",
        ),
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_connection_arguments(parser)
    parser.add_argument("--execute", action="store_true", help="Enable real physical motion after operator safety checks.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--prefix", default="scan")
    parser.add_argument("--preset", choices=sorted(SCAN_PRESETS), default="near_red_block")
    parser.add_argument("--device-name", default="HD Webcam")
    parser.add_argument("--include-csi", action="store_true")
    parser.add_argument("--skip-wrist", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run_remote(client: paramiko.SSHClient, command: str, timeout: int = 30) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")


def read_servo_state(client: paramiko.SSHClient) -> dict:
    command = (
        "bash -lc '"
        + ROS_SETUP
        + "timeout 8 ros2 topic echo /controller_manager/servo_states --once'"
    )
    code, stdout, stderr = run_remote(client, command, timeout=12)
    states: dict[str, int] = {}
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("- id:"):
            current_id = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("id:"):
            current_id = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("position:"):
            if "current_id" in locals():
                states[current_id] = int(float(stripped.split(":", 1)[1].strip()))
                del current_id
    return {"ok": bool(states), "states": states, "raw": stdout, "stderr": stderr, "exit_code": code}


def validate_goals(goals: list[tuple[int, int]]) -> None:
    allowed = {1, 2, 3, 4, 5, 10}
    for servo_id, pulse in goals:
        if servo_id not in allowed:
            raise ValueError(f"unsupported servo id: {servo_id}")
        if not 0 <= pulse <= 1000:
            raise ValueError(f"unsafe pulse for servo {servo_id}: {pulse}")


def publish_pose(pose: ScanPose, script_dir: Path, args) -> None:
    validate_goals(pose.goals)
    cmd = [
        sys.executable,
        str(script_dir / "jetarm_servo_publish.py"),
        "--duration",
        str(pose.duration),
    ]
    for servo_id, pulse in pose.goals:
        cmd.extend(["--goal", f"{servo_id}:{pulse}"])
    cmd.extend(connection_cli(args) + ["--execute"])
    subprocess.run(cmd, check=True)
    time.sleep(pose.settle)


def capture_local(script_dir: Path, output: Path, device_name: str) -> dict:
    ps_script = script_dir / "capture_windows_webcam.ps1"
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Sta",
        "-File",
        str(ps_script),
        "-OutputPath",
        str(output),
        "-DeviceName",
        device_name,
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return {"stdout": proc.stdout, "stderr": proc.stderr}


def detect_red_image(image_path: Path, output_prefix: Path) -> dict:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        return {"found": False, "error": f"failed to read {image_path}"}
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 65, 45]), np.array([12, 255, 255]))
    mask |= cv2.inRange(hsv, np.array([168, 65, 45]), np.array([179, 255, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= 80.0]
    annotated = image.copy()
    candidate = None
    if contours:
        contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(contour)
        moments = cv2.moments(contour)
        if abs(moments["m00"]) > 1e-6:
            cx = float(moments["m10"] / moments["m00"])
            cy = float(moments["m01"] / moments["m00"])
        else:
            cx = x + w / 2.0
            cy = y + h / 2.0
        rect = cv2.minAreaRect(contour)
        candidate = {
            "found": True,
            "bbox": [int(x), int(y), int(w), int(h)],
            "center_px": [cx, cy],
            "area": float(cv2.contourArea(contour)),
            "min_area_rect": {
                "center": [float(rect[0][0]), float(rect[0][1])],
                "size": [float(rect[1][0]), float(rect[1][1])],
                "angle": float(rect[2]),
                "box": cv2.boxPoints(rect).astype(int).tolist(),
            },
        }
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 255), 2)
        cv2.drawMarker(annotated, (int(round(cx)), int(round(cy))), (0, 255, 255), cv2.MARKER_CROSS, 16, 2)
    cv2.imwrite(str(output_prefix.with_name(output_prefix.name + "_red_mask.png")), mask)
    cv2.imwrite(str(output_prefix.with_name(output_prefix.name + "_annotated.jpg")), annotated)
    return candidate or {"found": False}


def run_helper(cmd: list[str], allow_failure: bool = False) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    result = {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    if proc.returncode != 0 and not allow_failure:
        raise subprocess.CalledProcessError(proc.returncode, cmd, proc.stdout, proc.stderr)
    return result


def main() -> int:
    args = parse_args()
    if preview_motion(args):
        return 0
    script_dir = Path(__file__).resolve().parent
    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = connect(args.host, args.username, args.key_file)
    entries = []
    try:
        require_driver(client)
        for index, pose in enumerate(SCAN_PRESETS[args.preset], start=1):
            stem = f"{args.prefix}_{index:02d}_{pose.name}"
            if not args.dry_run:
                publish_pose(pose, script_dir, args)
            state = read_servo_state(client)

            local_path = args.output_dir / f"{stem}_local.jpg"
            local_capture = capture_local(script_dir, local_path, args.device_name)
            local_red = detect_red_image(local_path, args.output_dir / f"{stem}_local")

            wrist_result = None
            wrist_meta = None
            if not args.skip_wrist:
                wrist_result = run_helper(
                    [
                        sys.executable,
                        str(script_dir / "capture_rdk_observation.py"),
                        *connection_cli(args),
                        "--output-dir",
                        str(args.output_dir),
                        "--prefix",
                        f"{stem}_wrist",
                    ],
                    allow_failure=True,
                )
                meta_path = args.output_dir / f"{stem}_wrist_meta.json"
                if meta_path.exists():
                    wrist_meta = json.loads(meta_path.read_text(encoding="utf-8"))

            csi_result = None
            csi_meta = None
            if args.include_csi:
                csi_result = run_helper(
                    [
                        sys.executable,
                        str(script_dir / "capture_rdk_csi_observation.py"),
                        *connection_cli(args),
                        "--output-dir",
                        str(args.output_dir),
                        "--prefix",
                        stem,
                    ],
                    allow_failure=True,
                )
                csi_path = args.output_dir / f"{stem}_csi_meta.json"
                if csi_path.exists():
                    csi_meta = json.loads(csi_path.read_text(encoding="utf-8"))

            entry = {
                "index": index,
                "name": pose.name,
                "note": pose.note,
                "commanded_goals": pose.goals,
                "duration_s": pose.duration,
                "servo_state": state,
                "local": {
                    "image": str(local_path),
                    "annotated": str(args.output_dir / f"{stem}_local_annotated.jpg"),
                    "red_candidate": local_red,
                    "capture": local_capture,
                },
                "wrist_rgbd": {
                    "result": wrist_result,
                    "meta": wrist_meta,
                },
                "csi": {
                    "result": csi_result,
                    "meta": csi_meta,
                },
            }
            entries.append(entry)
            (args.output_dir / f"{stem}_record.json").write_text(
                json.dumps(entry, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(json.dumps({"ok": True, "pose": pose.name, "local_red": local_red}, ensure_ascii=False))

        summary = {
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "preset": args.preset,
            "prefix": args.prefix,
            "entries": entries,
        }
        summary_path = args.output_dir / f"{args.prefix}_scan_summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "summary": str(summary_path)}, ensure_ascii=False))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
