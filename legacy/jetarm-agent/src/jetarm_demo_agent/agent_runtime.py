from __future__ import annotations

from collections.abc import Iterator
from traceback import format_exception_only
from uuid import uuid4

from jetarm_demo_agent.planner import decide_next_action
from jetarm_demo_agent.orchestration.open_desktop_safety import evaluate_manipulation_goal
from jetarm_demo_agent.schemas import ManipulationGoal, ObjectRef, SessionStatus, SkillResult, TaskRequest, TaskIntent
from jetarm_demo_agent.session_store import InMemorySessionStore


class AgentRuntime:
    def __init__(self, dispatcher, session_store: InMemorySessionStore | None = None):
        self.dispatcher = dispatcher
        self.session_store = session_store or InMemorySessionStore()

    def _event(self, event: str, session_id: str, payload: dict, turn_id: str | None = None) -> dict:
        return {
            "event": event,
            "session_id": session_id,
            "turn_id": turn_id,
            "payload": payload,
        }

    def _set_status(self, session, status: SessionStatus) -> dict:
        session.status = status
        session.recent_transitions.append(status.value)
        return self._event(
            "state_changed",
            session.session_id,
            {"state": status.value},
        )

    def _merge_clarification(self, session, message: str) -> str:
        if session.waiting_for_clarification and session.last_user_message:
            return f"{session.last_user_message} {message}"
        return message

    def _build_observation_task(self, task: TaskRequest) -> TaskRequest:
        return TaskRequest(
            task_id=f"{task.task_id}:observe:{uuid4().hex[:6]}",
            intent=TaskIntent.DETECT_COLOR,
            args={"target_color": task.args["target_color"]},
            control={"requires_observation": False, "clarify_if_ambiguous": False, "confidence": 1.0},
            source=task.source,
            display={
                "intent_label": "先确认目标颜色是否存在",
                "steps": [f"检测前方是否存在{task.args['target_color']}色木块"],
                "llm_summary": "动作前先进行受限观察",
            },
        )

    def _clarification_question(self, task: TaskRequest) -> str:
        clarify_slot = task.display.get("clarify_slot") or task.source.get("clarify_slot") or task.control.get("clarify_slot")
        if clarify_slot == "target_color" or clarify_slot is None:
            return "当前只支持红、绿、蓝木块。你要确认或操作哪一种颜色？"
        return "请补充当前任务缺少的关键信息。"

    def _chat_reply_message(self, understanding: dict, task: TaskRequest) -> str:
        return (
            task.display.get("chat_reply")
            or understanding["llm_understanding"].get("chat_reply")
            or task.display.get("llm_summary")
            or "我是 JetArm 机械臂智能助手。当前我可以观察周围环境，也可以抓起前方红色木块举起展示后放回原处附近。"
        )

    def _step_exception_result(self, task: TaskRequest, exc: Exception) -> dict:
        message = "".join(format_exception_only(type(exc), exc)).strip() or str(exc)
        return {
            "ok": False,
            "task_id": task.task_id,
            "executor_state": "FAILED",
            "mode": task.mode.value if task.mode else "safe",
            "intent": task.intent.value,
            "result": {
                "summary": message,
                "motion_executed": False,
            },
            "telemetry": {},
            "error": {
                "type": "EXECUTOR_ERROR",
                "code": "STEP_EXECUTION_FAILED",
                "message": message,
                "retryable": True,
            },
        }

    def _build_demo_step_task(self, parent_task: TaskRequest, action: str) -> TaskRequest:
        step_intent = {
            "scan_scene": TaskIntent.SCAN_SCENE,
            "find_red_block": TaskIntent.FIND_RED_BLOCK,
            "pick_red_block": TaskIntent.PICK_RED_BLOCK,
            "lift_red_block": TaskIntent.LIFT_RED_BLOCK,
            "place_red_block_near_origin": TaskIntent.PLACE_RED_BLOCK_NEAR_ORIGIN,
            "place_red_block_back_to_pick_xy": TaskIntent.PLACE_RED_BLOCK_BACK_TO_PICK_XY,
        }[action]
        step_args = dict(parent_task.args)
        if action == "find_red_block":
            step_args.setdefault("search_strategy", "directional_scan")
        return TaskRequest(
            task_id=f"{parent_task.task_id}:{action}:{uuid4().hex[:6]}",
            intent=step_intent,
            args=step_args,
            control=dict(parent_task.control),
            source=dict(parent_task.source),
            display={"intent_label": action, "steps": [action], "llm_summary": parent_task.display.get("llm_summary")},
        )

    def _build_fallback_find_task(self, parent_task: TaskRequest) -> TaskRequest:
        return TaskRequest(
            task_id=f"{parent_task.task_id}:find_red_block:global:{uuid4().hex[:6]}",
            intent=TaskIntent.FIND_RED_BLOCK,
            args={
                **dict(parent_task.args),
                "target_hint_sector": None,
                "search_strategy": "global_scan_fallback",
            },
            control=dict(parent_task.control),
            source=dict(parent_task.source),
            display={"intent_label": "find_red_block", "steps": ["find_red_block"], "llm_summary": parent_task.display.get("llm_summary")},
        )

    def _apply_step_context(self, session, action: str, result: dict) -> None:
        payload = result.get("result", {})
        if action == "find_red_block" and payload.get("detected"):
            session.recent_target_context = {
                "pose": payload.get("pose"),
                "raw_pose": payload.get("raw_pose"),
                "align_angle": payload.get("align_angle"),
                "search_sector": payload.get("search_sector"),
                "search_strategy": payload.get("search_strategy"),
                "detected_base": payload.get("detected_base"),
            }
        elif action == "pick_red_block" and payload.get("complete"):
            if session.recent_target_context:
                session.recent_target_context["picked"] = True
        elif action == "place_red_block_back_to_pick_xy" and payload.get("complete"):
            if session.recent_target_context:
                session.recent_target_context["placed_back"] = True

    def _match_vlm_object(self, objects: list[dict], query: str) -> ObjectRef | None:
        for item in objects:
            obj = item if isinstance(item, ObjectRef) else ObjectRef.model_validate(item)
            if query in obj.name or obj.name in query:
                return obj
        return None

    def _build_open_desktop_goal(self, task: TaskRequest, observation: dict) -> ManipulationGoal | SkillResult:
        objects = observation.get("vlm_objects", [])
        source_query = task.args.get("source_object", "")
        target_query = task.args.get("target_object", "")
        source = self._match_vlm_object(objects, source_query)
        target = self._match_vlm_object(objects, target_query)
        if source is None or target is None:
            missing = source_query if source is None else target_query
            return SkillResult(
                ok=False,
                stage="locating",
                motion_executed=False,
                object_locked=False,
                summary=f"没有在当前画面中可靠定位到：{missing}",
                error_code="OBJECT_NOT_FOUND",
                evidence_frames=[frame.get("label", "frame") for frame in observation.get("frames", [])],
            )
        return ManipulationGoal(
            action="move_near",
            source_object=source,
            target_object_or_region=target,
            placement_relation=task.args.get("placement_relation", "near"),
            constraints=["开放桌面任务必须先通过 VLM 定位、安全门和人工确认"],
            requires_human_confirmation=bool(task.control.get("requires_human_confirmation", True)),
        )

    def handle_message(self, session_id: str, message: str) -> Iterator[dict]:
        session = self.session_store.get_or_create(session_id)
        effective_message = self._merge_clarification(session, message)
        turn_id = f"{session_id}:{len(session.recent_transitions)}"

        session.updated_at = session.updated_at.now(session.updated_at.tzinfo)
        yield self._event("user_message_received", session_id, {"text": message}, turn_id)

        yield self._set_status(session, SessionStatus.UNDERSTANDING)
        if hasattr(self.dispatcher, "stream_understand"):
            understanding = None
            for stream_item in self.dispatcher.stream_understand(effective_message):
                if stream_item["type"] == "llm_stream_delta":
                    yield self._event(
                        "llm_stream_delta",
                        session_id,
                        {
                            "text": stream_item["text"],
                            "display_only": True,
                        },
                        turn_id,
                    )
                elif stream_item["type"] == "understanding_ready":
                    understanding = stream_item["data"]
        else:
            understanding = self.dispatcher.understand(effective_message)

        if understanding is None:
            yield self._set_status(session, SessionStatus.FAILED)
            yield self._event(
                "turn_completed",
                session_id,
                {"status": "failed", "reason": "understanding_unavailable"},
                turn_id,
            )
            yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
            return

        task: TaskRequest = understanding["approved_task"]
        session.last_user_message = effective_message
        yield self._event(
            "understanding_ready",
            session_id,
            {
                "interaction_type": understanding["llm_understanding"].get("interaction_type", "task"),
                "llm_understanding": understanding["llm_understanding"],
                "approved_task": {
                    "task_id": task.task_id,
                    "intent": task.intent.value,
                    "args": task.args,
                    "control": task.control,
                    "source": task.source,
                },
                "llm_display_only": True,
            },
            turn_id,
        )

        decision = decide_next_action(task)
        if decision.decision == "respond_only":
            yield self._set_status(session, SessionStatus.RESPONDING)
            message = self._chat_reply_message(understanding, task)
            session.waiting_for_clarification = False
            session.pending_task = None
            session.recent_chat_reply = message
            session.recent_plan = None
            session.recent_execution = None
            yield self._event(
                "chat_reply_ready",
                session_id,
                {
                    "interaction_type": "chat",
                    "message": message,
                    "capability_summary": task.display.get("capability_summary"),
                },
                turn_id,
            )
            yield self._set_status(session, SessionStatus.COMPLETED)
            yield self._event(
                "turn_completed",
                session_id,
                {"status": "completed", "interaction_type": "chat", "message": message},
                turn_id,
            )
            yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
            return

        yield self._set_status(session, SessionStatus.PLANNING)
        yield self._event(
            "plan_ready",
            session_id,
            {
                "decision": decision.decision,
                "steps": decision.steps,
                "reason": decision.reason,
                "plan": task.display.get("plan"),
            },
            turn_id,
        )
        session.recent_plan = task.display.get("plan")

        if decision.decision == "clarify_first":
            yield self._set_status(session, SessionStatus.AWAITING_CLARIFICATION)
            session.waiting_for_clarification = True
            session.pending_task = task
            yield self._event(
                "clarification_requested",
                session_id,
                {"question": self._clarification_question(task)},
                turn_id,
            )
            return

        if decision.decision == "reject":
            yield self._set_status(session, SessionStatus.REJECTED)
            session.waiting_for_clarification = False
            session.pending_task = None
            yield self._event(
                "turn_completed",
                session_id,
                {"status": "rejected", "reason": decision.reason},
                turn_id,
            )
            yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
            return

        if decision.decision == "execute_plan":
            yield self._set_status(session, SessionStatus.EXECUTING)
            plan = task.display.get("plan") or {}
            last_result = None
            session.recent_target_context = None
            if task.intent is TaskIntent.OPEN_DESKTOP_MANIPULATION:
                yield self._event("step_started", session_id, {"step": "scan_scene"}, turn_id)
                scan_task = self._build_demo_step_task(task, "scan_scene")
                try:
                    scan_execution = self.dispatcher.execute_task(scan_task)
                    scan_result = scan_execution["execution_result"]
                except Exception as exc:
                    scan_result = self._step_exception_result(scan_task, exc)
                yield self._event("step_result", session_id, {"step": "scan_scene", "result": scan_result}, turn_id)
                if not scan_result["ok"]:
                    yield self._set_status(session, SessionStatus.FAILED)
                    yield self._event("turn_completed", session_id, {"status": "failed", "execution_result": scan_result}, turn_id)
                    yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
                    return

                yield self._event("step_started", session_id, {"step": "locate_scene_objects"}, turn_id)
                try:
                    observation = self.dispatcher.locate_scene_objects(scan_result, task)
                except Exception as exc:
                    observation = {
                        "ok": False,
                        "frames": scan_result.get("result", {}).get("frames", []),
                        "vlm_objects": [],
                        "summary": str(exc),
                        "error": "VLM_LOCATE_FAILED",
                    }
                observation.setdefault("frames", scan_result.get("result", {}).get("frames", []))
                session.recent_observation = observation
                yield self._event("scene_objects_detected", session_id, {"observation": observation}, turn_id)
                locate_result = {
                    "ok": bool(observation.get("ok", True)) and bool(observation.get("vlm_objects")),
                    "task_id": task.task_id,
                    "executor_state": "SUCCEEDED" if observation.get("vlm_objects") else "FAILED",
                    "mode": "cloud",
                    "intent": "locate_scene_objects",
                    "result": {
                        "summary": observation.get("summary", "VLM 已返回候选物体"),
                        "objects": observation.get("vlm_objects", []),
                        "motion_executed": False,
                    },
                    "telemetry": {},
                    "error": None if observation.get("vlm_objects") else {"type": "VISION_ERROR", "code": observation.get("error", "NO_OBJECTS_FOUND"), "message": observation.get("summary", "no objects found"), "retryable": True},
                }
                yield self._event("step_result", session_id, {"step": "locate_scene_objects", "result": locate_result}, turn_id)
                if not locate_result["ok"]:
                    session.recent_execution = locate_result
                    yield self._set_status(session, SessionStatus.FAILED)
                    yield self._event("turn_completed", session_id, {"status": "failed", "execution_result": locate_result}, turn_id)
                    yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
                    return

                yield self._event("step_started", session_id, {"step": "safety_check"}, turn_id)
                goal_or_result = self._build_open_desktop_goal(task, observation)
                if isinstance(goal_or_result, SkillResult):
                    skill_result = goal_or_result
                    goal_payload = None
                else:
                    goal_payload = goal_or_result.model_dump(mode="json")
                    skill_result = evaluate_manipulation_goal(goal_or_result)
                session.recent_execution = skill_result.model_dump(mode="json")
                yield self._event("step_result", session_id, {"step": "safety_check", "result": session.recent_execution}, turn_id)
                if skill_result.error_code == "HUMAN_CONFIRMATION_REQUIRED" and goal_payload is not None:
                    session.pending_task = task
                    session.waiting_for_clarification = False
                    yield self._set_status(session, SessionStatus.AWAITING_CONFIRMATION)
                    yield self._event(
                        "confirmation_required",
                        session_id,
                        {
                            "goal": goal_payload,
                            "skill_result": skill_result.model_dump(mode="json"),
                            "message": "开放桌面任务已到人工确认门。首版不会自动执行真实运动。",
                        },
                        turn_id,
                    )
                    yield self._event(
                        "turn_completed",
                        session_id,
                        {
                            "status": "awaiting_confirmation",
                            "goal": goal_payload,
                            "skill_result": skill_result.model_dump(mode="json"),
                        },
                        turn_id,
                    )
                    return
                if not skill_result.ok:
                    yield self._set_status(session, SessionStatus.FAILED)
                    yield self._event(
                        "turn_completed",
                        session_id,
                        {"status": "failed", "skill_result": skill_result.model_dump(mode="json")},
                        turn_id,
                    )
                    yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
                    return
                yield self._set_status(session, SessionStatus.COMPLETED)
                yield self._event(
                    "turn_completed",
                    session_id,
                    {"status": "completed", "skill_result": skill_result.model_dump(mode="json")},
                    turn_id,
                )
                yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
                return
            for step in plan.get("steps", []):
                action = step.get("action")
                if action == "summarize_scene":
                    yield self._event("step_started", session_id, {"step": "summarize_scene"}, turn_id)
                    try:
                        summary = self.dispatcher.summarize_scene(session.recent_observation or {}, task)
                    except Exception as exc:
                        summary = {
                            "ok": False,
                            "summary": str(exc),
                            "error": "VISION_FAILED",
                        }
                    last_result = {
                        "ok": summary.get("ok", False),
                        "task_id": task.task_id,
                        "executor_state": "SUCCEEDED" if summary.get("ok", False) else "FAILED",
                        "mode": "cloud",
                        "intent": "summarize_scene",
                        "result": summary,
                        "telemetry": {},
                        "error": None if summary.get("ok", False) else {"type": "VISION_ERROR", "code": summary.get("error", "VISION_FAILED"), "message": summary.get("summary", ""), "retryable": True},
                    }
                    yield self._event("step_result", session_id, {"step": "summarize_scene", "result": last_result}, turn_id)
                    if not summary.get("ok", False):
                        yield self._set_status(session, SessionStatus.FAILED)
                        yield self._event("turn_completed", session_id, {"status": "failed", "execution_result": last_result}, turn_id)
                        yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
                        return
                    session.recent_execution = last_result
                    continue

                step_task = self._build_demo_step_task(task, action)
                if action == "pick_red_block" and session.recent_target_context:
                    step_task.args["locked_pose"] = session.recent_target_context.get("pose")
                    step_task.args["locked_align_angle"] = session.recent_target_context.get("align_angle")
                if action == "place_red_block_back_to_pick_xy":
                    if not session.recent_target_context or not session.recent_target_context.get("pose"):
                        last_result = {
                            "ok": False,
                            "task_id": step_task.task_id,
                            "executor_state": "FAILED",
                            "mode": step_task.mode.value if step_task.mode else "safe",
                            "intent": step_task.intent.value,
                            "result": {"summary": "pick pose missing", "motion_executed": False},
                            "telemetry": {},
                            "error": {"type": "EXECUTOR_ERROR", "code": "PICK_POSE_MISSING", "message": "pick pose missing", "retryable": False},
                        }
                        yield self._event("step_started", session_id, {"step": action}, turn_id)
                        yield self._event("step_result", session_id, {"step": action, "result": last_result}, turn_id)
                        yield self._set_status(session, SessionStatus.FAILED)
                        yield self._event("turn_completed", session_id, {"status": "failed", "execution_result": last_result}, turn_id)
                        yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
                        return
                    step_task.args["pick_pose"] = session.recent_target_context.get("pose")
                    step_task.args["pick_align_angle"] = session.recent_target_context.get("align_angle")
                yield self._event("step_started", session_id, {"step": action}, turn_id)
                try:
                    execution = self.dispatcher.execute_task(step_task)
                    last_result = execution["execution_result"]
                except Exception as exc:
                    last_result = self._step_exception_result(step_task, exc)
                if action == "find_red_block" and not last_result["ok"] and task.args.get("target_hint_sector"):
                    yield self._event(
                        "planner_note",
                        session_id,
                        {
                            "message": f"{task.args.get('target_hint_sector')}方向没有找到红色木块，正在扩大到整个工作区继续寻找",
                            "fallback": "global_scan",
                        },
                        turn_id,
                    )
                    yield self._event("step_result", session_id, {"step": action, "result": last_result}, turn_id)
                    fallback_task = self._build_fallback_find_task(task)
                    yield self._event("step_started", session_id, {"step": "find_red_block(global_scan)"}, turn_id)
                    try:
                        execution = self.dispatcher.execute_task(fallback_task)
                        last_result = execution["execution_result"]
                    except Exception as exc:
                        last_result = self._step_exception_result(fallback_task, exc)
                    if last_result["ok"]:
                        self._apply_step_context(session, "find_red_block", last_result)
                    yield self._event("step_result", session_id, {"step": "find_red_block(global_scan)", "result": last_result}, turn_id)
                    if not last_result["ok"]:
                        session.recent_execution = last_result
                        yield self._set_status(session, SessionStatus.FAILED)
                        yield self._event("turn_completed", session_id, {"status": "failed", "execution_result": last_result}, turn_id)
                        yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
                        return
                    session.recent_execution = last_result
                    continue
                if action == "scan_scene":
                    session.recent_observation = last_result
                else:
                    session.recent_execution = last_result
                    self._apply_step_context(session, action, last_result)
                yield self._event("step_result", session_id, {"step": action, "result": last_result}, turn_id)
                if not last_result["ok"]:
                    yield self._set_status(session, SessionStatus.FAILED)
                    yield self._event("turn_completed", session_id, {"status": "failed", "execution_result": last_result}, turn_id)
                    yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
                    return

            session.waiting_for_clarification = False
            session.pending_task = None
            yield self._set_status(session, SessionStatus.COMPLETED)
            yield self._event(
                "turn_completed",
                session_id,
                {"status": "completed", "execution_result": last_result},
                turn_id,
            )
            yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
            return

        yield self._set_status(session, SessionStatus.EXECUTING)
        if decision.decision == "observe_then_execute":
            observation_task = self._build_observation_task(task)
            yield self._event(
                "step_started",
                session_id,
                {"step": f"detect_color({task.args['target_color']})"},
                turn_id,
            )
            try:
                observation = self.dispatcher.execute_task(observation_task)
            except Exception as exc:
                observation = {
                    "execution_result": {
                        "ok": False,
                        "task_id": observation_task.task_id,
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
                        "error": {
                            "type": "EXECUTOR_ERROR",
                            "code": "OBSERVATION_STEP_FAILED",
                            "message": str(exc),
                            "retryable": True,
                        },
                    }
                }
            session.recent_observation = observation["execution_result"]
            yield self._event(
                "step_result",
                session_id,
                {
                    "step": f"detect_color({task.args['target_color']})",
                    "result": observation["execution_result"],
                },
                turn_id,
            )
            observation_result = observation["execution_result"]["result"]
            if not observation_result.get("observation_available", True):
                yield self._event(
                    "planner_note",
                    session_id,
                    {
                        "message": "观测链当前不可用，回退到受限直接执行路径",
                        "fallback": "execute_without_observation",
                    },
                    turn_id,
                )
            elif not observation_result.get("detected", False):
                session.waiting_for_clarification = False
                session.pending_task = None
                yield self._set_status(session, SessionStatus.COMPLETED)
                yield self._event(
                    "turn_completed",
                    session_id,
                    {
                        "status": "completed",
                        "outcome": "observation_not_confirmed",
                        "message": f"未检测到{task.args['target_color']}色木块，因此未执行后续动作",
                        "execution_result": observation["execution_result"],
                    },
                    turn_id,
                )
                yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
                return

        yield self._event(
            "step_started",
            session_id,
            {
                "step": (
                    f"pick_and_place_color({task.args['target_color']}, {task.args['destination']})"
                    if task.intent is TaskIntent.PICK_AND_PLACE_COLOR
                    else task.intent.value
                )
            },
            turn_id,
        )
        execution = self.dispatcher.execute_task(task)
        session.waiting_for_clarification = False
        session.pending_task = None
        session.recent_execution = execution["execution_result"]
        yield self._event(
            "step_result",
            session_id,
            {
                "step": (
                    f"pick_and_place_color({task.args['target_color']}, {task.args['destination']})"
                    if task.intent is TaskIntent.PICK_AND_PLACE_COLOR
                    else task.intent.value
                ),
                "result": execution["execution_result"],
            },
            turn_id,
        )
        yield self._set_status(session, SessionStatus.COMPLETED)
        yield self._event(
            "turn_completed",
            session_id,
            {"status": "completed", "execution_result": execution["execution_result"]},
            turn_id,
        )
        yield self._set_status(session, SessionStatus.WAITING_FOR_USER_INPUT)
