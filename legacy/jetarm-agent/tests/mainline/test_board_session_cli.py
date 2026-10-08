import json

from jetarm_agent.baseline.board_session import cli_main


def test_cli_plan_session_writes_manifest_runbook_and_result(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    runbook_path = tmp_path / "runbook.md"
    result_path = tmp_path / "result.json"

    exit_code = cli_main(
        [
            "--plan-session",
            "--session-id",
            "session-001",
            "--board-target",
            "jetarm@board",
            "--mode",
            "ssh_shell",
            "--manifest-json",
            str(manifest_path),
            "--runbook-md",
            str(runbook_path),
            "--result-json",
            str(result_path),
        ]
    )

    assert exit_code == 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert manifest["mode"] == "ssh_shell"
    assert manifest["actions"][0]["action_name"] == "go_home"
    assert result["action_results"][0]["status"] == "pending"
    assert "现场有人值守" in runbook_path.read_text(encoding="utf-8")


def test_cli_print_command_returns_selected_action_template(capsys):
    exit_code = cli_main(
        [
            "--print-command",
            "--session-id",
            "session-001",
            "--action",
            "pick_place",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "/object_sortting/enable_sortting" in captured.out


def test_cli_record_result_updates_failure_and_blocks_following_steps(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    result_path = tmp_path / "result.json"

    cli_main(
        [
            "--plan-session",
            "--session-id",
            "session-001",
            "--manifest-json",
            str(manifest_path),
            "--result-json",
            str(result_path),
        ]
    )

    exit_code = cli_main(
        [
            "--record-result",
            "--result-json",
            str(result_path),
            "--action",
            "stop_all",
            "--status",
            "failed",
            "--observed-behavior",
            "task-flow interrupt did not stop cleanly",
        ]
    )

    assert exit_code == 0
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    stop_result = next(item for item in payload["action_results"] if item["action_name"] == "stop_all")
    pick_place_result = next(item for item in payload["action_results"] if item["action_name"] == "pick_place")
    assert stop_result["status"] == "failed"
    assert pick_place_result["status"] == "blocked"
