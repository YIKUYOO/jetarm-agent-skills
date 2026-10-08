---
name: jetarm-task-evaluate
description: Assess robot task completion from command, state, visual and safety evidence.
---

Compare the requested physical outcome with before/after evidence. Use four axes: command execution, robot state, visible world change and safe recoverability. Return `success`, `partial`, `failed`, `unsafe` or `unknown` with evidence paths and uncertainty.

A grasp requires a post-lift image showing the target clear of the table and retained by the gripper. A low closed pose, action-server success or changed servo state alone is insufficient. The red-block classifier is camera-specific; its label is only a heuristic. Missing evidence gives `unknown`, and a visible contradiction gives `failed`. Keep individual trials separate from statistical performance claims.
