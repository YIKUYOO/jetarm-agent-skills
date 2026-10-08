---
name: jetarm-visual-observe
description: Capture and interpret JetArm local, RGB-D and optional CSI observations without commanding motion.
---

Read the repository README and obtain state evidence first. Select the requested view using `capture_local_opencv.py`, Windows webcam helpers, `capture_rdk_observation.py` or `capture_rdk_csi_observation.py` in `scripts/local`. `jetarm_triview_cycle.py` combines current servo readings and available views without motion commands.

Record image paths, capture time, camera identity, target visibility, occlusion and depth quality. Original RGB and depth resolutions differed; shape scaling is not calibrated registration. Downgrade unregistered, clipped or invalid depth. Capture fresh observations after the object moves. Do not claim a metric target pose from a plausible-looking pixel alone.
