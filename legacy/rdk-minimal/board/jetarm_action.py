#!/usr/bin/env python3
import argparse
import json
import os
import time

ALLOWED_SERVO_IDS = {1, 2, 3, 4, 5, 10}
DEFAULT_HOME_POSITIONS = {1: 500, 2: 500, 3: 500, 4: 500, 5: 500, 10: 700}
PULSE_MIN = 0
PULSE_MAX = 1000
DEFAULT_MAX_STEP = 30
DEFAULT_MAX_DURATION = 2.0


def _servo_id(value):
    return int(value)


def _number(value):
    return float(value)


def validate_action(payload, current_positions, max_step=DEFAULT_MAX_STEP, max_duration=DEFAULT_MAX_DURATION):
    action_type = payload.get("action_type")
    if action_type == "stop":
        return {"ok": True, "command": {"action_type": "stop"}}
    if action_type not in ("servo_pulse", "servo_delta"):
        return {"ok": False, "error_code": "UNSUPPORTED_ACTION_TYPE", "message": str(action_type)}

    try:
        duration = _number(payload.get("duration_s", 0.5))
    except (TypeError, ValueError) as exc:
        return {"ok": False, "error_code": "BAD_DURATION", "message": str(exc)}
    if duration <= 0 or duration > max_duration:
        return {"ok": False, "error_code": "BAD_DURATION", "message": str(duration)}

    values = payload.get("values")
    if not isinstance(values, dict) or not values:
        return {"ok": False, "error_code": "BAD_VALUES", "message": "values must be a non-empty object"}

    positions = {}
    for raw_id, raw_value in values.items():
        try:
            servo_id = _servo_id(raw_id)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error_code": "BAD_SERVO_ID", "message": str(exc)}
        if servo_id not in ALLOWED_SERVO_IDS:
            return {"ok": False, "error_code": "UNSUPPORTED_SERVO_ID", "message": str(servo_id)}
        try:
            value = _number(raw_value)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error_code": "BAD_SERVO_VALUE", "message": str(exc)}
        current = int(current_positions.get(servo_id, DEFAULT_HOME_POSITIONS[servo_id]))
        target = int(round(value if action_type == "servo_pulse" else current + value))
        if target < PULSE_MIN or target > PULSE_MAX:
            return {"ok": False, "error_code": "PULSE_OUT_OF_RANGE", "message": str(target)}
        if abs(target - current) > max_step:
            return {"ok": False, "error_code": "STEP_TOO_LARGE", "message": f"{servo_id}:{current}->{target}"}
        positions[servo_id] = target

    return {
        "ok": True,
        "command": {
            "action_type": action_type,
            "topic": "/servo_controller",
            "duration_s": duration,
            "position_unit": "pulse",
            "positions": positions,
        },
    }


def _read_current_positions(timeout_s):
    import rclpy
    from rclpy.node import Node
    from servo_controller_msgs.msg import ServoStateList

    class Reader(Node):
        def __init__(self):
            super().__init__("jetarm_action_state_reader")
            self.positions = {}
            self.create_subscription(ServoStateList, "/controller_manager/servo_states", self._on_state, 10)

        def _on_state(self, msg):
            for item in msg.servo_state:
                self.positions[int(item.id)] = int(item.position)

    rclpy.init()
    node = Reader()
    deadline = time.time() + timeout_s
    try:
        while time.time() < deadline and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
            if ALLOWED_SERVO_IDS.issubset(set(node.positions)):
                return dict(node.positions)
        return dict(node.positions)
    finally:
        node.destroy_node()
        rclpy.shutdown()


def _publish_command(command):
    import rclpy
    from rclpy.node import Node
    from servo_controller_msgs.msg import ServoPosition, ServosPosition

    class Publisher(Node):
        def __init__(self):
            super().__init__("jetarm_action_publisher")
            self.pub = self.create_publisher(ServosPosition, "/servo_controller", 1)

    rclpy.init()
    node = Publisher()
    try:
        msg = ServosPosition()
        msg.duration = float(command["duration_s"])
        msg.position_unit = command["position_unit"]
        for servo_id, position in sorted(command["positions"].items()):
            item = ServoPosition()
            item.id = int(servo_id)
            item.position = float(position)
            msg.position.append(item)
        for _ in range(3):
            node.pub.publish(msg)
            rclpy.spin_once(node, timeout_sec=0.05)
            time.sleep(0.05)
    finally:
        node.destroy_node()
        rclpy.shutdown()


def load_action_payload(action_json, action_json_file):
    if action_json and action_json_file:
        raise ValueError("use only one of --action-json or --action-json-file")
    if action_json_file:
        with open(action_json_file, "r", encoding="utf-8") as handle:
            return json.load(handle)
    if action_json:
        return json.loads(action_json)
    raise ValueError("one of --action-json or --action-json-file is required")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action-json")
    parser.add_argument("--action-json-file")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--state-timeout", type=float, default=5.0)
    parser.add_argument("--max-step", type=float, default=DEFAULT_MAX_STEP)
    args = parser.parse_args()

    try:
        payload = load_action_payload(args.action_json, args.action_json_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error_code": "BAD_ACTION_JSON", "message": str(exc)}, ensure_ascii=False))
        return 2

    current = _read_current_positions(args.state_timeout) if args.execute else {}
    result = validate_action(payload, current_positions=current, max_step=args.max_step)
    result["execute"] = bool(args.execute)
    result["dev_rrc_present"] = os.path.exists("/dev/rrc")

    if args.execute and result["ok"] and not result["dev_rrc_present"]:
        result = {"ok": False, "execute": True, "error_code": "RRC_MISSING", "dev_rrc_present": False}
    if args.execute and result["ok"] and result["command"]["action_type"] != "stop":
        _publish_command(result["command"])
        result["published"] = True

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
