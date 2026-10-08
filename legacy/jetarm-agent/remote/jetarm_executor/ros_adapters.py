import base64
import json
import subprocess
import time
from typing import List, Optional


SETUP = "source /opt/ros/melodic/setup.bash && source ~/jetarm/devel/setup.bash"
COLOR_DETECTION_NODE = "jetarm_demo_color_detection"
OBJECT_TRACKING_IMAGE_TOPIC = "/rgbd_cam/color/image_rect_color"
APP_SCRIPTS_DIR = "~/jetarm/src/jetarm_6dof/jetarm_6dof_app/scripts"
FUNCTION_SCRIPTS_DIR = "~/jetarm/src/jetarm_6dof/jetarm_6dof_functions/scripts"
SIMPLE_LIBRARY_DIR = "~/jetarm/src/jetarm_example/src/Simple_library"
POSITIONING_CLAMP_DIR = "~/jetarm/src/jetarm_example/src/9.position_clamp"
RGB_CAMERA_TOPIC = "/rgbd_cam/color/image_rect_color"
DEPTH_CAMERA_TOPIC = "/rgbd_cam/depth/image_raw"
RGB_CAMERA_INFO_TOPIC = "/rgbd_cam/color/camera_info"
LATERAL_PICK_X_BACKOFF = 0.055
CAMERA_LAUNCH_CMD = (
    "nohup bash -lc 'source /opt/ros/melodic/setup.bash && "
    "source ~/jetarm/devel/setup.bash && export CAMERA_TYPE=GEMINI && "
    "roslaunch jetarm_peripherals camera.launch' "
    ">/tmp/jetarm_camera_relaunch.log 2>&1 &"
)


