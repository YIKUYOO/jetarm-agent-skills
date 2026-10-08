import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "agent_cli" / "jetarm_full_control_agent.py"


def load_cli_module():
    spec = importlib.util.spec_from_file_location("jetarm_full_control_agent", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_list_tools_exposes_raw_full_control_surfaces(tmp_path):
    cli = load_cli_module()
    agent = cli.FullControlAgent(transcript_path=str(tmp_path / "transcript.jsonl"), skill_root=str(tmp_path / "skills"))

    output = agent.call("list_tools", {})

    tool_names = {tool["name"] for tool in output["telemetry"]["tools"]}
    assert output["ok"] is True
    assert {"shell", "ros", "rostopic", "rosservice", "servo_debug", "stop_all"} <= tool_names


def test_shell_tool_records_transcript(tmp_path):
    cli = load_cli_module()
    transcript = tmp_path / "transcript.jsonl"
    agent = cli.FullControlAgent(transcript_path=str(transcript), skill_root=str(tmp_path / "skills"))

    output = agent.call("shell", {"command": f'"{sys.executable}" -c "print(\'hello\', end=\'\')"', "timeout_seconds": 5})

    assert output["ok"] is True
    assert output["stdout"] == "hello"
    entry = json.loads(transcript.read_text().splitlines()[0])
    assert entry["mode"] == "full-control"
    assert entry["tool_name"] == "shell"
    assert entry["result"]["ok"] is True


def test_skill_create_and_activate_flow(tmp_path):
    cli = load_cli_module()
    agent = cli.FullControlAgent(transcript_path=str(tmp_path / "transcript.jsonl"), skill_root=str(tmp_path / "skills"))

    created = agent.call("create_skill", {"name": "demo-skill", "description": "demo"})
    activated = agent.call("activate_skill", {"name": "demo-skill", "review_notes": "reviewed in test"})
    listed = agent.call("list_skills", {})

    assert created["ok"] is True
    assert activated["ok"] is True
    assert listed["ok"] is True
    assert listed["telemetry"]["skills"][0]["install_state"] == "active"
    assert (tmp_path / "skills" / "active" / "demo-skill" / "SKILL.md").exists()


def test_repl_unknown_command_returns_structured_error(tmp_path):
    cli = load_cli_module()
    output = cli.result(False, "repl", stderr="unknown command", error_code="UNKNOWN_REPL_COMMAND")

    assert output["ok"] is False
    assert output["stage"] == "repl"
    assert output["error_code"] == "UNKNOWN_REPL_COMMAND"


class FakeLlmClient:
    model = "gpt-5.5"

    def __init__(self, content):
        self.content = content
        self.messages = None

    def chat(self, messages):
        self.messages = messages
        return self.content


def test_agent_chat_can_return_plain_reply(tmp_path):
    cli = load_cli_module()
    llm = FakeLlmClient('{"reply":"可以，我会先观察。"}')
    agent = cli.FullControlAgent(
        transcript_path=str(tmp_path / "transcript.jsonl"),
        skill_root=str(tmp_path / "skills"),
        llm_client=llm,
    )

    output = agent.call("agent_chat", {"message": "你好"})

    assert output["ok"] is True
    assert output["stdout"] == "可以，我会先观察。"
    assert "available_tools" in llm.messages[1]["content"]


def test_agent_chat_extracts_json_after_think_block(tmp_path):
    cli = load_cli_module()
    llm = FakeLlmClient('<think>hidden</think>\n{"reply":"已接入。"}')
    agent = cli.FullControlAgent(
        transcript_path=str(tmp_path / "transcript.jsonl"),
        skill_root=str(tmp_path / "skills"),
        llm_client=llm,
    )

    output = agent.call("agent_chat", {"message": "状态"})

    assert output["ok"] is True
    assert output["stdout"] == "已接入。"


def test_agent_chat_can_delegate_to_tool_and_redacts_secret_args(tmp_path):
    cli = load_cli_module()
    llm = FakeLlmClient('{"tool_name":"shell","args":{"command":"echo ok","api_key":"secret"},"reason":"probe"}')
    transcript = tmp_path / "transcript.jsonl"
    agent = cli.FullControlAgent(
        transcript_path=str(transcript),
        skill_root=str(tmp_path / "skills"),
        llm_client=llm,
    )

    output = agent.call("agent_chat", {"message": "检查一下"})

    assert output["ok"] is True
    assert output["stage"] == "agent_chat"
    lines = transcript.read_text().splitlines()
    assert len(lines) == 2
    assert "<redacted>" in lines[0]
    assert "secret" not in transcript.read_text()
