import ast
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("module,args", [
    ("jetarm_servo_publish", ["--goal", "10:200"]),
    ("jetarm_tabletop_motion", ["--observation-meta", "nonexistent.json"]),
    ("jetarm_tabletop_place", ["--x", "0.18", "--y", "0.02"]),
    ("jetarm_tabletop_scan", ["--output-dir", "must-not-be-created"]),
])
def test_motion_defaults_to_offline_preview(module, args, monkeypatch, capsys, tmp_path):
    mod = importlib.import_module(module)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [module] + args)
    monkeypatch.setattr(mod, "connect", lambda *a, **k: pytest.fail("default path attempted network"))
    assert mod.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["physical_motion"] is False
    assert result["mode"] == "dry_run"
    assert not list(tmp_path.iterdir())

@pytest.mark.parametrize("goals", [["6:500"], ["1:nan"], ["1:inf"], ["1:-1"], ["1:1001"], ["1:400", "1:500"]])
def test_invalid_servo_requests_are_rejected(goals):
    from jetarm_servo_publish import parse_goals
    with pytest.raises(ValueError):
        parse_goals(goals)

def test_supported_servo_request():
    from jetarm_servo_publish import parse_goals
    assert parse_goals(["1:500", "10:200"]) == [[1, 500], [10, 200]]

def test_connection_requires_explicit_configuration(monkeypatch):
    import jetarm_connection as connection
    monkeypatch.setattr(connection.paramiko, "SSHClient", lambda: pytest.fail("SSH client created before configuration check"))
    with pytest.raises(ValueError):
        connection.connect(None, None)

def test_child_connection_arguments():
    from jetarm_connection import connection_cli
    args = SimpleNamespace(host="robot.example", username="operator", key_file="robot-key")
    assert connection_cli(args) == ["--host", "robot.example", "--username", "operator", "--key-file", "robot-key"]

def test_execution_mode_conflict():
    from jetarm_connection import preview_motion
    with pytest.raises(ValueError):
        preview_motion(SimpleNamespace(execute=True, dry_run=True))

def test_real_execution_path_is_explicit():
    from jetarm_connection import preview_motion
    assert preview_motion(SimpleNamespace(execute=True, dry_run=False)) is False

def test_synthetic_red_target_detection():
    from evaluate_local_red_block import detect_red
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[600:650, 300:350] = (0, 0, 255)
    target = detect_red(image)
    assert target["found"]
    assert target["center_px"] == pytest.approx([324.5, 624.5])

def test_blank_image_is_not_success():
    from evaluate_local_red_block import detect_red, classify
    assert classify(detect_red(np.zeros((720, 1280, 3), dtype=np.uint8))) == "not_found"

def test_python_and_embedded_remote_syntax():
    for path in (ROOT / "scripts/local").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith("REMOTE_") for t in node.targets):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and "import " in node.value.value:
                    ast.parse(node.value.value, filename=path.name + " embedded")

def test_plugin_manifest_and_four_skills():
    manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
    assert manifest["version"] == "0.1.0"
    assert len(list((ROOT / "skills").glob("*/SKILL.md"))) == 4

def test_calibration_remote_payload_handles_nan_without_motion(monkeypatch):
    import shlex
    import jetarm_multiview_pick_analyze as analysis
    payload = {"red_candidate": {"center_px": [100, 150], "depth_median_at_center": float("nan")},
               "camera_info": {"k": [1, 0, 0, 0, 1, 0, 0, 0, 1]}}
    class Stream:
        channel = SimpleNamespace(recv_exit_status=lambda: 0)
        def read(self):
            return b'{"center_px":[100,150],"pose_xy":[0.1,0.2],"raw_plane_xyz":[0,0,0]}'
    class Client:
        def exec_command(self, command, timeout):
            shell = shlex.split(command)[2]
            code = shlex.split(shell.split("python3 -c ", 1)[1])[0]
            ast.parse(code)
            assert "Commander" not in code
            assert "json.loads(" in code
            return None, Stream(), Stream()
        def close(self):
            pass
    monkeypatch.setattr(analysis, "connect", lambda *args: Client())
    result = analysis.board_pixels_to_xy(payload, SimpleNamespace(host="robot.example", username="operator", key_file=None))
    assert result["depth_m"] is None
    assert result["board_calibrated_xy_m"] == [0.1, 0.2]
