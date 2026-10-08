#!/usr/bin/env python3
"""Capture a minimal JetArm observation bundle for later VLA/Codex tooling."""

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
from cv_bridge import CvBridge
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image, JointState
from servo_controller_msgs.msg import ServoStateList


class ObservationCapture(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("jetarm_capture_observation")
        self.args = args
        self.bridge = CvBridge()
        self.rgb: Optional[np.ndarray] = None
        self.depth: Optional[np.ndarray] = None
        self.rgb_info: Optional[Dict[str, Any]] = None
        self.depth_info: Optional[Dict[str, Any]] = None
        self.joint_state: Optional[Dict[str, Any]] = None
        self.servo_state: Optional[Dict[str, Any]] = None
        self.rgb_meta: Optional[Dict[str, Any]] = None
        self.depth_meta: Optional[Dict[str, Any]] = None

        self.create_subscription(Image, args.rgb_topic, self._on_rgb, 10)
        self.create_subscription(CameraInfo, args.rgb_info_topic, self._on_rgb_info, 10)
        self.create_subscription(Image, args.depth_topic, self._on_depth, 10)
        self.create_subscription(CameraInfo, args.depth_info_topic, self._on_depth_info, 10)
        self.create_subscription(JointState, args.joint_state_topic, self._on_joint_state, 10)
        self.create_subscription(ServoStateList, args.servo_state_topic, self._on_servo_state, 10)

    def _stamp(self, msg: Any) -> Dict[str, int]:
        return {"sec": int(msg.header.stamp.sec), "nanosec": int(msg.header.stamp.nanosec)}

    def _on_rgb(self, msg: Image) -> None:
        if self.rgb is None:
            self.rgb = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            self.rgb_meta = {
                "topic": self.args.rgb_topic,
                "encoding": msg.encoding,
                "height": msg.height,
                "width": msg.width,
                "stamp": self._stamp(msg),
            }

    def _on_depth(self, msg: Image) -> None:
        if self.depth is None:
            self.depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
            self.depth_meta = {
                "topic": self.args.depth_topic,
                "encoding": msg.encoding,
                "height": msg.height,
                "width": msg.width,
                "stamp": self._stamp(msg),
            }

    def _camera_info_payload(self, msg: CameraInfo, topic: str) -> Dict[str, Any]:
        return {
            "topic": topic,
            "frame_id": msg.header.frame_id,
            "width": msg.width,
            "height": msg.height,
            "k": list(msg.k),
            "d": list(msg.d),
            "distortion_model": msg.distortion_model,
            "stamp": self._stamp(msg),
        }

    def _on_rgb_info(self, msg: CameraInfo) -> None:
        if self.rgb_info is None:
            self.rgb_info = self._camera_info_payload(msg, self.args.rgb_info_topic)

    def _on_depth_info(self, msg: CameraInfo) -> None:
        if self.depth_info is None:
            self.depth_info = self._camera_info_payload(msg, self.args.depth_info_topic)

    def _on_joint_state(self, msg: JointState) -> None:
        if self.joint_state is None:
            self.joint_state = {
                "topic": self.args.joint_state_topic,
                "name": list(msg.name),
                "position": list(msg.position),
                "velocity": list(msg.velocity),
                "effort": list(msg.effort),
                "stamp": self._stamp(msg),
            }

    def _on_servo_state(self, msg: ServoStateList) -> None:
        if self.servo_state is None:
            self.servo_state = {
                "topic": self.args.servo_state_topic,
                "stamp": self._stamp(msg),
                "servo_state": [
                    {
                        "id": int(item.id),
                        "goal": int(item.goal),
                        "position": int(item.position),
                        "error": int(item.error),
                        "voltage": int(item.voltage),
                    }
                    for item in msg.servo_state
                ],
            }

    def complete(self) -> bool:
        if self.rgb is None or self.rgb_info is None:
            return False
        if self.args.require_depth and self.depth is None:
            return False
        if self.args.require_state and (self.joint_state is None or self.servo_state is None):
            return False
        return True

    def save(self) -> Dict[str, Any]:
        output_dir = Path(self.args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        rgb_path = output_dir / "rgb.png"
        cv2.imwrite(str(rgb_path), self.rgb)
        depth_path = None
        if self.depth is not None:
            depth_path = output_dir / "depth_raw.png"
            cv2.imwrite(str(depth_path), self.depth)

        payload: Dict[str, Any] = {
            "created_unix_s": time.time(),
            "instruction": self.args.instruction,
            "rgb": {"path": rgb_path.name, "meta": self.rgb_meta},
            "depth": {"path": depth_path.name if depth_path else None, "meta": self.depth_meta},
            "camera_info": {"rgb": self.rgb_info, "depth": self.depth_info},
            "state": {"joint_state": self.joint_state, "servo_state": self.servo_state},
            "missing": {
                "depth": self.depth is None,
                "rgb_info": self.rgb_info is None,
                "depth_info": self.depth_info is None,
                "joint_state": self.joint_state is None,
                "servo_state": self.servo_state is None,
            },
        }
        (output_dir / "observation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--instruction", default="")
    parser.add_argument("--timeout-s", type=float, default=10.0)
    parser.add_argument("--rgb-topic", default="/depth_cam/rgb/image_raw")
    parser.add_argument("--rgb-info-topic", default="/depth_cam/rgb/camera_info")
    parser.add_argument("--depth-topic", default="/depth_cam/depth/image_raw")
    parser.add_argument("--depth-info-topic", default="/depth_cam/depth/camera_info")
    parser.add_argument("--joint-state-topic", default="/controller_manager/joint_states")
    parser.add_argument("--servo-state-topic", default="/controller_manager/servo_states")
    parser.add_argument("--require-depth", action="store_true")
    parser.add_argument("--require-state", action="store_true")
    args = parser.parse_args()

    rclpy.init()
    node = ObservationCapture(args)
    start = time.monotonic()
    try:
        while rclpy.ok() and not node.complete() and time.monotonic() - start <= args.timeout_s:
            rclpy.spin_once(node, timeout_sec=0.1)
        if not node.complete():
            if node.rgb is None or node.rgb_info is None:
                print(json.dumps({"status": "failed", "reason": "missing required rgb or rgb camera_info"}, indent=2))
                return 1
            if args.require_depth and node.depth is None:
                print(json.dumps({"status": "failed", "reason": "missing required depth"}, indent=2))
                return 1
            if args.require_state and (node.joint_state is None or node.servo_state is None):
                print(json.dumps({"status": "failed", "reason": "missing required state"}, indent=2))
                return 1
        payload = node.save()
        print(json.dumps({"status": "saved", "output_dir": args.output_dir, "missing": payload["missing"]}, indent=2))
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
