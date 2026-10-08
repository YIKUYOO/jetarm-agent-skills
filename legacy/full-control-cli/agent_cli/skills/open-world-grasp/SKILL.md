---
name: open-world-grasp
description: "Perform open-world desktop grasp attempts by observing, locating, planning, executing, verifying, and repairing failures."
---

# Open World Grasp

Use this skill when the user asks the agent to manipulate an object on the desktop.

## Workflow

1. Start from a known state with `go_home` and `open_gripper`.
2. Capture a `camera_frame` and inspect current scene evidence.
3. Use available VLM/cloud tools outside this CLI to identify the target and describe uncertainty.
4. Prefer official JetArm ROS workflows if they can solve the task.
5. If official workflows are insufficient, use `python_script`, `ros`, and `servo_debug` to experiment directly.
6. After every motion attempt, capture another `camera_frame` and verify whether the target moved as intended.
7. On failure, classify the failure as observe, locate, reachability, grasp, place, release, or verify.
8. Run `stop_all` before retrying after an uncertain or failed motion.
