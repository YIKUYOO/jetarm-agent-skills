import numpy as np

from jetarm_vla_common.schema import DatasetFrame, normalize_servo_positions


def test_normalize_servo_positions_maps_pulse_range_to_unit_interval():
    assert normalize_servo_positions([0, 250, 500, 750, 1000, 1200]) == [
        0.0,
        0.25,
        0.5,
        0.75,
        1.0,
        1.0,
    ]


def test_dataset_frame_requires_fixed_state_and_action_shapes():
    frame = DatasetFrame(
        timestamp=1.5,
        language_instruction="pick the red block and place it in the box",
        rgb=np.zeros((4, 4, 3), dtype=np.uint8),
        depth_raw_mm=np.zeros((4, 4), dtype=np.uint16),
        depth_vis=np.zeros((4, 4, 3), dtype=np.uint8),
        state=np.zeros(13, dtype=np.float32),
        action=np.zeros(6, dtype=np.float32),
        ee_pose=np.zeros(7, dtype=np.float32),
        color_camera_info={"width": 4, "height": 4},
        depth_camera_info={"width": 4, "height": 4},
    )

    frame.validate()

    bad = DatasetFrame(
        timestamp=frame.timestamp,
        language_instruction=frame.language_instruction,
        rgb=frame.rgb,
        depth_raw_mm=frame.depth_raw_mm,
        depth_vis=frame.depth_vis,
        state=np.zeros(12, dtype=np.float32),
        action=frame.action,
        ee_pose=frame.ee_pose,
        color_camera_info=frame.color_camera_info,
        depth_camera_info=frame.depth_camera_info,
    )

    try:
        bad.validate()
    except ValueError as exc:
        assert "state" in str(exc)
    else:
        raise AssertionError("DatasetFrame should reject non-13D state")
