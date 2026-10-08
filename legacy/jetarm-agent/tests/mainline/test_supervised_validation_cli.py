import json

from jetarm_agent.baseline.supervised_validation import cli_main


def test_cli_lists_actions_without_operator_ready(capsys):
    exit_code = cli_main(["--list-actions"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "go_home" in captured.out
    assert "pick_place" in captured.out


def test_cli_rejects_live_plan_without_operator_ready(capsys):
    exit_code = cli_main(["--action", "go_home"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--operator-ready" in captured.err


def test_cli_writes_pending_templates_when_operator_is_ready(tmp_path):
    json_out = tmp_path / "validation.json"
    markdown_out = tmp_path / "validation.md"

    exit_code = cli_main(
        [
            "--action",
            "go_home",
            "--action",
            "pick_place",
            "--operator-ready",
            "--json-out",
            str(json_out),
            "--markdown-out",
            str(markdown_out),
        ]
    )

    assert exit_code == 0
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert [item["action_name"] for item in payload] == ["go_home", "pick_place"]
    assert payload[0]["status"] == "pending"
    assert "现场有人值守" in markdown_out.read_text(encoding="utf-8")
