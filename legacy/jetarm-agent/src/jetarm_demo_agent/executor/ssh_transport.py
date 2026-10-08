from __future__ import annotations

import base64
import json
from pathlib import Path, PurePosixPath
import subprocess
from shlex import quote

import paramiko

from jetarm_demo_agent.config import Settings
from jetarm_demo_agent.schemas import TaskRequest


def build_remote_command(remote_python: str, remote_executor_path: str, request_json: str) -> str:
    return f"{quote(remote_python)} {quote(remote_executor_path)} --request-json {quote(request_json)}"


def build_camera_unavailable_payload(message: str, stream: str = "color") -> dict:
    safe_message = (message or "JetArm camera unavailable").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return {
        "content": (
            "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'>"
            "<rect width='100%' height='100%' fill='#efe7db'/>"
            "<text x='50%' y='45%' dominant-baseline='middle' text-anchor='middle' "
            "font-family='sans-serif' font-size='24' fill='#6e675d'>JetArm camera unavailable</text>"
            f"<text x='50%' y='58%' dominant-baseline='middle' text-anchor='middle' "
            f"font-family='sans-serif' font-size='16' fill='#6e675d'>{safe_message}</text>"
            "</svg>"
        ).encode("utf-8"),
        "media_type": "image/svg+xml",
        "stream": stream,
    }


