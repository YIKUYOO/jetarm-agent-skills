"""Run a small JetArm tabletop motion from an RGB-D observation.

The script uses the board-side calibration from the official sorting demo to
convert an observed object pixel into JetArm world x/y coordinates, then sends a
bounded motion through the board's IK and servo controller. Use it for
experiment stages, not as a final skill.
"""

from __future__ import annotations

from jetarm_connection import add_connection_arguments, connect, connection_cli, require_driver, preview_motion

import argparse
import json
import posixpath
import shlex
import sys
import time
from pathlib import Path

import paramiko


REMOTE_SCRIPT = r'''
import argparse
import json
import math
import time

import numpy as np
import rclpy
import yaml
from kinematics.kinematics_control import set_pose_target
from kinematics_msgs.srv import SetRobotPose
from rclpy.node import Node
from servo_controller_msgs.msg import ServoPosition, ServosPosition


from pathlib import Path
from sdk.common import pixels_to_world, extristric_plane_shift

CONFIG_PATH = Path.home() / "jetarm_ros2_ws/src/bringup/config/config.yaml"


def compute_pose_xy(observation):
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    K = np.array(observation["camera_info"]["k"], dtype=float).reshape(3, 3)
    extr = np.array(cfg["extristric"], dtype=float)
    tvec = extr[:1]
    rmat = extr[1:]
    center = observation["red_candidate"]["center_px"]
    shifted_t, shifted_r = extristric_plane_shift(tvec.T, rmat, 0.03)
    transform = np.eye(4)
    transform[:3, :3] = shifted_r
    transform[:3, 3] = np.asarray(shifted_t).reshape(3)
    raw = np.asarray(pixels_to_world([center], np.asmatrix(K), np.asmatrix(transform))[0]).reshape(3)
    local = raw.copy()
    local[1] = -local[1]
    local[2] = 0.03
    white = np.array(cfg["white_area_pose_world"], dtype=float)
    transformed = white @ np.array([local[0], local[1], local[2], 1.0], dtype=float)
    return {
        "center_px": center,
        "raw_plane_xyz": [float(v) for v in raw],
        "local_white_xyz": [float(v) for v in local],
        "pose_xy": [float(transformed[0]), float(transformed[1])],
    }


def servo5_from_rect(rect_angle, yaw):
    rect_r = rect_angle % 90.0
    if rect_r > 45.0:
        rect_r -= 90.0
    return max(350, min(650, 500 + int(1000.0 * (rect_r + yaw) / 240.0)))


class Commander(Node):
    def __init__(self):
        super().__init__("codex_tabletop_motion")
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
        raise RuntimeError(f"IK timed out for target={target}, pitch={pitch}")

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
        time.sleep(float(duration) + 0.15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--observation-json", required=True)
    parser.add_argument("--stage", choices=["approach", "probe", "pick"], default="approach")
    parser.add_argument("--x-offset", type=float, default=0.0)
    parser.add_argument("--y-offset", type=float, default=0.0)
    parser.add_argument("--target-x", type=float, default=None)
    parser.add_argument("--target-y", type=float, default=None)
    parser.add_argument("--approach-z", type=float, default=0.052)
    parser.add_argument("--target-z", type=float, default=0.004)
    parser.add_argument("--retreat-z", type=float, default=0.072)
    parser.add_argument("--pitch", type=float, default=90.0)
    parser.add_argument("--pre-grasp", type=int, default=350)
    parser.add_argument("--close", type=int, default=650)
    parser.add_argument("--servo5", type=int, default=None)
    args = parser.parse_args()

    observation = json.loads(args.observation_json)
    pose = compute_pose_xy(observation)
    x = args.target_x if args.target_x is not None else pose["pose_xy"][0] + args.x_offset
    y = args.target_y if args.target_y is not None else pose["pose_xy"][1] + args.y_offset
    rect_angle = float(observation["red_candidate"]["min_area_rect"]["angle"])

    rclpy.init()
    commander = Commander()
    try:
        commander.wait_ready()
        approach = commander.ik([x, y, args.approach_z], args.pitch, 1.6)
        yaw = float(approach.rpy[-1]) if approach.rpy else 0.0
        servo5 = int(args.servo5 if args.servo5 is not None else servo5_from_rect(rect_angle, yaw))
        result = {
            "stage": args.stage,
            "pose": pose,
            "target_xy": [x, y],
            "target_xy_source": "override" if args.target_x is not None or args.target_y is not None else "observation",
            "approach_z": args.approach_z,
            "target_z": args.target_z,
            "retreat_z": args.retreat_z,
            "pitch": args.pitch,
            "servo5": servo5,
            "approach_pulse": list(approach.pulse),
            "approach_rpy": list(approach.rpy),
        }
        commander.publish(0.45, [(10, args.pre_grasp)])
        commander.publish(
            1.7,
            [(1, approach.pulse[0]), (2, approach.pulse[1]), (3, approach.pulse[2]), (4, approach.pulse[3]), (5, servo5), (10, args.pre_grasp)],
        )
        if args.stage in ("probe", "pick"):
            target = commander.ik([x, y, args.target_z], args.pitch, 1.3)
            retreat = commander.ik([x, y, args.retreat_z], args.pitch, 1.3)
            result["target_pulse"] = list(target.pulse)
            result["retreat_pulse"] = list(retreat.pulse)
            commander.publish(
                1.4,
                [(1, target.pulse[0]), (2, target.pulse[1]), (3, target.pulse[2]), (4, target.pulse[3]), (5, servo5), (10, args.pre_grasp)],
            )
            if args.stage == "probe":
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return
            commander.publish(0.55, [(10, args.close)])
            commander.publish(
                1.3,
                [(1, retreat.pulse[0]), (2, retreat.pulse[1]), (3, retreat.pulse[2]), (4, retreat.pulse[3]), (5, servo5), (10, args.close)],
            )
            commander.publish(1.0, [(1, 500), (2, 560), (3, 130), (4, 115), (5, 500), (10, args.close)])
        print(json.dumps(result, ensure_ascii=False, indent=2))
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
    parser.add_argument("--observation-meta", required=True, type=Path)
    parser.add_argument("--stage", choices=["approach", "probe", "pick"], default="approach")
    parser.add_argument("--x-offset", type=float, default=0.0)
    parser.add_argument("--y-offset", type=float, default=0.0)
    parser.add_argument("--target-x", type=float, default=None)
    parser.add_argument("--target-y", type=float, default=None)
    parser.add_argument("--approach-z", type=float, default=0.052)
    parser.add_argument("--target-z", type=float, default=0.004)
    parser.add_argument("--retreat-z", type=float, default=0.072)
    parser.add_argument("--pitch", type=float, default=90.0)
    parser.add_argument("--pre-grasp", type=int, default=350)
    parser.add_argument("--close", type=int, default=650)
    parser.add_argument("--servo5", type=int, default=None)
    return parser.parse_args()


def run(client: paramiko.SSHClient, command: str, timeout: int = 60) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    return code, stdout.read().decode("utf-8", "replace"), stderr.read().decode("utf-8", "replace")


def main() -> int:
    args = parse_args()
    if preview_motion(args):
        return 0
    observation = json.loads(args.observation_meta.read_text(encoding="utf-8"))
    remote_script = f"/tmp/codex_tabletop_motion_{int(time.time())}.py"
    client = connect(args.host, args.username, args.key_file)
    try:
        require_driver(client)
        sftp = client.open_sftp()
        with sftp.open(remote_script, "w") as fh:
            fh.write(REMOTE_SCRIPT)
        sftp.close()
        obs_arg = json.dumps(observation, ensure_ascii=False)
        remote_args = [
            "python3",
            remote_script,
            "--stage",
            args.stage,
            "--observation-json",
            obs_arg,
            "--x-offset",
            str(args.x_offset),
            "--y-offset",
            str(args.y_offset),
            "--approach-z",
            str(args.approach_z),
            "--target-z",
            str(args.target_z),
            "--retreat-z",
            str(args.retreat_z),
            "--pitch",
            str(args.pitch),
            "--pre-grasp",
            str(args.pre_grasp),
            "--close",
            str(args.close),
        ]
        if args.servo5 is not None:
            remote_args.extend(["--servo5", str(args.servo5)])
        if args.target_x is not None:
            remote_args.extend(["--target-x", str(args.target_x)])
        if args.target_y is not None:
            remote_args.extend(["--target-y", str(args.target_y)])
        command = (
            "bash -lc "
            + shlex.quote(
                "source /opt/ros/humble/setup.bash; "
                "source ~/jetarm_ros2_ws/install/setup.bash; "
                + " ".join(shlex.quote(v) for v in remote_args)
            )
        )
        code, stdout, stderr = run(client, command, timeout=90)
        print(stdout, end="")
        print(stderr, end="", file=sys.stderr)
        return code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