def run_ros_shell(command: str, timeout: int = 20) -> str:
    completed = subprocess.run(
        ["bash", "-lc", "{} && {}".format(SETUP, command)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=timeout,
    )
    return completed.stdout.strip()


def run_ros_python(script: str, timeout: int = 20) -> str:
    command = "{} && python3 - <<'PY'\n{}\nPY".format(SETUP, script)
    completed = subprocess.run(
        ["bash", "-lc", command],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=timeout,
    )
    return completed.stdout.strip()


def _wait_for_camera_topic(topic: str, timeout: float = 3.0) -> None:
    run_ros_python(
        """
import rospy
from sensor_msgs.msg import Image as RosImage

rospy.init_node('jetarm_demo_wait_camera_topic', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
rospy.wait_for_message({topic!r}, RosImage, timeout={timeout})
print('ok')
        """.format(topic=topic, timeout=timeout).strip(),
        timeout=max(10, int(timeout) + 6),
    )


def _recover_camera_stack() -> None:
    run_ros_shell("rosnode kill /rgbd_cam/camera /rgbd_cam/color/image_proc >/dev/null 2>&1 || true", timeout=20)
    run_ros_shell("pkill -f astra_camera_node || true", timeout=20)
    run_ros_shell("pkill -f 'roslaunch jetarm_peripherals camera.launch' || true", timeout=20)
    time.sleep(3.0)
    run_ros_shell(CAMERA_LAUNCH_CMD, timeout=20)
    time.sleep(8.0)


def ensure_camera_topic_ready(topic: str) -> dict:
    try:
        _wait_for_camera_topic(topic, timeout=3.0)
        return {"recovered": False}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        _recover_camera_stack()
        _wait_for_camera_topic(topic, timeout=5.0)
        return {"recovered": True}


def check_ros_nodes() -> dict:
    output = run_ros_shell("rosnode list", timeout=20)
    nodes = set(line.strip() for line in output.splitlines() if line.strip())
    return {
        "tracking_node": "/object_tracking" in nodes,
        "sorting_node": "/object_sortting" in nodes,
        "grasp_node": "/grasp" in nodes,
        "kinematics_node": "/kinematics" in nodes,
        "color_detection_node": "/{}".format(COLOR_DETECTION_NODE) in nodes,
    }


def ensure_color_detection_node() -> None:
    output = run_ros_shell("rosnode list", timeout=20)
    if "/{}".format(COLOR_DETECTION_NODE) in output.splitlines():
        return

    launch_cmd = (
        "nohup roslaunch color_detection color_detection_node.launch "
        "node_name:={} source_image_topic:=/rgbd_cam/color/image_rect_color "
        "enable_display:=false debug:=false >/tmp/{}_launch.log 2>&1 &"
    ).format(COLOR_DETECTION_NODE, COLOR_DETECTION_NODE)
    run_ros_shell(launch_cmd, timeout=20)
    time.sleep(3.0)


def detect_color(target_color: str) -> dict:
    frames_sampled = 0
    detected = False
    observation_available = True
    summary = "object_tracking color detection checked for {}".format(target_color)
    try:
        ros_nodes = check_ros_nodes()
        if not ros_nodes.get("tracking_node", False):
            raise RuntimeError("object_tracking node is offline")
        try:
            output = run_ros_python(
                """
import json
import os
import sys
import rospy
import numpy as np
from sensor_msgs.msg import Image as RosImage

sys.path.insert(0, os.path.expanduser("{app_scripts_dir}"))
from color_tracker import ColorTracker

TARGET_COLOR = {target_color!r}
SOURCE_IMAGE_TOPIC = {source_image_topic!r}

rospy.init_node('jetarm_demo_detect_color', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
tracker = ColorTracker(TARGET_COLOR)
color_ranges = rospy.get_param('/config/lab', {{}})
frames_sampled = 0
detected = False
deadline = rospy.Time.now() + rospy.Duration(6.0)

while rospy.Time.now() < deadline and not rospy.is_shutdown():
    try:
        msg = rospy.wait_for_message(SOURCE_IMAGE_TOPIC, RosImage, timeout=1.0)
        rgb_image = np.ndarray(shape=(msg.height, msg.width, 3), dtype=np.uint8, buffer=msg.data)
        result_image = np.copy(rgb_image)
        _, tracking_pose = tracker.proc(rgb_image, result_image, color_ranges)
        frames_sampled += 1
        if tracking_pose is not None:
            detected = True
            break
    except rospy.ROSException:
        pass

print(json.dumps({{
    'detected': detected,
    'frames_sampled': frames_sampled,
}}))
                """.format(
                    app_scripts_dir=APP_SCRIPTS_DIR,
                    target_color=target_color,
                    source_image_topic=OBJECT_TRACKING_IMAGE_TOPIC,
                ).strip(),
                timeout=10,
            )
            payload = json.loads(output)
            detected = bool(payload.get("detected", False))
            frames_sampled = int(payload.get("frames_sampled", 0))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
            raise
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
        observation_available = False
        summary = "object_tracking color detection unavailable for {}".format(target_color)
    except RuntimeError:
        observation_available = False
        summary = "object_tracking color detection unavailable for {}".format(target_color)

    return {
        "summary": summary,
        "detected": detected,
        "observation_available": observation_available,
        "frames_sampled": frames_sampled,
        "target_color": target_color,
        "motion_executed": False,
    }


def go_home() -> dict:
    script = """
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur
from jetarm_sdk import bus_servo_control

rospy.init_node('jetarm_demo_go_home', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
bus_servo_control.set_servos(pub, 800, ((1, 500), (2, 560), (3, 130), (4, 115), (5, 500), (10, 200)))
rospy.sleep(1.0)
print('ok')
""".strip()
    output = run_ros_python(script, timeout=20)
    return {
        "summary": "go_home command sent",
        "motion_executed": True,
        "output": output,
    }


def pick_and_place_color(target_color: str, destination: str, mode: str, single_block_demo_mode: bool) -> dict:
    if mode != "live":
        return {
            "summary": "dry-run only, live pick-and-place not executed",
            "motion_executed": False,
            "target_color": target_color,
            "destination": destination,
        }

    if not single_block_demo_mode:
        return {
            "summary": "live motion blocked because single_block_demo_mode is false",
            "motion_executed": False,
            "target_color": target_color,
            "destination": destination,
        }

    cycle_completed = False
    run_ros_shell("rosservice call /object_sortting/enter", timeout=30)
    run_ros_shell('rosservice call /object_sortting/set_color_target "{{data_str: {}, data_bool: true}}"'.format(target_color), timeout=20)
    run_ros_shell('rosservice call /object_sortting/enable_sortting "data: true"', timeout=20)
    try:
        run_ros_shell("timeout 90 rostopic echo -n 2 /grasp/result", timeout=92)
        cycle_completed = True
    except subprocess.CalledProcessError as exc:
        if exc.returncode != 124:
            raise
    finally:
        run_ros_shell('rosservice call /object_sortting/enable_sortting "data: false"', timeout=20)
        run_ros_shell('rosservice call /object_sortting/set_color_target "{{data_str: {}, data_bool: false}}"'.format(target_color), timeout=20)
        run_ros_shell("rosservice call /object_sortting/exit", timeout=30)

    return {
        "summary": (
            "live pick-and-place cycle completed"
            if cycle_completed
            else "live pick-and-place command sent, but no full cycle was observed before timeout"
        ),
        "motion_executed": True,
        "cycle_completed": cycle_completed,
        "target_color": target_color,
        "destination": destination,
    }


def scan_scene(mode: str = "live") -> dict:
    if mode != "live":
        try:
            frame = capture_camera_frame("color")
        except Exception as exc:
            return {
                "summary": "dry-run camera observation unavailable: {}".format(str(exc)[:160]),
                "frames": [],
                "capture_failures": [{"label": "center", "error": str(exc)[:300]}],
                "continue_ready": True,
                "motion_executed": False,
            }
        return {
            "summary": "dry-run captured current camera frame without scan motion",
            "frames": [
                {
                    "label": "center",
                    "image_base64": frame["image_base64"],
                    "media_type": frame.get("media_type", "image/jpeg"),
                }
            ],
            "capture_failures": [],
            "continue_ready": True,
            "motion_executed": False,
            "camera_recovered": bool(frame.get("camera_recovered", False)),
        }

    camera_status = ensure_camera_topic_ready(RGB_CAMERA_TOPIC)

    output = run_ros_python(
        """
import os
import sys
import cv2
import json
import time
import base64
import rospy
import numpy as np
from sensor_msgs.msg import Image as RosImage
from hiwonder_interfaces.msg import MultiRawIdPosDur

sys.path.insert(0, os.path.expanduser({function_scripts_dir!r}))
import actions

rospy.init_node('jetarm_demo_scan_scene', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)

poses = [
    ('left', actions.goto_left),
    ('center', actions.go_home),
    ('right', actions.goto_right),
]
frames = []
capture_failures = []

for label, pose_fn in poses:
    try:
        pose_fn(pub, duration=0.9)
        rospy.sleep(0.4)
        msg = rospy.wait_for_message({topic!r}, RosImage, timeout=3.0)
        image = np.ndarray(shape=(msg.height, msg.width, 3), dtype=np.uint8, buffer=msg.data).copy()
        if msg.encoding.lower().startswith('rgb'):
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        image = cv2.resize(image, (480, 270))
        ok, encoded = cv2.imencode('.jpg', image)
        if not ok:
            raise RuntimeError('failed to encode frame')
        frames.append({{'label': label, 'image_base64': base64.b64encode(encoded.tobytes()).decode('ascii'), 'media_type': 'image/jpeg'}})
    except Exception as exc:
        capture_failures.append({{'label': label, 'error': str(exc)}})

actions.go_home(pub, duration=0.8)
rospy.sleep(0.5)
print(json.dumps({{'frames': frames, 'capture_failures': capture_failures, 'continue_ready': True}}))
        """.format(function_scripts_dir=FUNCTION_SCRIPTS_DIR, topic=RGB_CAMERA_TOPIC).strip(),
        timeout=30,
    )
    payload = json.loads(output)
    return {
        "summary": "scan scene completed" if payload.get("frames") else "scan scene did not capture any usable frames",
        "frames": payload.get("frames", []),
        "capture_failures": payload.get("capture_failures", []),
        "continue_ready": bool(payload.get("continue_ready", True)),
        "motion_executed": True,
        "camera_recovered": bool(camera_status.get("recovered", False)),
    }


def find_red_block(target_hint_sector: Optional[str] = None, search_strategy: str = "directional_scan", mode: str = "live") -> dict:
    if mode != "live":
        return {"summary": "dry-run only, search not executed", "motion_executed": False, "detected": False}

    camera_status = ensure_camera_topic_ready(RGB_CAMERA_TOPIC)
    output = run_ros_python(
        """
import json
import math
import os
import sys
import cv2
import rospy
import numpy as np
from sensor_msgs.msg import Image as RosImage, CameraInfo
from hiwonder_interfaces.msg import MultiRawIdPosDur
from jetarm_sdk import bus_servo_control
from vision_utils import xyz_euler_to_mat, mat_to_xyz_euler, pixels_to_world, extristric_plane_shift

sys.path.insert(0, os.path.expanduser({function_scripts_dir!r}))
sys.path.insert(0, os.path.expanduser({simple_library_dir!r}))
import actions
import color_detection_base

SECTOR = {target_hint_sector!r}
SEARCH_STRATEGY = {search_strategy!r}
SOURCE_IMAGE_TOPIC = {source_image_topic!r}
CAMERA_INFO_TOPIC = {camera_info_topic!r}
CONFIG_NAME = '/config'
LATERAL_PICK_X_BACKOFF = {lateral_pick_x_backoff}

rospy.init_node('jetarm_demo_find_red_block', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)

def scan_pose(base_value, duration=0.45):
    bus_servo_control.set_servos(pub, int(duration * 1000), ((1, base_value), (2, 560), (3, 130), (4, 115), (5, 500), (10, 200)))
    rospy.sleep(duration)

sector_poses = {{
    'left': [760, 680, 600],
    'front': [580, 500, 420],
    'right': [400, 320, 240],
}}

if SEARCH_STRATEGY == 'global_scan_fallback':
    pose_sequence = [('left', value) for value in sector_poses['left']] + [('front', value) for value in sector_poses['front']] + [('right', value) for value in sector_poses['right']]
else:
    chosen = SECTOR or 'front'
    pose_sequence = [(chosen, value) for value in sector_poses.get(chosen, sector_poses['front'])]

camera_info = rospy.wait_for_message(CAMERA_INFO_TOPIC, CameraInfo, timeout=5.0)
K = np.matrix(camera_info.K).reshape(1, -1, 3)
config = rospy.get_param(CONFIG_NAME)
tvec, rmat = config['extristric']
tvec, rmat = extristric_plane_shift(np.array(tvec).reshape((3, 1)), np.array(rmat), 0.030)
white_area_center = config['white_area_pose_world']
projection_matrix = np.row_stack((np.column_stack((rmat, tvec)), np.array([[0, 0, 0, 1]])))
detector = color_detection_base.color_detection()

detected = False
pose = None
raw_pose = None
align_angle = None
search_sector = SECTOR or 'front'
checked_poses = []
detected_base = None

for sector_name, base_value in pose_sequence:
    scan_pose(base_value)
    checked_poses.append({{'sector': sector_name, 'base': base_value}})
    try:
        image_msg = rospy.wait_for_message(SOURCE_IMAGE_TOPIC, RosImage, timeout=2.0)
    except rospy.ROSException:
        continue
    rgb_image = np.ndarray(shape=(image_msg.height, image_msg.width, 3), dtype=np.uint8, buffer=image_msg.data)
    image_bgr = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
    image_mask = detector.color_detection('red', image_bgr)
    contours = cv2.findContours(image_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[-2]
    if not contours:
        continue
    contour = max(contours, key=cv2.contourArea)
    area = math.fabs(cv2.contourArea(contour))
    if area < 150:
        continue
    rect = cv2.minAreaRect(contour)
    x, y = rect[0][0], rect[0][1]
    yaw = rect[2]
    world_pose = pixels_to_world([[x, y]], K, projection_matrix)[0]
    world_pose[1] = -world_pose[1]
    world_pose[2] = 0.03
    world_pose = np.matmul(white_area_center, xyz_euler_to_mat(world_pose, (0, 0, 0)))
    world_pose[2] = 0.03
    pose_t, _ = mat_to_xyz_euler(world_pose)
    raw_pose = [float(pose_t[0]), float(pose_t[1]), 0.012]
    base_angle = (float(base_value) - 500.0) * (240.0 / 1000.0) * math.pi / 180.0
    compensated_y = pose_t[0] * math.sin(base_angle) + pose_t[1] * math.cos(base_angle)
    r = yaw % 90
    r = r - 90 if r > 45 else (r + 90 if r < -45 else r)
    detected = True
    x_backoff = LATERAL_PICK_X_BACKOFF if sector_name in ('left', 'right') else 0.0
    pose = [float(pose_t[0] - x_backoff), float(compensated_y), 0.012]
    align_angle = float(r)
    search_sector = sector_name
    detected_base = int(base_value)
    break

if not detected:
    actions.go_home(pub, duration=0.8)
    rospy.sleep(0.3)
print(json.dumps({{
    'detected': detected,
    'pose': pose,
    'raw_pose': raw_pose,
    'align_angle': align_angle,
    'search_sector': search_sector,
    'search_strategy': SEARCH_STRATEGY,
    'checked_poses': checked_poses,
    'detected_base': detected_base,
}}))
        """.format(
            function_scripts_dir=FUNCTION_SCRIPTS_DIR,
            simple_library_dir=SIMPLE_LIBRARY_DIR,
            target_hint_sector=target_hint_sector,
            search_strategy=search_strategy,
            source_image_topic=RGB_CAMERA_TOPIC,
            camera_info_topic=RGB_CAMERA_INFO_TOPIC,
            lateral_pick_x_backoff=LATERAL_PICK_X_BACKOFF,
        ).strip(),
        timeout=40,
    )
    payload = json.loads(output)
    return {
        "summary": "found red block" if payload.get("detected") else "red block not found in current search path",
        "detected": bool(payload.get("detected", False)),
        "pose": payload.get("pose"),
        "raw_pose": payload.get("raw_pose"),
        "align_angle": payload.get("align_angle"),
        "search_sector": payload.get("search_sector"),
        "search_strategy": payload.get("search_strategy", search_strategy),
        "checked_poses": payload.get("checked_poses", []),
        "detected_base": payload.get("detected_base"),
        "motion_executed": True,
        "camera_recovered": bool(camera_status.get("recovered", False)),
    }


def pick_red_block(mode: str = "live", locked_pose: Optional[List[float]] = None, locked_align_angle: Optional[float] = None, locked_base: Optional[int] = None) -> dict:
    if mode != "live":
        return {"summary": "dry-run only, pick not executed", "motion_executed": False}
    output = run_ros_python(
        """
import json
import math
import os
import sys
import rospy
import actionlib
import cv2
import numpy as np
from geometry_msgs.msg import Point
from sensor_msgs.msg import Image as RosImage, CameraInfo
from hiwonder_interfaces.msg import MoveAction, MoveGoal, MultiRawIdPosDur
from jetarm_sdk import bus_servo_control
from vision_utils import xyz_euler_to_mat, mat_to_xyz_euler, pixels_to_world, extristric_plane_shift

sys.path.insert(0, os.path.expanduser({simple_library_dir!r}))
import color_detection_base

CONFIG_NAME = '/config'
LOCKED_POSE = {locked_pose!r}
LOCKED_ALIGN_ANGLE = {locked_align_angle!r}
LOCKED_BASE = {locked_base!r}
rospy.init_node('jetarm_demo_pick_red_block', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
client = actionlib.SimpleActionClient('/grasp', MoveAction)
client.wait_for_server()

camera_info = rospy.wait_for_message({camera_info_topic!r}, CameraInfo, timeout=5.0)
K = np.matrix(camera_info.K).reshape(1, -1, 3)
config = rospy.get_param(CONFIG_NAME)
tvec, rmat = config['extristric']
tvec, rmat = extristric_plane_shift(np.array(tvec).reshape((3, 1)), np.array(rmat), 0.030)
white_area_center = config['white_area_pose_world']
extristric = (tvec, rmat)
detector = color_detection_base.color_detection()

detected = False
complete = False
state = None
pose = LOCKED_POSE
align_angle = LOCKED_ALIGN_ANGLE
deadline = rospy.Time.now() + rospy.Duration(8.0)

if LOCKED_POSE is not None:
    detected = True
    if LOCKED_BASE is not None:
        bus_servo_control.set_servos(pub, 450, ((1, int(LOCKED_BASE)), (2, 560), (3, 130), (4, 115), (5, 500), (10, 200)))
        rospy.sleep(0.35)
    goal = MoveGoal()
    goal.grasp.mode = 'pick'
    goal.grasp.position = Point(x=LOCKED_POSE[0], y=LOCKED_POSE[1], z=LOCKED_POSE[2])
    goal.grasp.pitch = 80
    goal.grasp.align_angle = LOCKED_ALIGN_ANGLE if LOCKED_ALIGN_ANGLE is not None else 0.0
    goal.grasp.grasp_approach.z = 0.04
    goal.grasp.grasp_retreat.z = 0.05
    goal.grasp.grasp_posture = 570
    goal.grasp.pre_grasp_posture = 350
    client.send_goal(goal)
    client.wait_for_result(rospy.Duration(25))
    result = client.get_result()
    state = client.get_state()
    complete = bool(getattr(getattr(result, 'result', None), 'complete', False))
else:
    while rospy.Time.now() < deadline and not rospy.is_shutdown():
        image_msg = rospy.wait_for_message({source_image_topic!r}, RosImage, timeout=2.0)
        rgb_image = np.ndarray(shape=(image_msg.height, image_msg.width, 3), dtype=np.uint8, buffer=image_msg.data)
        image_bgr = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
        image_mask = detector.color_detection('red', image_bgr)
        contours = cv2.findContours(image_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[-2]
        if not contours:
            continue

        c = max(contours, key=cv2.contourArea)
        area = math.fabs(cv2.contourArea(c))
        if area < 150:
            continue
        rect = cv2.minAreaRect(c)
        x, y = rect[0][0], rect[0][1]
        yaw = rect[2]
        projection_matrix = np.row_stack((np.column_stack((extristric[1], extristric[0])), np.array([[0, 0, 0, 1]])))
        world_pose = pixels_to_world([[x, y]], K, projection_matrix)[0]
        world_pose[1] = -world_pose[1]
        world_pose[2] = 0.03
        world_pose = np.matmul(white_area_center, xyz_euler_to_mat(world_pose, (0, 0, 0)))
        world_pose[2] = 0.03
        pose_t, _ = mat_to_xyz_euler(world_pose)
        r = yaw % 90
        r = r - 90 if r > 45 else (r + 90 if r < -45 else r)

        goal = MoveGoal()
        goal.grasp.mode = 'pick'
        goal.grasp.position = Point(x=pose_t[0], y=pose_t[1], z=0.012)
        goal.grasp.pitch = 80
        goal.grasp.align_angle = r
        goal.grasp.grasp_approach.z = 0.04
        goal.grasp.grasp_retreat.z = 0.05
        goal.grasp.grasp_posture = 570
        goal.grasp.pre_grasp_posture = 350
        client.send_goal(goal)
        client.wait_for_result(rospy.Duration(25))
        result = client.get_result()
        state = client.get_state()
        complete = bool(getattr(getattr(result, 'result', None), 'complete', False))
        detected = True
        pose = [float(pose_t[0]), float(pose_t[1]), 0.012]
        align_angle = float(r)
        break

print(json.dumps({{
    'detected': detected,
    'state': state,
    'complete': complete,
    'pose': pose,
    'align_angle': align_angle,
}}))
        """.format(
            simple_library_dir=SIMPLE_LIBRARY_DIR,
            source_image_topic=RGB_CAMERA_TOPIC,
            camera_info_topic=RGB_CAMERA_INFO_TOPIC,
            locked_pose=locked_pose,
            locked_align_angle=locked_align_angle,
            locked_base=locked_base,
        ).strip(),
        timeout=30,
    )
    payload = json.loads(output)
    return {
        "summary": (
            "pick_red_block completed via detected red target"
            if payload.get("complete")
            else "pick_red_block did not complete"
        ),
        "detected": bool(payload.get("detected", False)),
        "complete": bool(payload.get("complete", False)),
        "state": payload.get("state"),
        "pose": payload.get("pose"),
        "align_angle": payload.get("align_angle"),
        "motion_executed": True,
    }


def debug_move_to_pick_pose(mode: str = "live", locked_pose: Optional[List[float]] = None, locked_align_angle: Optional[float] = None) -> dict:
    if mode != "live":
        return {"summary": "dry-run only, debug move not executed", "motion_executed": False}
    if locked_pose is None:
        return {"summary": "locked pose missing", "complete": False, "motion_executed": False}
    output = run_ros_python(
        """
import json
import rospy
import actionlib
from geometry_msgs.msg import Point
from hiwonder_interfaces.msg import MoveAction, MoveGoal

LOCKED_POSE = {locked_pose!r}
LOCKED_ALIGN_ANGLE = {locked_align_angle!r}

rospy.init_node('jetarm_demo_debug_move_to_pick_pose', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
client = actionlib.SimpleActionClient('/grasp', MoveAction)
client.wait_for_server()

goal = MoveGoal()
goal.grasp.mode = 'pick'
goal.grasp.position = Point(x=LOCKED_POSE[0], y=LOCKED_POSE[1], z=LOCKED_POSE[2])
goal.grasp.pitch = 80
goal.grasp.align_angle = LOCKED_ALIGN_ANGLE if LOCKED_ALIGN_ANGLE is not None else 0.0
goal.grasp.grasp_approach.z = 0.04
goal.grasp.grasp_retreat.z = 0.05
goal.grasp.grasp_posture = 350
goal.grasp.pre_grasp_posture = 350
client.send_goal(goal)
client.wait_for_result(rospy.Duration(25))
result = client.get_result()
state = client.get_state()
complete = bool(getattr(getattr(result, 'result', None), 'complete', False))
print(json.dumps({{'state': state, 'complete': complete, 'debug_pose': LOCKED_POSE}}))
        """.format(locked_pose=locked_pose, locked_align_angle=locked_align_angle).strip(),
        timeout=30,
    )
    payload = json.loads(output)
    return {
        "summary": "debug_move_to_pick_pose completed" if payload.get("complete") else "debug_move_to_pick_pose did not complete",
        "complete": bool(payload.get("complete", False)),
        "state": payload.get("state"),
        "debug_pose": payload.get("debug_pose"),
        "motion_executed": True,
    }


def lift_red_block(mode: str = "live") -> dict:
    if mode != "live":
        return {"summary": "dry-run only, lift not executed", "motion_executed": False}
    output = run_ros_python(
        """
import os
import sys
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur

sys.path.insert(0, os.path.expanduser({function_scripts_dir!r}))
import actions

rospy.init_node('jetarm_demo_lift_red_block', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
actions.go_back(pub, duration=0.8)
print('ok')
        """.format(function_scripts_dir=FUNCTION_SCRIPTS_DIR).strip(),
        timeout=15,
    )
    return {
        "summary": "lift_red_block completed",
        "output": output,
        "motion_executed": True,
    }


def place_red_block_back_to_pick_xy(mode: str = "live", pick_pose: Optional[List[float]] = None, pick_align_angle: Optional[float] = None) -> dict:
    if mode != "live":
        return {"summary": "dry-run only, place not executed", "motion_executed": False}
    if pick_pose is None:
        return {"summary": "pick pose missing", "complete": False, "motion_executed": False}
    output = run_ros_python(
        """
import os
import sys
import json
import rospy
import actionlib
from geometry_msgs.msg import Point
from hiwonder_interfaces.msg import MoveAction, MoveGoal, MultiRawIdPosDur

sys.path.insert(0, os.path.expanduser({function_scripts_dir!r}))
import actions

rospy.init_node('jetarm_demo_place_red_block_near_origin', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
client = actionlib.SimpleActionClient('/grasp', MoveAction)
client.wait_for_server()

PICK_POSE = {pick_pose!r}
PICK_ALIGN_ANGLE = {pick_align_angle!r}

goal = MoveGoal()
goal.grasp.mode = 'place'
goal.grasp.position = Point(x=PICK_POSE[0], y=PICK_POSE[1], z=0.018)
goal.grasp.pitch = 80
goal.grasp.align_angle = PICK_ALIGN_ANGLE if PICK_ALIGN_ANGLE is not None else -90
goal.grasp.grasp_approach.z = 0.04
goal.grasp.grasp_retreat.z = 0.04
goal.grasp.grasp_posture = 400
goal.grasp.pre_grasp_posture = 600
client.send_goal(goal)
client.wait_for_result(rospy.Duration(25))
result = client.get_result()
state = client.get_state()
complete = bool(getattr(getattr(result, 'result', None), 'complete', False))
actions.go_home(pub, duration=0.8)
print(json.dumps({{'state': state, 'complete': complete}}))
        """.format(function_scripts_dir=FUNCTION_SCRIPTS_DIR, pick_pose=pick_pose, pick_align_angle=pick_align_angle).strip(),
        timeout=35,
    )
    payload = json.loads(output)
    return {
        "summary": "place_red_block_back_to_pick_xy completed" if payload.get("complete") else "place_red_block_back_to_pick_xy did not complete",
        "complete": bool(payload.get("complete", False)),
        "state": payload.get("state"),
        "motion_executed": True,
    }


def place_red_block_near_origin(mode: str = "live") -> dict:
    return place_red_block_back_to_pick_xy(mode=mode, pick_pose=[0.215, -0.055, 0.012], pick_align_angle=-90)


def capture_camera_frame(stream: str = "color") -> dict:
    source_topic = RGB_CAMERA_TOPIC if stream != "depth" else DEPTH_CAMERA_TOPIC
    camera_status = ensure_camera_topic_ready(source_topic)
    output = run_ros_python(
        """
import base64
import json
import cv2
import numpy as np
import rospy
from sensor_msgs.msg import Image as RosImage

STREAM = {stream!r}
SOURCE_TOPIC = {source_topic!r}

rospy.init_node('jetarm_demo_camera_frame', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
msg = rospy.wait_for_message(SOURCE_TOPIC, RosImage, timeout=3.0)

if STREAM == 'depth':
    if msg.encoding == '32FC1':
        depth = np.ndarray(shape=(msg.height, msg.width), dtype=np.float32, buffer=msg.data).copy()
    else:
        depth = np.ndarray(shape=(msg.height, msg.width), dtype=np.uint16, buffer=msg.data).astype(np.float32)
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
    image = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
else:
    image = np.ndarray(shape=(msg.height, msg.width, 3), dtype=np.uint8, buffer=msg.data).copy()
    if msg.encoding.lower().startswith('rgb'):
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

ok, encoded = cv2.imencode('.jpg', image)
if not ok:
    raise RuntimeError('failed to encode camera frame')

print(json.dumps({{
    'image_base64': base64.b64encode(encoded.tobytes()).decode('ascii'),
    'media_type': 'image/jpeg',
    'stream': STREAM,
}}))
        """.format(stream=stream, source_topic=source_topic).strip(),
        timeout=8,
    )
    payload = json.loads(output)
    payload["camera_recovered"] = bool(camera_status.get("recovered", False))
    return payload
