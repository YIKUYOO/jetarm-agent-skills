import json

from remote.jetarm_executor import executor_cli


def test_executor_cli_marks_pick_red_block_incomplete_as_failed(monkeypatch, capsys):
    monkeypatch.setattr(executor_cli, "pick_red_block", lambda mode, **kwargs: {"summary": "pick failed", "complete": False, "motion_executed": True})
    monkeypatch.setattr(executor_cli, "get_health", lambda: {"ros_context": {}})

    exit_code = executor_cli.main(
        [
            "--request-json",
            json.dumps({"task_id": "t1", "intent": "pick_red_block", "mode": "live", "args": {}}),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is False
    assert payload["executor_state"] == "FAILED"


def test_executor_cli_marks_scan_scene_without_frames_as_failed(monkeypatch, capsys):
    monkeypatch.setattr(executor_cli, "scan_scene", lambda mode: {"summary": "no frames", "frames": [], "continue_ready": False, "motion_executed": True})
    monkeypatch.setattr(executor_cli, "get_health", lambda: {"ros_context": {}})

    exit_code = executor_cli.main(
        [
            "--request-json",
            json.dumps({"task_id": "t2", "intent": "scan_scene", "mode": "live", "args": {}}),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is False
    assert payload["executor_state"] == "FAILED"


def test_executor_cli_marks_find_red_block_without_detection_as_failed(monkeypatch, capsys):
    monkeypatch.setattr(executor_cli, "find_red_block", lambda mode, target_hint_sector=None, search_strategy="directional_scan": {"summary": "not found", "detected": False, "motion_executed": True})
    monkeypatch.setattr(executor_cli, "get_health", lambda: {"ros_context": {}})

    exit_code = executor_cli.main(
        [
            "--request-json",
            json.dumps({"task_id": "t3", "intent": "find_red_block", "mode": "live", "args": {"target_hint_sector": "left"}}),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is False
    assert payload["executor_state"] == "FAILED"


def test_executor_cli_marks_debug_move_without_completion_as_failed(monkeypatch, capsys):
    monkeypatch.setattr(executor_cli, "debug_move_to_pick_pose", lambda mode, **kwargs: {"summary": "debug move failed", "complete": False, "motion_executed": True})
    monkeypatch.setattr(executor_cli, "get_health", lambda: {"ros_context": {}})

    exit_code = executor_cli.main(
        [
            "--request-json",
            json.dumps({"task_id": "t4", "intent": "debug_move_to_pick_pose", "mode": "live", "args": {"locked_pose": [0.1, 0.1, 0.012]}}),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is False
    assert payload["executor_state"] == "FAILED"
