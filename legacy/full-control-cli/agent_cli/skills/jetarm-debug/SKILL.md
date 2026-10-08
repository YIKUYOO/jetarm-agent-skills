---
name: jetarm-debug
description: "Inspect JetArm ROS, topics, services, launch state, camera, logs, and recovery state with full-control tools."
---

# JetArm Debug

Use this skill when the agent needs to understand why the robot, camera, ROS graph, grasp pipeline, or servo path is not working.

## Workflow

1. Run `list_tools` and confirm full-control tools are available.
2. Run `ros rostopic list` and verify camera, `/grasp`, `/object_sortting`, servo, and controller topics.
3. Capture a `camera_frame` if perception is involved.
4. Inspect failing commands with `shell`, `ros`, `rostopic`, and `rosservice`.
5. Run `stop_all` before retrying motion or changing workflows.
6. Record the failure stage and exact recovery command in the transcript.
