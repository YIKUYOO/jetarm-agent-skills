from __future__ import annotations

import argparse
import shlex
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from jetarm_agent.baseline.supervised_validation import ValidatedActionName, build_supervised_validation_specs


class BoardSessionMode(str, Enum):
    LOCAL_SHELL = "local_shell"
    SSH_SHELL = "ssh_shell"


class BoardActionStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class PickPlaceFailureStage(str, Enum):
    ENTER = "enter"
    DETECT = "detect"
    GRASP = "grasp"
    PLACE = "place"
    EXIT = "exit"


class BoardSessionAction(BaseModel):
    action_name: ValidatedActionName
    command_templates: list[str]
    evidence_requirements: list[str]
    pass_criteria: list[str]
    stop_on_failure: bool = True
    subcases: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class BoardSessionManifest(BaseModel):
    session_id: str
    board_target: str
    mode: BoardSessionMode
    actions: list[BoardSessionAction]
    operator_checklist: list[str]
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class BoardActionResult(BaseModel):
    action_name: ValidatedActionName
    status: BoardActionStatus = BoardActionStatus.PENDING
    observed_behavior: str = ""
    failure_stage: PickPlaceFailureStage | None = None
    command_outputs: list[str] = Field(default_factory=list)
    operator_notes: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class BoardSessionResult(BaseModel):
    session_id: str
    board_target: str
    mode: BoardSessionMode
    overall_status: BoardActionStatus = BoardActionStatus.PENDING
    action_results: list[BoardActionResult]
    blocked_reason: str | None = None
    artifacts: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


def _wrap_command(mode: BoardSessionMode, board_target: str, command: str) -> str:
    if mode is BoardSessionMode.SSH_SHELL:
        return f"ssh {board_target} {shlex.quote(command)}"
    return command


def _command_templates_for(
    action_name: ValidatedActionName,
    *,
    board_target: str,
    mode: BoardSessionMode,
) -> list[str]:
    templates_by_action = {
        ValidatedActionName.GO_HOME: [
            "source ~/jetarm/devel/setup.bash && python3 ~/jetarm/src/jetarm_6dof/jetarm_6dof_app/scripts/actions.py  # call the official go_home entrypoint confirmed onsite",
        ],
        ValidatedActionName.OPEN_GRIPPER: [
            "source ~/jetarm/devel/setup.bash && rostopic pub --once /jetarm_sdk/serial_servo/move <servo_move_msg_with_id_10_and_guarded_open_values>",
        ],
        ValidatedActionName.CLOSE_GRIPPER: [
            "source ~/jetarm/devel/setup.bash && rostopic pub --once /jetarm_sdk/serial_servo/move <servo_move_msg_with_id_10_and_guarded_close_values>",
        ],
        ValidatedActionName.STOP_ALL: [
            "source ~/jetarm/devel/setup.bash && rostopic pub --once /jetarm_sdk/serial_servo/stop <servo_stop_msg>",
            "source ~/jetarm/devel/setup.bash && rosservice call /object_sortting/enable_sortting \"data: false\" && rosservice call /object_sortting/exit",
        ],
        ValidatedActionName.PICK_PLACE: [
            "source ~/jetarm/devel/setup.bash && rosservice call /object_sortting/enter",
            "source ~/jetarm/devel/setup.bash && rosservice call /object_sortting/set_color_target \"data_str: 'red' data_bool: true\"",
            "source ~/jetarm/devel/setup.bash && rosservice call /object_sortting/enable_sortting \"data: true\"",
            "source ~/jetarm/devel/setup.bash && timeout 90 rostopic echo -n 2 /grasp/result",
            "source ~/jetarm/devel/setup.bash && rosservice call /object_sortting/enable_sortting \"data: false\"",
            "source ~/jetarm/devel/setup.bash && rosservice call /object_sortting/set_color_target \"data_str: 'red' data_bool: false\"",
            "source ~/jetarm/devel/setup.bash && rosservice call /object_sortting/exit",
        ],
    }
    return [_wrap_command(mode, board_target, command) for command in templates_by_action[action_name]]


def _operator_checklist() -> list[str]:
    return [
        "现场有人值守，并已准备好随时断电或接管机械臂。",
        "机械臂工作区已清空，目标物体与目标区域已按当前用例摆放。",
        "官方 bringup、相机、运动学、抓取与目标任务流节点已在线。",
        "本轮只按 manifest 顺序执行，不跳步、不连跑高风险动作。",
    ]


