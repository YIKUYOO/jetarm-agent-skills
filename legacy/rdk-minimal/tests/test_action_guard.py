import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "board"
sys.path.insert(0, str(BOARD))

import jetarm_action


def test_servo_pulse_rejects_unknown_servo_id():
    payload = {"action_type": "servo_pulse", "duration_s": 0.5, "values": {"6": 500}}
    result = jetarm_action.validate_action(payload, current_positions={1: 500})
    assert result["ok"] is False
    assert result["error_code"] == "UNSUPPORTED_SERVO_ID"


def test_servo_delta_limits_step_size():
    payload = {"action_type": "servo_delta", "duration_s": 0.5, "values": {"1": 80}}
    result = jetarm_action.validate_action(payload, current_positions={1: 500}, max_step=30)
    assert result["ok"] is False
    assert result["error_code"] == "STEP_TOO_LARGE"


def test_servo_delta_builds_safe_target():
    payload = {"action_type": "servo_delta", "duration_s": 0.5, "values": {"1": 8, "10": -8}}
    result = jetarm_action.validate_action(payload, current_positions={1: 500, 10: 700}, max_step=30)
    assert result["ok"] is True
    assert result["command"]["positions"] == {1: 508, 10: 692}
    assert result["command"]["position_unit"] == "pulse"


def test_stop_action_is_valid_without_positions():
    result = jetarm_action.validate_action({"action_type": "stop"}, current_positions={})
    assert result["ok"] is True
    assert result["command"]["action_type"] == "stop"


def test_load_action_payload_from_file(tmp_path):
    path = tmp_path / "action.json"
    path.write_text(json.dumps({"action_type": "servo_delta", "duration_s": 0.35, "values": {"1": 8}}), encoding="utf-8")
    payload = jetarm_action.load_action_payload(None, str(path))
    assert payload["action_type"] == "servo_delta"
    assert payload["values"] == {"1": 8}
