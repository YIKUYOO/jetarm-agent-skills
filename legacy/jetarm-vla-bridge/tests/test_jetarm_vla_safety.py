import pytest

from jetarm_vla_common.safety import ActionSafetyConfig, ActionSafetyError, clamp_and_validate_action


def test_clamp_and_validate_action_clamps_values_and_limits_step_size():
    cfg = ActionSafetyConfig(max_step=0.2, timeout_s=1.0)

    action = clamp_and_validate_action(
        action=[1.2, -0.1, 0.75, 0.3, 0.1, 0.6],
        previous_action=[0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
        action_timestamp=10.0,
        now=10.2,
        config=cfg,
    )

    assert action == pytest.approx([0.7, 0.3, 0.7, 0.3, 0.3, 0.6])


def test_clamp_and_validate_action_rejects_stale_and_emergency_stop():
    cfg = ActionSafetyConfig(timeout_s=0.5)

    with pytest.raises(ActionSafetyError, match="stale"):
        clamp_and_validate_action(
            action=[0.5] * 6,
            previous_action=[0.5] * 6,
            action_timestamp=10.0,
            now=11.0,
            config=cfg,
        )

    with pytest.raises(ActionSafetyError, match="emergency"):
        clamp_and_validate_action(
            action=[0.5] * 6,
            previous_action=[0.5] * 6,
            action_timestamp=10.0,
            now=10.1,
            config=cfg,
            emergency_stop=True,
        )
