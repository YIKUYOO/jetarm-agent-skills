from __future__ import annotations

import json
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from jetarm_agent.adapter import Phase2BoardAdapter
from jetarm_agent.agent_protocol import (
    RobotToolCall,
    RobotToolMode,
    RobotToolResult,
    RobotToolRiskLevel,
    RobotToolSpec,
    RobotToolTranscriptEntry,
)
from jetarm_agent.cli_transport import CliBoardTransportConfig, CommandRunner
from jetarm_agent.schemas import CalibrationProfile, PickPlaceRequest
from jetarm_agent.skill_contract import (
    DetectTargetRequest,
    GoHomeRequest,
    GripperRequest,
    RecoverRequest,
    StopRequest,
)


ToolHandler = Callable[[dict[str, Any], RobotToolCall], RobotToolResult]


class RobotToolRegistry:
    def __init__(
        self,
        *,
        adapter: Phase2BoardAdapter | None = None,
        runner: CommandRunner | None = None,
        ros_setup_command: str | None = None,
        default_profile: CalibrationProfile | None = None,
        transcript_path: Path | None = None,
    ):
        self.adapter = adapter
        self.runner = runner
        self.ros_setup_command = ros_setup_command or CliBoardTransportConfig().ros_setup_command
        self.default_profile = default_profile
        self.transcript_path = transcript_path
        self._specs: dict[str, RobotToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self.transcript: list[RobotToolTranscriptEntry] = []
        self._register_builtin_tools()

    def list_tools(self) -> list[RobotToolSpec]:
        return sorted(self._specs.values(), key=lambda spec: spec.name)

    def call(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        *,
        session_id: str = "default",
        mode: RobotToolMode | str | None = None,
    ) -> RobotToolResult:
        if tool_name not in self._specs:
            return RobotToolResult(
                ok=False,
                stage="dispatch",
                error_code="UNKNOWN_TOOL",
                next_recovery_hint="Call list_tools and choose one registered JetArm tool.",
            )
        spec = self._specs[tool_name]
        call = RobotToolCall(
            tool_name=tool_name,
            args=args or {},
            session_id=session_id,
            mode=RobotToolMode(mode) if mode else spec.default_mode,
            risk_level=spec.risk_level,
            operator_visible_summary=f"{spec.group}.{tool_name}: {spec.description}",
        )
        try:
            result = self._handlers[tool_name](call.args, call)
        except ValidationError as exc:
            result = RobotToolResult(
                ok=False,
                stage="schema",
                error_code="INVALID_TOOL_ARGUMENTS",
                stderr=str(exc),
                next_recovery_hint="Repair the tool arguments to match the JetArm schema.",
            )
        except Exception as exc:
            result = RobotToolResult(
                ok=False,
                stage="runtime",
                error_code="TOOL_RUNTIME_ERROR",
                stderr=str(exc),
                next_recovery_hint="Inspect the transcript and call stop_all or recover if motion may be active.",
            )
        self._record(call, result)
        return result

    def _register(self, spec: RobotToolSpec, handler: ToolHandler) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def _register_builtin_tools(self) -> None:
        self._register(
            RobotToolSpec(
                name="list_tools",
                group="robot_safe_tools",
                description="List the JetArm tools available to the agent.",
                default_mode=RobotToolMode.SAFE,
                risk_level=RobotToolRiskLevel.LOW,
            ),
            self._list_tools,
        )
        self._register_safe("observe_scene", "Observe the current workcell through the board adapter.", self._observe_scene)
        self._register_safe("detect_target", "Detect one structured target with adapter-safe filters.", self._detect_target)
        self._register_safe("go_home", "Move JetArm to the adapter home pose.", self._go_home, RobotToolRiskLevel.HIGH)
        self._register_safe("open_gripper", "Open the JetArm gripper through the guarded adapter path.", self._open_gripper, RobotToolRiskLevel.HIGH)
        self._register_safe("close_gripper", "Close the JetArm gripper through the guarded adapter path.", self._close_gripper, RobotToolRiskLevel.HIGH)
        self._register_safe("pick_place", "Run the canonical fixed-scene pick/place workflow.", self._pick_place, RobotToolRiskLevel.CRITICAL)
        self._register_safe("recover", "Run stop and recovery through adapter-safe semantics.", self._recover, RobotToolRiskLevel.HIGH)
        self._register_safe("stop_all", "Interrupt active motion/workflows with highest priority.", self._stop_all, RobotToolRiskLevel.CRITICAL)
        self._register_raw("shell", "Run an unrestricted shell command on the agent host.", self._shell)
        self._register_raw("rosrun", "Run rosrun inside the configured JetArm ROS environment.", self._rosrun)
        self._register_raw("roslaunch", "Run roslaunch inside the configured JetArm ROS environment.", self._roslaunch)
        self._register_raw("rostopic", "Run rostopic inside the configured JetArm ROS environment.", self._rostopic)
        self._register_raw("rosservice", "Run rosservice inside the configured JetArm ROS environment.", self._rosservice)
        self._register_raw("python_script", "Execute an arbitrary Python script through python3.", self._python_script)
        self._register_raw("servo_debug", "Run raw servo debug Python against JetArm SDK.", self._servo_debug)

    def _register_safe(
        self,
        name: str,
        description: str,
        handler: ToolHandler,
        risk_level: RobotToolRiskLevel = RobotToolRiskLevel.MEDIUM,
    ) -> None:
        self._register(
            RobotToolSpec(
                name=name,
                group="robot_safe_tools",
                description=description,
                default_mode=RobotToolMode.LIVE if risk_level in {RobotToolRiskLevel.HIGH, RobotToolRiskLevel.CRITICAL} else RobotToolMode.SAFE,
                risk_level=risk_level,
            ),
            handler,
        )

    def _register_raw(self, name: str, description: str, handler: ToolHandler) -> None:
        self._register(
            RobotToolSpec(
                name=name,
                group="robot_raw_tools",
                description=description,
                default_mode=RobotToolMode.FULL_CONTROL,
                risk_level=RobotToolRiskLevel.CRITICAL,
            ),
            handler,
        )

    def _require_adapter(self) -> Phase2BoardAdapter:
        if self.adapter is None:
            raise RuntimeError("Phase2BoardAdapter is not configured")
        return self.adapter

    def _require_runner(self) -> CommandRunner:
        if self.runner is None:
            raise RuntimeError("CommandRunner is not configured")
        return self.runner

    def _record(self, call: RobotToolCall, result: RobotToolResult) -> None:
        entry = RobotToolTranscriptEntry(call=call, result=result)
        self.transcript.append(entry)
        if self.transcript_path is None:
            return
        self.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        with self.transcript_path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")

    def _skill_result(self, stage: str, payload) -> RobotToolResult:
        return RobotToolResult(
            ok=payload.status.value == "succeeded",
            stage=stage,
            motion_executed=stage in {"go_home", "open_gripper", "close_gripper", "pick_place", "recover", "stop_all"}
            and payload.status.value == "succeeded",
            telemetry=payload.telemetry,
            artifacts=payload.artifacts,
            error_code=payload.error_code.value if payload.error_code else None,
            stdout=payload.message,
            next_recovery_hint=None if payload.status.value == "succeeded" else "Inspect adapter telemetry; call stop_all or recover before retrying.",
        )

    def _list_tools(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        return RobotToolResult(
            ok=True,
            stage="list_tools",
            telemetry={"tools": [spec.model_dump(mode="json") for spec in self.list_tools()]},
        )

    def _observe_scene(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        profile = args.get("profile") or self.default_profile
        if profile is None:
            raise ValueError("profile is required")
        profile = CalibrationProfile.model_validate(profile)
        observed = self._require_adapter().observe_scene(profile)
        return RobotToolResult(
            ok=True,
            stage="observe_scene",
            telemetry={"targets": [target.model_dump(mode="json") for target in observed]},
        )

    def _detect_target(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        if "profile" not in args and self.default_profile is not None:
            args = {**args, "profile": self.default_profile.model_dump(mode="json")}
        request = DetectTargetRequest.model_validate(args)
        return self._skill_result("detect_target", self._require_adapter().detect_target(request))

    def _go_home(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        return self._skill_result("go_home", self._require_adapter().go_home(GoHomeRequest.model_validate(args or {})))

    def _open_gripper(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        return self._skill_result("open_gripper", self._require_adapter().open_gripper(GripperRequest.model_validate(args or {})))

    def _close_gripper(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        return self._skill_result("close_gripper", self._require_adapter().close_gripper(GripperRequest.model_validate(args or {})))

    def _pick_place(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        request = PickPlaceRequest.model_validate(args)
        result = self._require_adapter().execute_pick_place(request)
        return RobotToolResult(
            ok=result.status.value == "succeeded",
            stage=result.failure_stage or "pick_place",
            motion_executed=result.status.value == "succeeded",
            telemetry=result.telemetry,
            artifacts=result.artifacts,
            error_code=None if result.status.value == "succeeded" else result.status.value.upper(),
            next_recovery_hint=None if result.status.value == "succeeded" else "Call stop_all, inspect artifacts, then recover before retrying.",
        )

    def _recover(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        return self._skill_result("recover", self._require_adapter().recover(RecoverRequest.model_validate(args or {})))

    def _stop_all(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        return self._skill_result("stop_all", self._require_adapter().stop_all(StopRequest.model_validate(args or {})))

    def _shell(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        command = str(args.get("command", "")).strip()
        if not command:
            raise ValueError("command is required")
        return self._run_command(command, args, stage="shell")

    def _rosrun(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        package = str(args.get("package", "")).strip()
        executable = str(args.get("executable", "")).strip()
        extra_args = str(args.get("args", "")).strip()
        if not package or not executable:
            raise ValueError("package and executable are required")
        command = f"{self.ros_setup_command} && rosrun {shlex.quote(package)} {shlex.quote(executable)} {extra_args}".strip()
        return self._run_command(command, args, stage="rosrun")

    def _roslaunch(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        package = str(args.get("package", "")).strip()
        launch_file = str(args.get("launch_file", "")).strip()
        extra_args = str(args.get("args", "")).strip()
        if not package or not launch_file:
            raise ValueError("package and launch_file are required")
        command = f"{self.ros_setup_command} && roslaunch {shlex.quote(package)} {shlex.quote(launch_file)} {extra_args}".strip()
        return self._run_command(command, args, stage="roslaunch")

    def _rostopic(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        rostopic_args = str(args.get("args", "")).strip()
        if not rostopic_args:
            raise ValueError("args is required")
        return self._run_command(f"{self.ros_setup_command} && rostopic {rostopic_args}", args, stage="rostopic")

    def _rosservice(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        rosservice_args = str(args.get("args", "")).strip()
        if not rosservice_args:
            raise ValueError("args is required")
        return self._run_command(f"{self.ros_setup_command} && rosservice {rosservice_args}", args, stage="rosservice")

    def _python_script(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        script = str(args.get("script", "")).strip()
        if not script:
            raise ValueError("script is required")
        command = f"python3 -c {shlex.quote(script)}"
        if args.get("with_ros", False):
            command = f"{self.ros_setup_command} && {command}"
        return self._run_command(command, args, stage="python_script")

    def _servo_debug(self, args: dict[str, Any], call: RobotToolCall) -> RobotToolResult:
        servo_id = int(args.get("servo_id"))
        position = int(args.get("position"))
        duration_ms = int(args.get("duration_ms", 500))
        script = f"""
import rospy
from hiwonder_interfaces.msg import MultiRawIdPosDur
from jetarm_sdk import bus_servo_control
rospy.init_node('jetarm_agent_full_control_servo_debug', anonymous=True, disable_signals=True, log_level=rospy.ERROR)
pub = rospy.Publisher('/controllers/multi_id_pos_dur', MultiRawIdPosDur, queue_size=1)
rospy.sleep(0.5)
bus_servo_control.set_servos(pub, {duration_ms}, (({servo_id}, {position}),))
rospy.sleep(max({duration_ms} / 1000.0, 0.5))
print('ok')
        """.strip()
        return self._run_command(
            f"{self.ros_setup_command} && python3 -c {shlex.quote(script)}",
            args,
            stage="servo_debug",
            motion_executed=True,
        )

    def _run_command(
        self,
        command: str,
        args: dict[str, Any],
        *,
        stage: str,
        motion_executed: bool = False,
    ) -> RobotToolResult:
        timeout_seconds = int(args.get("timeout_seconds", 20))
        result = self._require_runner().run(command, timeout_seconds=timeout_seconds)
        ok = result.exit_code == 0 and not result.timed_out
        return RobotToolResult(
            ok=ok,
            stage=stage,
            motion_executed=motion_executed,
            stdout=result.stdout,
            stderr=result.stderr,
            telemetry={
                "command": command,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "duration_ms": result.duration_ms,
            },
            error_code=None if ok else "COMMAND_FAILED",
            next_recovery_hint=None if ok else "Read stdout/stderr. If robot motion may be active, call stop_all.",
        )


def render_tool_result(result: RobotToolResult) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
