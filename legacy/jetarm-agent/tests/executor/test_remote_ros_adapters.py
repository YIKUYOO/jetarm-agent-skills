import json
import subprocess
import base64

from remote.jetarm_executor import ros_adapters


def test_detect_color_marks_red_when_labels_use_red_prefix(monkeypatch):
    monkeypatch.setattr(
        ros_adapters,
        "run_ros_python",
        lambda script, timeout=20: json.dumps({"detected": True, "frames_sampled": 2}),
    )
    monkeypatch.setattr(ros_adapters, "check_ros_nodes", lambda: {"tracking_node": True})

    result = ros_adapters.detect_color("red")

    assert result["detected"] is True
    assert result["frames_sampled"] == 2
    assert result["observation_available"] is True
    assert "object_tracking color detection checked for red" == result["summary"]


def test_detect_color_returns_negative_result_when_listener_times_out(monkeypatch):
    monkeypatch.setattr(
        ros_adapters,
        "run_ros_python",
        lambda script, timeout=20: (_ for _ in ()).throw(subprocess.TimeoutExpired("detect", timeout)),
    )
    monkeypatch.setattr(ros_adapters, "check_ros_nodes", lambda: {"tracking_node": True})

    result = ros_adapters.detect_color("red")

    assert result["detected"] is False
    assert result["observation_available"] is False
    assert "object_tracking color detection unavailable for red" == result["summary"]


def test_detect_color_returns_unavailable_when_startup_service_times_out(monkeypatch):
    monkeypatch.setattr(ros_adapters, "check_ros_nodes", lambda: {"tracking_node": False})

    result = ros_adapters.detect_color("red")

    assert result["detected"] is False
    assert result["observation_available"] is False
    assert "unavailable" in result["summary"]


def test_pick_and_place_live_waits_for_one_cycle_and_disables_sortting(monkeypatch):
    commands = []

    def fake_run_ros_shell(command: str, timeout: int = 20) -> str:
        commands.append(command)
        return ""

    monkeypatch.setattr(ros_adapters, "run_ros_shell", fake_run_ros_shell)

    result = ros_adapters.pick_and_place_color(
        target_color="red",
        destination="left",
        mode="live",
        single_block_demo_mode=True,
    )

    assert result["motion_executed"] is True
    enter_index = next(i for i, command in enumerate(commands) if "/object_sortting/enter" in command)
    set_target_index = next(i for i, command in enumerate(commands) if "/object_sortting/set_color_target" in command and "data_bool: true" in command)
    enable_index = next(i for i, command in enumerate(commands) if '/object_sortting/enable_sortting "data: true"' in command)
    assert enter_index < set_target_index < enable_index
    assert any('/object_sortting/enable_sortting "data: true"' in command for command in commands)
    assert any("rostopic echo -n 2 /grasp/result" in command for command in commands)
    assert any('/object_sortting/enable_sortting "data: false"' in command for command in commands)
    assert any("/object_sortting/exit" in command for command in commands)


def test_capture_camera_frame_returns_color_snapshot_payload(monkeypatch):
    expected = base64.b64encode(b"jpeg-bytes").decode("ascii")
    monkeypatch.setattr(ros_adapters, "ensure_camera_topic_ready", lambda topic: {"recovered": False})
    monkeypatch.setattr(
        ros_adapters,
        "run_ros_python",
        lambda script, timeout=20: json.dumps({"image_base64": expected, "media_type": "image/jpeg", "stream": "color"}),
    )

    result = ros_adapters.capture_camera_frame("color")

    assert result["image_base64"] == expected
    assert result["media_type"] == "image/jpeg"
    assert result["stream"] == "color"
    assert result["camera_recovered"] is False


def test_scan_scene_collects_frames_and_returns_continue_ready(monkeypatch):
    encoded = base64.b64encode(b"scan-frame").decode("ascii")
    monkeypatch.setattr(ros_adapters, "ensure_camera_topic_ready", lambda topic: {"recovered": False})
    monkeypatch.setattr(
        ros_adapters,
        "run_ros_python",
        lambda script, timeout=20: json.dumps(
            {
                "frames": [
                    {"label": "left", "image_base64": encoded},
                    {"label": "center", "image_base64": encoded},
                    {"label": "right", "image_base64": encoded},
                ],
                "continue_ready": True,
            }
        ),
    )

    result = ros_adapters.scan_scene()

    assert len(result["frames"]) == 3
    assert result["continue_ready"] is True
    assert result["motion_executed"] is True
    assert result["camera_recovered"] is False


def test_scan_scene_tolerates_partial_frame_failures(monkeypatch):
    encoded = base64.b64encode(b"scan-frame").decode("ascii")
    monkeypatch.setattr(ros_adapters, "ensure_camera_topic_ready", lambda topic: {"recovered": True})
    monkeypatch.setattr(
        ros_adapters,
        "run_ros_python",
        lambda script, timeout=20: json.dumps(
            {
                "frames": [
                    {"label": "center", "image_base64": encoded},
                ],
                "continue_ready": True,
                "capture_failures": [
                    {"label": "left", "error": "timeout"},
                    {"label": "right", "error": "timeout"},
                ],
            }
        ),
    )

    result = ros_adapters.scan_scene()

    assert len(result["frames"]) == 1
    assert result["continue_ready"] is True
    assert result["motion_executed"] is True
    assert len(result["capture_failures"]) == 2
    assert result["camera_recovered"] is True


