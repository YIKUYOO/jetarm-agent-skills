#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

set +e
source "$SCRIPT_DIR/jetarm_env.sh" >/tmp/jetarm_status_env.log 2>&1
ENV_STATUS=$?
set -e

export JETARM_ENV_STATUS="$ENV_STATUS"

python3 - <<'PY'
import json
import os
import subprocess


def run(args):
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "returncode": 999}
    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode,
    }


lsusb = run(["lsusb"])["stdout"]
nodes_result = run(["ros2", "node", "list"])
nodes = [line.strip() for line in nodes_result["stdout"].splitlines() if line.strip()] if nodes_result["ok"] else []

packages = {}
for pkg in ("ros_robot_controller", "servo_controller", "kinematics", "sdk", "peripherals"):
    packages[pkg] = run(["ros2", "pkg", "prefix", pkg])["ok"]

payload = {
    "ok": True,
    "control_serial": {
        "rrc_exists": os.path.exists("/dev/rrc"),
        "rrc_target": os.path.realpath("/dev/rrc") if os.path.exists("/dev/rrc") else None,
        "ch340_usb": "1a86:7523" in lsusb or "QinHeng" in lsusb or "CH340" in lsusb,
    },
    "camera_usb": {
        "orbbec_depth": "2bc5:0614" in lsusb,
        "orbbec_rgb": "2bc5:0511" in lsusb,
        "lsusb_orbbec": [line for line in lsusb.splitlines() if "2bc5:" in line or "Orbbec" in line],
    },
    "ros": {
        "env_status": int(os.environ.get("JETARM_ENV_STATUS", "999")),
        "ros_distro": os.environ.get("ROS_DISTRO"),
        "rmw": os.environ.get("RMW_IMPLEMENTATION"),
    },
    "packages": packages,
    "nodes": nodes,
}
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
