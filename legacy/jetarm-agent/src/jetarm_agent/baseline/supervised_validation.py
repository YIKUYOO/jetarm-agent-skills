from __future__ import annotations

import argparse
import sys
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ValidatedActionName(str, Enum):
    GO_HOME = "go_home"
    OPEN_GRIPPER = "open_gripper"
    CLOSE_GRIPPER = "close_gripper"
    STOP_ALL = "stop_all"
    PICK_PLACE = "pick_place"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ValidationEvidenceBundle(BaseModel):
    command_hints: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    operator_notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SupervisedValidationStep(BaseModel):
    description: str
    expected_result: str

    model_config = ConfigDict(extra="forbid")


class SupervisedValidationSpec(BaseModel):
    action_name: ValidatedActionName
    official_entrypoints: list[str]
    safety_preconditions: list[str]
    success_criteria: list[str]
    command_hints: list[str]
    steps: list[SupervisedValidationStep]
    artifacts_required: list[str]
    notes: str = ""

    model_config = ConfigDict(extra="forbid")


class ValidationOutcome(BaseModel):
    action_name: ValidatedActionName
    official_entrypoints: list[str]
    status: ValidationStatus = ValidationStatus.PENDING
    safety_preconditions: list[str]
    observed_behavior: str = ""
    failure_mode: str | None = None
    artifacts: ValidationEvidenceBundle = Field(default_factory=ValidationEvidenceBundle)

    model_config = ConfigDict(extra="forbid")


