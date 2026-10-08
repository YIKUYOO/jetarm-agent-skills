from jetarm_demo_agent.agent_runtime import AgentRuntime
from jetarm_demo_agent.schemas import ExecutionMode, TaskIntent, TaskRequest


class FakeDispatcher:
    def __init__(self):
        self.execute_calls = []

    def understand(self, raw_command: str):
        if "木块的颜色" in raw_command:
            task = TaskRequest(
                task_id="t_color_clarify",
                intent=TaskIntent.CLARIFY,
                control={"clarify_if_ambiguous": True},
            )
            return {
                "raw_command": raw_command,
                "llm_understanding": {
                    "intent": "clarify",
                    "args": {},
                    "steps": ["需要先明确颜色范围"],
                    "llm_summary": "当前只支持红、绿、蓝木块，需要先补充颜色",
                },
                "approved_task": task,
            }

        if "木块放到左边" in raw_command and "红" not in raw_command:
            task = TaskRequest(task_id="t_clarify", intent=TaskIntent.CLARIFY)
            return {
                "raw_command": raw_command,
                "llm_understanding": {"intent": "clarify", "args": {}, "steps": [], "llm_summary": None},
                "approved_task": task,
            }

        if "回到初始位置" in raw_command:
            task = TaskRequest(task_id="t_home", intent=TaskIntent.GO_HOME, mode=ExecutionMode.SAFE)
            return {
                "raw_command": raw_command,
                "llm_understanding": {"intent": "go_home", "args": {}, "steps": [], "llm_summary": None},
                "approved_task": task,
            }

        task = TaskRequest(
            task_id="t_pick",
            intent=TaskIntent.PICK_AND_PLACE_COLOR,
            args={"target_color": "red", "destination": "left"},
            control={"requires_observation": False},
            mode=ExecutionMode.DRY_RUN,
        )
        return {
            "raw_command": raw_command,
            "llm_understanding": {
                "intent": "pick_and_place_color",
                "args": {"target_color": "red", "destination": "left"},
                "steps": [],
                "llm_summary": None,
            },
            "approved_task": task,
        }

    def execute_task(self, task: TaskRequest):
        self.execute_calls.append(task)
        return {
            "health": {"ok": True, "single_block_demo_mode": True},
            "execution_result": {
                "ok": True,
                "task_id": task.task_id,
                "executor_state": "SUCCEEDED",
                "mode": task.mode.value if task.mode else "safe",
                "intent": task.intent.value,
                "result": {"summary": "done", "motion_executed": False},
                "telemetry": {},
                "error": None,
            },
        }


class FakeChatDispatcher(FakeDispatcher):
    def understand(self, raw_command: str):
        if "你是谁" in raw_command:
            task = TaskRequest(
                task_id="t_chat_identity",
                intent=TaskIntent.CHAT,
                display={
                    "chat_reply": "我是 JetArm 机械臂智能助手，可以和你对话，并在当前演示环境中观察周围环境或抓起前方红色木块展示后放下。",
                    "llm_summary": "用户在询问机器人身份与能力。",
                },
            )
            return {
                "raw_command": raw_command,
                "llm_understanding": {
                    "interaction_type": "chat",
                    "intent": "chat",
                    "args": {},
                    "steps": [],
                    "llm_summary": "用户在询问机器人身份与能力。",
                    "chat_reply": task.display["chat_reply"],
                },
                "approved_task": task,
            }
        return super().understand(raw_command)


def test_agent_runtime_requests_clarification_and_tracks_pending_task():
    runtime = AgentRuntime(dispatcher=FakeDispatcher())

    events = list(runtime.handle_message("s1", "把前面的木块放到左边"))

    assert any(event["event"] == "clarification_requested" for event in events)
    session = runtime.session_store.get_or_create("s1")
    assert session.waiting_for_clarification is True
    assert session.pending_task is not None


def test_agent_runtime_asks_for_clarification_for_observe_color_requests_without_color():
    runtime = AgentRuntime(dispatcher=FakeDispatcher())

    events = list(runtime.handle_message("s1", "观察你面前木块的颜色"))

    clarification = [event for event in events if event["event"] == "clarification_requested"]
    assert clarification
    assert "哪一种颜色" in clarification[-1]["payload"]["question"]


