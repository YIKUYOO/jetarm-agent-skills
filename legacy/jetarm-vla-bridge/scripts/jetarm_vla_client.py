#!/usr/bin/env python3
import base64
import io
import sys
import time
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import message_filters
import numpy as np
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur, RawIdPosDur, ServoStateList
from sensor_msgs.msg import CameraInfo, Image

from jetarm_vla_common.dataset_writer import EpisodeWriter
from jetarm_vla_common.depth import depth_to_vis
from jetarm_vla_common.safety import ActionSafetyConfig, ActionSafetyError, clamp_and_validate_action
from jetarm_vla_common.schema import DatasetFrame, normalize_servo_positions

try:
    import requests
except ImportError:  # pragma: no cover - handled at runtime on Jetson.
    requests = None

try:
    from PIL import Image as PILImage
except ImportError:  # pragma: no cover - handled at runtime on Jetson.
    PILImage = None

SERVO_IDS = [1, 2, 3, 4, 5, 10]


class JetArmVLAClientNode:
    def __init__(self) -> None:
        rospy.init_node("jetarm_vla_client", anonymous=False)
        if requests is None or PILImage is None:
            raise RuntimeError("jetarm_vla_client requires requests and pillow")

        self.server_url = rospy.get_param("~server_url", "http://127.0.0.1:8008/select_action")
        self.instruction = rospy.get_param("~instruction", "pick the red block and place it in the box")
        self.dry_run = bool(rospy.get_param("~dry_run", True))
        self.rate_hz = float(rospy.get_param("~rate_hz", 3.0))
        self.request_timeout_s = float(rospy.get_param("~request_timeout_s", 8.0))
        self.record_rollout = bool(rospy.get_param("~record_rollout", False))
        self.record_rejected = bool(rospy.get_param("~record_rejected", True))
        self.output_dir = Path(rospy.get_param("~output_dir", str(Path.home() / "jetarm_vla_data/rollouts/raw")))
        self.episode_id = rospy.get_param("~episode_id", "")
        if not self.episode_id:
            self.episode_id = time.strftime("ep_vla_rollout_%Y%m%d_%H%M%S")
        self.success = bool(rospy.get_param("~success", False))
        self.failure_reason = rospy.get_param("~failure_reason", "not_labeled")
        self.max_depth_mm = int(rospy.get_param("~max_depth_mm", 4000))
        self.safety = ActionSafetyConfig(
            max_step=float(rospy.get_param("~max_step", 0.12)),
            timeout_s=float(rospy.get_param("~action_timeout_s", 1.0)),
        )
        self.action_duration_ms = int(rospy.get_param("~action_duration_ms", 1000))
        self.previous_action = None
        self.latest_servo_positions = np.asarray([0.5] * 6, dtype=np.float32)
        self.last_request = 0.0
        self.shutting_down = False
        self.action_pub = rospy.Publisher("/controllers/multi_id_pos_dur", MultiRawIdPosDur, queue_size=1)
        self.writer = None
        if self.record_rollout:
            self.writer = EpisodeWriter(
                root=self.output_dir,
                episode_id=self.episode_id,
                language_instruction=self.instruction,
                fps=max(1, int(round(self.rate_hz))),
            )
            rospy.on_shutdown(self._shutdown)

        rospy.Subscriber("/servo_states", ServoStateList, self._servo_states_cb, queue_size=1)
        rgb_sub = message_filters.Subscriber("/rgbd_cam/color/image_raw", Image, queue_size=1)
        depth_sub = message_filters.Subscriber("/rgbd_cam/depth/image_raw", Image, queue_size=1)
        color_info_sub = message_filters.Subscriber("/rgbd_cam/color/camera_info", CameraInfo, queue_size=1)
        depth_info_sub = message_filters.Subscriber("/rgbd_cam/depth/camera_info", CameraInfo, queue_size=1)
        sync = message_filters.ApproximateTimeSynchronizer(
            [rgb_sub, depth_sub, color_info_sub, depth_info_sub],
            3,
            0.03,
        )
        sync.registerCallback(self._frame_cb)
        rospy.loginfo("jetarm_vla_client started dry_run=%s server=%s", self.dry_run, self.server_url)

    def _servo_states_cb(self, msg: ServoStateList) -> None:
        by_id = {state.id: state.position for state in msg.servo_states}
        positions = [by_id.get(servo_id, 500) for servo_id in SERVO_IDS]
        self.latest_servo_positions = np.asarray(normalize_servo_positions(positions), dtype=np.float32)
        if self.previous_action is None:
            self.previous_action = self.latest_servo_positions.copy()

    def _frame_cb(
        self,
        rgb_msg: Image,
        depth_msg: Image,
        color_info: CameraInfo,
        depth_info: CameraInfo,
    ) -> None:
        if self.shutting_down or rospy.is_shutdown():
            return
        now = time.time()
        if now - self.last_request < 1.0 / max(self.rate_hz, 0.01):
            return
        self.last_request = now

        rgb = np.ndarray(shape=(rgb_msg.height, rgb_msg.width, 3), dtype=np.uint8, buffer=rgb_msg.data)
        crop_top = 40 if rgb.shape[0] >= 440 else 0
        crop_bottom = 440 if rgb.shape[0] >= 440 else rgb.shape[0]
        rgb = rgb[crop_top:crop_bottom, :]
        rgb = np.ascontiguousarray(rgb)
        depth = np.ndarray(shape=(depth_msg.height, depth_msg.width), dtype=np.uint16, buffer=depth_msg.data)
        if depth.shape[0] >= crop_bottom:
            depth = depth[crop_top:crop_bottom, : rgb.shape[1]]
        else:
            depth = depth[: rgb.shape[0], : rgb.shape[1]]
        depth = np.ascontiguousarray(depth)
        depth_vis = depth_to_vis(depth, self.max_depth_mm)
        state = np.concatenate([self.latest_servo_positions, np.zeros(7, dtype=np.float32)]).astype(np.float32)
        payload = {
            "language_instruction": self.instruction,
            "observation.images.rgb_front": encode_png(rgb),
            "observation.images.depth_front_vis": encode_png(depth_vis),
            "observation.state": state.tolist(),
            "metadata.camera.depth_info": {
                "width": depth_info.width,
                "height": depth_info.height,
                "K": list(depth_info.K),
            },
        }
        body = {}
        raw_action = None
        latency_ms = None
        request_started = time.time()
        try:
            response = requests.post(self.server_url, json=payload, timeout=self.request_timeout_s)
            response.raise_for_status()
            body = response.json()
            raw_action = body["action"]
            latency_ms = float(body.get("debug", {}).get("latency_ms", (time.time() - request_started) * 1000.0))
            previous_action = self.previous_action
            if previous_action is None:
                previous_action = self.latest_servo_positions
            action = clamp_and_validate_action(
                raw_action,
                previous_action=previous_action,
                action_timestamp=float(body.get("timestamp", now)),
                now=time.time(),
                config=self.safety,
                emergency_stop=bool(rospy.get_param("~emergency_stop", False)),
            )
        except (ActionSafetyError, KeyError, ValueError, requests.RequestException) as exc:
            rospy.logwarn_throttle(2.0, "VLA action rejected: %s", exc)
            if self.record_rollout and self.record_rejected:
                safe_hold = self.previous_action
                if safe_hold is None:
                    safe_hold = self.latest_servo_positions
                self._record_frame(
                    timestamp=rgb_msg.header.stamp.to_sec() if rgb_msg.header.stamp else now,
                    rgb=rgb,
                    depth=depth,
                    depth_vis=depth_vis,
                    state=state,
                    action=np.asarray(safe_hold, dtype=np.float32),
                    color_info=color_info,
                    depth_info=depth_info,
                    raw_action=raw_action,
                    safe_action=np.asarray(safe_hold, dtype=np.float32).tolist(),
                    latency_ms=latency_ms,
                    mode=body.get("mode", ""),
                    message=body.get("message", ""),
                    executed=False,
                    rejected=True,
                    reject_reason=str(exc),
                )
            return

        if self.shutting_down or rospy.is_shutdown():
            return
        if self.dry_run:
            rospy.loginfo_throttle(1.0, "dry-run action=%s", np.round(action, 3).tolist())
        else:
            self.action_pub.publish(action_to_msg(action, duration_ms=self.action_duration_ms))
            rospy.loginfo_throttle(1.0, "published action=%s", np.round(action, 3).tolist())
        if self.record_rollout:
            self._record_frame(
                timestamp=rgb_msg.header.stamp.to_sec() if rgb_msg.header.stamp else now,
                rgb=rgb,
                depth=depth,
                depth_vis=depth_vis,
                state=state,
                action=np.asarray(action, dtype=np.float32),
                color_info=color_info,
                depth_info=depth_info,
                raw_action=raw_action,
                safe_action=action,
                latency_ms=latency_ms,
                mode=body.get("mode", ""),
                message=body.get("message", ""),
                executed=not self.dry_run,
                rejected=False,
                reject_reason="",
            )
        self.previous_action = np.asarray(action, dtype=np.float32)

    def _record_frame(
        self,
        timestamp,
        rgb,
        depth,
        depth_vis,
        state,
        action,
        color_info,
        depth_info,
        raw_action,
        safe_action,
        latency_ms,
        mode,
        message,
        executed,
        rejected,
        reject_reason,
    ):
        if self.writer is None:
            return
        extra_metadata = {
            "metadata.policy.raw_action": _round_list(raw_action),
            "metadata.policy.safe_action": _round_list(safe_action),
            "metadata.policy.latency_ms": None if latency_ms is None else round(float(latency_ms), 3),
            "metadata.policy.mode": mode,
            "metadata.policy.message": message,
            "metadata.safety.executed": bool(executed),
            "metadata.safety.rejected": bool(rejected),
            "metadata.safety.reject_reason": reject_reason,
        }
        frame = DatasetFrame(
            timestamp=timestamp,
            language_instruction=self.instruction,
            rgb=rgb,
            depth_raw_mm=depth,
            depth_vis=depth_vis,
            state=state,
            action=np.asarray(action, dtype=np.float32),
            ee_pose=np.zeros(7, dtype=np.float32),
            color_camera_info=camera_info_to_dict(color_info),
            depth_camera_info=camera_info_to_dict(depth_info),
            extra_metadata=extra_metadata,
        )
        try:
            self.writer.add_frame(frame)
        except Exception as exc:
            rospy.logwarn_throttle(2.0, "failed to record VLA rollout frame: %s", exc)

    def _shutdown(self):
        self.shutting_down = True
        if self.writer is not None:
            self.writer.close(success=self.success, failure_reason=self.failure_reason)
            self.writer = None
            rospy.loginfo("closed rollout episode=%s", self.episode_id)


def encode_png(array: np.ndarray) -> str:
    image = PILImage.fromarray(np.ascontiguousarray(array))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def action_to_msg(action, duration_ms):
    msg = MultiRawIdPosDur()
    msg.id_pos_dur_list = [
        RawIdPosDur(id=servo_id, position=int(round(value * 1000.0)), duration=duration_ms)
        for servo_id, value in zip(SERVO_IDS, action)
    ]
    return msg


def camera_info_to_dict(msg):
    return {
        "width": msg.width,
        "height": msg.height,
        "distortion_model": msg.distortion_model,
        "D": list(msg.D),
        "K": list(msg.K),
        "R": list(msg.R),
        "P": list(msg.P),
    }


def _round_list(values):
    if values is None:
        return None
    return np.asarray(values, dtype=np.float32).round(6).tolist()


if __name__ == "__main__":
    JetArmVLAClientNode()
    rospy.spin()
