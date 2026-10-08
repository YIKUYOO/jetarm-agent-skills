#!/usr/bin/env python3
"""Safely nudge each JetArm servo a little, then return to the observed start pose."""

import argparse
import json
import os
import time
from typing import Dict, Iterable, List

import rclpy
from rclpy.node import Node
from servo_controller_msgs.msg import ServoPosition, ServoStateList, ServosPosition


DEFAULT_SERVO_IDS = [1, 2, 3, 4, 5, 10]


def clamp_pulse(value: float) -> float:
    return min(1000.0, max(0.0, float(value)))


def parse_ids(text: str) -> List[int]:
    ids = [int(item.strip()) for item in text.split(",") if item.strip()]
    invalid = [servo_id for servo_id in ids if servo_id not in DEFAULT_SERVO_IDS]
    if invalid:
        raise ValueError(f"unsupported servo id(s): {invalid}; allowed: {DEFAULT_SERVO_IDS}")
    return ids


class JointNudgeTest(Node):
    def __init__(self, servo_ids: Iterable[int]) -> None:
        super().__init__("jetarm_joint_nudge_test")
        self.servo_ids = list(servo_ids)
        self.latest_positions: Dict[int, float] = {}
        self.publisher = self.create_publisher(ServosPosition, "/servo_controller", 1)
        self.subscription = self.create_subscription(
            ServoStateList,
            "/controller_manager/servo_states",
            self._servo_state_callback,
            10,
        )

    def _servo_state_callback(self, msg: ServoStateList) -> None:
        for item in msg.servo_state:
            if int(item.id) in self.servo_ids:
                self.latest_positions[int(item.id)] = float(item.position)

    def wait_for_positions(self, timeout_s: float) -> Dict[int, float]:
        deadline = time.time() + timeout_s
        while time.time() < deadline and rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.1)
            if all(servo_id in self.latest_positions for servo_id in self.servo_ids):
                return dict(self.latest_positions)
        missing = [servo_id for servo_id in self.servo_ids if servo_id not in self.latest_positions]
        raise TimeoutError(f"missing servo state for id(s): {missing}")

    def publish_positions(self, positions: Dict[int, float], duration_s: float) -> None:
        msg = ServosPosition()
        msg.duration = float(duration_s)
        msg.position_unit = "pulse"
        for servo_id in sorted(positions):
            item = ServoPosition()
            item.id = int(servo_id)
            item.position = float(clamp_pulse(positions[servo_id]))
            msg.position.append(item)
        for _ in range(3):
            self.publisher.publish(msg)
            rclpy.spin_once(self, timeout_sec=0.05)
            time.sleep(0.05)


def target_for(start: float, delta: float) -> float:
    if start + delta <= 980:
        return start + delta
    if start - delta >= 20:
        return start - delta
    return start


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", default="1,2,3,4,5,10", help="Comma-separated servo ids to test.")
    parser.add_argument("--delta", type=float, default=8.0, help="Small pulse offset for each nudge.")
    parser.add_argument("--duration", type=float, default=0.35, help="Motion duration for each nudge/return.")
    parser.add_argument("--settle", type=float, default=0.35, help="Pause after each command.")
    parser.add_argument("--state-timeout", type=float, default=5.0)
    parser.add_argument("--execute", action="store_true", help="Actually publish commands. Default is dry-run.")
    parser.add_argument("--allow-without-rrc", action="store_true", help="Allow execution when /dev/rrc is absent.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    servo_ids = parse_ids(args.ids)
    payload = {
        "status": "starting",
        "execute": bool(args.execute),
        "dev_rrc_present": os.path.exists("/dev/rrc"),
        "topic": "/servo_controller",
        "state_topic": "/controller_manager/servo_states",
        "ids": servo_ids,
        "delta": args.delta,
        "duration": args.duration,
    }

    if args.execute and not payload["dev_rrc_present"] and not args.allow_without_rrc:
        payload["status"] = "blocked"
        payload["reason"] = "/dev/rrc is missing"
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else payload)
        return 2

    rclpy.init()
    node = JointNudgeTest(servo_ids)
    try:
        start_positions = node.wait_for_positions(args.state_timeout)
        plan = []
        for servo_id in servo_ids:
            start = start_positions[servo_id]
            target = target_for(start, args.delta)
            plan.append({"id": servo_id, "start": start, "target": target, "return": start})
        payload["start_positions"] = start_positions
        payload["plan"] = plan

        if not args.execute:
            payload["status"] = "dry_run"
            print(json.dumps(payload, indent=2, sort_keys=True) if args.json else payload)
            return 0

        for item in plan:
            node.publish_positions({int(item["id"]): float(item["target"])}, args.duration)
            time.sleep(args.settle)
            node.publish_positions({int(item["id"]): float(item["return"])}, args.duration)
            time.sleep(args.settle)
        payload["status"] = "completed"
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else payload)
        return 0
    except Exception as exc:
        payload["status"] = "failed"
        payload["error"] = str(exc)
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else payload)
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
