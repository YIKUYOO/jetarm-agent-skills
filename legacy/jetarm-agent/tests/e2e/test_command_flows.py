from jetarm_demo_agent.cli import run_command
from jetarm_demo_agent.orchestration.dispatcher import Dispatcher


class FakeTransport:
    def health(self):
        return {
            "ok": True,
            "single_block_demo_mode": True,
            "ros_context": {"tracking_node": True, "sorting_node": True, "grasp_node": True},
        }

    def run_task(self, task):
        return {
            "ok": True,
            "task_id": task.task_id,
            "executor_state": "DRY_RUN_COMPLETED" if task.mode.value == "dry_run" else "SUCCEEDED",
            "mode": task.mode.value,
            "intent": task.intent.value,
            "result": {"summary": "ok", "motion_executed": False},
            "telemetry": {"single_block_demo_mode": True},
            "error": None,
        }


def test_cli_go_home_flow_contains_sections():
    output = run_command("回到初始位置", dispatcher=Dispatcher(transport=FakeTransport()))
    assert "原始命令" in output
    assert "批准后的任务对象" in output
    assert "go_home" in output


def test_cli_pick_and_place_flow_shows_dry_run():
    output = run_command("把前面的红色木块放到左边", dispatcher=Dispatcher(transport=FakeTransport()))
    assert "pick_and_place_color" in output
    assert "dry_run" in output


def test_cli_detect_flow_shows_detected_field():
    output = run_command("看看前面有没有红色木块", dispatcher=Dispatcher(transport=FakeTransport()))
    assert "detect_color" in output
    assert "执行结果" in output
