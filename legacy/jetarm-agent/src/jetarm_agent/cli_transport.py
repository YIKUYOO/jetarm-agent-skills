from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from jetarm_agent.schemas import CalibrationProfile, DetectedTarget, PickPlaceRequest, PickPlaceResult, PickPlaceStatus


def _find_local_bash() -> str | None:
    bash_path = shutil.which("bash")
    if bash_path and not (
        os.name == "nt"
        and ("\\system32\\bash.exe" in bash_path.lower() or "\\windowsapps\\bash.exe" in bash_path.lower())
    ):
        return bash_path

    if os.name == "nt":
        git_path = shutil.which("git")
        if git_path:
            candidate = os.path.abspath(os.path.join(os.path.dirname(git_path), "..", "bin", "bash.exe"))
            if os.path.exists(candidate):
                return candidate

    return None


class CommandResult(BaseModel):
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_ms: int = 0

    model_config = ConfigDict(extra="forbid")


class CommandRunner(Protocol):
    def run(self, command: str, *, timeout_seconds: int) -> CommandResult:
        """Run a shell command and return a structured result."""


class LocalShellRunner:
    def run(self, command: str, *, timeout_seconds: int) -> CommandResult:
        started = time.monotonic()
        bash_path = _find_local_bash()
        argv = [bash_path, "-lc", command] if bash_path else command
        try:
            completed = subprocess.run(
                argv,
                shell=bash_path is None,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            return CommandResult(
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                timed_out=False,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                timed_out=True,
                duration_ms=int((time.monotonic() - started) * 1000),
            )


class SshShellRunner:
    def __init__(
        self,
        *,
        host: str,
        user: str,
        connect_timeout_seconds: int = 5,
        identity_file: str | None = None,
        password: str | None = None,
    ):
        self.host = host
        self.user = user
        self.connect_timeout_seconds = connect_timeout_seconds
        self.identity_file = identity_file
        self.password = password

    def run(self, command: str, *, timeout_seconds: int) -> CommandResult:
        started = time.monotonic()
        argv = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"ConnectTimeout={self.connect_timeout_seconds}",
        ]
        if self.identity_file:
            argv.extend(["-i", self.identity_file])
        argv.extend([f"{self.user}@{self.host}", f"bash -lc {shlex.quote(command)}"])
        env = None
        askpass_path = None
        stdin = None
        if self.password:
            with tempfile.NamedTemporaryFile("w", delete=False) as handle:
                handle.write("#!/bin/sh\n")
                handle.write('printf "%s" "$JETARM_SSH_PASSWORD"\n')
                askpass_path = handle.name
            os.chmod(askpass_path, 0o700)
            env = os.environ.copy()
            env["DISPLAY"] = "codex-ssh"
            env["SSH_ASKPASS"] = askpass_path
            env["SSH_ASKPASS_REQUIRE"] = "force"
            env["JETARM_SSH_PASSWORD"] = self.password
            argv = ["setsid", *argv]
            stdin = subprocess.DEVNULL
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
                stdin=stdin,
            )
            return CommandResult(
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                timed_out=False,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                timed_out=True,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        finally:
            if askpass_path:
                try:
                    os.unlink(askpass_path)
                except FileNotFoundError:
                    pass


class CliBoardTransportConfig(BaseModel):
    ros_setup_command: str = (
        "export ROS_HOSTNAME=localhost && "
        "export ROS_MASTER_URI=http://localhost:11311 && "
        ". /opt/ros/melodic/setup.bash >/dev/null 2>&1 && "
        ". ~/jetarm/devel/setup.bash >/dev/null 2>&1"
    )
    command_timeout_seconds: int = 20
    grasp_result_timeout_seconds: int = 90
    observe_target_color: str = "red"
    observe_timeout_seconds: int = 20
    gripper_open_position: int = 200
    gripper_closed_position: int = 500
    gripper_duration_ms: int = 450
    stop_target_color: str = "red"

    model_config = ConfigDict(extra="forbid")


class CliBoardTransport:
    def __init__(self, *, runner: CommandRunner, config: CliBoardTransportConfig | None = None):
        self.runner = runner
        self.config = config or CliBoardTransportConfig()

    def observe_scene(self, profile: CalibrationProfile) -> list[DetectedTarget]:
        payload = self._observe_fixed_scene_color_block()
        if not payload.get("detected"):
            return []

        observed_at = payload.get("observed_at")
        timestamp = (
            datetime.fromisoformat(observed_at)
            if isinstance(observed_at, str) and observed_at
            else datetime.now(timezone.utc)
        )
        object_class = (
            "color_block"
            if "color_block" in profile.workcell.allowed_object_classes
            else profile.workcell.allowed_object_classes[0]
        )
        pose_values = payload.get("pose") or [0.0, 0.0, 0.0]
        return [
            DetectedTarget(
                entity_id=f"{self.config.observe_target_color}-{object_class}-1",
                object_class=object_class,
                color=self.config.observe_target_color,
                confidence=float(payload.get("confidence", 0.9)),
                source_timestamp=timestamp,
                pose={
                    "frame": profile.base_frame,
                    "x": pose_values[0],
                    "y": pose_values[1],
                    "z": pose_values[2],
                    "align_angle": payload.get("align_angle"),
                    "raw_pose": payload.get("raw_pose"),
                    "observation_mode": "fixed_front",
                },
            )
        ]

    def go_home(self) -> dict:
        result = self._run_python(
            """
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur
from jetarm_sdk import bus_servo_control

rospy.init_node('jetarm_agent_phase2_go_home', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
bus_servo_control.set_servos(pub, 800, ((1, 500), (2, 560), (3, 130), (4, 115), (5, 500), (10, 200)))
rospy.sleep(1.0)
print('ok')
            """.strip(),
            timeout_seconds=self.config.command_timeout_seconds,
        )
        self._require_success(result, "go_home")
        return {
            "final_pose_summary": "home",
            "motion_executed": True,
            "stdout": result.stdout,
        }

    def set_gripper(self, *, opened: bool) -> dict:
        position = self.config.gripper_open_position if opened else self.config.gripper_closed_position
        result = self._run_python(
            f"""
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur
from jetarm_sdk import bus_servo_control

rospy.init_node('jetarm_agent_phase2_set_gripper', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
bus_servo_control.set_servos(pub, {self.config.gripper_duration_ms}, ((10, {position}),))
rospy.sleep(0.7)
print('ok')
            """.strip(),
            timeout_seconds=self.config.command_timeout_seconds,
        )
        self._require_success(result, "set_gripper")
        return {
            "gripper_state": "open" if opened else "closed",
            "position": position,
            "duration_ms": self.config.gripper_duration_ms,
            "stdout": result.stdout,
        }

    def stop_all(self) -> dict:
        stage_results = self._run_cleanup_sequence(target_color=self.config.stop_target_color)
        continue_ready = all(item["exit_code"] == 0 and not item["timed_out"] for item in stage_results)
        if not continue_ready:
            raise RuntimeError("stop_all cleanup sequence did not complete successfully")
        return {
            "stop_scope": "workflow_exit_only",
            "continue_ready": continue_ready,
            "stage_results": stage_results,
        }

    def recover(self, *, last_error_code=None) -> dict:
        stop_telemetry = self.stop_all()
        go_home_telemetry = self.go_home()
        return {
            "continue_ready": True,
            "recovery_actions": ["stop_all", "go_home"],
            "last_error_code": last_error_code.value if last_error_code is not None else None,
            "stop": stop_telemetry,
            "go_home": go_home_telemetry,
        }

    def _board_command(self, body: str) -> str:
        return f"{self.config.ros_setup_command} && {body}"

    def _run(self, body: str, *, timeout_seconds: int | None = None) -> CommandResult:
        return self.runner.run(
            self._board_command(body),
            timeout_seconds=timeout_seconds or self.config.command_timeout_seconds,
        )

    def _run_python(self, script: str, *, timeout_seconds: int | None = None) -> CommandResult:
        return self._run(
            f"python3 -c {shlex.quote(script)}",
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _require_success(result: CommandResult, stage_name: str) -> None:
        if result.exit_code != 0 or result.timed_out:
            raise RuntimeError(
                f"{stage_name} failed: exit_code={result.exit_code} timed_out={result.timed_out} stderr={result.stderr.strip()}"
            )

    @staticmethod
    def _summarize_grasp_result(output: str) -> dict:
        return {
            "complete_true_count": output.count("complete: True"),
            "state_3_count": output.count("state: 3"),
            "raw_excerpt": output.strip()[:500],
        }

    def _cleanup_after_pick_place(self, *, target_color: str) -> tuple[list[dict], bool]:
        cleanup_results = self._run_cleanup_sequence(target_color=target_color)
        all_ok = all(item["exit_code"] == 0 and not item["timed_out"] for item in cleanup_results)
        return cleanup_results, all_ok

    def _run_cleanup_sequence(self, *, target_color: str) -> list[dict]:
        cleanup_steps = [
            ("disable_sortting", 'rosservice call /object_sortting/enable_sortting "data: false"'),
            (
                "unset_target",
                f'rosservice call /object_sortting/set_color_target "{{data_str: \'{target_color}\', data_bool: false}}"',
            ),
            ("exit", "rosservice call /object_sortting/exit"),
        ]
        results = []
        for name, body in cleanup_steps:
            command_result = self._run(body)
            results.append(
                {
                    "step": name,
                    "exit_code": command_result.exit_code,
                    "stdout": command_result.stdout,
                    "stderr": command_result.stderr,
                    "timed_out": command_result.timed_out,
                }
            )
        return results

    def _observe_fixed_scene_color_block(self) -> dict:
        result = self._run_python(
            f"""
import json
import math
import os
import sys
from datetime import datetime, timezone

import cv2
import rospy
import numpy as np
from sensor_msgs.msg import CameraInfo, Image as RosImage
from hiwonder_interfaces.msg import MultiRawIdPosDur
from vision_utils import xyz_euler_to_mat, mat_to_xyz_euler, pixels_to_world, extristric_plane_shift

sys.path.insert(0, os.path.expanduser('~/jetarm/src/jetarm_6dof/jetarm_6dof_functions/scripts'))
sys.path.insert(0, os.path.expanduser('~/jetarm/src/jetarm_example/src/Simple_library'))
import actions
import color_detection_base

rospy.init_node('jetarm_agent_phase2_observe_scene', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
actions.go_home(pub, duration=0.8)
rospy.sleep(0.4)

camera_info = rospy.wait_for_message('/rgbd_cam/color/camera_info', CameraInfo, timeout=5.0)
K = np.matrix(camera_info.K).reshape(1, -1, 3)
config = rospy.get_param('/config')
tvec, rmat = config['extristric']
tvec, rmat = extristric_plane_shift(np.array(tvec).reshape((3, 1)), np.array(rmat), 0.030)
white_area_center = config['white_area_pose_world']
projection_matrix = np.row_stack((np.column_stack((rmat, tvec)), np.array([[0, 0, 0, 1]])))
detector = color_detection_base.color_detection()

detected = False
pose = None
raw_pose = None
align_angle = None
confidence = 0.0
deadline = rospy.Time.now() + rospy.Duration(4.0)

while rospy.Time.now() < deadline and not rospy.is_shutdown():
    try:
        image_msg = rospy.wait_for_message('/rgbd_cam/color/image_rect_color', RosImage, timeout=1.0)
    except rospy.ROSException:
        continue
    rgb_image = np.ndarray(shape=(image_msg.height, image_msg.width, 3), dtype=np.uint8, buffer=image_msg.data)
    image_bgr = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
    image_mask = detector.color_detection({self.config.observe_target_color!r}, image_bgr)
    contours = cv2.findContours(image_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[-2]
    if not contours:
        continue
    contour = max(contours, key=cv2.contourArea)
    area = float(math.fabs(cv2.contourArea(contour)))
    if area < 150:
        continue
    rect = cv2.minAreaRect(contour)
    x, y = rect[0][0], rect[0][1]
    yaw = rect[2]
    world_pose = pixels_to_world([[x, y]], K, projection_matrix)[0]
    world_pose[1] = -world_pose[1]
    world_pose[2] = 0.03
    world_pose = np.matmul(white_area_center, xyz_euler_to_mat(world_pose, (0, 0, 0)))
    pose_t, _ = mat_to_xyz_euler(world_pose)
    r = yaw % 90
    r = r - 90 if r > 45 else (r + 90 if r < -45 else r)
    raw_pose = [float(pose_t[0]), float(pose_t[1]), 0.012]
    pose = [float(pose_t[0]), float(pose_t[1]), 0.012]
    align_angle = float(r)
    confidence = min(0.99, 0.5 + area / 5000.0)
    detected = True
    break

print(json.dumps({{
    'detected': detected,
    'observed_at': datetime.now(timezone.utc).isoformat(),
    'pose': pose,
    'raw_pose': raw_pose,
    'align_angle': align_angle,
    'confidence': confidence,
}}))
            """.strip(),
            timeout_seconds=self.config.observe_timeout_seconds,
        )
        self._require_success(result, "observe_scene")
        try:
            return json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"observe_scene returned invalid JSON: {exc}") from exc

    def _failure(
        self,
        *,
        request_id: str,
        failure_stage: str,
        message: str,
        stage_commands: list[dict],
        cleanup_results: list[dict],
        cleanup_succeeded: bool,
        grasp_result_summary: dict | None = None,
    ) -> PickPlaceResult:
        return PickPlaceResult(
            request_id=request_id,
            status=PickPlaceStatus.FAILED,
            failure_stage=failure_stage,
            telemetry={
                "transport_mode": self.runner.__class__.__name__,
                "stage_commands": stage_commands,
                "cleanup_attempted": True,
                "cleanup_succeeded": cleanup_succeeded,
                "grasp_result_summary": grasp_result_summary or {},
            },
            artifacts={
                "message": message,
                "cleanup_results": cleanup_results,
            },
        )

    def run_object_sortting_pick_place(self, request: PickPlaceRequest, *, target_color: str) -> PickPlaceResult:
        stage_results: list[dict] = []
        startup_steps = [
            ("enter", "rosservice call /object_sortting/enter"),
            (
                "set_target",
                f'rosservice call /object_sortting/set_color_target "{{data_str: \'{target_color}\', data_bool: true}}"',
            ),
            ("enable_sortting", 'rosservice call /object_sortting/enable_sortting "data: true"'),
        ]

        for stage_name, body in startup_steps:
            result = self._run(body)
            stage_results.append(
                {
                    "stage": stage_name,
                    "command": self._board_command(body),
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "timed_out": result.timed_out,
                }
            )
            if result.exit_code != 0 or result.timed_out:
                cleanup_results, cleanup_succeeded = self._cleanup_after_pick_place(target_color=target_color)
                return self._failure(
                    request_id=request.request_id,
                    failure_stage="enter",
                    message=f"{stage_name} failed",
                    stage_commands=stage_results,
                    cleanup_results=cleanup_results,
                    cleanup_succeeded=cleanup_succeeded,
                )

        grasp_body = f"timeout {self.config.grasp_result_timeout_seconds} rostopic echo -n 2 /grasp/result"
        grasp_result = self._run(grasp_body, timeout_seconds=self.config.grasp_result_timeout_seconds + 5)
        stage_results.append(
            {
                "stage": "grasp_result",
                "command": self._board_command(grasp_body),
                "exit_code": grasp_result.exit_code,
                "stdout": grasp_result.stdout,
                "stderr": grasp_result.stderr,
                "timed_out": grasp_result.timed_out,
            }
        )

        grasp_summary = self._summarize_grasp_result(grasp_result.stdout)
        cleanup_results, cleanup_succeeded = self._cleanup_after_pick_place(target_color=target_color)

        if grasp_result.timed_out or (grasp_result.exit_code != 0 and not grasp_result.stdout.strip()):
            return self._failure(
                request_id=request.request_id,
                failure_stage="detect",
                message="no completed grasp/place result observed before timeout",
                stage_commands=stage_results,
                cleanup_results=cleanup_results,
                cleanup_succeeded=cleanup_succeeded,
                grasp_result_summary=grasp_summary,
            )

        if grasp_summary["complete_true_count"] <= 0:
            return self._failure(
                request_id=request.request_id,
                failure_stage="grasp",
                message="grasp result did not show a completed pick stage",
                stage_commands=stage_results,
                cleanup_results=cleanup_results,
                cleanup_succeeded=cleanup_succeeded,
                grasp_result_summary=grasp_summary,
            )

        if grasp_summary["complete_true_count"] < 2:
            return self._failure(
                request_id=request.request_id,
                failure_stage="place",
                message="grasp result did not show a completed place stage",
                stage_commands=stage_results,
                cleanup_results=cleanup_results,
                cleanup_succeeded=cleanup_succeeded,
                grasp_result_summary=grasp_summary,
            )

        if not cleanup_succeeded:
            return self._failure(
                request_id=request.request_id,
                failure_stage="exit",
                message="workflow cleanup did not complete successfully",
                stage_commands=stage_results,
                cleanup_results=cleanup_results,
                cleanup_succeeded=cleanup_succeeded,
                grasp_result_summary=grasp_summary,
            )

        return PickPlaceResult(
            request_id=request.request_id,
            status=PickPlaceStatus.SUCCEEDED,
            failure_stage=None,
            telemetry={
                "transport_mode": self.runner.__class__.__name__,
                "stage_commands": stage_results,
                "cleanup_attempted": True,
                "cleanup_succeeded": True,
                "grasp_result_summary": grasp_summary,
                "release_confirmed": True,
                "continue_ready": True,
            },
            artifacts={"cleanup_results": cleanup_results, "workflow": "object_sortting"},
        )
