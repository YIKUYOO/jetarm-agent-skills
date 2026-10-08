from __future__ import annotations

from datetime import datetime, timezone

from jetarm_agent.cli_transport import (
    CliBoardTransport,
    CliBoardTransportConfig,
    CommandResult,
    LocalShellRunner,
    SshShellRunner,
)
from jetarm_agent.schemas import (
    CalibrationOffsets,
    CalibrationProfile,
    DetectedTarget,
    PickPlaceRequest,
    PickPlaceStatus,
    WorkcellConstraints,
)


def build_request() -> PickPlaceRequest:
    profile = CalibrationProfile(
        profile_name="lab-a",
        camera_frame="rgbd_cam_color_optical_frame",
        base_frame="base_link",
        offsets=CalibrationOffsets(),
        workcell=WorkcellConstraints(
            allowed_object_classes=["color_block"],
            destination_zones={"left_bin": {"frame": "base_link", "x": 0.25, "y": 0.12, "z": 0.08}},
        ),
    )
    return PickPlaceRequest(
        request_id="req-1",
        profile=profile,
        target=DetectedTarget(
            entity_id="block-red-1",
            object_class="color_block",
            color="red",
            confidence=0.9,
            source_timestamp="2026-03-30T00:00:00Z",
            pose={"frame": "base_link", "x": 0.1, "y": 0.2, "z": 0.3},
        ),
        destination_zone="left_bin",
    )


class StubRunner:
    def __init__(self, results: list[CommandResult]):
        self.results = list(results)
        self.commands: list[tuple[str, int]] = []

    def run(self, command: str, *, timeout_seconds: int) -> CommandResult:
        self.commands.append((command, timeout_seconds))
        if not self.results:
            raise AssertionError("no more stubbed command results")
        return self.results.pop(0)


def test_local_shell_runner_executes_simple_command():
    runner = LocalShellRunner()

    result = runner.run("printf 'hello'", timeout_seconds=2)

    assert result.exit_code == 0
    assert result.stdout == "hello"
    assert result.timed_out is False