def test_scan_scene_dry_run_captures_current_frame_without_motion(monkeypatch):
    encoded = base64.b64encode(b"safe-observation-frame").decode("ascii")
    monkeypatch.setattr(
        ros_adapters,
        "capture_camera_frame",
        lambda stream="color": {
            "image_base64": encoded,
            "media_type": "image/jpeg",
            "stream": stream,
            "camera_recovered": False,
        },
    )

    result = ros_adapters.scan_scene(mode="dry_run")

    assert result["summary"] == "dry-run captured current camera frame without scan motion"
    assert result["frames"] == [
        {"label": "center", "image_base64": encoded, "media_type": "image/jpeg"}
    ]
    assert result["capture_failures"] == []
    assert result["continue_ready"] is True
    assert result["motion_executed"] is False
    assert result["camera_recovered"] is False


def test_ensure_camera_topic_ready_recovers_after_initial_timeout(monkeypatch):
    waits = {"count": 0}
    recovered = {"count": 0}

    def fake_wait(topic, timeout=3.0):
        waits["count"] += 1
        if waits["count"] == 1:
            raise subprocess.TimeoutExpired("camera", timeout)

    def fake_recover():
        recovered["count"] += 1

    monkeypatch.setattr(ros_adapters, "_wait_for_camera_topic", fake_wait)
    monkeypatch.setattr(ros_adapters, "_recover_camera_stack", fake_recover)

    result = ros_adapters.ensure_camera_topic_ready("/rgbd_cam/color/image_rect_color")

    assert result == {"recovered": True}
    assert waits["count"] == 2
    assert recovered["count"] == 1


def test_pick_red_block_uses_active_board_pitch_fields(monkeypatch):
    captured = {}

    def fake_run_ros_python(script, timeout=20):
        captured["script"] = script
        return json.dumps({"detected": True, "state": 3, "complete": True, "pose": [0.2, -0.05, 0.012], "align_angle": 12.0})

    monkeypatch.setattr(ros_adapters, "run_ros_python", fake_run_ros_python)

    result = ros_adapters.pick_red_block()

    assert result["complete"] is True
    assert result["detected"] is True
    assert result["pose"] == [0.2, -0.05, 0.012]
    assert result["align_angle"] == 12.0
    assert "pixels_to_world" in captured["script"]
    assert "color_detection_base" in captured["script"]
    assert "goal.grasp.pitch = 80" in captured["script"]
    assert "goal.grasp.roll" not in captured["script"]
    assert "goal.grasp.grasp_posture = 570" in captured["script"]
    assert "goal.grasp.pre_grasp_posture = 350" in captured["script"]


def test_find_red_block_uses_sector_hint_and_reports_pose(monkeypatch):
    captured = {}

    def fake_run_ros_python(script, timeout=20):
        captured["script"] = script
        return json.dumps({
            "detected": True,
            "pose": [0.22, -0.04, 0.012],
            "raw_pose": [0.18, 0.02, 0.012],
            "align_angle": 9.0,
            "search_sector": "left",
            "search_strategy": "directional_scan",
            "detected_base": 760,
        })

    monkeypatch.setattr(ros_adapters, "ensure_camera_topic_ready", lambda topic: {"recovered": False})
    monkeypatch.setattr(ros_adapters, "run_ros_python", fake_run_ros_python)

    result = ros_adapters.find_red_block(target_hint_sector="left", search_strategy="directional_scan")

    assert result["detected"] is True
    assert result["pose"] == [0.22, -0.04, 0.012]
    assert result["raw_pose"] == [0.18, 0.02, 0.012]
    assert result["search_sector"] == "left"
    assert result["detected_base"] == 760
    assert "SECTOR = 'left'" in captured["script"]
    assert "scan_pose" in captured["script"]
    assert "compensated_y" in captured["script"]
    assert "LATERAL_PICK_X_BACKOFF" in captured["script"]


def test_pick_red_block_can_use_locked_pose_from_find_step(monkeypatch):
    captured = {}

    def fake_run_ros_python(script, timeout=20):
        captured["script"] = script
        return json.dumps({"detected": True, "state": 3, "complete": True, "pose": [0.2, -0.05, 0.012], "align_angle": 12.0})

    monkeypatch.setattr(ros_adapters, "run_ros_python", fake_run_ros_python)

    result = ros_adapters.pick_red_block(locked_pose=[0.21, -0.03, 0.012], locked_align_angle=7.5, locked_base=760)

    assert result["complete"] is True
    assert "LOCKED_POSE = [0.21, -0.03, 0.012]" in captured["script"]
    assert "LOCKED_ALIGN_ANGLE = 7.5" in captured["script"]
    assert "LOCKED_BASE = 760" in captured["script"]
    assert "if LOCKED_POSE is not None" in captured["script"]
    assert "bus_servo_control.set_servos" in captured["script"]


def test_place_red_block_back_to_pick_xy_uses_recorded_pick_xy(monkeypatch):
    captured = {}

    def fake_run_ros_python(script, timeout=20):
        captured["script"] = script
        return json.dumps({"state": 3, "complete": True})

    monkeypatch.setattr(ros_adapters, "run_ros_python", fake_run_ros_python)

    result = ros_adapters.place_red_block_back_to_pick_xy(pick_pose=[0.23, -0.06, 0.012], pick_align_angle=14.0)

    assert result["complete"] is True
    assert "PICK_POSE = [0.23, -0.06, 0.012]" in captured["script"]
    assert "PICK_ALIGN_ANGLE = 14.0" in captured["script"]
    assert "Point(x=PICK_POSE[0], y=PICK_POSE[1], z=0.018)" in captured["script"]
    assert "goal.grasp.align_angle = PICK_ALIGN_ANGLE if PICK_ALIGN_ANGLE is not None else -90" in captured["script"]
    assert "goal.grasp.pitch = 80" in captured["script"]
    assert "goal.grasp.roll" not in captured["script"]
    assert "goal.grasp.grasp_posture = 400" in captured["script"]
    assert "goal.grasp.pre_grasp_posture = 600" in captured["script"]
