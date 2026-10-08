#!/usr/bin/env bash
# Common environment loader for the minimal JetArm ROS2 workspace on RDK X5.

set +u
JETARM_WS="${JETARM_WS:-$HOME/jetarm_ros2_ws}"

if [ ! -f "$JETARM_WS/jetarm_rdk_env.sh" ]; then
  echo "missing $JETARM_WS/jetarm_rdk_env.sh" >&2
  return 1 2>/dev/null || exit 1
fi

source "$JETARM_WS/jetarm_rdk_env.sh"

if [ -f "$JETARM_WS/install/setup.bash" ]; then
  source "$JETARM_WS/install/setup.bash"
fi

export JETARM_WS
