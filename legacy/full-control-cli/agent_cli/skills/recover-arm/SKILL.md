---
name: recover-arm
description: "Recover JetArm from uncertain workflow, servo, or grasp states using full-control stop and reset commands."
---

# Recover Arm

Use this skill before retrying any motion after a failed, interrupted, or uncertain command.

## Workflow

1. Run `stop_all`.
2. Inspect ROS graph with `ros rostopic list` if cleanup fails.
3. Run `open_gripper` if an object may still be held.
4. Run `go_home` only if the arm is physically clear and not blocked.
5. Capture evidence with `camera_frame` when scene state matters.
6. Write the recovery outcome to the transcript by summarizing the command result.
