import pytest

from jetarm_demo_agent.schemas import TaskIntent, TaskRequest
from jetarm_demo_agent.understanding.normalizer import normalize_candidate
from jetarm_demo_agent.understanding.rule_parser import ParsedCommand


def test_pick_and_place_task_schema():
    task = TaskRequest(
        task_id="t1",
        intent=TaskIntent.PICK_AND_PLACE_COLOR,
        args={"target_color": "red", "destination": "left"},
    )
    assert task.intent.value == "pick_and_place_color"


def test_task_request_supports_clarify_intent_and_control_metadata():
    task = TaskRequest(
        task_id="t3",
        intent=TaskIntent.CLARIFY,
        control={"clarify_if_ambiguous": True, "requires_observation": False, "confidence": 0.5},
    )

    assert task.intent.value == "clarify"
    assert task.control["clarify_if_ambiguous"] is True


def test_invalid_color_rejected():
    with pytest.raises(Exception):
        TaskRequest(
            task_id="t2",
            intent=TaskIntent.DETECT_COLOR,
            args={"target_color": "yellow"},
        )


def test_normalize_rule_candidate_sets_source_and_leaves_mode_empty():
    candidate = ParsedCommand(
        intent="detect_color",
        args={"target_color": "red"},
        metadata={
            "requires_observation": False,
            "clarify_if_ambiguous": False,
            "confidence": 0.92,
        },
    )
    task = normalize_candidate(
        raw_command="看看前面有没有红色木块",
        candidate=candidate,
        parsed_by="rule",
    )
    assert task.intent == TaskIntent.DETECT_COLOR
    assert task.mode is None
    assert task.source["parsed_by"] == "rule"
    assert task.control["requires_observation"] is False
    assert task.control["confidence"] == 0.92


def test_normalize_missing_color_detection_candidate_turns_into_clarify_task():
    candidate = ParsedCommand(
        intent="detect_color",
        args={},
        metadata={
            "clarify_if_ambiguous": True,
            "confidence": 0.4,
            "clarify_slot": "target_color",
            "llm_summary": "需要先明确要确认哪一种颜色",
        },
    )

    task = normalize_candidate(
        raw_command="观察你面前木块的颜色",
        candidate=candidate,
        parsed_by="llm",
        llm_used_for_display=True,
    )

    assert task.intent == TaskIntent.CLARIFY
    assert task.control["clarify_if_ambiguous"] is True
    assert task.display["llm_summary"] == "需要先明确要确认哪一种颜色"


def test_normalize_observe_environment_preserves_structured_plan():
    candidate = ParsedCommand(
        intent="observe_environment",
        metadata={
            "steps": ["扫描环境", "总结结果"],
            "llm_summary": "我会先转动观察，再总结可见物体。",
            "plan": {
                "goal": "说明周围有什么",
                "constraints": ["只执行安全扫描"],
                "steps": [
                    {"action": "scan_scene", "description": "安全扫描"},
                    {"action": "summarize_scene", "description": "云端总结"},
                ],
            },
        },
    )

    task = normalize_candidate(
        raw_command="观察周围环境都有什么",
        candidate=candidate,
        parsed_by="llm",
        llm_used_for_display=True,
    )

    assert task.intent == TaskIntent.OBSERVE_ENVIRONMENT
    assert task.display["plan"]["steps"][0]["action"] == "scan_scene"


def test_normalize_pick_lift_place_red_block_preserves_return_policy():
    candidate = ParsedCommand(
        intent="pick_lift_place_red_block",
        args={
            "target_color": "red",
            "return_policy": "pick_xy",
        },
        metadata={
            "llm_summary": "我会先在前方搜索红色木块，再抓起展示并放回抓取点。",
            "plan": {
                "goal": "抓起并展示红色木块",
                "steps": [
                    {"action": "find_red_block", "description": "在前方搜索红色木块"},
                    {"action": "pick_red_block", "description": "抓起红色木块"},
                    {"action": "lift_red_block", "description": "举起展示"},
                    {"action": "place_red_block_back_to_pick_xy", "description": "放回抓取点附近"},
                ],
            },
        },
    )

    task = normalize_candidate(
        raw_command="抓起前面的红色木块并举起来，再放下",
        candidate=candidate,
        parsed_by="llm",
        llm_used_for_display=True,
    )

    assert task.intent == TaskIntent.PICK_LIFT_PLACE_RED_BLOCK
    assert task.args["return_policy"] == "pick_xy"
    assert task.display["plan"]["steps"][-1]["action"] == "place_red_block_back_to_pick_xy"
