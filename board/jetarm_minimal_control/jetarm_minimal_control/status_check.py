from __future__ import annotations

import argparse
import subprocess
import time
from dataclasses import dataclass

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    warning: bool = False


class StatusCheck(Node):
    def __init__(self) -> None:
        super().__init__("jetarm_status_check")

    def check_service(self, name: str, timeout_sec: float) -> CheckResult:
        client = self.create_client(Trigger, name)
        ok = client.wait_for_service(timeout_sec=timeout_sec)
        return CheckResult(name, ok, "service ready" if ok else "service missing")

    def check_topic(self, name: str) -> CheckResult:
        topics = dict(self.get_topic_names_and_types())
        ok = name in topics
        detail = ", ".join(topics.get(name, [])) if ok else "topic missing"
        return CheckResult(name, ok, detail)

    def check_action(self, name: str) -> CheckResult:
        proc = subprocess.run(
            ["ros2", "action", "list", "-t"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        actions = {}
        for line in proc.stdout.splitlines():
            if " [" not in line or not line.endswith("]"):
                continue
            action_name, action_type = line.rsplit(" [", 1)
            actions[action_name.strip()] = [action_type[:-1].strip()]
        ok = name in actions
        detail = ", ".join(actions.get(name, [])) if ok else "action missing"
        return CheckResult(name, ok, detail)

    def check_param(self, node_name: str, param_name: str, warn_if: str | None = None) -> CheckResult:
        proc = subprocess.run(
            ["ros2", "param", "get", node_name, param_name],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        name = f"{node_name} {param_name}"
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip() or "parameter unavailable"
            return CheckResult(name, False, detail)
        detail = proc.stdout.strip()
        warning = bool(warn_if and warn_if in detail)
        return CheckResult(name, True, detail, warning)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check the minimal JetArm RDK control stack.")
    parser.add_argument("--timeout", type=float, default=2.0, help="Seconds to wait for each service.")
    parser.add_argument("--require-camera", action="store_true", help="Also require legacy RGB-D topics.")
    parser.add_argument("--require-point-cloud", action="store_true", help="Require the optional point cloud topic.")
    parser.add_argument("--require-actions", action="store_true", help="Also require FollowJointTrajectory actions.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rclpy.init(args=None)
    node = StatusCheck()
    try:
        time.sleep(0.5)
        results = [
            node.check_service("/ros_robot_controller/init_finish", args.timeout),
            node.check_service("/controller_manager/init_finish", args.timeout),
            node.check_service("/kinematics/init_finish", args.timeout),
            node.check_service("/jetarm_preset_server/go_home", args.timeout),
            node.check_param("/jetarm_preset_server", "dry_run", warn_if="True"),
            node.check_param("/jetarm_preset_server", "topic"),
            node.check_topic("/controller_manager/servo_states"),
            node.check_topic("/servo_controller"),
        ]
        if args.require_camera:
            results.extend(
                [
                    node.check_topic("/depth_cam/color/image_raw"),
                    node.check_topic("/depth_cam/depth/image_raw"),
                    node.check_param("/depth_cam/depth_cam", "color_fps"),
                    node.check_param("/depth_cam/depth_cam", "depth_fps"),
                    node.check_param("/depth_cam/depth_cam", "enable_point_cloud"),
                ]
            )
        if args.require_point_cloud:
            results.append(node.check_topic("/depth_cam/depth/points"))
        if args.require_actions:
            results.extend(
                [
                    node.check_action("/arm_controller/follow_joint_trajectory"),
                    node.check_action("/gripper_controller/follow_joint_trajectory"),
                ]
            )

        for result in results:
            status = "WARN" if result.warning else ("OK" if result.ok else "MISSING")
            print(f"{status:7} {result.name} - {result.detail}")
        return 0 if all(result.ok for result in results) else 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
