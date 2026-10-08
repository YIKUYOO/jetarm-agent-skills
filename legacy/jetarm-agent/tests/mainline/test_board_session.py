from jetarm_agent.baseline.board_session import (
    BoardActionStatus,
    BoardSessionMode,
    PickPlaceFailureStage,
    build_board_session_manifest,
    initialize_board_session_result,
    record_board_action_result,
    render_board_session_runbook,
)
from jetarm_agent.baseline.supervised_validation import ValidatedActionName


def test_build_board_session_manifest_preserves_action_order_and_stop_subcases():
    manifest = build_board_session_manifest(
        session_id="session-001",
        board_target="jetarm@board",
        mode=BoardSessionMode.SSH_SHELL,
    )

    assert [action.action_name for action in manifest.actions] == [
        ValidatedActionName.GO_HOME,
        ValidatedActionName.OPEN_GRIPPER,
        ValidatedActionName.CLOSE_GRIPPER,
        ValidatedActionName.STOP_ALL,
        ValidatedActionName.PICK_PLACE,
    ]
    stop_action = next(action for action in manifest.actions if action.action_name is ValidatedActionName.STOP_ALL)
    assert stop_action.subcases == ["single_action_interrupt", "task_flow_interrupt"]
    assert any(command.startswith("ssh jetarm@board ") for command in stop_action.command_templates)


def test_record_board_action_result_blocks_following_actions_after_failure():
    manifest = build_board_session_manifest(
        session_id="session-001",
        board_target="localhost",
        mode=BoardSessionMode.LOCAL_SHELL,
    )
    result = initialize_board_session_result(manifest)
    updated = record_board_action_result(
        result,
        action_name=ValidatedActionName.CLOSE_GRIPPER,
        status=BoardActionStatus.FAILED,
        observed_behavior="gripper stalled",
    )

    statuses = {item.action_name: item.status for item in updated.action_results}
    assert statuses[ValidatedActionName.CLOSE_GRIPPER] is BoardActionStatus.FAILED
    assert statuses[ValidatedActionName.STOP_ALL] is BoardActionStatus.BLOCKED
    assert statuses[ValidatedActionName.PICK_PLACE] is BoardActionStatus.BLOCKED
    assert updated.overall_status is BoardActionStatus.FAILED


def test_pick_place_failure_stage_enum_covers_all_required_stages():
    assert {item.value for item in PickPlaceFailureStage} == {
        "enter",
        "detect",
        "grasp",
        "place",
        "exit",
    }


def test_render_board_session_runbook_mentions_operator_gate_and_pick_place():
    manifest = build_board_session_manifest(
        session_id="session-001",
        board_target="localhost",
        mode=BoardSessionMode.LOCAL_SHELL,
    )

    report = render_board_session_runbook(manifest)

    assert "现场有人值守" in report
    assert "pick_place" in report
    assert "/object_sortting/enable_sortting" in report
