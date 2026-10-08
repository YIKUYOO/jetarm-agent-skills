from jetarm_demo_agent.state_machine import TaskState
from jetarm_demo_agent.orchestration.dispatcher import Dispatcher
from jetarm_demo_agent.schemas import ExecutionMode


class FakeTransport:
    def __init__(self):
        self.seen_task = None

    def health(self):
        return {
            "ok": True,
            "single_block_demo_mode": True,
            "ros_context": {"tracking_node": True, "sorting_node": True, "grasp_node": True},
        }

    def run_task(self, task):
        self.seen_task = task
        return {
            "ok": True,
            "task_id": task.task_id,
            "executor_state": "SUCCEEDED",
            "mode": task.mode.value,
            "intent": task.intent.value,
            "result": {"summary": "done", "motion_executed": False},
            "telemetry": {"single_block_demo_mode": True},
            "error": None,
        }


def test_state_machine_contains_required_states():
    assert TaskState.RECEIVED.value == "RECEIVED"
    assert TaskState.DRY_RUN_COMPLETED.value == "DRY_RUN_COMPLETED"


def test_dispatcher_assigns_dry_run_for_motion_tasks():
    transport = FakeTransport()
    dispatcher = Dispatcher(transport=transport)

    result = dispatcher.handle("把前面的红色木块放到左边")

    assert result["approved_task"]["intent"] == "pick_and_place_color"
    assert result["approved_task"]["mode"] == ExecutionMode.DRY_RUN.value
    assert transport.seen_task.mode == ExecutionMode.DRY_RUN


def test_dispatcher_assigns_safe_for_detect_command():
    transport = FakeTransport()
    dispatcher = Dispatcher(transport=transport)

    result = dispatcher.handle("看看前面有没有红色木块")

    assert result["approved_task"]["intent"] == "detect_color"
    assert result["approved_task"]["mode"] == ExecutionMode.SAFE.value


def test_dispatcher_understand_returns_task_object_with_control_metadata():
    transport = FakeTransport()
    dispatcher = Dispatcher(transport=transport)

    result = dispatcher.understand("把那个红块移到左侧")

    assert result["approved_task"].intent.value == "pick_and_place_color"
    assert result["approved_task"].control["requires_observation"] is True


def test_dispatcher_execute_task_returns_health_and_execution_result():
    transport = FakeTransport()
    dispatcher = Dispatcher(transport=transport)
    understood = dispatcher.understand("回到初始位置")

    result = dispatcher.execute_task(understood["approved_task"])

    assert result["health"]["ok"] is True
    assert result["execution_result"]["intent"] == "go_home"
