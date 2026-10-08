from jetarm_demo_agent.planner import decide_next_action
from jetarm_demo_agent.schemas import TaskIntent, TaskRequest


def test_planner_executes_go_home_directly():
    task = TaskRequest(task_id="t1", intent=TaskIntent.GO_HOME)

    decision = decide_next_action(task)

    assert decision.decision == "execute_now"


def test_planner_executes_detect_directly():
    task = TaskRequest(task_id="t2", intent=TaskIntent.DETECT_COLOR, args={"target_color": "red"})

    decision = decide_next_action(task)

    assert decision.decision == "execute_now"


def test_planner_observes_before_pick_and_place():
    task = TaskRequest(
        task_id="t3",
        intent=TaskIntent.PICK_AND_PLACE_COLOR,
        args={"target_color": "red", "destination": "left"},
        control={"requires_observation": True},
    )

    decision = decide_next_action(task)

    assert decision.decision == "observe_then_execute"


def test_planner_clarifies_for_clarify_intent():
    task = TaskRequest(task_id="t4", intent=TaskIntent.CLARIFY)

    decision = decide_next_action(task)

    assert decision.decision == "clarify_first"


def test_planner_rejects_abort_intent():
    task = TaskRequest(task_id="t5", intent=TaskIntent.ABORT)

    decision = decide_next_action(task)

    assert decision.decision == "reject"
