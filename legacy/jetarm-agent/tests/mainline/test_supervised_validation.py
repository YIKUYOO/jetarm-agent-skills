from jetarm_agent.baseline.supervised_validation import (
    ValidatedActionName,
    ValidationStatus,
    build_supervised_validation_specs,
    build_validation_outcomes,
    render_supervised_validation_protocol,
)


def test_build_supervised_validation_specs_covers_all_formal_actions():
    specs = build_supervised_validation_specs()

    assert set(specs) == {
        ValidatedActionName.GO_HOME,
        ValidatedActionName.OPEN_GRIPPER,
        ValidatedActionName.CLOSE_GRIPPER,
        ValidatedActionName.STOP_ALL,
        ValidatedActionName.PICK_PLACE,
    }
    assert any("actions.py" in entry for entry in specs[ValidatedActionName.GO_HOME].official_entrypoints)


def test_pick_place_spec_preserves_official_task_flow_foundations():
    specs = build_supervised_validation_specs()
    pick_place = specs[ValidatedActionName.PICK_PLACE]

    assert "positioning_clamp.launch" in pick_place.official_entrypoints
    assert "color_sorting.launch" in pick_place.official_entrypoints
    assert "/object_sortting/enable_sortting" in pick_place.official_entrypoints
    assert "/grasp" in pick_place.official_entrypoints


def test_build_validation_outcomes_defaults_to_pending_with_entrypoints():
    outcomes = build_validation_outcomes([ValidatedActionName.STOP_ALL])
    stop_outcome = outcomes[0]

    assert stop_outcome.action_name is ValidatedActionName.STOP_ALL
    assert stop_outcome.status is ValidationStatus.PENDING
    assert stop_outcome.official_entrypoints


def test_render_supervised_validation_protocol_mentions_safety_gate_and_pick_place():
    specs = build_supervised_validation_specs()
    report = render_supervised_validation_protocol(
        [
            specs[ValidatedActionName.GO_HOME],
            specs[ValidatedActionName.PICK_PLACE],
        ]
    )

    assert "现场有人值守" in report
    assert "pick_place" in report
    assert "positioning_clamp.launch" in report
