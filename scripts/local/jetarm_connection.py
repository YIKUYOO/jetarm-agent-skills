"""Explicit SSH configuration and offline-by-default physical motion gate."""
from __future__ import annotations
import json
import math
import os
import shlex
from pathlib import Path
import paramiko

def add_connection_arguments(parser):
    parser.add_argument("--host", default=os.environ.get("JETARM_HOST"))
    parser.add_argument("--username", default=os.environ.get("JETARM_USER"))
    parser.add_argument("--key-file", default=os.environ.get("JETARM_SSH_KEY"))

def connect(host, username, key_file=None):
    if not host or not username:
        raise ValueError("Set JETARM_HOST and JETARM_USER, or pass --host and --username")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    known_hosts = os.environ.get("JETARM_KNOWN_HOSTS")
    if known_hosts:
        client.load_host_keys(str(Path(known_hosts).expanduser()))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(hostname=host, username=username,
                   key_filename=str(Path(key_file).expanduser()) if key_file else None,
                   look_for_keys=True, allow_agent=True, timeout=10)
    return client

def connection_cli(args):
    result = []
    for flag, value in (("--host", args.host), ("--username", args.username), ("--key-file", args.key_file)):
        if value:
            result.extend([flag, str(value)])
    return result

def require_driver(client):
    command = "source /opt/ros/humble/setup.bash; source ~/jetarm_ros2_ws/install/setup.bash; ros2 node list"
    _, stdout, stderr = client.exec_command("bash -lc " + shlex.quote(command), timeout=15)
    status = stdout.channel.recv_exit_status()
    nodes = stdout.read().decode("utf-8", "replace").splitlines()
    if status or "/ros_robot_controller" not in {n.strip() for n in nodes}:
        raise RuntimeError("Physical motion blocked: /ros_robot_controller is not present")

def preview_motion(args):
    for name, value in vars(args).items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        if name in {"pre_grasp", "close", "closed", "open", "servo5"} and value is not None and not 0 <= value <= 1000:
            raise ValueError(f"{name} pulse must be between 0 and 1000")
    if hasattr(args, "duration") and not 0.1 <= args.duration <= 30:
        raise ValueError("duration must be between 0.1 and 30 seconds")
    if hasattr(args, "goal"):
        from jetarm_servo_publish import parse_goals
        parse_goals(args.goal)
    if args.execute and getattr(args, "dry_run", False):
        raise ValueError("--execute and --dry-run are mutually exclusive")
    if args.execute:
        return False
    request = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items() if k not in {"key_file", "host", "username"}}
    print(json.dumps({"mode": "dry_run", "physical_motion": False,
                      "note": "Offline request preview only; no IK, reachability or collision validation.",
                      "request": request}, ensure_ascii=False, indent=2))
    return True