def build_supervised_validation_specs() -> dict[ValidatedActionName, SupervisedValidationSpec]:
    return {
        ValidatedActionName.GO_HOME: SupervisedValidationSpec(
            action_name=ValidatedActionName.GO_HOME,
            official_entrypoints=[
                "jetarm_6dof_app/scripts/actions.py",
                "/controllers/multi_id_pos_dur",
            ],
            safety_preconditions=[
                "现场有人值守，可立即断电或接管机械臂。",
                "机械臂工作区无障碍物，夹爪为空载。",
                "当前板端已进入官方 bringup 且控制节点在线。",
            ],
            success_criteria=[
                "机械臂稳定回到官方初始位姿。",
                "连续 3 次执行结果一致，无异常抖动或偏差扩散。",
            ],
            command_hints=[
                "运行官方 actions.py 对应的 go_home 封装，而不是直接发底层舵机 topic。",
                "必要时抓取 /controllers/multi_id_pos_dur 的观测日志作为底层证据。",
            ],
            steps=[
                SupervisedValidationStep(
                    description="确认 official bringup 与控制节点在线，清空机械臂工作区。",
                    expected_result="系统可接受官方动作指令，现场安全条件满足。",
                ),
                SupervisedValidationStep(
                    description="执行 go_home 一次并记录起止位姿与耗时。",
                    expected_result="机械臂回到初始位姿，无碰撞或明显抖动。",
                ),
                SupervisedValidationStep(
                    description="重复执行至少 2 次，比较结果一致性。",
                    expected_result="重复动作收敛且行为稳定。",
                ),
            ],
            artifacts_required=[
                "现场操作记录",
                "动作开始/结束时间",
                "必要的板端日志片段",
            ],
            notes="正式 adapter 的 go_home 必须建立在官方动作封装之上。",
        ),
        ValidatedActionName.OPEN_GRIPPER: SupervisedValidationSpec(
            action_name=ValidatedActionName.OPEN_GRIPPER,
            official_entrypoints=[
                "gripper servo semantics on servo id 10",
                "/jetarm_sdk/serial_servo/move",
            ],
            safety_preconditions=[
                "现场有人值守，夹爪前方无被动碰撞物。",
                "使用 guarded 范围，不直接暴露原始舵机参数给上层。",
            ],
            success_criteria=[
                "夹爪张开到目标范围，动作可重复且不过冲。",
                "连续 3 次动作无卡滞、异响或超程。",
            ],
            command_hints=[
                "通过 adapter 内部 guarded 封装驱动 10 号舵机语义。",
                "同时记录底层舵机目标值和持续时间作为证据。",
            ],
            steps=[
                SupervisedValidationStep(
                    description="从安全闭合或中立状态执行 open_gripper。",
                    expected_result="夹爪张开到预期范围，没有碰撞或过冲。",
                ),
                SupervisedValidationStep(
                    description="重复执行并观察张开范围和时间。",
                    expected_result="动作稳定且范围可重复。",
                ),
            ],
            artifacts_required=[
                "夹爪范围记录",
                "操作员观察记录",
            ],
            notes="原始舵机 topic 仅作为 adapter 内部实现依据。",
        ),
        ValidatedActionName.CLOSE_GRIPPER: SupervisedValidationSpec(
            action_name=ValidatedActionName.CLOSE_GRIPPER,
            official_entrypoints=[
                "gripper servo semantics on servo id 10",
                "/jetarm_sdk/serial_servo/move",
            ],
            safety_preconditions=[
                "现场有人值守，夹爪闭合路径无遮挡。",
                "空载优先验证，再做轻载夹持测试。",
            ],
            success_criteria=[
                "夹爪闭合到目标范围，没有卡滞和持续顶死。",
                "连续 3 次动作可重复。",
            ],
            command_hints=[
                "通过 guarded gripper wrapper 驱动 10 号舵机闭合语义。",
                "记录底层目标值、持续时间和任何异常声响。",
            ],
            steps=[
                SupervisedValidationStep(
                    description="执行 close_gripper 并记录闭合范围。",
                    expected_result="夹爪平稳闭合，没有过载迹象。",
                ),
                SupervisedValidationStep(
                    description="必要时加入轻载目标做一次夹持验证。",
                    expected_result="夹持成功或明确暴露失败模式。",
                ),
            ],
            artifacts_required=[
                "夹爪闭合范围记录",
                "轻载夹持结果",
            ],
            notes="若闭合范围不稳定，正式 adapter 不得冻结。",
        ),
        ValidatedActionName.STOP_ALL: SupervisedValidationSpec(
            action_name=ValidatedActionName.STOP_ALL,
            official_entrypoints=[
                "/jetarm_sdk/serial_servo/stop",
                "official stop or exit flow when present",
                "/object_sortting/exit",
            ],
            safety_preconditions=[
                "现场有人值守，验证前先约定中断手势和断电方案。",
                "仅在单动作和任务流两类场景下分别测试，不连续叠加高风险动作。",
            ],
            success_criteria=[
                "正在执行的动作可被中断或进入受控停止状态。",
                "任务流退出后系统状态明确，可重新进入下一轮验证。",
            ],
            command_hints=[
                "优先验证官方 stop 或 exit 语义；底层 stop topic 只作为内部回退依据。",
                "分别记录单动作中断和任务流中断的效果差异。",
            ],
            steps=[
                SupervisedValidationStep(
                    description="在 go_home 或夹爪动作执行中触发 stop_all。",
                    expected_result="动作停止或进入受控停止状态。",
                ),
                SupervisedValidationStep(
                    description="在官方任务流中触发 stop_all 或 exit。",
                    expected_result="任务流终止且系统可恢复到下一轮验证状态。",
                ),
            ],
            artifacts_required=[
                "中断前后状态记录",
                "stop 或 exit 调用证据",
            ],
            notes="如果不同任务流的中断语义不一致，adapter 内必须做统一封装。",
        ),
        ValidatedActionName.PICK_PLACE: SupervisedValidationSpec(
            action_name=ValidatedActionName.PICK_PLACE,
            official_entrypoints=[
                "positioning_clamp.launch",
                "color_sorting.launch",
                "/object_sortting/enable_sortting",
                "/object_sortting/set_color_target",
                "/grasp",
            ],
            safety_preconditions=[
                "现场有人值守，验证前完成相机、坐标和工作区基础检查。",
                "先单轮验证，不启用长时间连续任务流。",
                "目标物体和目标区域符合官方示例约束。",
            ],
            success_criteria=[
                "完成一次完整的观察、定位、抓取、放置。",
                "明确记录进入条件、退出条件、失败阶段和恢复方式。",
            ],
            command_hints=[
                "优先走官方 positioning_clamp 或 color_sorting 任务流。",
                "若走 object_sortting 模式，记录 enable、target 设置、/grasp 调用和 exit 顺序。",
            ],
            steps=[
                SupervisedValidationStep(
                    description="确认相机画面、目标物体和目标区域准备完成。",
                    expected_result="系统进入可执行单轮抓放的已知场景。",
                ),
                SupervisedValidationStep(
                    description="执行一次单轮 pick_place，并记录进入与退出语义。",
                    expected_result="完成单轮抓放或暴露清晰的失败阶段。",
                ),
                SupervisedValidationStep(
                    description="在失败时记录恢复步骤，避免直接重启为唯一恢复手段。",
                    expected_result="得到可用于正式 adapter 的失败模式结论。",
                ),
            ],
            artifacts_required=[
                "单轮任务流日志",
                "失败阶段记录",
                "恢复步骤记录",
            ],
            notes="正式 mainline pick_place 只能建立在官方任务流层，不得直接拼底层舵机和 kinematics service。",
        ),
    }


