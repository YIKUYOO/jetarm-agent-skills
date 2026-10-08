import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_without_ros(monkeypatch, filename):
    rclpy = ModuleType("rclpy")

    def forbid_ros(*args, **kwargs):
        raise AssertionError("Offline preview or missing-device gate attempted to start ROS")

    rclpy.init = forbid_ros
    node = ModuleType("rclpy.node")
    node.Node = object
    messages = ModuleType("servo_controller_msgs.msg")
    messages.ServoPosition = type("ServoPosition", (), {})
    messages.ServosPosition = type("ServosPosition", (), {})
    messages.ServoStateList = type("ServoStateList", (), {})
    for name, module in {
        "rclpy": rclpy,
        "rclpy.node": node,
        "servo_controller_msgs": ModuleType("servo_controller_msgs"),
        "servo_controller_msgs.msg": messages,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(filename, ROOT / "tools" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_position_parse_preserves_supported_joint_ids(monkeypatch):
    module = load_without_ros(monkeypatch, "jetarm_safe_servo_move.py")
    assert module.parse_positions("1:490,10:200") == {1: 490.0, 10: 200.0}


def test_position_parse_rejects_unsupported_joint(monkeypatch):
    module = load_without_ros(monkeypatch, "jetarm_safe_servo_move.py")
    with pytest.raises(ValueError, match="unsupported servo id"):
        module.parse_positions("6:500")


def test_pulse_clamp_does_not_change_degree_input(monkeypatch):
    module = load_without_ros(monkeypatch, "jetarm_safe_servo_move.py")
    assert module.clamp_positions({1: -10, 10: 1010}, "pulse") == {1: 0, 10: 1000}
    assert module.clamp_positions({1: 90}, "deg") == {1: 90}


def test_nudge_plan_reverses_direction_near_upper_bound(monkeypatch):
    module = load_without_ros(monkeypatch, "jetarm_joint_nudge_test.py")
    assert module.target_for(500, 8) == 508
    assert module.target_for(980, 8) == 972


def test_missing_control_board_blocks_before_ros_start(monkeypatch, capsys):
    module = load_without_ros(monkeypatch, "jetarm_safe_servo_move.py")
    monkeypatch.setattr(module.os.path, "exists", lambda path: False)
    monkeypatch.setattr(sys, "argv", ["servo", "--positions", "10:200", "--execute", "--json"])
    assert module.main() == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "blocked"
    assert output["reason"] == "/dev/rrc is missing"


def test_default_preview_never_starts_ros(monkeypatch, capsys):
    module = load_without_ros(monkeypatch, "jetarm_safe_servo_move.py")
    monkeypatch.setattr(sys, "argv", ["servo", "--positions", "10:200", "--json"])
    assert module.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "dry_run"
    assert output["execute"] is False
