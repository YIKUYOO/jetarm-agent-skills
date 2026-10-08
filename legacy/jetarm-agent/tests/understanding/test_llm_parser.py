from jetarm_demo_agent.understanding.llm_parser import parse_llm_json


def test_llm_json_parses_pick_and_place():
    payload = {
        "intent": "pick_and_place_color",
        "args": {"target_color": "red", "destination": "left"},
        "display": {"steps": ["确认目标颜色", "进入安全模式", "执行 dry-run"]},
    }
    parsed = parse_llm_json(payload)
    assert parsed.intent == "pick_and_place_color"


def test_llm_json_ignores_mode_from_model_output():
    payload = {
        "intent": "detect_color",
        "mode": "live",
        "args": {"target_color": "red"},
    }
    parsed = parse_llm_json(payload)
    assert parsed.intent == "detect_color"
    assert "mode" not in parsed.metadata


def test_llm_json_accepts_deepseek_parameter_aliases():
    payload = {
        "intent": "pick_and_place_color",
        "parameters": {"color": "red", "direction": "left"},
    }
    parsed = parse_llm_json(payload)
    assert parsed.args["target_color"] == "red"
    assert parsed.args["destination"] == "left"


def test_llm_json_reads_agent_control_metadata():
    payload = {
        "intent": "pick_and_place_color",
        "args": {"target_color": "red", "destination": "left"},
        "control": {
            "requires_observation": True,
            "clarify_if_ambiguous": True,
            "confidence": 0.81,
        },
    }
    parsed = parse_llm_json(payload)
    assert parsed.metadata["requires_observation"] is True
    assert parsed.metadata["clarify_if_ambiguous"] is True
    assert parsed.metadata["confidence"] == 0.81


def test_llm_json_preserves_demo_plan_steps_and_goal():
    payload = {
        "intent": "observe_environment",
        "display": {
            "steps": ["转动扫描环境", "总结看到的物体"],
            "llm_summary": "我会先环顾周围，再总结看到的内容。",
        },
        "plan": {
            "goal": "总结当前工作区可见物体",
            "constraints": ["只使用安全扫描动作"],
            "steps": [
                {"action": "scan_scene", "description": "转动机械臂扫描"},
                {"action": "summarize_scene", "description": "总结多帧画面"},
            ],
            "safety_notes": ["不要离开安全扫描轨迹"],
        },
    }

    parsed = parse_llm_json(payload)

    assert parsed.intent == "observe_environment"
    assert parsed.metadata["plan"]["goal"] == "总结当前工作区可见物体"
    assert parsed.metadata["plan"]["steps"][0]["action"] == "scan_scene"


def test_llm_json_normalizes_pick_lift_place_red_block_to_front_only_contract():
    payload = {
        "intent": "pick_lift_place_red_block",
        "args": {
            "target_color": "red",
            "target_hint_sector": "right",
            "return_policy": "pick_xy",
        },
        "display": {
            "llm_summary": "我会先去右侧寻找红色木块，抓起后举起展示，再放回抓取点。",
        },
        "plan": {
            "goal": "找到并展示红色木块后放回原处",
            "steps": [
                {"action": "find_red_block", "description": "在右侧搜索红色木块"},
                {"action": "pick_red_block", "description": "抓起红色木块"},
                {"action": "lift_red_block", "description": "举起展示"},
                {"action": "place_red_block_back_to_pick_xy", "description": "放回抓取点附近"},
            ],
        },
    }

    parsed = parse_llm_json(payload)

    assert parsed.intent == "pick_lift_place_red_block"
    assert "target_hint_sector" not in parsed.args
    assert parsed.args["return_policy"] == "pick_xy"
    assert parsed.metadata["plan"]["steps"][0]["action"] == "find_red_block"


def test_llm_json_accepts_open_desktop_manipulation_contract():
    payload = {
        "intent": "open_desktop_manipulation",
        "args": {
            "source_object": "药盒",
            "target_object": "碗",
            "placement_relation": "near",
        },
        "display": {
            "steps": ["扫描桌面", "定位药盒和碗", "等待人工确认"],
            "llm_summary": "我会先找到药盒和碗，再请求确认后执行。",
        },
        "control": {
            "requires_observation": True,
            "requires_human_confirmation": True,
            "confidence": 0.84,
        },
    }

    parsed = parse_llm_json(payload)

    assert parsed.intent == "open_desktop_manipulation"
    assert parsed.args["source_object"] == "药盒"
    assert parsed.args["target_object"] == "碗"
    assert parsed.args["placement_relation"] == "near"
    assert parsed.metadata["requires_human_confirmation"] is True
