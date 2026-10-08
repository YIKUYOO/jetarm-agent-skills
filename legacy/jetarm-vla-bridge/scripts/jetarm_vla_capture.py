#!/usr/bin/env python3
import sys
import threading
import time
import queue
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import message_filters
import numpy as np
import rospy
from geometry_msgs.msg import Pose
from hiwonder_interfaces.msg import MultiRawIdPosDur, ServoStateList
from hiwonder_interfaces.srv import GetRobotPose
from sensor_msgs.msg import CameraInfo, Image, JointState

from jetarm_vla_common.dataset_writer import EpisodeWriter
from jetarm_vla_common.depth import depth_to_vis
from jetarm_vla_common.images import crop_rgb_depth_front
from jetarm_vla_common.schema import DatasetFrame, normalize_servo_positions

SERVO_IDS = [1, 2, 3, 4, 5, 10]


class JetArmVLACaptureNode:
    def __init__(self) -> None:
        rospy.init_node("jetarm_vla_capture", anonymous=False)
        self.output_dir = Path(rospy.get_param("~output_dir", str(Path.home() / "jetarm_vla_data/raw")))
        self.episode_id = rospy.get_param("~episode_id", time.strftime("ep_%Y%m%d_%H%M%S"))
        self.instruction = rospy.get_param("~instruction", "pick the red block and place it in the box")
        self.fps = int(rospy.get_param("~fps", 10))
        self.duration_s = float(rospy.get_param("~duration_s", 30.0))
        self.success = bool(rospy.get_param("~success", False))
        self.failure_reason = rospy.get_param("~failure_reason", "not_labeled")
        self.max_depth_mm = int(rospy.get_param("~max_depth_mm", 4000))
        self.query_ee_pose = bool(rospy.get_param("~query_ee_pose", False))
        self.capture_source = rospy.get_param("~capture_source", "manual")
        self.png_compress_level = int(rospy.get_param("~png_compress_level", 1))

        self.latest_servo_positions = np.zeros(6, dtype=np.float32)
        self.latest_action = np.zeros(6, dtype=np.float32)
        self.latest_ee_pose = np.zeros(7, dtype=np.float32)
        self.latest_joint_names = []
        self.latest_joint_positions = []
        self.last_frame_time = 0.0
        self.recording = True
        self.frame_lock = threading.Lock()
        self.stop_writer = False
        self.frame_queue = queue.Queue(maxsize=int(rospy.get_param("~writer_queue_size", 20)))

        rospy.Subscriber("/servo_states", ServoStateList, self._servo_states_cb, queue_size=1)
        rospy.Subscriber("/joint_states", JointState, self._joint_states_cb, queue_size=1)
        rospy.Subscriber("/controllers/multi_id_pos_dur", MultiRawIdPosDur, self._action_cb, queue_size=10)
        self.get_current_pose = rospy.ServiceProxy("/kinematics/get_current_pose", GetRobotPose)
        self.pose_timer = None
        if self.query_ee_pose:
            self.pose_timer = rospy.Timer(rospy.Duration(0.5), self._pose_timer_cb)

        rgb_sub = message_filters.Subscriber("/rgbd_cam/color/image_raw", Image, queue_size=1)
        depth_sub = message_filters.Subscriber("/rgbd_cam/depth/image_raw", Image, queue_size=1)
        color_info_sub = message_filters.Subscriber("/rgbd_cam/color/camera_info", CameraInfo, queue_size=1)
        depth_info_sub = message_filters.Subscriber("/rgbd_cam/depth/camera_info", CameraInfo, queue_size=1)
        sync = message_filters.ApproximateTimeSynchronizer(
            [rgb_sub, depth_sub, color_info_sub, depth_info_sub],
            queue_size=3,
            slop=0.03,
        )
        sync.registerCallback(self._frame_cb)

        self.writer = EpisodeWriter(
            root=self.output_dir,
            episode_id=self.episode_id,
            language_instruction=self.instruction,
            fps=self.fps,
            png_compress_level=self.png_compress_level,
        )
        self.writer_thread = threading.Thread(target=self._writer_loop)
        self.writer_thread.daemon = True
        self.writer_thread.start()
        self.start_time = time.time()
        self.duration_timer = None
        if self.duration_s > 0:
            self.duration_timer = threading.Timer(self.duration_s, self._duration_timer_cb)
            self.duration_timer.daemon = True
            self.duration_timer.start()
        rospy.on_shutdown(self._shutdown)
        rospy.loginfo("jetarm_vla_capture started episode=%s output=%s", self.episode_id, self.output_dir)

    def _servo_states_cb(self, msg: ServoStateList) -> None:
        by_id = {state.id: state.position for state in msg.servo_states}
        positions = [by_id.get(servo_id, 0) for servo_id in SERVO_IDS]
        self.latest_servo_positions = np.asarray(normalize_servo_positions(positions), dtype=np.float32)
        if not self.latest_action.any():
            self.latest_action = self.latest_servo_positions.copy()

    def _joint_states_cb(self, msg: JointState) -> None:
        self.latest_joint_names = list(msg.name)
        self.latest_joint_positions = list(msg.position)

    def _action_cb(self, msg: MultiRawIdPosDur) -> None:
        action = self.latest_action.copy()
        index_by_id = {servo_id: idx for idx, servo_id in enumerate(SERVO_IDS)}
        for item in msg.id_pos_dur_list:
            if item.id in index_by_id:
                action[index_by_id[item.id]] = normalize_servo_positions([item.position])[0]
        self.latest_action = action.astype(np.float32)

    def _pose_timer_cb(self, _event):
        self.latest_ee_pose = pose_to_vector(self._get_pose_safe())

    def _frame_cb(
        self,
        rgb_msg: Image,
        depth_msg: Image,
        color_info: CameraInfo,
        depth_info: CameraInfo,
    ) -> None:
        if not self.recording or rospy.is_shutdown():
            return
        now = time.time()
        with self.frame_lock:
            if now - self.last_frame_time < 1.0 / max(self.fps, 1):
                return
            self.last_frame_time = now

        rgb = ros_rgb_to_numpy(rgb_msg)
        depth = ros_depth_to_numpy(depth_msg)
        rgb, depth = crop_rgb_depth_front(rgb, depth)
        depth_vis = depth_to_vis(depth, max_depth_mm=self.max_depth_mm)
        ee_pose = self.latest_ee_pose.copy()
        state = np.concatenate([self.latest_servo_positions, ee_pose[:7]]).astype(np.float32)
        frame = DatasetFrame(
            timestamp=rgb_msg.header.stamp.to_sec() if rgb_msg.header.stamp else now,
            language_instruction=self.instruction,
            rgb=rgb,
            depth_raw_mm=depth,
            depth_vis=depth_vis,
            state=state,
            action=self.latest_action.astype(np.float32),
            ee_pose=ee_pose,
            color_camera_info=camera_info_to_dict(color_info),
            depth_camera_info=camera_info_to_dict(depth_info),
            extra_metadata={
                "metadata.capture.source": self.capture_source,
                "metadata.capture.latest_joint_names": list(self.latest_joint_names),
                "metadata.capture.latest_joint_positions": list(self.latest_joint_positions),
            },
        )
        try:
            self.frame_queue.put_nowait(frame)
        except queue.Full:
            try:
                self.frame_queue.get_nowait()
                self.frame_queue.task_done()
            except queue.Empty:
                pass
            self.frame_queue.put_nowait(frame)
            rospy.logwarn_throttle(2.0, "frame queue full; dropped oldest frame")

        if self.duration_s > 0 and now - self.start_time >= self.duration_s:
            self._request_shutdown("requested episode duration reached")

    def _duration_timer_cb(self):
        self._request_shutdown("requested episode duration reached")

    def _request_shutdown(self, reason):
        if self.recording:
            self.recording = False
            rospy.signal_shutdown(reason)

    def _get_pose_safe(self) -> Pose:
        try:
            return self.get_current_pose().pose
        except Exception as exc:  # ROS services may be temporarily unavailable during startup.
            rospy.logwarn_throttle(5.0, "failed to query /kinematics/get_current_pose: %s", exc)
            return Pose()

    def _shutdown(self) -> None:
        self.recording = False
        if self.duration_timer is not None:
            self.duration_timer.cancel()
        self.stop_writer = True
        if hasattr(self, "writer_thread"):
            self.frame_queue.join()
            self.writer_thread.join()
        self.writer.close(success=self.success, failure_reason=self.failure_reason)
        rospy.loginfo("jetarm_vla_capture closed episode=%s", self.episode_id)

    def _writer_loop(self):
        while not self.stop_writer or not self.frame_queue.empty():
            try:
                frame = self.frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self.writer.add_frame(frame)
            except Exception as exc:
                rospy.logerr("failed to write JetArm VLA frame: %s", exc)
            finally:
                self.frame_queue.task_done()


def ros_rgb_to_numpy(msg: Image) -> np.ndarray:
    array = np.ndarray(shape=(msg.height, msg.width, 3), dtype=np.uint8, buffer=msg.data)
    return np.ascontiguousarray(array)


def ros_depth_to_numpy(msg: Image) -> np.ndarray:
    array = np.ndarray(shape=(msg.height, msg.width), dtype=np.uint16, buffer=msg.data)
    return np.ascontiguousarray(array)


def pose_to_vector(pose: Pose) -> np.ndarray:
    return np.asarray(
        [
            pose.position.x,
            pose.position.y,
            pose.position.z,
            pose.orientation.x,
            pose.orientation.y,
            pose.orientation.z,
            pose.orientation.w,
        ],
        dtype=np.float32,
    )


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


if __name__ == "__main__":
    JetArmVLACaptureNode()
    rospy.spin()
