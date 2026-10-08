from jetarm_demo_agent.understanding.rule_parser import RuleParser


def test_go_home_rule():
    parsed = RuleParser().parse("回到初始位置")
    assert parsed.intent == "go_home"


def test_detect_red_rule():
    parsed = RuleParser().parse("看看前面有没有红色木块")
    assert parsed.intent == "detect_color"
    assert parsed.args["target_color"] == "red"


def test_pick_and_place_red_left_rule():
    parsed = RuleParser().parse("把前面的红色木块放到左边")
    assert parsed.intent == "pick_and_place_color"
    assert parsed.args["target_color"] == "red"
    assert parsed.args["destination"] == "left"


def test_pick_and_place_synonym_variant_maps_to_same_intent():
    parsed = RuleParser().parse("把那个红块移到左侧")
    assert parsed.intent == "pick_and_place_color"
    assert parsed.args["target_color"] == "red"
    assert parsed.args["destination"] == "left"


def test_missing_color_triggers_clarify():
    parsed = RuleParser().parse("把前面的木块放到左边")
    assert parsed.intent == "clarify"


def test_observe_color_without_explicit_target_color_triggers_clarify():
    parsed = RuleParser().parse("观察你面前木块的颜色")
    assert parsed.intent == "clarify"
    assert parsed.metadata["clarify_slot"] == "target_color"


def test_open_world_request_maps_to_observe_environment_plan():
    parsed = RuleParser().parse("看看前面有什么")
    assert parsed.intent == "observe_environment"
    assert parsed.metadata["plan"]["steps"][0]["action"] == "scan_scene"
    assert parsed.metadata["plan"]["steps"][1]["action"] == "summarize_scene"


def test_open_desktop_move_extracts_source_target_and_relation():
    parsed = RuleParser().parse("把药盒放到碗旁边")

    assert parsed.intent == "open_desktop_manipulation"
    assert parsed.args["source_object"] == "药盒"
    assert parsed.args["target_object"] == "碗"
    assert parsed.args["placement_relation"] == "near"
    assert parsed.metadata["plan"]["steps"][0]["action"] == "scan_scene"
    assert parsed.metadata["plan"]["steps"][1]["action"] == "locate_scene_objects"
    assert parsed.metadata["plan"]["steps"][2]["action"] == "safety_check"


def test_pick_lift_place_red_block_rule_uses_front_only_plan():
    parsed = RuleParser().parse("抓起左边的红色木块并举起来，再放下")

    assert parsed.intent == "pick_lift_place_red_block"
    assert parsed.args["target_color"] == "red"
    assert parsed.args["return_policy"] == "pick_xy"
    assert parsed.metadata["plan"]["steps"][0]["action"] == "find_red_block"
    assert parsed.metadata["plan"]["steps"][0]["description"] == "在前方搜索红色木块"
    assert parsed.metadata["plan"]["steps"][-1]["action"] == "place_red_block_back_to_pick_xy"