def build_validation_outcomes(actions: list[ValidatedActionName]) -> list[ValidationOutcome]:
    specs = build_supervised_validation_specs()
    return [
        ValidationOutcome(
            action_name=action,
            official_entrypoints=specs[action].official_entrypoints,
            safety_preconditions=specs[action].safety_preconditions,
            artifacts=ValidationEvidenceBundle(command_hints=specs[action].command_hints),
        )
        for action in actions
    ]


def render_supervised_validation_protocol(specs: list[SupervisedValidationSpec]) -> str:
    sections: list[str] = [
        "# Supervised Board Validation Protocol",
        "",
        "- 现场有人值守，且操作者已准备好随时接管或断电。",
        "- 本协议只用于有人监督的真机验证，不用于无人值守自动执行。",
        "",
    ]
    for spec in specs:
        sections.extend(
            [
                f"## {spec.action_name.value}",
                "",
                "### Official Entrypoints",
                "",
                *[f"- `{entry}`" for entry in spec.official_entrypoints],
                "",
                "### Safety Preconditions",
                "",
                *[f"- {item}" for item in spec.safety_preconditions],
                "",
                "### Success Criteria",
                "",
                *[f"- {item}" for item in spec.success_criteria],
                "",
                "### Command Hints",
                "",
                *[f"- {item}" for item in spec.command_hints],
                "",
                "### Steps",
                "",
                *[
                    f"- {step.description} 预期结果：{step.expected_result}"
                    for step in spec.steps
                ],
                "",
            ]
        )
    return "\n".join(sections).strip() + "\n"


def cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-actions", action="store_true", help="List supported supervised validation actions.")
    parser.add_argument(
        "--action",
        action="append",
        choices=[item.value for item in ValidatedActionName],
        help="Action to prepare for supervised validation. Repeat to include multiple actions.",
    )
    parser.add_argument(
        "--operator-ready",
        action="store_true",
        help="Confirm that a human operator is present and ready before generating live validation materials.",
    )
    parser.add_argument("--json-out", help="Optional JSON output path for pending validation outcomes.")
    parser.add_argument("--markdown-out", help="Optional markdown output path for the validation protocol.")
    args = parser.parse_args(argv)

    if args.list_actions:
        print("\n".join(item.value for item in ValidatedActionName))
        return 0

    if not args.action:
        parser.error("at least one --action is required unless --list-actions is used")

    if not args.operator_ready:
        print("Refusing to prepare live validation without --operator-ready.", file=sys.stderr)
        return 2

    selected_actions = [ValidatedActionName(item) for item in args.action]
    specs_by_action = build_supervised_validation_specs()
    selected_specs = [specs_by_action[action] for action in selected_actions]
    outcomes = build_validation_outcomes(selected_actions)
    markdown_payload = render_supervised_validation_protocol(selected_specs)
    json_payload = "[\n" + ",\n".join(item.model_dump_json(indent=2) for item in outcomes) + "\n]\n"

    if args.json_out:
        Path(args.json_out).write_text(json_payload, encoding="utf-8")
    if args.markdown_out:
        Path(args.markdown_out).write_text(markdown_payload, encoding="utf-8")
    if not args.json_out and not args.markdown_out:
        print(markdown_payload)
    return 0