def build_board_session_manifest(
    *,
    session_id: str,
    board_target: str,
    mode: BoardSessionMode,
) -> BoardSessionManifest:
    specs = build_supervised_validation_specs()
    ordered_actions = [
        ValidatedActionName.GO_HOME,
        ValidatedActionName.OPEN_GRIPPER,
        ValidatedActionName.CLOSE_GRIPPER,
        ValidatedActionName.STOP_ALL,
        ValidatedActionName.PICK_PLACE,
    ]
    actions = []
    for action_name in ordered_actions:
        spec = specs[action_name]
        subcases = []
        if action_name is ValidatedActionName.STOP_ALL:
            subcases = ["single_action_interrupt", "task_flow_interrupt"]
        actions.append(
            BoardSessionAction(
                action_name=action_name,
                command_templates=_command_templates_for(action_name, board_target=board_target, mode=mode),
                evidence_requirements=spec.artifacts_required,
                pass_criteria=spec.success_criteria,
                stop_on_failure=True,
                subcases=subcases,
            )
        )
    return BoardSessionManifest(
        session_id=session_id,
        board_target=board_target,
        mode=mode,
        actions=actions,
        operator_checklist=_operator_checklist(),
        created_at=datetime.now(UTC),
    )


def initialize_board_session_result(manifest: BoardSessionManifest) -> BoardSessionResult:
    return BoardSessionResult(
        session_id=manifest.session_id,
        board_target=manifest.board_target,
        mode=manifest.mode,
        overall_status=BoardActionStatus.PENDING,
        action_results=[
            BoardActionResult(action_name=action.action_name)
            for action in manifest.actions
        ],
    )


def _compute_overall_status(result: BoardSessionResult) -> BoardActionStatus:
    statuses = {item.status for item in result.action_results}
    if BoardActionStatus.FAILED in statuses:
        return BoardActionStatus.FAILED
    if statuses == {BoardActionStatus.PASSED}:
        return BoardActionStatus.PASSED
    if BoardActionStatus.BLOCKED in statuses:
        return BoardActionStatus.BLOCKED
    return BoardActionStatus.PENDING


def record_board_action_result(
    result: BoardSessionResult,
    *,
    action_name: ValidatedActionName,
    status: BoardActionStatus,
    observed_behavior: str,
    command_outputs: list[str] | None = None,
    operator_notes: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    failure_stage: PickPlaceFailureStage | None = None,
) -> BoardSessionResult:
    updated_results: list[BoardActionResult] = []
    block_following = False
    blocked_reason = result.blocked_reason
    for item in result.action_results:
        if block_following and item.status is BoardActionStatus.PENDING:
            updated_results.append(
                item.model_copy(
                    update={
                        "status": BoardActionStatus.BLOCKED,
                        "blocked_reason": blocked_reason or f"blocked after {action_name.value} failed",
                    }
                )
            )
            continue
        if item.action_name is action_name:
            updated_item = item.model_copy(
                update={
                    "status": status,
                    "observed_behavior": observed_behavior,
                    "failure_stage": failure_stage,
                    "command_outputs": command_outputs or [],
                    "operator_notes": operator_notes or [],
                    "artifact_refs": artifact_refs or [],
                    "blocked_reason": None,
                }
            )
            updated_results.append(updated_item)
            if status is BoardActionStatus.FAILED:
                blocked_reason = f"blocked after {action_name.value} failed"
                block_following = True
            continue
        updated_results.append(item)

    updated = result.model_copy(
        update={
            "action_results": updated_results,
            "blocked_reason": blocked_reason,
        }
    )
    return updated.model_copy(update={"overall_status": _compute_overall_status(updated)})


def render_board_session_runbook(manifest: BoardSessionManifest) -> str:
    lines = [
        "# Board Validation Session Runbook",
        "",
        f"- Session ID: `{manifest.session_id}`",
        f"- Board target: `{manifest.board_target}`",
        f"- Mode: `{manifest.mode.value}`",
        "",
        "## Operator Checklist",
        "",
        *[f"- {item}" for item in manifest.operator_checklist],
        "",
    ]
    for action in manifest.actions:
        lines.extend(
            [
                f"## {action.action_name.value}",
                "",
                "### Command Templates",
                "",
                *[f"- `{command}`" for command in action.command_templates],
                "",
                "### Evidence Requirements",
                "",
                *[f"- {item}" for item in action.evidence_requirements],
                "",
                "### Pass Criteria",
                "",
                *[f"- {item}" for item in action.pass_criteria],
                "",
            ]
        )
        if action.subcases:
            lines.extend(
                [
                    "### Subcases",
                    "",
                    *[f"- `{item}`" for item in action.subcases],
                    "",
                ]
            )
    return "\n".join(lines).strip() + "\n"


