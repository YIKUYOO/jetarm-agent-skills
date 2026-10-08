#!/usr/bin/env python3
"""Capture one RGB frame from the verified JetArm RGB topic."""

import argparse
import json
from pathlib import Path
import time

import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image


class OneShotRgbCapture(Node):
    def __init__(self, topic: str, camera_info_topic: str, output: Path, timeout_s: float):
        super().__init__("jetarm_capture_rgb_once")
        self.topic = topic
        self.camera_info_topic = camera_info_topic
        self.output = output
        self.timeout_s = timeout_s
        self.bridge = CvBridge()
        self.image_saved = False
        self.camera_info = None
        self.create_subscription(Image, topic, self._on_image, 10)
        self.create_subscription(CameraInfo, camera_info_topic, self._on_camera_info, 10)
        self.deadline = self.get_clock().now().nanoseconds / 1e9 + timeout_s
        self.timer = self.create_timer(0.1, self._on_timer)

    def _on_camera_info(self, msg: CameraInfo) -> None:
        if self.camera_info is None:
            self.camera_info = {
                "frame_id": msg.header.frame_id,
                "width": msg.width,
                "height": msg.height,
                "k": list(msg.k),
                "d": list(msg.d),
                "distortion_model": msg.distortion_model,
            }

    def _on_image(self, msg: Image) -> None:
        if self.image_saved:
            return
        image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        self.output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(self.output), image):
            raise RuntimeError(f"failed to write {self.output}")
        metadata = {
            "topic": self.topic,
            "encoding": msg.encoding,
            "width": msg.width,
            "height": msg.height,
            "stamp": {"sec": msg.header.stamp.sec, "nanosec": msg.header.stamp.nanosec},
            "camera_info": self.camera_info,
        }
        self.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        self.image_saved = True
        self.get_logger().info(f"saved {self.output}")

    def _on_timer(self) -> None:
        now = self.get_clock().now().nanoseconds / 1e9
        if now > self.deadline and not self.image_saved:
            self.get_logger().error(f"timeout waiting for {self.topic}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="/depth_cam/rgb/image_raw")
    parser.add_argument("--camera-info-topic", default="/depth_cam/rgb/camera_info")
    parser.add_argument("--output", default="/tmp/jetarm_rgb_once.png")
    parser.add_argument("--timeout-s", type=float, default=10.0)
    args = parser.parse_args()

    rclpy.init()
    node = OneShotRgbCapture(
        topic=args.topic,
        camera_info_topic=args.camera_info_topic,
        output=Path(args.output),
        timeout_s=args.timeout_s,
    )
    start = time.monotonic()
    try:
        while rclpy.ok() and not node.image_saved and time.monotonic() - start <= args.timeout_s:
            rclpy.spin_once(node, timeout_sec=0.1)
        return 0 if node.image_saved else 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