def test_ssh_shell_runner_wraps_command_with_board_target(monkeypatch):
    captured = {}

    def fake_run(argv, capture_output, text, timeout, env=None, stdin=None):
        captured["argv"] = argv
        captured["timeout"] = timeout
        captured["env"] = env
        captured["stdin"] = stdin

        class Completed:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)
    runner = SshShellRunner(host="192.0.2.10", user="hiwonder", connect_timeout_seconds=5)

    result = runner.run("echo READY", timeout_seconds=9)

    assert result.exit_code == 0
    assert captured["argv"][:5] == ["ssh", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=5"]
    assert captured["argv"][5] == "hiwonder@192.0.2.10"
    assert captured["argv"][6].startswith("bash -lc ")
    assert "echo READY" in captured["argv"][6]
    assert captured["timeout"] == 9
    assert captured["env"] is None


def test_ssh_shell_runner_uses_askpass_when_password_is_provided(monkeypatch):
    captured = {}

    def fake_run(argv, capture_output, text, timeout, env=None, stdin=None):
        captured["argv"] = argv
        captured["timeout"] = timeout
        captured["env"] = env
        captured["stdin"] = stdin

        class Completed:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)
    runner = SshShellRunner(
        host="192.0.2.10",
        user="hiwonder",
        connect_timeout_seconds=5,
        password="secret",
    )

    result = runner.run("echo READY", timeout_seconds=9)

    assert result.exit_code == 0
    assert captured["argv"][0] == "setsid"
    assert captured["argv"][1:6] == ["ssh", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=5"]
    assert captured["argv"][6] == "hiwonder@192.0.2.10"
    assert captured["argv"][7].startswith("bash -lc ")
    assert captured["env"]["SSH_ASKPASS_REQUIRE"] == "force"
    assert captured["env"]["DISPLAY"] == "codex-ssh"
    assert captured["env"]["JETARM_SSH_PASSWORD"] == "secret"
    assert captured["stdin"] is not None


def test_cli_board_transport_runs_canonical_object_sortting_happy_path():
    runner = StubRunner(
        [
            CommandResult(exit_code=0, stdout="enter ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="set ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="enable ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(
                exit_code=0,
                stdout="status: 3\ncomplete: True\n---\nstatus: 3\ncomplete: True\n",
                stderr="",
                timed_out=False,
                duration_ms=30,
            ),
            CommandResult(exit_code=0, stdout="disable ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="unset ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="exit ok", stderr="", timed_out=False, duration_ms=10),
        ]
    )
    transport = CliBoardTransport(runner=runner, config=CliBoardTransportConfig())

    result = transport.run_object_sortting_pick_place(build_request(), target_color="red")

    assert result.status is PickPlaceStatus.SUCCEEDED
    assert result.telemetry["cleanup_attempted"] is True
    assert result.telemetry["cleanup_succeeded"] is True
    assert result.telemetry["grasp_result_summary"]["complete_true_count"] == 2
    assert len(runner.commands) == 7
    assert "/object_sortting/enter" in runner.commands[0][0]
    assert "/grasp/result" in runner.commands[3][0]


def test_cli_board_transport_marks_enter_failure_and_still_runs_cleanup():
    runner = StubRunner(
        [
            CommandResult(exit_code=1, stdout="", stderr="enter failed", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="disable ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="unset ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="exit ok", stderr="", timed_out=False, duration_ms=10),
        ]
    )
    transport = CliBoardTransport(runner=runner, config=CliBoardTransportConfig())

    result = transport.run_object_sortting_pick_place(build_request(), target_color="red")

    assert result.status is PickPlaceStatus.FAILED
    assert result.failure_stage == "enter"
    assert result.telemetry["cleanup_attempted"] is True
    assert result.telemetry["cleanup_succeeded"] is True
    assert len(runner.commands) == 4
    assert "/object_sortting/enable_sortting" in runner.commands[1][0]


def test_cli_board_transport_maps_grasp_timeout_to_detect_failure():
    runner = StubRunner(
        [
            CommandResult(exit_code=0, stdout="enter ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="set ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="enable ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=124, stdout="", stderr="timeout", timed_out=True, duration_ms=90000),
            CommandResult(exit_code=0, stdout="disable ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="unset ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="exit ok", stderr="", timed_out=False, duration_ms=10),
        ]
    )
    transport = CliBoardTransport(runner=runner, config=CliBoardTransportConfig())

    result = transport.run_object_sortting_pick_place(build_request(), target_color="red")

    assert result.status is PickPlaceStatus.FAILED
    assert result.failure_stage == "detect"
    assert result.telemetry["cleanup_succeeded"] is True


def test_cli_board_transport_marks_exit_failure_when_cleanup_breaks_after_successful_grasp():
    runner = StubRunner(
        [
            CommandResult(exit_code=0, stdout="enter ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="set ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="enable ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(
                exit_code=0,
                stdout="status: 3\ncomplete: True\n---\nstatus: 3\ncomplete: True\n",
                stderr="",
                timed_out=False,
                duration_ms=30,
            ),
            CommandResult(exit_code=1, stdout="", stderr="disable failed", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="unset ok", stderr="", timed_out=False, duration_ms=10),
            CommandResult(exit_code=0, stdout="exit ok", stderr="", timed_out=False, duration_ms=10),
        ]
    )
    transport = CliBoardTransport(runner=runner, config=CliBoardTransportConfig())

    result = transport.run_object_sortting_pick_place(build_request(), target_color="red")

    assert result.status is PickPlaceStatus.FAILED
    assert result.failure_stage == "exit"
    assert result.telemetry["cleanup_succeeded"] is False


def test_cli_board_transport_go_home_runs_board_python_command():
    runner = StubRunner(
        [
            CommandResult(exit_code=0, stdout="ok\n", stderr="", timed_out=False, duration_ms=50),
        ]
    )
    transport = CliBoardTransport(runner=runner, config=CliBoardTransportConfig())

    result = transport.go_home()

    assert result["final_pose_summary"] == "home"
    assert result["motion_executed"] is True
    assert "python3 -c" in runner.commands[0][0]
    assert "bus_servo_control.set_servos" in runner.commands[0][0]


def test_cli_board_transport_set_gripper_uses_guarded_servo_10_positions():
    runner = StubRunner(
        [
            CommandResult(exit_code=0, stdout="ok\n", stderr="", timed_out=False, duration_ms=40),
            CommandResult(exit_code=0, stdout="ok\n", stderr="", timed_out=False, duration_ms=40),
        ]
    )
    transport = CliBoardTransport(
        runner=runner,
        config=CliBoardTransportConfig(gripper_open_position=200, gripper_closed_position=500),
    )

    open_result = transport.set_gripper(opened=True)
    close_result = transport.set_gripper(opened=False)

    assert open_result["gripper_state"] == "open"
    assert close_result["gripper_state"] == "closed"
    assert "(10, 200)" in runner.commands[0][0]
    assert "(10, 500)" in runner.commands[1][0]


def test_cli_board_transport_stop_all_uses_workflow_exit_semantics():
    runner = StubRunner(
        [
            CommandResult(exit_code=0, stdout="disable ok", stderr="", timed_out=False, duration_ms=20),
            CommandResult(exit_code=0, stdout="unset ok", stderr="", timed_out=False, duration_ms=20),
            CommandResult(exit_code=0, stdout="exit ok", stderr="", timed_out=False, duration_ms=20),
        ]
    )
    transport = CliBoardTransport(runner=runner, config=CliBoardTransportConfig())

    result = transport.stop_all()

    assert result["stop_scope"] == "workflow_exit_only"
    assert result["continue_ready"] is True
    assert len(result["stage_results"]) == 3
    assert "/object_sortting/enable_sortting" in runner.commands[0][0]


def test_cli_board_transport_recover_runs_stop_then_go_home_sequence():
    runner = StubRunner(
        [
            CommandResult(exit_code=0, stdout="disable ok", stderr="", timed_out=False, duration_ms=20),
            CommandResult(exit_code=0, stdout="unset ok", stderr="", timed_out=False, duration_ms=20),
            CommandResult(exit_code=0, stdout="exit ok", stderr="", timed_out=False, duration_ms=20),
            CommandResult(exit_code=0, stdout="ok\n", stderr="", timed_out=False, duration_ms=50),
        ]
    )
    transport = CliBoardTransport(runner=runner, config=CliBoardTransportConfig())

    result = transport.recover()

    assert result["continue_ready"] is True
    assert result["recovery_actions"] == ["stop_all", "go_home"]
    assert "/object_sortting/exit" in runner.commands[2][0]
    assert "bus_servo_control.set_servos" in runner.commands[3][0]


def test_cli_board_transport_observe_scene_returns_structured_targets_for_fixed_scene():
    runner = StubRunner(
        [
            CommandResult(
                exit_code=0,
                stdout='{"detected": true, "observed_at": "2026-04-02T08:00:00+00:00", "pose": [0.181, 0.024, 0.012], "raw_pose": [0.181, 0.024, 0.012], "align_angle": -3.5, "confidence": 0.94}\n',
                stderr="",
                timed_out=False,
                duration_ms=120,
            ),
        ]
    )
    transport = CliBoardTransport(runner=runner, config=CliBoardTransportConfig())

    observed = transport.observe_scene(build_request().profile)

    assert len(observed) == 1
    assert observed[0].entity_id == "red-color_block-1"
    assert observed[0].object_class == "color_block"
    assert observed[0].color == "red"
    assert observed[0].confidence == 0.94
    assert observed[0].source_timestamp == datetime(2026, 4, 2, 8, 0, tzinfo=timezone.utc)
    assert observed[0].pose["frame"] == "base_link"
    assert observed[0].pose["align_angle"] == -3.5
    assert "color_detection_base" in runner.commands[0][0]


def test_cli_board_transport_observe_scene_returns_empty_when_no_target_detected():
    runner = StubRunner(
        [
            CommandResult(
                exit_code=0,
                stdout='{"detected": false, "observed_at": "2026-04-02T08:00:00+00:00", "confidence": 0.0}\n',
                stderr="",
                timed_out=False,
                duration_ms=120,
            ),
        ]
    )
    transport = CliBoardTransport(runner=runner, config=CliBoardTransportConfig())

    observed = transport.observe_scene(build_request().profile)

    assert observed == []
