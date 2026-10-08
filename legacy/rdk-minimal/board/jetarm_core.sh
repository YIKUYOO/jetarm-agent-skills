#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/jetarm_env.sh"

PID_FILE="$JETARM_MINIMAL_LOG_DIR/core.pid"

start_core() {
  if [ ! -e /dev/rrc ]; then
    echo '{"ok":false,"error_code":"RRC_MISSING"}'
    exit 2
  fi
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo '{"ok":true,"status":"already_running"}'
    exit 0
  fi
  local log_file="$JETARM_MINIMAL_LOG_DIR/core_$(date +%Y%m%d_%H%M%S).log"
  ros2 launch sdk jetarm_sdk.launch.py >"$log_file" 2>&1 &
  echo $! >"$PID_FILE"
  sleep "${JETARM_CORE_WARMUP_S:-12}"
  echo "{\"ok\":true,\"status\":\"started\",\"pid\":$(cat "$PID_FILE"),\"log\":\"$log_file\"}"
}

stop_core() {
  if [ -f "$PID_FILE" ]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    rm -f "$PID_FILE"
  fi
  pkill -f '[r]os_robot_controller' 2>/dev/null || true
  pkill -f '[s]ervo_controller' 2>/dev/null || true
  pkill -f '[s]earch_kinematics_solutions' 2>/dev/null || true
  pkill -f '[c]heck_servo_connection' 2>/dev/null || true
  sleep 2
  echo '{"ok":true,"status":"stopped"}'
}

status_core() {
  local nodes
  nodes="$(ros2 node list 2>/dev/null | tr '\n' ' ' | sed 's/ *$//')"
  echo "{\"ok\":true,\"nodes\":\"$nodes\"}"
}

case "${1:-status}" in
  start) start_core ;;
  stop) stop_core ;;
  status) status_core ;;
  *) echo '{"ok":false,"error_code":"BAD_COMMAND"}'; exit 2 ;;
esac
