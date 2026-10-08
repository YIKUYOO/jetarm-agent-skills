import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def modules(monkeypatch):
    package = ModuleType("jetarm_minimal_control")
    package.__path__ = [str(ROOT / "jetarm_minimal_control")]
    rclpy = ModuleType("rclpy")
    node = ModuleType("rclpy.node")
    node.Node = object
    messages = ModuleType("servo_controller_msgs.msg")
    messages.ServoPosition = type("ServoPosition", (), {})
    messages.ServosPosition = type("ServosPosition", (), {})
    for name, module in {
        "jetarm_minimal_control": package,
        "rclpy": rclpy,
        "rclpy.node": node,
        "servo_controller_msgs": ModuleType("servo_controller_msgs"),
        "servo_controller_msgs.msg": messages,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    result = {}
    for stem in ("presets", "action_runner"):
        full_name = "jetarm_minimal_control." + stem
        spec = importlib.util.spec_from_file_location(full_name, ROOT / "jetarm_minimal_control" / (stem + ".py"))
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, full_name, module)
        spec.loader.exec_module(module)
        result[stem] = module
    return SimpleNamespace(**result)


def test_aliases_resolve_to_known_actions(modules):
    assert modules.presets.get_action("home").name == "go_home"
    assert modules.presets.get_action("observe").name == "observe_sorting"


def test_all_stored_steps_pass_declared_numerical_contract(modules):
    for action in modules.presets.PRESET_ACTIONS.values():
        for step in action.steps:
            modules.presets.validate_step(step)
            msg = modules.presets.make_servos_position(step)
            assert len(msg.position) == len(step.goals)


def test_unknown_action_is_rejected(modules):
    with pytest.raises(ValueError, match="Unknown JetArm preset"):
        modules.presets.get_action("unregistered_action")


def test_duplicate_servo_in_a_step_is_rejected(modules):
    step = modules.presets.MotionStep(0.3, ((1, 500), (1, 600)))
    with pytest.raises(ValueError, match="more than once"):
        modules.presets.validate_step(step)


def test_unsupported_servo_is_rejected(modules):
    with pytest.raises(ValueError, match="not allowed"):
        modules.presets.validate_step(modules.presets.MotionStep(0.3, ((6, 500),)))


@pytest.mark.parametrize("duration", [-1, float("nan")])
def test_invalid_duration_is_rejected(modules, duration):
    with pytest.raises(ValueError, match="Duration"):
        modules.presets.validate_step(modules.presets.MotionStep(duration, ((1, 500),)))


@pytest.mark.parametrize("pulse", [-1, 1001])
def test_out_of_range_pulse_is_rejected(modules, pulse):
    with pytest.raises(ValueError, match="outside"):
        modules.presets.validate_step(modules.presets.MotionStep(0.3, ((1, pulse),)))


def test_default_runner_does_not_publish(modules):
    args = modules.action_runner.build_parser().parse_args(["go_home"])
    assert args.execute is False
    logger = SimpleNamespace(info=lambda *_: None, warn=lambda *_: None)

    def reject_publication(*_):
        raise AssertionError("Dry-run path attempted publication")

    fake_runner = SimpleNamespace(
        get_logger=lambda: logger,
        wait_for_subscriber=reject_publication,
        publisher=SimpleNamespace(publish=reject_publication),
    )
    assert modules.action_runner.ActionRunner.run_action(fake_runner, args.action, args.execute)
