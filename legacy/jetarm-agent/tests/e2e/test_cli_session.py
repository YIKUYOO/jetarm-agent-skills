from jetarm_demo_agent.cli import run_interactive_session
from jetarm_demo_agent.schemas import ExecutionMode, TaskIntent, TaskRequest


class FakeInteractiveDispatcher:
    def stream_understand(self, raw_command: str):
        if "木块放到左边" in raw_command and "红" not in raw_command:
            task = TaskRequest(
                task_id="t_clarify",
                intent=TaskIntent.CLARIFY,
                source={"raw_command": raw_command, "parsed_by": "rule+llm", "llm_used_for_display": True},
            )
            yield {"type": "llm_stream_delta", "text": '{"intent":"clarify"'}
            yield {
                "type": "understanding_ready",
                "data": {
                    "raw_command": raw_command,
                    "llm_understanding": {
                        "intent": "clarify",
                        "args": {},
                        "steps": ["识别到缺少颜色信息"],
                        "llm_summary": "需要先补充颜色",
                    },
                    "approved_task": task,
                },
            }
            return

        task = TaskRequest(
            task_id="t_pick",
            intent=TaskIntent.PICK_AND_PLACE_COLOR,
            args={"target_color": "red", "destination": "left"},
            control={"requires_observation": True},
            mode=ExecutionMode.DRY_RUN,
            source={"raw_command": raw_command, "parsed_by": "rule+llm", "llm_used_for_display": True},
        )
        yield {"type": "llm_stream_delta", "text": '{"intent":"pick_and_place_color"'}
        yield {
            "type": "understanding_ready",
            "data": {
                "raw_command": raw_command,
                "llm_understanding": {
                    "intent": "pick_and_place_color",
                    "args": {"target_color": "red", "destination": "left"},
                    "steps": ["先检测", "再执行放到左边"],
                    "llm_summary": "将红色木块移动到左边",
                },
                "approved_task": task,
            },
        }

    def understand(self, raw_command: str):
        raise AssertionError("interactive mode should use stream_understand")

    def execute_task(self, task: TaskRequest):
        if task.intent is TaskIntent.DETECT_COLOR:
            return {
                "health": {"ok": True, "single_block_demo_mode": True},
                "execution_result": {
                    "ok": True,
                    "task_id": task.task_id,
                    "executor_state": "SUCCEEDED",
                    "mode": "safe",
                    "intent": "detect_color",
                    "result": {"summary": "checked", "detected": True, "target_color": "red", "motion_executed": False},
                    "telemetry": {},
                    "error": None,
                },
            }
        return {
            "health": {"ok": True, "single_block_demo_mode": True},
            "execution_result": {
                "ok": True,
                "task_id": task.task_id,
                "executor_state": "DRY_RUN_COMPLETED",
                "mode": "dry_run",
                "intent": task.intent.value,
                "result": {"summary": "ok", "motion_executed": False},
                "telemetry": {},
                "error": None,
            },
        }


def test_interactive_session_supports_clarification_and_continues_same_turn():
    dispatcher = FakeInteractiveDispatcher()
    inputs = iter(["把前面的木块放到左边", "红色", "退出"])
    outputs: list[str] = []

    def fake_input(prompt: str) -> str:
        outputs.append(prompt)
        return next(inputs)

    def fake_output(message: str) -> None:
        outputs.append(message)

    exit_code = run_interactive_session(
        dispatcher=dispatcher,
        input_fn=fake_input,
        output_fn=fake_output,
        session_id="demo",
    )

    assert exit_code == 0
    rendered = "\n".join(outputs)
    assert "LLM流式理解（展示层）" in rendered
    assert "需要澄清" in rendered
    assert "批准后的任务对象" in rendered
    assert "等待下一次输入" in rendered


def test_interactive_session_announces_dry_run_mode_by_default():
    dispatcher = FakeInteractiveDispatcher()
    inputs = iter(["退出"])
    outputs: list[str] = []

    exit_code = run_interactive_session(
        dispatcher=dispatcher,
        input_fn=lambda prompt: next(inputs),
        output_fn=outputs.append,
        session_id="demo",
    )

    assert exit_code == 0
    rendered = "\n".join(outputs)
    assert "当前动作为 dry-run 模式" in rendered