def test_agent_runtime_uses_follow_up_reply_to_continue_same_pending_task():
    runtime = AgentRuntime(dispatcher=FakeDispatcher())
    list(runtime.handle_message("s1", "把前面的木块放到左边"))

    events = list(runtime.handle_message("s1", "红色"))

    assert any(event["event"] == "turn_completed" for event in events)
    session = runtime.session_store.get_or_create("s1")
    assert session.waiting_for_clarification is False
    assert session.pending_task is None


def test_agent_runtime_executes_direct_task_and_returns_to_waiting_state():
    runtime = AgentRuntime(dispatcher=FakeDispatcher())

    events = list(runtime.handle_message("s1", "回到初始位置"))

    assert any(event["event"] == "turn_completed" for event in events)
    session = runtime.session_store.get_or_create("s1")
    assert session.status.value == "waiting_for_user_input"


def test_agent_runtime_handles_identity_question_as_chat_without_execution():
    dispatcher = FakeChatDispatcher()
    runtime = AgentRuntime(dispatcher=dispatcher)

    events = list(runtime.handle_message("s1", "你是谁，你能做什么？"))

    assert any(event["event"] == "chat_reply_ready" for event in events)
    assert not any(event["event"] == "plan_ready" for event in events)
    assert not any(event["event"] == "step_started" for event in events)
    assert dispatcher.execute_calls == []
    reply = [event for event in events if event["event"] == "chat_reply_ready"][-1]
    assert "JetArm 机械臂智能助手" in reply["payload"]["message"]
    session = runtime.session_store.get_or_create("s1")
    assert session.status.value == "waiting_for_user_input"


class FakeStreamingDispatcher:
    def __init__(self, detect_result: bool = True):
        self.detect_result = detect_result
        self.execute_calls = []

    def stream_understand(self, raw_command: str):
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
                    "steps": ["先检测", "再搬运"],
                    "llm_summary": "将红色木块移动到左边",
                },
                "approved_task": task,
            },
        }

    def understand(self, raw_command: str):
        raise AssertionError("stream_understand should be used")

    def execute_task(self, task: TaskRequest):
        self.execute_calls.append(task)
        if task.intent is TaskIntent.DETECT_COLOR:
            return {
                "health": {"ok": True, "single_block_demo_mode": True},
                "execution_result": {
                    "ok": True,
                    "task_id": task.task_id,
                    "executor_state": "SUCCEEDED",
                    "mode": "safe",
                    "intent": "detect_color",
                    "result": {
                        "summary": "checked",
                        "detected": self.detect_result,
                        "target_color": "red",
                        "motion_executed": False,
                    },
                    "telemetry": {},
                    "error": None,
                },
            }

        return {
            "health": {"ok": True, "single_block_demo_mode": True},
            "execution_result": {
                "ok": True,
                "task_id": task.task_id,
                "executor_state": "SUCCEEDED",
                "mode": "dry_run",
                "intent": "pick_and_place_color",
                "result": {"summary": "done", "motion_executed": False},
                "telemetry": {},
                "error": None,
            },
        }


def test_agent_runtime_observes_then_executes_when_detection_succeeds():
    runtime = AgentRuntime(dispatcher=FakeStreamingDispatcher(detect_result=True))

    events = list(runtime.handle_message("s1", "如果前面有红色木块，就把它放到左边"))

    assert any(event["event"] == "llm_stream_delta" for event in events)
    started_steps = [event["payload"]["step"] for event in events if event["event"] == "step_started"]
    assert started_steps == ["detect_color(red)", "pick_and_place_color(red, left)"]
    session = runtime.session_store.get_or_create("s1")
    assert session.recent_observation["result"]["detected"] is True
    assert session.recent_execution["intent"] == "pick_and_place_color"
    assert session.status.value == "waiting_for_user_input"


