from jetarm_demo_agent.orchestration.open_desktop_safety import evaluate_manipulation_goal
from jetarm_demo_agent.schemas import ManipulationGoal, ObjectRef


def _object(name, confidence=0.9, world_pose=None):
    return ObjectRef(
        name=name,
        bbox_xyxy_norm=[0.2, 0.2, 0.4, 0.4],
        confidence=confidence,
        source="vlm",
        world_pose_optional=world_pose,
    )


def test_safety_blocks_low_confidence_source_object():
    goal = ManipulationGoal(
        action="move_near",
        source_object=_object("药盒", confidence=0.51),
        target_object_or_region=_object("碗"),
        placement_relation="near",
        requires_human_confirmation=True,
    )

    result = evaluate_manipulation_goal(goal)

    assert result.ok is False
    assert result.stage == "locating"
    assert result.motion_executed is False
    assert result.error_code == "LOW_VLM_CONFIDENCE"


def test_safety_blocks_missing_world_pose_before_live_motion():
    goal = ManipulationGoal(
        action="move_near",
        source_object=_object("药盒"),
        target_object_or_region=_object("碗"),
        placement_relation="near",
        requires_human_confirmation=True,
    )

    result = evaluate_manipulation_goal(goal)

    assert result.ok is False
    assert result.stage == "localizing"
    assert result.error_code == "WORLD_POSE_MISSING"


def test_safety_requires_human_confirmation_for_open_desktop_goal():
    goal = ManipulationGoal(
        action="move_near",
        source_object=_object("药盒", world_pose=[0.18, 0.02, 0.03]),
        target_object_or_region=_object("碗", world_pose=[0.08, 0.12, 0.03]),
        placement_relation="near",
        requires_human_confirmation=True,
    )

    result = evaluate_manipulation_goal(goal)

    assert result.ok is False
    assert result.stage == "safety_check"
    assert result.error_code == "HUMAN_CONFIRMATION_REQUIRED"
    assert result.motion_executed is False
