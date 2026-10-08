#!/usr/bin/env python3
import argparse
import json
import os
import shlex
from pathlib import Path

DEFAULT_HOST = os.environ.get("JETARM_RDK_HOST", "")
DEFAULT_PORT = int(os.environ.get("JETARM_RDK_PORT", "22"))
DEFAULT_USER = os.environ.get("JETARM_RDK_USER", "")
DEFAULT_PASSWORD = os.environ.get("JETARM_RDK_PASSWORD")
DEFAULT_REMOTE_ROOT = os.environ.get("JETARM_RDK_REMOTE_ROOT", "")


def remote_join(*parts):
    cleaned = []
    for index, part in enumerate(parts):
        text = str(part).replace("\\", "/")
        if index == 0:
            cleaned.append(text.rstrip("/"))
        else:
            cleaned.append(text.strip("/"))
    return "/".join(item for item in cleaned if item)


def summarize_status(text):
    payload = json.loads(text)
    missing = []
    control = payload.get("control_serial", {})
    cameras = payload.get("camera_usb", {})
    packages = payload.get("packages", {})
    if not control.get("rrc_exists"):
        missing.append("rrc")
    if not control.get("ch340_usb"):
        missing.append("ch340")
    if not cameras.get("orbbec_rgb"):
        missing.append("orbbec_rgb")
    if not cameras.get("orbbec_depth"):
        missing.append("orbbec_depth")
    for pkg in ("ros_robot_controller", "servo_controller", "kinematics", "sdk", "peripherals"):
        if packages.get(pkg) is not True:
            missing.append(f"pkg:{pkg}")
    return {"ready": not missing, "missing": missing, "payload": payload}


def connect(args):
    import paramiko

    client = paramiko.SSHClient()
    if not args.host or not args.user:
        raise ValueError("Set JETARM_RDK_HOST and JETARM_RDK_USER (or --host and --user)")
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        hostname=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
        look_for_keys=True,
        allow_agent=True,
    )
    return client


def exec_command(args, command):
    client = connect(args)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=args.timeout)
        exit_code = stdout.channel.recv_exit_status()
        return {
            "ok": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout.read().decode("utf-8", "replace"),
            "stderr": stderr.read().decode("utf-8", "replace"),
            "command": command,
        }
    finally:
        client.close()


def _mkdir(client, remote_path):
    quoted = shlex.quote(remote_path)
    stdin, stdout, stderr = client.exec_command(f"mkdir -p {quoted}")
    return stdout.channel.recv_exit_status()


def _chmod_executable(client, remote_path):
    quoted = shlex.quote(remote_path)
    stdin, stdout, stderr = client.exec_command(f"chmod +x {quoted}")
    return stdout.channel.recv_exit_status()


def deploy(args):
    if not args.remote_root or not args.remote_root.startswith("/"):
        return {"ok": False, "error_code": "REMOTE_ROOT_REQUIRED", "message": "Set an absolute --remote-root or JETARM_RDK_REMOTE_ROOT"}
    root = Path(args.local_root).resolve()
    board_dir = root / "board"
    if not board_dir.is_dir():
        return {"ok": False, "error_code": "MISSING_BOARD_DIR", "board_dir": str(board_dir)}

    client = connect(args)
    try:
        sftp = client.open_sftp()
        _mkdir(client, remote_join(args.remote_root, "board"))
        uploaded = []
        for path in sorted(board_dir.glob("*")):
            if path.is_file() and path.name != ".gitkeep":
                remote = remote_join(args.remote_root, "board", path.name)
                sftp.put(str(path), remote)
                _chmod_executable(client, remote)
                uploaded.append(remote)
        sftp.close()
        return {"ok": True, "remote_root": args.remote_root, "uploaded": uploaded}
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT)
    parser.add_argument("--local-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--timeout", type=int, default=60)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("deploy")
    exec_p = sub.add_parser("exec")
    exec_p.add_argument("remote_command")
    args = parser.parse_args()

    if args.cmd == "deploy":
        result = deploy(args)
    else:
        result = exec_command(args, args.remote_command)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