def test_agent_runtime_stops_after_observation_when_target_not_detected():
    runtime = AgentRuntime(dispatcher=FakeStreamingDispatcher(detect_result=False))

    events = list(runtime.handle_message("s1", "如果前面有红色木块，就把它放到左边"))

    started_steps = [event["payload"]["step"] for event in events if event["event"] == "step_started"]
    assert started_steps == ["detect_color(red)"]
    completed = [event for event in events if event["event"] == "turn_completed"][-1]
    assert completed["payload"]["status"] == "completed"
    assert completed["payload"]["outcome"] == "observation_not_confirmed"
    session = runtime.session_store.get_or_create("s1")
    assert session.recent_observation["result"]["detected"] is False
    assert session.recent_execution is None


class FakeUnavailableObservationDispatcher(FakeStreamingDispatcher):
    def execute_task(self, task: TaskRequest):
        if task.intent is TaskIntent.DETECT_COLOR:
            return {
                "health": {"ok": True, "single_block_demo_mode": True},
                "execution_result": {
                    "ok": True,
                    "task_id": task.task_id,
                    "executor_state": "FAILED",
                    "mode": "safe",
                    "intent": "detect_color",
                    "result": {
                        "summary": "observation unavailable",
                        "detected": False,
                        "observation_available": False,
                        "motion_executed": False,
                    },
                    "telemetry": {},
                    "error": None,
                },
            }
        return super().execute_task(task)


def test_agent_runtime_falls_back_to_constrained_execution_when_observation_is_unavailable():
    runtime = AgentRuntime(dispatcher=FakeUnavailableObservationDispatcher())

    events = list(runtime.handle_message("s1", "如果前面有红色木块，就把它放到左边"))

    started_steps = [event["payload"]["step"] for event in events if event["event"] == "step_started"]
    assert started_steps == ["detect_color(red)", "pick_and_place_color(red, left)"]
    completed = [event for event in events if event["event"] == "turn_completed"][-1]
    assert completed["payload"]["status"] == "completed"
    assert completed["payload"]["execution_result"]["intent"] == "pick_and_place_color"


class FakeDemoDispatcher:
    def __init__(self):
        self.executed_steps = []

    def stream_understand(self, raw_command: str):
        if "观察周围环境" in raw_command:
            task = TaskRequest(
                task_id="t_observe",
                intent=TaskIntent.OBSERVE_ENVIRONMENT,
                display={
                    "llm_summary": "我会先转动扫描，再总结周围环境。",
                    "plan": {
                        "goal": "描述周围可见物体",
                        "steps": [
                            {"action": "scan_scene", "description": "转动机械臂扫描"},
                            {"action": "summarize_scene", "description": "总结多帧图像"},
                        ],
                    },
                },
            )
            yield {"type": "llm_stream_delta", "text": '{"intent":"observe_environment"'}
            yield {
                "type": "understanding_ready",
                "data": {
                    "raw_command": raw_command,
                    "llm_understanding": {"intent": "observe_environment", "args": {}, "steps": ["扫描", "总结"], "llm_summary": "我会先转动扫描，再总结周围环境。"},
                    "approved_task": task,
                },
            }
            return

        task = TaskRequest(
            task_id="t_demo_pick",
            intent=TaskIntent.PICK_LIFT_PLACE_RED_BLOCK,
            args={"target_color": "red", "return_policy": "pick_xy"},
            display={
                "llm_summary": "我会先寻找前方红色木块，抓起后举起来展示，再放回抓取点附近。",
                "plan": {
                    "goal": "抓起前方红色木块并展示后放回",
                    "steps": [
                        {"action": "find_red_block", "description": "在前方搜索红色木块"},
                        {"action": "pick_red_block", "description": "抓起红色木块"},
                        {"action": "lift_red_block", "description": "举起展示"},
                        {"action": "place_red_block_back_to_pick_xy", "description": "放回抓取点附近"},
                    ],
                },
            },
        )
        yield {"type": "llm_stream_delta", "text": '{"intent":"pick_lift_place_red_block"'}
        yield {
            "type": "understanding_ready",
            "data": {
                "raw_command": raw_command,
                "llm_understanding": {"intent": "pick_lift_place_red_block", "args": {"target_color": "red"}, "steps": ["抓起", "举起", "放下"], "llm_summary": "我会抓起红色木块，举起来展示，再放回原处附近。"},
                "approved_task": task,
            },
        }

    def understand(self, raw_command: str):
        raise AssertionError("stream_understand should be used")

    def execute_task(self, task: TaskRequest):
        self.executed_steps.append(task.intent.value)
        if task.intent is TaskIntent.SCAN_SCENE:
            return {
                "health": {"ok": True},
                "execution_result": {
                    "ok": True,
                    "task_id": task.task_id,
                    "executor_state": "SUCCEEDED",
                    "mode": "live",
                    "intent": task.intent.value,
                    "result": {"summary": "scan ok", "frames": ["f1", "f2", "f3"], "motion_executed": True},
                    "telemetry": {},
                    "error": None,
                },
            }
        if task.intent is TaskIntent.FIND_RED_BLOCK:
            return {
                "health": {"ok": True},
                "execution_result": {
                    "ok": True,
                    "task_id": task.task_id,
                    "executor_state": "SUCCEEDED",
                    "mode": "live",
                    "intent": task.intent.value,
                    "result": {
                        "summary": "found red block",
                        "detected": True,
                        "pose": [0.218, -0.041, 0.012],
                        "raw_pose": [0.112, 0.053, 0.012],
                        "align_angle": 11.0,
                        "search_sector": "front",
                        "search_strategy": "directional_scan",
                        "detected_base": 760,
                        "motion_executed": True,
                    },
                    "telemetry": {},
                    "error": None,
                },
            }
        return {
            "health": {"ok": True},
            "execution_result": {
                "ok": True,
                "task_id": task.task_id,
                "executor_state": "SUCCEEDED",
                "mode": "live",
                "intent": task.intent.value,
                "result": {"summary": f"{task.intent.value} ok", "motion_executed": True, "args": task.args},
                "telemetry": {},
                "error": None,
            },
        }

    def summarize_scene(self, scan_result: dict, task: TaskRequest):
        return {
            "ok": True,
            "summary": "我看到工作区里有一个红色木块和机械臂本体。",
            "objects": ["red block", "robot arm"],
            "frames_used": 3,
        }


