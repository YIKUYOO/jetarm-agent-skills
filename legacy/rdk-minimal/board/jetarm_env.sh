#!/usr/bin/env bash
set -e

export JETARM_ROS_WS="${JETARM_ROS_WS:-$HOME/jetarm_ros2_ws}"
export JETARM_MINIMAL_ROOT="${JETARM_MINIMAL_ROOT:-$HOME/jetarm_codex_minimal}"
export JETARM_MINIMAL_LOG_DIR="${JETARM_MINIMAL_LOG_DIR:-/tmp/jetarm_codex_minimal_logs}"

export need_compile="${need_compile:-True}"
export CHASSIS_TYPE="${CHASSIS_TYPE:-None}"
export CAMERA_TYPE="${CAMERA_TYPE:-GEMINI}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"

mkdir -p "$JETARM_MINIMAL_LOG_DIR"

if [ -f /opt/tros/humble/setup.bash ]; then
  source /opt/tros/humble/setup.bash
fi

if [ -f "$JETARM_ROS_WS/install/setup.bash" ]; then
  source "$JETARM_ROS_WS/install/setup.bash"
fi
