---
name: jetarm-tabletop-pick
description: Plan and evaluate a supervised JetArm tabletop grasp using fresh multi-view evidence and explicit execution gating.
---

Read the README and establish state and visual evidence with the other skills. This experimental workflow has one historical red-block lift baseline; it does not establish reliable arbitrary-object grasping.

1. Resolve the requested target and capture local plus wrist/side observations. Check registration, clipping, occlusion and calibration.
2. Use `jetarm_multiview_pick_analyze.py` for a board-calibrated estimate when the SDK is available, and `jetarm_triview_relation.py` for conservative gripper/target relation evidence.
3. Preview a bounded approach or open-gripper probe with `jetarm_tabletop_motion.py`. The default preview is offline and cannot verify IK or collision freedom.
4. After explicit current authorization and physical safety checks, add `--execute` for the reviewed action. Keep experiments small, low speed and supervised. Stop when camera or servo evidence becomes unreliable.
5. Recapture after every contact or target displacement. Close only after fresh evidence places the object inside the working finger volume; an advisory overlap score is insufficient by itself.
6. Use independent post-lift evidence and `jetarm-task-evaluate` to record the actual result. Preserve failures and do not reuse stale coordinates.

The direct servo helper and place helper also require `--execute`. Do not copy fixed historical pulses into a different robot geometry. Public packaging and SDK adapter changes require fresh device acceptance before claiming reproductions.