class FailingScanDemoDispatcher(FakeDemoDispatcher):
    def execute_task(self, task: TaskRequest):
        if task.intent is TaskIntent.SCAN_SCENE:
            raise RuntimeError("remote scan failed")
        return super().execute_task(task)


def test_agent_runtime_executes_observe_environment_as_two_step_plan():
    runtime = AgentRuntime(dispatcher=FakeDemoDispatcher())

    events = list(runtime.handle_message("demo", "观察周围环境都有什么"))

    started_steps = [event["payload"]["step"] for event in events if event["event"] == "step_started"]
    assert started_steps == ["scan_scene", "summarize_scene"]
    completed = [event for event in events if event["event"] == "turn_completed"][-1]
    assert completed["payload"]["status"] == "completed"
    assert "红色木块" in completed["payload"]["execution_result"]["result"]["summary"]


def test_agent_runtime_executes_pick_lift_place_as_multi_step_plan():
    runtime = AgentRuntime(dispatcher=FakeDemoDispatcher())

    events = list(runtime.handle_message("demo", "抓起面前的红色木块并举起来，再放下"))

    started_steps = [event["payload"]["step"] for event in events if event["event"] == "step_started"]
    assert started_steps == ["find_red_block", "pick_red_block", "lift_red_block", "place_red_block_back_to_pick_xy"]
    completed = [event for event in events if event["event"] == "turn_completed"][-1]
    assert completed["payload"]["status"] == "completed"
    session = runtime.session_store.get_or_create("demo")
    assert session.recent_target_context["pose"] == [0.218, -0.041, 0.012]
    assert session.recent_target_context["raw_pose"] == [0.112, 0.053, 0.012]
    assert session.recent_target_context["detected_base"] == 760
    assert session.recent_target_context["search_sector"] == "front"
    assert session.recent_execution["intent"] == "place_red_block_back_to_pick_xy"


def test_agent_runtime_converts_plan_step_exception_into_failed_turn():
    runtime = AgentRuntime(dispatcher=FailingScanDemoDispatcher())

    events = list(runtime.handle_message("demo", "观察周围环境都有什么"))

    completed = [event for event in events if event["event"] == "turn_completed"][-1]
    assert completed["payload"]["status"] == "failed"
    assert completed["payload"]["execution_result"]["intent"] == "scan_scene"
    assert completed["payload"]["execution_result"]["error"]["code"] == "STEP_EXECUTION_FAILED"


