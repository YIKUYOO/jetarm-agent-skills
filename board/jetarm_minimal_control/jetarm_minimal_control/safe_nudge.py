from __future__ import annotations

import argparse
import sys
import time
from typing import Dict, Iterable, List

import rclpy
from rclpy.node import Node
from ros_robot_controller_msgs.msg import GetBusServoCmd, ServoPosition, ServosPosition
from ros_robot_controller_msgs.srv import GetBusServoState

SAFE_SERVO_IDS = (1, 2, 3, 4, 5, 10)
DEFAULT_DELTAS = {1: 8, 2: 8, 3: 8, 4: 8, 5: 8, 10: 12}


class SafeNudge(Node):
    def __init__(self, service_name: str, topic_name: str) -> None:
        super().__init__("jetarm_safe_nudge")
        self.client = self.create_client(GetBusServoState, service_name)
        self.publisher = self.create_publisher(ServosPosition, topic_name, 1)
        if not self.client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError(f"Service not available: {service_name}")

    def read_positions(self, servo_ids: Iterable[int]) -> Dict[int, int]:
        request = GetBusServoState.Request()
        for servo_id in servo_ids:
            cmd = GetBusServoCmd()
            cmd.id = int(servo_id)
            cmd.get_position = 1
            request.cmd.append(cmd)

        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=8.0)
        response = future.result()
        if response is None or not response.success:
            raise RuntimeError("Failed to read bus servo states")

        positions: Dict[int, int] = {}
        for servo_id, state in zip(servo_ids, response.state):
            if not state.position:
                self.get_logger().warn(f"servo {servo_id} did not return a valid position; skipping")
                continue
            positions[int(servo_id)] = int(state.position[0])
        if not positions:
            raise RuntimeError("No requested servos returned a valid position")
        return positions

    def publish_goal(self, servo_id: int, pulse: int, duration: float) -> None:
        msg = ServosPosition()
        msg.duration = float(duration)
        position = ServoPosition()
        position.id = int(servo_id)
        position.position = int(pulse)
        msg.position.append(position)
        self.publisher.publish(msg)
        self.get_logger().info(f"published servo {servo_id}: {pulse} over {duration:.2f}s")

    def nudge(self, servo_ids: List[int], duration: float, execute: bool) -> Dict[int, int]:
        start_positions = self.read_positions(servo_ids)
        self.get_logger().info("current pulses: " + ", ".join(f"{sid}:{pos}" for sid, pos in start_positions.items()))
        if not execute:
            self.get_logger().warn("dry-run only; pass --execute to publish servo goals")
            return start_positions

        # Give discovery a short moment before one-shot publications.
        time.sleep(0.25)
        skipped = [servo_id for servo_id in servo_ids if servo_id not in start_positions]
        if skipped:
            self.get_logger().warn(f"skipping unreadable servo ids: {skipped}")

        for servo_id in [servo_id for servo_id in servo_ids if servo_id in start_positions]:
            start = start_positions[servo_id]
            delta = DEFAULT_DELTAS.get(servo_id, 8)
            direction = 1 if start + delta <= 980 else -1
            target = max(20, min(980, start + direction * delta))
            self.publish_goal(servo_id, target, duration)
            time.sleep(duration + 0.15)
            self.publish_goal(servo_id, start, duration)
            time.sleep(duration + 0.25)
        return start_positions


def parse_servo_ids(raw_ids: str) -> List[int]:
    if raw_ids == "all":
        return list(SAFE_SERVO_IDS)
    ids = [int(item.strip()) for item in raw_ids.split(",") if item.strip()]
    unknown = [servo_id for servo_id in ids if servo_id not in SAFE_SERVO_IDS]
    if unknown:
        raise ValueError(f"Unsupported servo id(s): {unknown}; allowed: {list(SAFE_SERVO_IDS)}")
    return ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read JetArm bus servo positions and do tiny one-joint nudges.")
    parser.add_argument("--servos", default="all", help="Comma-separated servo ids or 'all'. Default: all")
    parser.add_argument("--duration", type=float, default=0.35, help="Seconds per tiny move. Default: 0.35")
    parser.add_argument("--execute", action="store_true", help="Actually publish tiny moves. Default is dry-run.")
    parser.add_argument("--service", default="/ros_robot_controller/bus_servo/get_state")
    parser.add_argument("--topic", default="/ros_robot_controller/bus_servo/set_position")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        servo_ids = parse_servo_ids(args.servos)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    rclpy.init(args=None)
    node = None
    try:
        node = SafeNudge(args.service, args.topic)
        node.nudge(servo_ids, args.duration, args.execute)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
