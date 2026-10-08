from dataclasses import dataclass, field

from jetarm_demo_agent.schemas import TaskIntent, TaskRequest


@dataclass
class PlanDecision:
    decision: str
    steps: list[str] = field(default_factory=list)
    reason: str | None = None


def decide_next_action(task: TaskRequest) -> PlanDecision:
    if task.intent is TaskIntent.CHAT:
        return PlanDecision(decision="respond_only")

    if task.intent in {TaskIntent.OBSERVE_ENVIRONMENT, TaskIntent.PICK_LIFT_PLACE_RED_BLOCK}:
        plan = task.display.get("plan") or {}
        return PlanDecision(
            decision="execute_plan",
            steps=[step.get("description", step.get("action", "")) for step in plan.get("steps", [])],
        )

    if task.intent is TaskIntent.OPEN_DESKTOP_MANIPULATION:
        plan = task.display.get("plan") or {}
        return PlanDecision(
            decision="execute_plan",
            steps=[step.get("description", step.get("action", "")) for step in plan.get("steps", [])],
        )

    if task.intent in {TaskIntent.GO_HOME, TaskIntent.DETECT_COLOR, TaskIntent.CHECK_COLOR}:
        return PlanDecision(decision="execute_now")

    if task.intent == TaskIntent.PICK_AND_PLACE_COLOR:
        if task.control.get("requires_observation", True):
            return PlanDecision(
                decision="observe_then_execute",
                steps=[
                    "先检测前方是否有目标颜色木块",
                    "如果检测到，再执行搬运到左边",
                ],
            )
        return PlanDecision(decision="execute_now")

    if task.intent == TaskIntent.CLARIFY:
        return PlanDecision(decision="clarify_first")

    if task.intent == TaskIntent.ABORT:
        return PlanDecision(decision="reject", reason="outside_constrained_world")

    return PlanDecision(decision="reject", reason="unsupported_intent")
