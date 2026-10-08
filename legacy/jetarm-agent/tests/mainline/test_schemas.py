from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from jetarm_agent.schemas import (
    CalibrationProfile,
    CalibrationOffsets,
    DetectedTarget,
    PickPlaceRequest,
    PickPlaceResult,
    PickPlaceStatus,
    WorkcellConstraints,
)


def test_detected_target_validates_required_fields():
    detected = DetectedTarget(
        entity_id="block-red-1",
        object_class="color_block",
        color="red",
        confidence=0.93,
        source_timestamp=datetime(2026, 3, 29, tzinfo=timezone.utc),
        pose={"frame": "camera", "x": 0.1, "y": 0.2, "z": 0.3},
    )

    assert detected.entity_id == "block-red-1"
    assert detected.confidence == pytest.approx(0.93)


def test_detected_target_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        DetectedTarget(
            entity_id="block-red-1",
            object_class="color_block",
            color="red",
            confidence=1.5,
            source_timestamp=datetime(2026, 3, 29, tzinfo=timezone.utc),
            pose={"frame": "camera"},
        )


def test_pick_place_request_uses_formal_profile_and_destination():
    profile = CalibrationProfile(
        profile_name="lab-a",
        camera_frame="rgbd_cam_color_optical_frame",
        base_frame="base_link",
        offsets=CalibrationOffsets(pick={"x": 0.0}, place={"x": 0.01}),
        workcell=WorkcellConstraints(
            allowed_object_classes=["color_block"],
            destination_zones={"left_bin": {"frame": "base_link", "x": 0.25, "y": 0.12, "z": 0.08}},
        ),
    )

    request = PickPlaceRequest(
        request_id="req-1",
        profile=profile,
        target=DetectedTarget(
            entity_id="block-red-1",
            object_class="color_block",
            color="red",
            confidence=0.9,
            source_timestamp=datetime(2026, 3, 29, tzinfo=timezone.utc),
            pose={"frame": "camera", "x": 0.1, "y": 0.2, "z": 0.3},
        ),
        destination_zone="left_bin",
    )

    assert request.destination_zone == "left_bin"
    assert request.profile.profile_name == "lab-a"


def test_pick_place_request_rejects_unknown_destination_zone():
    profile = CalibrationProfile(
        profile_name="lab-a",
        camera_frame="rgbd_cam_color_optical_frame",
        base_frame="base_link",
        offsets=CalibrationOffsets(),
        workcell=WorkcellConstraints(
            allowed_object_classes=["color_block"],
            destination_zones={"left_bin": {"frame": "base_link", "x": 0.25, "y": 0.12, "z": 0.08}},
        ),
    )

    with pytest.raises(ValidationError):
        PickPlaceRequest(
            request_id="req-1",
            profile=profile,
            target=DetectedTarget(
                entity_id="block-red-1",
                object_class="color_block",
                color="red",
                confidence=0.9,
                source_timestamp=datetime(2026, 3, 29, tzinfo=timezone.utc),
                pose={"frame": "camera", "x": 0.1, "y": 0.2, "z": 0.3},
            ),
            destination_zone="right_bin",
        )


def test_pick_place_result_preserves_status_and_failure_stage():
    result = PickPlaceResult(
        request_id="req-1",
        status=PickPlaceStatus.FAILED,
        failure_stage="pick",
        telemetry={"attempts": 1},
        artifacts={"log": "pick failed"},
    )

    assert result.status is PickPlaceStatus.FAILED
    assert result.failure_stage == "pick"
