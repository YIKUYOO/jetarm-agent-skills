from jetarm_demo_agent import cli


def test_main_forwards_live_flag_to_single_shot(monkeypatch, capsys):
    calls = {}

    def fake_run_command(command: str, dispatcher=None, allow_live_motion: bool = False):
        calls["command"] = command
        calls["allow_live_motion"] = allow_live_motion
        return "ok"

    monkeypatch.setattr(cli, "run_command", fake_run_command)

    exit_code = cli.main(["--live", "把前面的红色木块放到左边"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == {
        "command": "把前面的红色木块放到左边",
        "allow_live_motion": True,
    }
    assert "ok" in captured.out


def test_main_forwards_live_flag_to_interactive_mode(monkeypatch):
    calls = {}

    def fake_run_interactive_session(dispatcher=None, input_fn=input, output_fn=print, session_id="default", allow_live_motion=False):
        calls["allow_live_motion"] = allow_live_motion
        calls["session_id"] = session_id
        return 0

    monkeypatch.setattr(cli, "run_interactive_session", fake_run_interactive_session)

    exit_code = cli.main(["--live"])

    assert exit_code == 0
    assert calls["allow_live_motion"] is True
    assert calls["session_id"] == "default"
