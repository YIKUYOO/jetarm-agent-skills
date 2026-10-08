"""Publish direct JetArm servo pulse goals through the RDK ROS bridge."""

from __future__ import annotations

from jetarm_connection import add_connection_arguments, connect, connection_cli, require_driver, preview_motion

import argparse
import json
import shlex
import sys
import time

import paramiko


REMOTE_SCRIPT = r'''
import argparse
import json
import time

import rclpy
from rclpy.node import Node
from servo_controller_msgs.msg import ServoPosition, ServosPosition


class Publisher(Node):
    def __init__(self):
        super().__init__("codex_servo_publish")
        self.pub = self.create_publisher(ServosPosition, "/servo_controller", 1)

    def wait_ready(self):
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self.pub.get_subscription_count() > 0:
                return
            rclpy.spin_once(self, timeout_sec=0.1)
        raise RuntimeError("no subscriber on /servo_controller")

    def publish(self, duration, goals):
        if not 0.1 <= float(duration) <= 30.0:
            raise ValueError("duration must be between 0.1 and 30 seconds")
        if not goals or any(int(i) not in (1, 2, 3, 4, 5, 10) or not 0 <= float(p) <= 1000 for i, p in goals):
            raise ValueError("invalid servo goal")
        msg = ServosPosition()
        msg.duration = float(duration)
        msg.position_unit = "pulse"
        msg.position = []
        for servo_id, pulse in goals:
            item = ServoPosition()
            item.id = int(servo_id)
            item.position = float(pulse)
            msg.position.append(item)
        self.pub.publish(msg)
        time.sleep(float(duration) + 0.2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--goals-json", required=True)
    args = parser.parse_args()

    goals = json.loads(args.goals_json)
    rclpy.init()
    node = Publisher()
    try:
        node.wait_ready()
        node.publish(args.duration, goals)
        print(json.dumps({"ok": True, "duration": args.duration, "goals": goals}, ensure_ascii=False))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_connection_arguments(parser)
    parser.add_argument("--execute", action="store_true", help="Enable real physical motion after operator safety checks.")
    parser.add_argument("--duration", type=float, default=1.5)
    parser.add_argument(
        "--goal",
        action="append",
        required=True,
        help="Servo goal as ID:PULSE. Repeat for multiple servos.",
    )
    return parser.parse_args()


def parse_goals(raw_goals: list[str]) -> list[list[float]]:
    goals = []
    for raw in raw_goals:
        servo_id, pulse = raw.split(":", 1)
        servo_id, pulse = int(servo_id), float(pulse)
        if servo_id not in (1, 2, 3, 4, 5, 10) or not 0 <= pulse <= 1000:
            raise ValueError("invalid servo ID or pulse")
        if any(goal[0] == servo_id for goal in goals):
            raise ValueError("duplicate servo ID")
        goals.append([servo_id, pulse])
    return goals


def run(client: paramiko.SSHClient, command: str, timeout: int = 30) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")


def main() -> int:
    args = parse_args()
    if preview_motion(args):
        return 0
    goals = parse_goals(args.goal)
    remote_script = f"/tmp/codex_servo_publish_{int(time.time())}.py"
    client = connect(args.host, args.username, args.key_file)
    try:
        require_driver(client)
        sftp = client.open_sftp()
        with sftp.open(remote_script, "w") as fh:
            fh.write(REMOTE_SCRIPT)
        sftp.close()
        remote_args = [
            "python3",
            remote_script,
            "--duration",
            str(args.duration),
            "--goals-json",
            json.dumps(goals),
        ]
        command = (
            "bash -lc "
            + shlex.quote(
                "source /opt/ros/humble/setup.bash; "
                "source ~/jetarm_ros2_ws/install/setup.bash; "
                + " ".join(shlex.quote(v) for v in remote_args)
            )
        )
        code, stdout, stderr = run(client, command, timeout=45)
        print(stdout, end="")
        print(stderr, end="", file=sys.stderr)
        return code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
