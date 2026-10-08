import pytest

from jetarm_demo_agent import schemas


def test_open_desktop_public_models_round_trip():
    object_ref = schemas.ObjectRef(
        name="药盒",
        bbox_xyxy_norm=[0.10, 0.20, 0.40, 0.60],
        center_px=[160, 192],
        confidence=0.88,
        source="vlm",
    )
    goal = schemas.ManipulationGoal(
        action="move_near",
        source_object=object_ref,
        target_object_or_region=schemas.ObjectRef(
            name="碗",
            bbox_xyxy_norm=[0.55, 0.30, 0.85, 0.70],
            center_px=[448, 240],
            confidence=0.9,
            source="vlm",
        ),
        placement_relation="near",
        requires_human_confirmation=True,
    )
    observation = schemas.SceneObservation(
        frames=[{"label": "center", "image_base64": "ZmFrZQ==", "media_type": "image/jpeg"}],
        vlm_objects=[object_ref, goal.target_object_or_region],
        calibration_version="jetarm-rgbd-v1",
        timestamp="2026-05-03T15:00:00+08:00",
    )

    assert observation.vlm_objects[0].name == "药盒"
    assert goal.requires_human_confirmation is True
    assert goal.source_object.confidence == 0.88


def test_object_ref_rejects_invalid_normalized_bbox():
    with pytest.raises(ValueError, match="bbox_xyxy_norm"):
        schemas.ObjectRef(
            name="越界物体",
            bbox_xyxy_norm=[-0.1, 0.2, 0.4, 0.6],
            confidence=0.8,
            source="vlm",
        )


def test_skill_result_exposes_failure_stage_and_motion_guard():
    result = schemas.SkillResult(
        ok=False,
        stage="safety_check",
        motion_executed=False,
        object_locked=False,
        summary="需要人工确认后才能执行开放桌面搬运",
        error_code="HUMAN_CONFIRMATION_REQUIRED",
        evidence_frames=["center"],
    )

    assert result.stage == "safety_check"
    assert result.motion_executed is False
    assert result.error_code == "HUMAN_CONFIRMATION_REQUIRED"