def render_board_session_result_markdown(result: BoardSessionResult) -> str:
    lines = [
        "# Board Validation Session Result",
        "",
        f"- Session ID: `{result.session_id}`",
        f"- Board target: `{result.board_target}`",
        f"- Overall status: `{result.overall_status.value}`",
        "",
    ]
    for item in result.action_results:
        lines.extend(
            [
                f"## {item.action_name.value}",
                "",
                f"- Status: `{item.status.value}`",
                f"- Observed behavior: {item.observed_behavior or 'pending'}",
                f"- Failure stage: `{item.failure_stage.value if item.failure_stage else 'n/a'}`",
                *[f"- Operator note: {note}" for note in item.operator_notes],
                *[f"- Artifact: {ref}" for ref in item.artifact_refs],
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _read_result(path: Path) -> BoardSessionResult:
    return BoardSessionResult.model_validate_json(path.read_text(encoding="utf-8"))


def _write_text(path: str | None, payload: str) -> None:
    if path:
        Path(path).write_text(payload, encoding="utf-8")


def cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-session", action="store_true")
    parser.add_argument("--record-result", action="store_true")
    parser.add_argument("--print-command", action="store_true")
    parser.add_argument("--session-id", default="board-session")
    parser.add_argument("--board-target", default="localhost")
    parser.add_argument(
        "--mode",
        default=BoardSessionMode.LOCAL_SHELL.value,
        choices=[item.value for item in BoardSessionMode],
    )
    parser.add_argument("--action", choices=[item.value for item in ValidatedActionName])
    parser.add_argument("--status", choices=[item.value for item in BoardActionStatus])
    parser.add_argument("--failure-stage", choices=[item.value for item in PickPlaceFailureStage])
    parser.add_argument("--observed-behavior", default="")
    parser.add_argument("--command-output", action="append")
    parser.add_argument("--operator-note", action="append")
    parser.add_argument("--artifact-ref", action="append")
    parser.add_argument("--manifest-json")
    parser.add_argument("--runbook-md")
    parser.add_argument("--result-json")
    parser.add_argument("--result-md")
    args = parser.parse_args(argv)

    mode = BoardSessionMode(args.mode)

    if args.plan_session:
        manifest = build_board_session_manifest(
            session_id=args.session_id,
            board_target=args.board_target,
            mode=mode,
        )
        result = initialize_board_session_result(manifest)
        manifest_json = manifest.model_dump_json(indent=2)
        result_json = result.model_dump_json(indent=2)
        runbook = render_board_session_runbook(manifest)
        _write_text(args.manifest_json, manifest_json)
        _write_text(args.runbook_md, runbook)
        _write_text(args.result_json, result_json)
        if args.result_md:
            _write_text(args.result_md, render_board_session_result_markdown(result))
        if not args.manifest_json and not args.runbook_md and not args.result_json and not args.result_md:
            print(runbook)
        return 0

    if args.print_command:
        if not args.action:
            parser.error("--action is required with --print-command")
        manifest = build_board_session_manifest(
            session_id=args.session_id,
            board_target=args.board_target,
            mode=mode,
        )
        selected = next(action for action in manifest.actions if action.action_name.value == args.action)
        print("\n".join(selected.command_templates))
        return 0

    if args.record_result:
        if not args.result_json:
            parser.error("--result-json is required with --record-result")
        if not args.action or not args.status:
            parser.error("--action and --status are required with --record-result")
        result_path = Path(args.result_json)
        result = _read_result(result_path)
        updated = record_board_action_result(
            result,
            action_name=ValidatedActionName(args.action),
            status=BoardActionStatus(args.status),
            observed_behavior=args.observed_behavior,
            command_outputs=args.command_output,
            operator_notes=args.operator_note,
            artifact_refs=args.artifact_ref,
            failure_stage=PickPlaceFailureStage(args.failure_stage) if args.failure_stage else None,
        )
        result_path.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
        if args.result_md:
            _write_text(args.result_md, render_board_session_result_markdown(updated))
        return 0

    parser.error("one of --plan-session, --record-result, or --print-command is required")
