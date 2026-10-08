from __future__ import annotations

import time
from typing import Callable

import rclpy
from interfaces.srv import SetString
from rclpy.node import Node
from servo_controller_msgs.msg import ServosPosition
from std_srvs.srv import Trigger

from .presets import action_to_lines, get_action, iter_messages, list_action_names


class PresetServer(Node):
    def __init__(self) -> None:
        super().__init__("jetarm_preset_server")
        self.declare_parameter("topic", "/servo_controller")
        self.declare_parameter("dry_run", True)
        self.topic = str(self.get_parameter("topic").value)
        self.publisher = self.create_publisher(ServosPosition, self.topic, 1)

        self.create_service(SetString, "~/run", self.run_named_action)
        for action_name in ("go_home", "goto_home", "observe_sorting", "place_center", "open_gripper", "close_gripper"):
            self.create_service(Trigger, f"~/{action_name}", self.make_trigger_callback(action_name))

        known = ", ".join(list_action_names())
        self.get_logger().info(f"JetArm preset server ready on {self.topic}; known presets: {known}")
        self.get_logger().info("dry_run parameter defaults to true; set dry_run:=false before hardware execution")

    def dry_run_enabled(self) -> bool:
        return bool(self.get_parameter("dry_run").value)

    def wait_for_subscriber(self, timeout_sec: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self.publisher.get_subscription_count() > 0:
                return True
            rclpy.spin_once(self, timeout_sec=0.1)
        return self.publisher.get_subscription_count() > 0

    def make_trigger_callback(self, action_name: str) -> Callable[[Trigger.Request, Trigger.Response], Trigger.Response]:
        def callback(_request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
            ok, message = self.execute_preset(action_name)
            response.success = ok
            response.message = message
            return response

        return callback

    def run_named_action(self, request: SetString.Request, response: SetString.Response) -> SetString.Response:
        ok, message = self.execute_preset(request.data)
        response.success = ok
        response.message = message
        return response

    def execute_preset(self, requested_name: str) -> tuple[bool, str]:
        try:
            action = get_action(requested_name)
        except ValueError as exc:
            self.get_logger().error(str(exc))
            return False, str(exc)

        for line in action_to_lines(action):
            self.get_logger().info(line)

        if self.dry_run_enabled():
            message = f"dry-run only; preset {action.name} was not published"
            self.get_logger().warn(message)
            return True, message

        if not self.wait_for_subscriber():
            message = f"no subscriber on {self.topic}; servo_controller is not receiving presets"
            self.get_logger().error(message)
            return False, message

        for step, msg in iter_messages(action):
            self.publisher.publish(msg)
            time.sleep(step.duration + 0.05)
        return True, f"published preset {action.name}"


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = PresetServer()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
