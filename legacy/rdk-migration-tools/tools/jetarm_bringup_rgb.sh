#!/usr/bin/env bash
# Start the verified RGB fallback camera path.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/jetarm_env.sh"

LOG_DIR="${LOG_DIR:-/tmp/jetarm_minimal_logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/rgb_$(date +%Y%m%d_%H%M%S).log"

if [ "${JETARM_SKIP_CLEANUP:-0}" != "1" ]; then
  "$SCRIPT_DIR/jetarm_cleanup.sh" >/dev/null 2>&1 || true
fi

echo "Starting RGB fallback camera."
echo "Log: $LOG_FILE"

CAMERA_TYPE=USB ros2 launch peripherals depth_camera.launch.py >"$LOG_FILE" 2>&1 &
echo $! >"$LOG_DIR/rgb.pid"

sleep "${JETARM_RGB_WARMUP_S:-8}"

echo "RGB topics:"
ros2 topic list -t 2>/dev/null | grep -E 'depth_cam|image|camera' || true

if timeout 8 ros2 topic echo --once /depth_cam/rgb/image_raw --field encoding >/tmp/jetarm_rgb_encoding.txt 2>/tmp/jetarm_rgb_encoding.err; then
  echo "RGB encoding: $(tr -d '\n' </tmp/jetarm_rgb_encoding.txt)"
else
  echo "RGB sample failed:"
  cat /tmp/jetarm_rgb_encoding.err
  exit 1
fi