class FakeOpenDesktopDispatcher:
    def stream_understand(self, raw_command: str):
        task = TaskRequest(
            task_id="t_open_desktop",
            intent=TaskIntent.OPEN_DESKTOP_MANIPULATION,
            args={
                "source_object": "药盒",
                "target_object": "碗",
                "placement_relation": "near",
            },
            control={
                "requires_observation": True,
                "requires_human_confirmation": True,
                "confidence": 0.86,
            },
            source={"raw_command": raw_command, "parsed_by": "rule"},
            display={
                "llm_summary": "我会先定位药盒和碗，确认安全后等待你批准真实运动。",
                "plan": {
                    "goal": "把药盒放到碗旁边",
                    "steps": [
                        {"action": "scan_scene", "description": "获取当前桌面图像"},
                        {"action": "locate_scene_objects", "description": "定位药盒和碗"},
                        {"action": "safety_check", "description": "检查置信度、坐标和人工确认"},
                    ],
                },
            },
        )
        yield {
            "type": "understanding_ready",
            "data": {
                "raw_command": raw_command,
                "llm_understanding": {
                    "intent": "open_desktop_manipulation",
                    "args": task.args,
                    "steps": ["扫描", "定位", "安全确认"],
                    "llm_summary": task.display["llm_summary"],
                    "plan": task.display["plan"],
                },
                "approved_task": task,
            },
        }

    def understand(self, raw_command: str):
        raise AssertionError("stream_understand should be used")

    def execute_task(self, task: TaskRequest):
        assert task.intent is TaskIntent.SCAN_SCENE
        return {
            "health": {"ok": True},
            "execution_result": {
                "ok": True,
                "task_id": task.task_id,
                "executor_state": "DRY_RUN_COMPLETED",
                "mode": "dry_run",
                "intent": "scan_scene",
                "result": {
                    "summary": "captured current frame",
                    "frames": [{"label": "center", "image_base64": "ZmFrZQ==", "media_type": "image/jpeg"}],
                    "motion_executed": False,
                },
                "telemetry": {},
                "error": None,
            },
        }

    def locate_scene_objects(self, scan_result: dict, task: TaskRequest):
        return {
            "frames": scan_result["result"]["frames"],
            "vlm_objects": [
                {
                    "name": "药盒",
                    "bbox_xyxy_norm": [0.1, 0.2, 0.4, 0.6],
                    "center_px": [160, 192],
                    "confidence": 0.91,
                    "source": "vlm",
                    "world_pose_optional": [0.18, 0.02, 0.03],
                },
                {
                    "name": "碗",
                    "bbox_xyxy_norm": [0.55, 0.3, 0.85, 0.7],
                    "center_px": [448, 240],
                    "confidence": 0.93,
                    "source": "vlm",
                    "world_pose_optional": [0.08, 0.12, 0.03],
                },
            ],
            "calibration_version": "jetarm-rgbd-v1",
            "timestamp": "2026-05-03T15:00:00+08:00",
        }


def test_agent_runtime_open_desktop_task_stops_at_human_confirmation_gate():
    runtime = AgentRuntime(dispatcher=FakeOpenDesktopDispatcher())

    events = list(runtime.handle_message("desktop", "把药盒放到碗旁边"))

    started_steps = [event["payload"]["step"] for event in events if event["event"] == "step_started"]
    assert started_steps == ["scan_scene", "locate_scene_objects", "safety_check"]
    assert any(event["event"] == "scene_objects_detected" for event in events)
    confirmation = [event for event in events if event["event"] == "confirmation_required"][-1]
    assert confirmation["payload"]["goal"]["source_object"]["name"] == "药盒"
    assert confirmation["payload"]["skill_result"]["error_code"] == "HUMAN_CONFIRMATION_REQUIRED"
    completed = [event for event in events if event["event"] == "turn_completed"][-1]
    assert completed["payload"]["status"] == "awaiting_confirmation"
    session = runtime.session_store.get_or_create("desktop")
    assert session.recent_observation["vlm_objects"][0]["name"] == "药盒"
    assert session.pending_task is not None