class SSHExecutorTransport:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def _local_remote_sources(self) -> list[Path]:
        root = Path(__file__).resolve().parents[3]
        remote_dir = root / "remote" / "jetarm_executor"
        return [
            remote_dir / "depth_viz_bridge.py",
            remote_dir / "executor_cli.py",
            remote_dir / "health.py",
            remote_dir / "ros_adapters.py",
        ]

    def _resolve_remote_paths(self, client: paramiko.SSHClient) -> tuple[str, str]:
        with client.open_sftp() as sftp:
            remote_home = sftp.normalize(".")
        relative_path = self.settings.remote_executor_path.lstrip("/")
        remote_file = f"{remote_home}/{relative_path}"
        remote_dir = str(PurePosixPath(remote_file).parent)
        return remote_dir, remote_file

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(
            hostname=self.settings.ssh_host,
            username=self.settings.ssh_user,
            password=self.settings.ssh_password,
            timeout=10,
        )
        return client

    def _ensure_remote_executor_uploaded(self, client: paramiko.SSHClient) -> str:
        remote_dir, remote_file = self._resolve_remote_paths(client)
        _, stdout, stderr = client.exec_command(f"mkdir -p {quote(remote_dir)}", timeout=10)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            message = stderr.read().decode("utf-8").strip() or f"mkdir failed with status {exit_status}"
            raise RuntimeError(message[:300])
        with client.open_sftp() as sftp:
            for source in self._local_remote_sources():
                remote_path = f"{remote_dir}/{source.name}"
                sftp.put(str(source), remote_path, confirm=True)
                remote_size = sftp.stat(remote_path).st_size
                local_size = source.stat().st_size
                if remote_size != local_size:
                    raise RuntimeError(
                        f"remote upload size mismatch for {source.name}: local={local_size} remote={remote_size}"
                    )
        return remote_file

    def health(self) -> dict:
        if not self.settings.ssh_host or not self.settings.ssh_user or not self.settings.ssh_password:
            return {
                "ok": True,
                "single_block_demo_mode": True,
                "ros_context": {
                    "tracking_node": True,
                    "sorting_node": True,
                    "grasp_node": True,
                },
                "transport": "local-fallback",
            }

        client = self._connect()
        try:
            remote_file = self._ensure_remote_executor_uploaded(client)
            _, stdout, stderr = client.exec_command(
                f"{quote(self.settings.remote_executor_python)} {quote(remote_file)} --health",
                timeout=60,
            )
            exit_status = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8")
            error_output = stderr.read().decode("utf-8")
            if exit_status != 0:
                raise subprocess.CalledProcessError(1, "remote-health", output=output, stderr=error_output)
            health = json.loads(output)
            health["transport"] = "ssh"
            if error_output.strip():
                health["transport_stderr"] = error_output.strip()
            return health
        finally:
            client.close()

    def run_task(self, task: TaskRequest) -> dict:
        if not self.settings.ssh_host or not self.settings.ssh_user or not self.settings.ssh_password:
            return {
                "ok": True,
                "task_id": task.task_id,
                "executor_state": "DRY_RUN_COMPLETED" if task.mode and task.mode.value == "dry_run" else "SUCCEEDED",
                "mode": task.mode.value if task.mode else "safe",
                "intent": task.intent.value,
                "result": {"summary": "local fallback result", "motion_executed": False},
                "telemetry": {"single_block_demo_mode": True, "transport": "local-fallback"},
                "error": None,
            }

        payload = {
            "task_id": task.task_id,
            "intent": task.intent.value,
            "mode": task.mode.value if task.mode else "safe",
            "args": task.args,
            "context": {"single_block_demo_mode": True},
        }
        request_json = json.dumps(payload, ensure_ascii=False)
        remote_cmd = build_remote_command(
            remote_python=self.settings.remote_executor_python,
            remote_executor_path="__REMOTE_FILE__",
            request_json=request_json,
        )
        client = self._connect()
        try:
            remote_file = self._ensure_remote_executor_uploaded(client)
            remote_cmd = remote_cmd.replace("__REMOTE_FILE__", remote_file)
            _, stdout, stderr = client.exec_command(remote_cmd, timeout=60)
            exit_status = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8")
            error_output = stderr.read().decode("utf-8")
            if exit_status != 0:
                message = (error_output or output or f"remote command failed with status {exit_status}").strip()
                return {
                    "ok": False,
                    "task_id": task.task_id,
                    "executor_state": "FAILED",
                    "mode": task.mode.value if task.mode else "safe",
                    "intent": task.intent.value,
                    "result": {
                        "summary": message[:300] or "remote execution failed",
                        "motion_executed": False,
                    },
                    "telemetry": {
                        "single_block_demo_mode": True,
                        "transport": "ssh",
                        "stdout": output,
                        "stderr": error_output,
                        "exit_status": exit_status,
                    },
                    "error": {
                        "type": "EXECUTOR_ERROR",
                        "code": "REMOTE_EXECUTION_FAILED",
                        "message": message[:300] or "remote execution failed",
                        "retryable": True,
                    },
                }
            return json.loads(output)
        except (json.JSONDecodeError, KeyError, ValueError, OSError, subprocess.CalledProcessError) as exc:
            return {
                "ok": False,
                "task_id": task.task_id,
                "executor_state": "FAILED",
                "mode": task.mode.value if task.mode else "safe",
                "intent": task.intent.value,
                "result": {
                    "summary": str(exc)[:300] or "transport execution failed",
                    "motion_executed": False,
                },
                "telemetry": {"single_block_demo_mode": True, "transport": "ssh"},
                "error": {
                    "type": "EXECUTOR_ERROR",
                    "code": "REMOTE_EXECUTION_FAILED",
                    "message": str(exc)[:300] or "transport execution failed",
                    "retryable": True,
                },
            }
        finally:
            client.close()

    def camera_frame(self, stream: str = "color") -> dict:
        if not self.settings.ssh_host or not self.settings.ssh_user or not self.settings.ssh_password:
            return build_camera_unavailable_payload("SSH not configured", stream)

        client = self._connect()
        try:
            remote_file = self._ensure_remote_executor_uploaded(client)
            command = f"{quote(self.settings.remote_executor_python)} {quote(remote_file)} --camera-frame --stream {quote(stream)}"
            _, stdout, stderr = client.exec_command(command, timeout=20)
            exit_status = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8")
            error_output = stderr.read().decode("utf-8")
            if exit_status != 0:
                message = (error_output or output or f"remote camera command failed with status {exit_status}").strip()
                return build_camera_unavailable_payload(message[:160], stream)
            payload = json.loads(output)
            return {
                "content": base64.b64decode(payload["image_base64"]),
                "media_type": payload.get("media_type", "image/jpeg"),
                "stream": payload.get("stream", stream),
            }
        except (json.JSONDecodeError, KeyError, ValueError, subprocess.CalledProcessError, OSError) as exc:
            return build_camera_unavailable_payload(str(exc)[:160], stream)
        finally:
            client.close()

    def ensure_depth_viz_stream_ready(self) -> None:
        if not self.settings.ssh_host or not self.settings.ssh_user or not self.settings.ssh_password:
            raise RuntimeError("SSH not configured")

        client = self._connect()
        try:
            remote_file = self._ensure_remote_executor_uploaded(client)
            remote_dir = str(PurePosixPath(remote_file).parent)
            bridge_file = f"{remote_dir}/depth_viz_bridge.py"
            marker = "jetarm_demo_agent_remote/depth_viz_bridge.py"
            remote_script = """
source /opt/ros/melodic/setup.bash >/dev/null 2>&1
source ~/jetarm/devel/setup.bash >/dev/null 2>&1
if ! timeout 2 rostopic echo -n 1 /jetarm_demo/depth_viz/image_raw >/dev/null 2>&1; then
  pkill -f {marker!r} >/dev/null 2>&1 || true
  setsid {remote_python} {bridge_file} >/tmp/jetarm_depth_viz_bridge.log 2>&1 < /dev/null &
  sleep 2
fi
python3 - <<'PY'
import rospy
from sensor_msgs.msg import Image

rospy.init_node('jetarm_demo_depth_viz_ready_check', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
rospy.wait_for_message('/jetarm_demo/depth_viz/image_raw', Image, timeout=6.0)
print('ok')
PY
            """.format(
                marker=marker,
                remote_python=quote(self.settings.remote_executor_python),
                bridge_file=quote(bridge_file),
            ).strip()
            command = f"bash -lc {quote(remote_script)}"
            _, stdout, stderr = client.exec_command(command, timeout=20)
            exit_status = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8")
            error_output = stderr.read().decode("utf-8")
            if exit_status != 0:
                raise RuntimeError((error_output or output or "depth viz bridge startup failed").strip()[:300])
        finally:
            client.close()
