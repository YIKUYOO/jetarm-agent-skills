from jetarm_demo_agent import web_server


def test_build_web_app_can_force_live_motion():
    app = web_server.build_web_app(allow_live_motion=True)

    assert app.state.dispatcher.settings.allow_live_motion is True


def test_web_server_main_forwards_host_port_and_live(monkeypatch):
    captured = {}

    def fake_run(app, host: str, port: int):
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(web_server.uvicorn, "run", fake_run)

    exit_code = web_server.main(["--host", "127.0.0.1", "--port", "9000", "--live"])

    assert exit_code == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9000
    assert captured["app"].state.dispatcher.settings.allow_live_motion is True
