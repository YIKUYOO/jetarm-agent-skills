"""Release-only HTTP contract checks; no ROS, device, data or model required."""
import importlib

from fastapi.testclient import TestClient


def mock_client(monkeypatch):
    monkeypatch.setenv("VLA_MODE", "mock")
    from gpu import server
    importlib.reload(server)
    return TestClient(server.app)


def test_mock_health_explicitly_identifies_hold_backend(monkeypatch):
    body = mock_client(monkeypatch).get("/health").json()
    assert body["ok"] is True
    assert body["mode"] == "hold-current-pose"


def test_mock_action_only_holds_clipped_state(monkeypatch):
    response = mock_client(monkeypatch).post("/select_action", json={
        "language_instruction": "an instruction the mock does not interpret",
        "observation.state": [-0.1, 0.2, 0.3, 0.4, 0.5, 1.2] + [0.0] * 7,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == [0.0, 0.2, 0.3, 0.4, 0.5, 1.0]
    assert body["mode"] == "hold-current-pose"
    assert body["confidence"] == 0.0


def test_mock_rejects_short_state(monkeypatch):
    response = mock_client(monkeypatch).post("/select_action", json={
        "language_instruction": "hold", "observation.state": [0.5] * 5,
    })
    assert response.status_code == 400


def test_unconfigured_real_mode_reports_unavailable(monkeypatch):
    monkeypatch.setenv("VLA_MODE", "smolvla")
    monkeypatch.setenv("VLA_POLICY_PATH", "")
    from gpu import server
    importlib.reload(server)
    result = TestClient(server.app).get("/health").json()
    assert result["ok"] is False
    assert result["mode"] == "smolvla"
