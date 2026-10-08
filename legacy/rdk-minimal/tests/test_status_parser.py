import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local"
sys.path.insert(0, str(LOCAL))

import rdk_minimal


def test_remote_path_uses_forward_slashes():
    assert rdk_minimal.remote_join("/home/example/x", "board", "a.sh") == "/home/example/x/board/a.sh"


def test_status_json_parser_rejects_missing_control():
    payload = {
        "control_serial": {"rrc_exists": False, "ch340_usb": True},
        "camera_usb": {"orbbec_depth": True, "orbbec_rgb": True},
        "packages": {"sdk": True},
    }
    result = rdk_minimal.summarize_status(json.dumps(payload))
    assert result["ready"] is False
    assert "rrc" in result["missing"]


def test_status_json_parser_accepts_minimal_ready_payload():
    payload = {
        "control_serial": {"rrc_exists": True, "ch340_usb": True},
        "camera_usb": {"orbbec_depth": True, "orbbec_rgb": True},
        "packages": {
            "ros_robot_controller": True,
            "servo_controller": True,
            "kinematics": True,
            "sdk": True,
            "peripherals": True,
        },
    }
    result = rdk_minimal.summarize_status(json.dumps(payload))
    assert result["ready"] is True
    assert result["missing"] == []
