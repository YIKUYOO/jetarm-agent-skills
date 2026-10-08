"""Place the currently grasped tabletop object at a specified JetArm XY pose."""

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
from kinematics.kinematics_control import set_pose_target
from kinematics_msgs.srv import SetRobotPose
from rclpy.node import Node
from servo_controller_msgs.msg import ServoPosition, ServosPosition


class Commander(Node):
    def __init__(self):
        super().__init__("codex_tabletop_place")
        self.client = self.create_client(SetRobotPose, "/kinematics/set_pose_target")
        self.pub = self.create_publisher(ServosPosition, "/servo_controller", 1)

    def wait_ready(self):
        if not self.client.wait_for_service(timeout_sec=8.0):
            raise RuntimeError("IK service not available")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self.pub.get_subscription_count() > 0:
                return
            rclpy.spin_once(self, timeout_sec=0.1)
        raise RuntimeError("no subscriber on /servo_controller")

    def ik(self, target, pitch, duration):
        req = set_pose_target(target, pitch, [-90.0, 90.0], 1.0, duration)
        future = self.client.call_async(req)
        deadline = time.monotonic() + 12.0
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if future.done():
                res = future.result()
                if res is None or not res.success or not res.pulse:
                    raise RuntimeError(f"IK failed for target={target}, pitch={pitch}: {res}")
                return res
        raise RuntimeError("IK request timed out")

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
        time.sleep(float(duration) + 0.12)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--x", type=float, required=True)
    parser.add_argument("--y", type=float, required=True)
    parser.add_argument("--approach-z", type=float, default=0.080)
    parser.add_argument("--place-z", type=float, default=0.006)
    parser.add_argument("--retreat-z", type=float, default=0.085)
    parser.add_argument("--pitch", type=float, default=90.0)
    parser.add_argument("--servo5", type=int, default=500)
    parser.add_argument("--closed", type=int, default=650)
    parser.add_argument("--open", type=int, default=200)
    parser.add_argument("--speed", choices=["safe", "fast"], default="safe")
    args = parser.parse_args()

    approach_duration = 1.5 if args.speed == "safe" else 0.85
    target_duration = 1.25 if args.speed == "safe" else 0.75
    gripper_duration = 0.55 if args.speed == "safe" else 0.35
    retreat_duration = 1.1 if args.speed == "safe" else 0.75

    rclpy.init()
    commander = Commander()
    try:
        commander.wait_ready()
        approach = commander.ik([args.x, args.y, args.approach_z], args.pitch, approach_duration)
        target = commander.ik([args.x, args.y, args.place_z], args.pitch, target_duration)
        retreat = commander.ik([args.x, args.y, args.retreat_z], args.pitch, retreat_duration)

        commander.publish(
            approach_duration,
            [(1, approach.pulse[0]), (2, approach.pulse[1]), (3, approach.pulse[2]), (4, approach.pulse[3]), (5, args.servo5), (10, args.closed)],
        )
        commander.publish(
            target_duration,
            [(1, target.pulse[0]), (2, target.pulse[1]), (3, target.pulse[2]), (4, target.pulse[3]), (5, args.servo5), (10, args.closed)],
        )
        commander.publish(gripper_duration, [(10, args.open)])
        commander.publish(
            retreat_duration,
            [(1, retreat.pulse[0]), (2, retreat.pulse[1]), (3, retreat.pulse[2]), (4, retreat.pulse[3]), (5, args.servo5), (10, args.open)],
        )
        print(json.dumps({
            "ok": True,
            "target_xy": [args.x, args.y],
            "approach_pulse": list(approach.pulse),
            "target_pulse": list(target.pulse),
            "retreat_pulse": list(retreat.pulse),
            "speed": args.speed,
        }, ensure_ascii=False, indent=2))
    finally:
        commander.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_connection_arguments(parser)
    parser.add_argument("--execute", action="store_true", help="Enable real physical motion after operator safety checks.")
    parser.add_argument("--x", type=float, required=True)
    parser.add_argument("--y", type=float, required=True)
    parser.add_argument("--approach-z", type=float, default=0.080)
    parser.add_argument("--place-z", type=float, default=0.006)
    parser.add_argument("--retreat-z", type=float, default=0.085)
    parser.add_argument("--pitch", type=float, default=90.0)
    parser.add_argument("--servo5", type=int, default=500)
    parser.add_argument("--closed", type=int, default=650)
    parser.add_argument("--open", type=int, default=200)
    parser.add_argument("--speed", choices=["safe", "fast"], default="safe")
    return parser.parse_args()


def run(client: paramiko.SSHClient, command: str, timeout: int = 60) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")


def main() -> int:
    args = parse_args()
    if preview_motion(args):
        return 0
    remote_script = f"/tmp/codex_tabletop_place_{int(time.time())}.py"
    client = connect(args.host, args.username, args.key_file)
    try:
        require_driver(client)
        sftp = client.open_sftp()
        with sftp.open(remote_script, "w") as fh:
            fh.write(REMOTE_SCRIPT)
        sftp.close()
        remote_args = [
            "python3", remote_script,
            "--x", str(args.x),
            "--y", str(args.y),
            "--approach-z", str(args.approach_z),
            "--place-z", str(args.place_z),
            "--retreat-z", str(args.retreat_z),
            "--pitch", str(args.pitch),
            "--servo5", str(args.servo5),
            "--closed", str(args.closed),
            "--open", str(args.open),
            "--speed", args.speed,
        ]
        command = (
            "bash -lc "
            + shlex.quote(
                "source /opt/ros/humble/setup.bash; "
                "source ~/jetarm_ros2_ws/install/setup.bash; "
                + " ".join(shlex.quote(v) for v in remote_args)
            )
        )
        code, stdout, stderr = run(client, command, timeout=75)
        print(stdout, end="")
        print(stderr, end="", file=sys.stderr)
        return code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
