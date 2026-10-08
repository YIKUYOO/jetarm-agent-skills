from typing import Any

import numpy as np


def normalize_servo_positions(positions, min_position=0.0, max_position=1000.0):
    """Normalize raw JetArm servo pulses into [0, 1]."""

    span = max_position - min_position
    if span <= 0:
        raise ValueError("max_position must be greater than min_position")
    values = np.asarray(positions, dtype=np.float32)
    normalized = (values - min_position) / span
    return np.clip(normalized, 0.0, 1.0).round(6).tolist()


class DatasetFrame:
    def __init__(
        self,
        timestamp,
        language_instruction,
        rgb,
        depth_raw_mm,
        depth_vis,
        state,
        action,
        ee_pose,
        color_camera_info,
        depth_camera_info,
        extra_metadata=None,
    ):
        self.timestamp = timestamp
        self.language_instruction = language_instruction
        self.rgb = rgb
        self.depth_raw_mm = depth_raw_mm
        self.depth_vis = depth_vis
        self.state = state
        self.action = action
        self.ee_pose = ee_pose
        self.color_camera_info = color_camera_info
        self.depth_camera_info = depth_camera_info
        self.extra_metadata = extra_metadata or {}

    def validate(self):
        if not self.language_instruction.strip():
            raise ValueError("language_instruction must be non-empty")
        _require_image(self.rgb, "rgb", channels=3, dtype=np.uint8)
        _require_image(self.depth_vis, "depth_vis", channels=3, dtype=np.uint8)
        if self.depth_raw_mm.ndim != 2 or self.depth_raw_mm.dtype != np.uint16:
            raise ValueError("depth_raw_mm must be a 2-D uint16 image")
        if self.rgb.shape[:2] != self.depth_raw_mm.shape:
            raise ValueError("rgb and depth_raw_mm must have matching height/width")
        if self.rgb.shape != self.depth_vis.shape:
            raise ValueError("rgb and depth_vis must have matching shape")
        _require_vector(self.state, "state", 13)
        _require_vector(self.action, "action", 6)
        _require_vector(self.ee_pose, "ee_pose", 7)


def _require_image(array, name, channels, dtype):
    if array.ndim != 3 or array.shape[2] != channels:
        raise ValueError("{} must be an HxWx{} image".format(name, channels))
    if array.dtype != dtype:
        raise ValueError("{} must have dtype {}".format(name, dtype))


def _require_vector(array, name, length):
    if array.shape != (length,):
        raise ValueError("{} must have shape ({},)".format(name, length))
    if not np.issubdtype(array.dtype, np.floating):
        raise ValueError("{} must use a floating dtype".format(name))
