from __future__ import annotations

import argparse
import sys
import time

import rclpy
from rclpy.node import Node
from servo_controller_msgs.msg import ServosPosition

from .presets import action_to_lines, get_action, iter_messages, list_action_names


class ActionRunner(Node):
    def __init__(self, topic: str) -> None:
        super().__init__("jetarm_action_runner")
        self.topic = topic
        self.publisher = self.create_publisher(ServosPosition, topic, 1)

    def wait_for_subscriber(self, timeout_sec: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self.publisher.get_subscription_count() > 0:
                return True
            rclpy.spin_once(self, timeout_sec=0.1)
        return self.publisher.get_subscription_count() > 0

    def run_action(self, action_name: str, execute: bool) -> bool:
        action = get_action(action_name)
        self.get_logger().info(f"Preset: {action.name} - {action.description}")
        for line in action_to_lines(action):
            self.get_logger().info(line)

        if not execute:
            self.get_logger().warn("dry-run only; pass --execute to publish servo goals")
            return True

        if not self.wait_for_subscriber():
            self.get_logger().error(
                f"no subscriber on {self.topic}; start servo_controller or pass the correct --topic"
            )
            return False

        for step, msg in iter_messages(action):
            self.publisher.publish(msg)
            goals = " ".join(f"{p.id}:{int(p.position)}" for p in msg.position)
            self.get_logger().info(f"published {step.duration:.2f}s {goals}")
            time.sleep(step.duration + 0.05)
        return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a minimal JetArm preset motion.")
    parser.add_argument("action", nargs="?", help="Preset name, for example go_home or observe_sorting.")
    parser.add_argument("--topic", default="/servo_controller", help="ServosPosition topic to publish.")
    parser.add_argument("--execute", action="store_true", help="Actually publish servo goals. Default is dry-run.")
    parser.add_argument("--list", action="store_true", help="List available presets and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        print("\n".join(list_action_names()))
        return 0
    if not args.action:
        print("Missing action. Use --list to show presets.", file=sys.stderr)
        return 2

    rclpy.init(args=None)
    node = ActionRunner(args.topic)
    try:
        ok = node.run_action(args.action, args.execute)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
