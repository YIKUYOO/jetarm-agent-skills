import cv2
import numpy as np
import rospy
from sensor_msgs.msg import Image as RosImage
import traceback


SOURCE_TOPIC = "/rgbd_cam/depth/image_raw"
TARGET_TOPIC = "/jetarm_demo/depth_viz/image_raw"


def _colorize_depth(msg: RosImage) -> np.ndarray:
    if msg.encoding == "32FC1":
        depth = np.frombuffer(msg.data, dtype=np.float32).reshape(msg.height, msg.width).copy()
    else:
        depth = np.frombuffer(msg.data, dtype=np.uint16).reshape(msg.height, msg.width).astype(np.float32)

    valid = np.isfinite(depth) & (depth > 0)
    if np.any(valid):
        values = depth[valid]
        low = np.percentile(values, 5)
        high = np.percentile(values, 95)
        if high <= low:
            high = low + 1.0
        clipped = np.clip(depth, low, high)
        normalized = ((clipped - low) / (high - low) * 255.0).astype(np.uint8)
    else:
        normalized = np.zeros((msg.height, msg.width), dtype=np.uint8)
    return cv2.applyColorMap(normalized, cv2.COLORMAP_JET)


def main() -> None:
    rospy.init_node("jetarm_demo_depth_viz_bridge", anonymous=False, disable_signals=True, log_level=rospy.ERROR)
    publisher = rospy.Publisher(TARGET_TOPIC, RosImage, queue_size=1)
    rospy.sleep(1.0)

    while not rospy.is_shutdown():
        try:
            msg = rospy.wait_for_message(SOURCE_TOPIC, RosImage, timeout=2.0)
        except rospy.ROSException:
            continue

        try:
            image = _colorize_depth(msg)
            out = RosImage()
            out.header = msg.header
            out.height = msg.height
            out.width = msg.width
            out.encoding = "bgr8"
            out.is_bigendian = 0
            out.step = msg.width * 3
            out.data = image.tostring()
            publisher.publish(out)
        except Exception:
            rospy.logerr_throttle(2.0, traceback.format_exc())


if __name__ == "__main__":
    main()
