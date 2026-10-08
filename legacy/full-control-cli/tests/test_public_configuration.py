import importlib.util
from pathlib import Path


def test_cloud_endpoint_requires_explicit_configuration(monkeypatch):
    monkeypatch.delenv("JETARM_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("JETARM_LLM_API_KEY", raising=False)
    path = Path(__file__).resolve().parents[1] / "agent_cli/jetarm_full_control_agent.py"
    spec = importlib.util.spec_from_file_location("cli_release_configuration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DEFAULT_LLM_BASE_URL == ""
    assert not module.OpenAICompatibleClient().configured()
