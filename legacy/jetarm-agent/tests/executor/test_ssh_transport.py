import base64
import io
import json
from pathlib import Path
import subprocess

from jetarm_demo_agent.executor.ssh_transport import build_remote_command
from jetarm_demo_agent.config import Settings
from jetarm_demo_agent.executor.ssh_transport import SSHExecutorTransport


def test_build_remote_command_contains_executor_path_and_payload():
    command = build_remote_command(
        remote_python="python3",
        remote_executor_path="~/remote/executor_cli.py",
        request_json='{"task_id":"t1"}',
    )
    assert "python3" in command
    assert "executor_cli.py" in command
    assert "--request-json" in command


def test_transport_uses_fallback_without_ssh_credentials():
    transport = SSHExecutorTransport(settings=Settings(account_file="/tmp/does-not-exist-account.txt"))
    health = transport.health()
    assert health["ok"] is True
    assert health["transport"] == "local-fallback"


def test_settings_default_remote_executor_path_targets_uploaded_runtime():
    settings = Settings(account_file="/tmp/does-not-exist-account.txt")
    assert "jetarm_demo_agent_remote" in settings.remote_executor_path


def test_transport_uploads_depth_viz_bridge_runtime_file():
    transport = SSHExecutorTransport(settings=Settings(account_file="/tmp/does-not-exist-account.txt"))

    names = [path.name for path in transport._local_remote_sources()]

    assert "depth_viz_bridge.py" in names


def test_camera_frame_uses_svg_fallback_without_ssh_credentials():
    transport = SSHExecutorTransport(settings=Settings(account_file="/tmp/does-not-exist-account.txt"))

    payload = transport.camera_frame("color")

    assert payload["media_type"] == "image/svg+xml"
    assert b"JetArm camera unavailable" in payload["content"]


class _FakeChannel:
    def __init__(self, status: int):
        self._status = status

    def recv_exit_status(self):
        return self._status


class _FakeStdout(io.BytesIO):
    def __init__(self, data: bytes, status: int):
        super().__init__(data)
        self.channel = _FakeChannel(status)


class _FakeSSHClient:
    def __init__(self, stdout_data: bytes, stderr_data: bytes, status: int = 0):
        self._stdout = stdout_data
        self._stderr = stderr_data
        self._status = status

    def exec_command(self, command, timeout=None):
        return None, _FakeStdout(self._stdout, self._status), io.BytesIO(self._stderr)

    def close(self):
        return None


class _FakeSFTPAttributes:
    def __init__(self, size: int):
        self.st_size = size


class _FakeSFTP:
    def __init__(self, home: str = "/home/hiwonder"):
        self.home = home
        self.put_calls = []
        self._sizes = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def normalize(self, path):
        assert path == "."
        return self.home

    def put(self, local_path, remote_path, confirm=True):
        self.put_calls.append((local_path, remote_path, confirm))
        self._sizes[remote_path] = Path(local_path).stat().st_size

    def stat(self, remote_path):
        return _FakeSFTPAttributes(self._sizes[remote_path])


class _FakeUploadSSHClient:
    def __init__(self, sftp: _FakeSFTP):
        self.sftp = sftp
        self.commands = []

    def open_sftp(self):
        return self.sftp

    def exec_command(self, command, timeout=None):
        self.commands.append((command, timeout))
        return None, _FakeStdout(b"", 0), io.BytesIO(b"")


def test_remote_paths_use_posix_separators_on_windows():
    transport = SSHExecutorTransport(settings=Settings(account_file="/tmp/does-not-exist-account.txt"))
    client = _FakeUploadSSHClient(_FakeSFTP())

    remote_dir, remote_file = transport._resolve_remote_paths(client)  # type: ignore[arg-type]

    assert remote_file == "/home/hiwonder/jetarm_demo_agent_remote/executor_cli.py"
    assert remote_dir == "/home/hiwonder/jetarm_demo_agent_remote"


def test_transport_upload_confirms_and_verifies_remote_runtime_files(tmp_path):
    source = tmp_path / "executor_cli.py"
    source.write_text("print('remote runtime')\n", encoding="utf-8")
    transport = SSHExecutorTransport(settings=Settings(account_file="/tmp/does-not-exist-account.txt"))
    transport._local_remote_sources = lambda: [source]  # type: ignore[method-assign]
    sftp = _FakeSFTP()
    client = _FakeUploadSSHClient(sftp)

    remote_file = transport._ensure_remote_executor_uploaded(client)  # type: ignore[arg-type]

    assert remote_file == "/home/hiwonder/jetarm_demo_agent_remote/executor_cli.py"
    assert client.commands == [("mkdir -p /home/hiwonder/jetarm_demo_agent_remote", 10)]
    assert sftp.put_calls == [
        (str(source), "/home/hiwonder/jetarm_demo_agent_remote/executor_cli.py", True)
    ]


def test_camera_frame_ignores_stderr_when_exit_status_zero_and_stdout_is_valid_json():
    payload = {
        "image_base64": base64.b64encode(b"jpeg-bytes").decode("ascii"),
        "media_type": "image/jpeg",
        "stream": "color",
    }
    transport = SSHExecutorTransport(settings=Settings(account_file="/tmp/does-not-exist-account.txt"))
    transport._connect = lambda: _FakeSSHClient(  # type: ignore[method-assign]
        json.dumps(payload).encode("utf-8"),
        b"warning on stderr\n",
        0,
    )
    transport._ensure_remote_executor_uploaded = lambda client: "/tmp/executor_cli.py"  # type: ignore[method-assign]
    transport.settings.ssh_host = "example"
    transport.settings.ssh_user = "user"
    transport.settings.ssh_password = "password"

    result = transport.camera_frame("color")

    assert result["media_type"] == "image/jpeg"
    assert result["content"] == b"jpeg-bytes"


def test_camera_frame_returns_svg_when_remote_command_fails():
    transport = SSHExecutorTransport(settings=Settings(account_file="/tmp/does-not-exist-account.txt"))
    transport._connect = lambda: _FakeSSHClient(b"", b"camera broken\n", 1)  # type: ignore[method-assign]
    transport._ensure_remote_executor_uploaded = lambda client: "/tmp/executor_cli.py"  # type: ignore[method-assign]
    transport.settings.ssh_host = "example"
    transport.settings.ssh_user = "user"
    transport.settings.ssh_password = "password"

    result = transport.camera_frame("color")

    assert result["media_type"] == "image/svg+xml"
    assert b"camera broken" in result["content"]


def test_run_task_returns_structured_failure_when_remote_command_fails():
    transport = SSHExecutorTransport(settings=Settings(account_file="/tmp/does-not-exist-account.txt"))
    transport._connect = lambda: _FakeSSHClient(b"", b"scan failed\n", 1)  # type: ignore[method-assign]
    transport._ensure_remote_executor_uploaded = lambda client: "/tmp/executor_cli.py"  # type: ignore[method-assign]
    transport.settings.ssh_host = "example"
    transport.settings.ssh_user = "user"
    transport.settings.ssh_password = "password"

    task = type("Task", (), {
        "task_id": "t_scan",
        "intent": type("Intent", (), {"value": "scan_scene"})(),
        "mode": type("Mode", (), {"value": "live"})(),
        "args": {},
    })()

    result = transport.run_task(task)

    assert result["ok"] is False
    assert result["executor_state"] == "FAILED"
    assert result["intent"] == "scan_scene"
    assert result["error"]["code"] == "REMOTE_EXECUTION_FAILED"
    assert "scan failed" in result["error"]["message"]
