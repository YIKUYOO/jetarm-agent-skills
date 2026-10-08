#!/usr/bin/env bash
# Stop JetArm minimal bringup processes without touching unrelated user jobs.

set -euo pipefail

patterns=(
  "ros2 launch sdk jetarm_sdk.launch.py"
  "ros2 launch peripherals depth_camera.launch.py"
  "ros2 launch orbbec_camera"
  "ros_robot_controller"
  "servo_controller"
  "search_kinematics_solutions"
  "check_servo_connection"
  "usb_cam_node_exe"
  "image_proc"
  "static_transform_publisher"
  "jetarm_capture_rgb_once.py"
  "jetarm_capture_observation.py"
  "jetarm_probe_control_port.py"
  "openni2_camera_driver"
  "orbbec_camera"
  "camera_container"
  "component_container"
  "component_container_mt"
  "launch_ros_"
)

for pattern in "${patterns[@]}"; do
  pkill -f "$pattern" 2>/dev/null || true
done

sleep 1

for pattern in "${patterns[@]}"; do
  pkill -9 -f "$pattern" 2>/dev/null || true
done

echo "JetArm minimal ROS2 processes cleaned."
