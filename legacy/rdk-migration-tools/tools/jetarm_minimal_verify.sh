#!/usr/bin/env bash
# Run the minimal JetArm ROS2 verification path for Codex/VLA bring-up.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/jetarm_env.sh"

WAIT_S="${WAIT_S:-5}"
OUT_DIR="${OUT_DIR:-/tmp/jetarm_minimal_verify_$(date +%Y%m%d_%H%M%S)}"
REQUIRE_DEPTH="${REQUIRE_DEPTH:-0}"
EXECUTE_NUDGE=0

usage() {
  cat <<'EOF'
Usage: jetarm_minimal_verify.sh [--wait-s SECONDS] [--out-dir DIR] [--require-depth] [--execute-nudge]

Default is safe: it verifies packages/devices, starts RGB fallback, captures an
observation, and only dry-runs the joint nudge plan. --execute-nudge requires
/dev/rrc and live servo state, then nudges each joint slightly and returns.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --wait-s)
      WAIT_S="$2"; shift 2 ;;
    --out-dir)
      OUT_DIR="$2"; shift 2 ;;
    --require-depth)
      REQUIRE_DEPTH=1; shift ;;
    --execute-nudge)
      EXECUTE_NUDGE=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2 ;;
  esac
done

mkdir -p "$OUT_DIR"
SUMMARY="$OUT_DIR/summary.json"
CLEANED_UP=0

cleanup_on_exit() {
  if [ "$CLEANED_UP" = "0" ]; then
    "$SCRIPT_DIR/jetarm_cleanup.sh" || true
    CLEANED_UP=1
  fi
}
trap cleanup_on_exit EXIT

section() {
  echo
  echo "=== $* ==="
}

write_summary() {
  local status="$1"
  local reason="${2:-}"
  python3 - "$SUMMARY" "$status" "$reason" "$OUT_DIR" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "status": sys.argv[2],
    "reason": sys.argv[3],
    "output_dir": sys.argv[4],
}
path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY
}

section "cleanup"
"$SCRIPT_DIR/jetarm_cleanup.sh" || true

section "status"
"$SCRIPT_DIR/jetarm_status.sh" | tee "$OUT_DIR/status.txt"

section "hardware gate"
if ! REQUIRE_DEPTH="$REQUIRE_DEPTH" "$SCRIPT_DIR/jetarm_wait_for_hardware.sh" "$WAIT_S" | tee "$OUT_DIR/hardware_gate.txt"; then
  section "rgb fallback still usable"
  "$SCRIPT_DIR/jetarm_bringup_rgb.sh" | tee "$OUT_DIR/rgb_bringup.txt" || true
  python3 "$SCRIPT_DIR/jetarm_capture_observation.py" \
    --output-dir "$OUT_DIR/observation_rgb_only" \
    --timeout-s 5 | tee "$OUT_DIR/observation_rgb_only.txt" || true
  "$SCRIPT_DIR/jetarm_cleanup.sh" || true
  write_summary "blocked" "hardware gate failed"
  echo "Minimal verification blocked by missing hardware gate. Summary: $SUMMARY"
  exit 2
fi

section "core bringup"
"$SCRIPT_DIR/jetarm_bringup_core.sh" | tee "$OUT_DIR/core_bringup.txt"

section "state dry-run nudge"
if ! python3 "$SCRIPT_DIR/jetarm_joint_nudge_test.py" --json --state-timeout 8 | tee "$OUT_DIR/nudge_dry_run.json"; then
  write_summary "failed" "state dry-run nudge failed"
  echo "Minimal verification failed during state dry-run nudge. Summary: $SUMMARY"
  exit 1
fi

section "rgb bringup"
JETARM_SKIP_CLEANUP=1 "$SCRIPT_DIR/jetarm_bringup_rgb.sh" | tee "$OUT_DIR/rgb_bringup.txt"

section "observation capture"
CAPTURE_ARGS=(--output-dir "$OUT_DIR/observation" --timeout-s 8 --require-state)
if [ "$REQUIRE_DEPTH" = "1" ]; then
  CAPTURE_ARGS+=(--require-depth)
fi
if ! python3 "$SCRIPT_DIR/jetarm_capture_observation.py" "${CAPTURE_ARGS[@]}" | tee "$OUT_DIR/observation_capture.txt"; then
  write_summary "failed" "observation capture failed"
  echo "Minimal verification failed during observation capture. Summary: $SUMMARY"
  exit 1
fi

if [ "$EXECUTE_NUDGE" = "1" ]; then
  section "execute nudge"
  if ! python3 "$SCRIPT_DIR/jetarm_joint_nudge_test.py" --execute --json --state-timeout 8 | tee "$OUT_DIR/nudge_execute.json"; then
    write_summary "failed" "execute nudge failed"
    echo "Minimal verification failed during execute nudge. Summary: $SUMMARY"
    exit 1
  fi
else
  section "execute nudge skipped"
  echo "Pass --execute-nudge to move joints after confirming the workspace is safe."
fi

section "final ros snapshot"
ros2 node list > "$OUT_DIR/ros_nodes.txt" 2>&1 || true
ros2 topic list -t > "$OUT_DIR/ros_topics.txt" 2>&1 || true
ros2 service list -t > "$OUT_DIR/ros_services.txt" 2>&1 || true

CLEANED_UP=1
"$SCRIPT_DIR/jetarm_cleanup.sh" || true
write_summary "passed" ""
echo "Minimal verification finished. Summary: $SUMMARY"
