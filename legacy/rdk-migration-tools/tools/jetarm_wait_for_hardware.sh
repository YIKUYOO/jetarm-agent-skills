#!/usr/bin/env bash
# Wait for the JetArm control board and optional Orbbec depth USB device.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/jetarm_env.sh"

TIMEOUT_S="${1:-60}"
REQUIRE_DEPTH="${REQUIRE_DEPTH:-0}"
START_TS="$(date +%s)"

has_control() {
  [ -e /dev/rrc ] || ls /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* >/dev/null 2>&1
}

has_depth_usb() {
  lsusb 2>/dev/null | grep -qi '2bc5:0614'
}

echo "Waiting for JetArm hardware for up to ${TIMEOUT_S}s..."
while true; do
  NOW="$(date +%s)"
  ELAPSED=$((NOW - START_TS))

  CONTROL=missing
  DEPTH=missing
  if has_control; then
    CONTROL=present
  fi
  if has_depth_usb; then
    DEPTH=present
  fi

  echo "elapsed=${ELAPSED}s control=${CONTROL} depth_usb=${DEPTH}"

  if [ "$CONTROL" = present ] && { [ "$REQUIRE_DEPTH" != "1" ] || [ "$DEPTH" = present ]; }; then
    echo "Hardware gate passed."
    exit 0
  fi

  if [ "$ELAPSED" -ge "$TIMEOUT_S" ]; then
    echo "Hardware gate timed out." >&2
    echo "Expected control: /dev/rrc or /dev/ttyUSB*/ttyACM*/serial/by-id." >&2
    if [ "$REQUIRE_DEPTH" = "1" ]; then
      echo "Expected depth USB: 2bc5:0614 Orbbec Depth Sensor." >&2
    fi
    exit 2
  fi

  sleep 2
done
