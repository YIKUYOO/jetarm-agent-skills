"""Capture one no-motion tri-view relation cycle for JetArm tabletop picking.

This helper does not move the robot. It records the current servo state,
captures the local webcam, CSI/srcampy, and optional wrist RGB-D views, then
runs the conservative gripper/block relation scorer. Use it before any close or
probe motion, especially when the object has been moved to a new position.
"""

from __future__ import annotations

from jetarm_connection import add_connection_arguments, connect, connection_cli, require_driver, preview_motion

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path


ROS_SETUP = (
    "source /opt/ros/humble/setup.bash; "
    "source ~/jetarm_ros2_ws/install/setup.bash; "
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--device-name", default="HD Webcam")
    parser.add_argument("--skip-wrist", action="store_true")
    parser.add_argument("--csi-gripper-bbox", help="Optional CSI gripper bbox as x,y,w,h after visual inspection.")
    add_connection_arguments(parser)
    return parser.parse_args()


def run(cmd: list[str], timeout: int) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    result = {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if proc.returncode != 0:
        raise RuntimeError(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def read_servo_state(args) -> dict:
    import shlex
    client = connect(args.host, args.username, args.key_file)
    try:
        _, out, err = client.exec_command("bash -lc " + shlex.quote(ROS_SETUP + "timeout 8 ros2 topic echo /controller_manager/servo_states --once"), timeout=15)
        code = out.channel.recv_exit_status()
        stdout = out.read().decode("utf-8", "replace")
        if code:
            raise RuntimeError(err.read().decode("utf-8", "replace"))
    finally:
        client.close()
    states: dict[str, int] = {}
    current_id = None
    for line in stdout.splitlines():
        stripped = line.strip()
        match = re.match(r"-?\s*id:\s*(\d+)", stripped)
        if match:
            current_id = match.group(1)
            continue
        if current_id and stripped.startswith("position:"):
            states[current_id] = int(float(stripped.split(":", 1)[1].strip()))
            current_id = None
    return {"states": states, "raw": stdout}


def servo_state_arg(states: dict[str, int]) -> str:
    ordered = [str(i) for i in (1, 2, 3, 4, 5, 10)]
    return ",".join(f"{servo_id}:{states[servo_id]}" for servo_id in ordered if servo_id in states)


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or time.strftime("triview_cycle_%Y%m%d_%H%M%S")

    servo = read_servo_state(args)
    servo_json = args.output_dir / f"{prefix}_servo_state.json"
    servo_json.write_text(json.dumps(servo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    local_image = args.output_dir / f"{prefix}_local.jpg"
    local_cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Sta",
        "-File",
        str(script_dir / "capture_windows_webcam.ps1"),
        "-OutputPath",
        str(local_image),
        "-DeviceName",
        args.device_name,
    ]
    local_result = run(local_cmd, timeout=25)

    csi_prefix = f"{prefix}_csi"
    csi_cmd = [
        sys.executable,
        str(script_dir / "capture_rdk_csi_observation.py"),
        *connection_cli(args),
        "--output-dir",
        str(args.output_dir),
        "--prefix",
        csi_prefix,
        "--timeout",
        "10",
    ]
    csi_result = run(csi_cmd, timeout=35)

    wrist_result = None
    wrist_image = None
    wrist_meta = None
    if not args.skip_wrist:
        wrist_prefix = f"{prefix}_wrist"
        wrist_cmd = [
            sys.executable,
            str(script_dir / "capture_rdk_observation.py"),
            *connection_cli(args),
            "--output-dir",
            str(args.output_dir),
            "--prefix",
            wrist_prefix,
            "--timeout",
            "8",
        ]
        wrist_result = run(wrist_cmd, timeout=35)
        wrist_image = args.output_dir / f"{wrist_prefix}_rgb.png"
        wrist_meta = args.output_dir / f"{wrist_prefix}_meta.json"

    csi_image = args.output_dir / f"{csi_prefix}_csi_rgb.png"
    csi_meta = args.output_dir / f"{csi_prefix}_csi_meta.json"
    relation_output = args.output_dir / f"{prefix}_relation.json"
    relation_cmd = [
        sys.executable,
        str(script_dir / "jetarm_triview_relation.py"),
        "--local-image",
        str(local_image),
        "--csi-image",
        str(csi_image),
        "--csi-meta",
        str(csi_meta),
        "--servo-state",
        servo_state_arg(servo["states"]),
        "--output",
        str(relation_output),
        "--annotated-dir",
        str(args.output_dir),
    ]
    if wrist_image and wrist_meta:
        relation_cmd.extend(["--wrist-image", str(wrist_image), "--wrist-meta", str(wrist_meta)])
    if args.csi_gripper_bbox:
        relation_cmd.extend(["--csi-gripper-bbox", args.csi_gripper_bbox])
    relation_result = run(relation_cmd, timeout=20)

    cycle = {
        "prefix": prefix,
        "servo_state": servo,
        "outputs": {
            "local_image": str(local_image),
            "csi_image": str(csi_image),
            "csi_meta": str(csi_meta),
            "wrist_image": str(wrist_image) if wrist_image else None,
            "wrist_meta": str(wrist_meta) if wrist_meta else None,
            "relation": str(relation_output),
        },
        "commands": {
            "local": local_result,
            "csi": csi_result,
            "wrist": wrist_result,
            "relation": relation_result,
        },
    }
    cycle_path = args.output_dir / f"{prefix}_cycle.json"
    cycle_path.write_text(json.dumps(cycle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "cycle": str(cycle_path), "relation": str(relation_output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
