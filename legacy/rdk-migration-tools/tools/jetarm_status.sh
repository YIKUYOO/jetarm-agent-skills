#!/usr/bin/env bash
# Print the current minimal JetArm ROS2 and hardware status.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/jetarm_env.sh"

echo "== time =="
date -Is

echo
echo "== readiness summary =="
if [ -e /dev/rrc ]; then
  echo "control: ready (/dev/rrc)"
elif ls /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* >/dev/null 2>&1; then
  echo "control: serial candidate present, /dev/rrc missing"
else
  echo "control: missing (no /dev/rrc, /dev/ttyUSB*, /dev/ttyACM*, or /dev/serial/by-id/*)"
fi

if lsusb 2>/dev/null | grep -qi '2bc5:0614'; then
  echo "depth_usb: present (2bc5:0614 Orbbec Depth Sensor)"
else
  echo "depth_usb: missing (2bc5:0614 not enumerated)"
fi

if lsusb 2>/dev/null | grep -qi '2bc5:0511'; then
  echo "rgb_usb: present (2bc5:0511 UVC RGB camera)"
elif ls /dev/video* >/dev/null 2>&1; then
  echo "rgb_usb: video device present"
else
  echo "rgb_usb: missing"
fi

echo
echo "== workspace =="
echo "JETARM_WS=$JETARM_WS"
test -d "$JETARM_WS" && echo "workspace: present" || echo "workspace: missing"
test -f "$JETARM_WS/install/setup.bash" && echo "install: present" || echo "install: missing"

echo
echo "== ros packages =="
for pkg in \
  ros_robot_controller_msgs servo_controller_msgs kinematics_msgs interfaces \
  ros_robot_controller servo_controller kinematics sdk peripherals bringup; do
  prefix="$(ros2 pkg prefix "$pkg" 2>/dev/null || true)"
  if [ -n "$prefix" ]; then
    echo "$pkg: $prefix"
  else
    echo "$pkg: MISSING"
  fi
done

echo
echo "== devices =="
ls -l /dev/rrc /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* /dev/video* 2>/dev/null || true

echo
echo "== tty candidates =="
ls -l /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* /dev/ttyS* /dev/ttyTHS* /dev/ttyAMA* /dev/ttymxc* 2>/dev/null || true

echo
echo "== usb =="
lsusb 2>/dev/null || true

echo
echo "== usb tree =="
lsusb -t 2>/dev/null || true

echo
echo "== ros nodes =="
ros2 node list 2>/dev/null || true

echo
echo "== ros topics =="
ros2 topic list -t 2>/dev/null || true

echo
echo "== ros services =="
ros2 service list -t 2>/dev/null || true

echo
echo "== serial dmesg tail =="
dmesg 2>/dev/null | grep -Ei 'ttyUSB|ttyACM|ch34|ch341|cp210|ftdi|1a86|usb serial' | tail -80 || true
