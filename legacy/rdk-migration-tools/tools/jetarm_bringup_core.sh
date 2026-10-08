#!/usr/bin/env bash
# Start the minimal arm control stack only when the control board is visible.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/jetarm_env.sh"

if [ ! -e /dev/rrc ]; then
  echo "Refusing to start arm control: /dev/rrc is missing." >&2
  echo "Check power/cabling, then verify: lsusb | grep 1a86 and ls -l /dev/ttyUSB* /dev/rrc" >&2
  exit 2
fi

LOG_DIR="${LOG_DIR:-/tmp/jetarm_minimal_logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/core_$(date +%Y%m%d_%H%M%S).log"

echo "Starting JetArm core stack."
echo "Log: $LOG_FILE"

ros2 launch sdk jetarm_sdk.launch.py >"$LOG_FILE" 2>&1 &
echo $! >"$LOG_DIR/core.pid"

sleep "${JETARM_CORE_WARMUP_S:-12}"

echo "Core nodes:"
ros2 node list 2>/dev/null || true

echo
echo "Core services:"
ros2 service list -t 2>/dev/null | grep -E 'ros_robot_controller|controller|kinematics|servo' || true
