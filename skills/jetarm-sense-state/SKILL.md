---
name: jetarm-sense-state
description: Inspect JetArm ROS2 control, servo and camera readiness before supervised physical experiments.
---

Use this workflow to establish what is currently observable. Read the repository README for SSH settings and board paths. Connect with the configured key and verified known-hosts entry. Inspect the ROS node list, servo readback, action-service readiness and camera topics. Do not start hardware or move the arm merely to inspect it.

Report board connectivity, exactly one control stack, `/ros_robot_controller` presence, servo readings, camera availability and evidence time. A changing software servo state without the hardware driver is insufficient. Label the state `ready_for_supervised_review`, `not_ready` or `unknown`; readiness never substitutes for user authorization to move.
