from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from jetarm_agent.skill_contract import (
    AdapterCapabilityLevel,
    CheckTargetRequest,
    DetectTargetRequest,
    RecoverRequest,
    SkillErrorCode,
    SkillResult,
    SkillStatus,
    SkillTargetPayload,
)
from jetarm_agent.schemas import CalibrationOffsets, CalibrationProfile, DetectedTarget, WorkcellConstraints


def build_profile() -> CalibrationProfile:
    return CalibrationProfile(
        profile_name="lab-a",
        camera_frame="rgbd_cam_color_optical_frame",
        base_frame="base_link",
        offsets=CalibrationOffsets(),
        workcell=WorkcellConstraints(
            allowed_object_classes=["color_block"],
            destination_zones={"left_bin": {"frame": "base_link", "x": 0.2, "y": 0.1, "z": 0.05}},
        ),
    )


def build_target() -> DetectedTarget:
    return DetectedTarget(
        entity_id="block-red-1",
        object_class="color_block",
        color="red",
        confidence=0.95,
        source_timestamp=datetime(2026, 3, 30, tzinfo=timezone.utc),
        pose={"frame": "base_link", "x": 0.1, "y": 0.2, "z": 0.3},
    )


def test_skill_result_preserves_status_error_and_payload():
    result = SkillResult[SkillTargetPayload](
        status=SkillStatus.SUCCEEDED,
        error_code=None,
        message="target confirmed",
        telemetry={"source": "test"},
        artifacts={"trace": "abc"},
        payload=SkillTargetPayload(target=build_target()),
    )

    assert result.status is SkillStatus.SUCCEEDED
    assert result.payload.target.entity_id == "block-red-1"
    assert result.telemetry["source"] == "test"


def test_detect_target_request_rejects_invalid_minimum_confidence():
    with pytest.raises(ValidationError):
        DetectTargetRequest(
            profile=build_profile(),
            object_class="color_block",
            color="red",
            minimum_confidence=1.5,
        )


def test_check_target_request_requires_known_destination_zone_when_provided():
    with pytest.raises(ValidationError):
        CheckTargetRequest(
            profile=build_profile(),
            target=build_target(),
            required_zone="right_bin",
        )


def test_check_target_request_rejects_non_positive_maximum_target_age():
    with pytest.raises(ValidationError):
        CheckTargetRequest(
            profile=build_profile(),
            target=build_target(),
            maximum_target_age_seconds=0.0,
        )


def test_recover_request_accepts_last_error_code():
    request = RecoverRequest(
        reason="cleanup after interrupted place",
        last_error_code=SkillErrorCode.STOP_REQUESTED,
    )

    assert request.last_error_code is SkillErrorCode.STOP_REQUESTED


def test_adapter_capability_level_values_are_stable():
    assert AdapterCapabilityLevel.FROZEN.value == "frozen"
    assert AdapterCapabilityLevel.PROVISIONAL.value == "provisional"
