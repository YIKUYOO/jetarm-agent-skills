#!/usr/bin/env python3
"""Publish a guarded JetArm servo command to the ROS2 /servo_controller topic."""

import argparse
import json
import os
import time
from typing import Dict, List

import rclpy
from rclpy.node import Node
from servo_controller_msgs.msg import ServoPosition, ServosPosition


VALID_SERVO_IDS = {1, 2, 3, 4, 5, 10}


def parse_positions(text: str) -> Dict[int, float]:
    positions: Dict[int, float] = {}
    if not text.strip():
        raise ValueError("positions must not be empty")
    for item in text.split(","):
        if ":" not in item:
            raise ValueError(f"invalid position item {item!r}; expected id:value")
        key, value = item.split(":", 1)
        servo_id = int(key.strip())
        if servo_id not in VALID_SERVO_IDS:
            raise ValueError(f"unsupported servo id {servo_id}; allowed ids: {sorted(VALID_SERVO_IDS)}")
        positions[servo_id] = float(value.strip())
    return positions


def clamp_positions(positions: Dict[int, float], unit: str) -> Dict[int, float]:
    if unit == "pulse":
        return {servo_id: min(1000.0, max(0.0, value)) for servo_id, value in positions.items()}
    return positions


class SafeServoMove(Node):
    def __init__(self) -> None:
        super().__init__("jetarm_safe_servo_move")
        self.publisher = self.create_publisher(ServosPosition, "/servo_controller", 1)

    def publish_once(self, positions: Dict[int, float], unit: str, duration: float) -> None:
        msg = ServosPosition()
        msg.duration = float(duration)
        msg.position_unit = unit
        for servo_id in sorted(positions):
            item = ServoPosition()
            item.id = int(servo_id)
            item.position = float(positions[servo_id])
            msg.position.append(item)
        for _ in range(3):
            self.publisher.publish(msg)
            rclpy.spin_once(self, timeout_sec=0.05)
            time.sleep(0.05)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--positions", required=True, help="Comma list such as 1:500,2:500,3:500,4:500,5:500,10:500")
    parser.add_argument("--unit", default="pulse", choices=["pulse", "deg", "rad"])
    parser.add_argument("--duration", type=float, default=0.8)
    parser.add_argument("--execute", action="store_true", help="Actually publish the ROS2 command. Default is dry-run.")
    parser.add_argument("--allow-without-rrc", action="store_true", help="Allow execution when /dev/rrc is absent.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable summary.")
    args = parser.parse_args()

    positions = clamp_positions(parse_positions(args.positions), args.unit)
    payload = {
        "topic": "/servo_controller",
        "unit": args.unit,
        "duration": args.duration,
        "positions": positions,
        "execute": bool(args.execute),
        "dev_rrc_present": os.path.exists("/dev/rrc"),
    }

    if not args.execute:
        payload["status"] = "dry_run"
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else payload)
        return 0

    if not payload["dev_rrc_present"] and not args.allow_without_rrc:
        payload["status"] = "blocked"
        payload["reason"] = "/dev/rrc is missing"
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json else payload)
        return 2

    rclpy.init()
    node = SafeServoMove()
    try:
        node.publish_once(positions, args.unit, args.duration)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    payload["status"] = "published"
    print(json.dumps(payload, indent=2, sort_keys=True) if args.json else payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
