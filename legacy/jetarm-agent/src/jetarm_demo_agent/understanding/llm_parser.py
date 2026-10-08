from jetarm_demo_agent.understanding.rule_parser import ParsedCommand


def parse_llm_json(payload: dict) -> ParsedCommand:
    intent = payload["intent"]
    args = dict(payload.get("args", {}))
    parameters = payload.get("parameters", {})
    if "target_color" not in args and "color" in parameters:
        args["target_color"] = parameters["color"]
    if "destination" not in args and "direction" in parameters:
        args["destination"] = parameters["direction"]
    if "target_hint_sector" not in args and "target_hint_sector" in parameters:
        args["target_hint_sector"] = parameters["target_hint_sector"]
    if "return_policy" not in args and "return_policy" in parameters:
        args["return_policy"] = parameters["return_policy"]
    if intent == "pick_lift_place_red_block":
        args.pop("target_hint_sector", None)
        args["return_policy"] = "pick_xy"
    metadata = {
        "interaction_type": payload.get("interaction_type"),
        "steps": payload.get("display", {}).get("steps", []),
        "llm_summary": payload.get("display", {}).get("llm_summary"),
        "chat_reply": payload.get("display", {}).get("chat_reply") or payload.get("reply", {}).get("message"),
    }
    if "capability_summary" in payload.get("display", {}):
        metadata["capability_summary"] = payload["display"]["capability_summary"]
    if "plan" in payload:
        metadata["plan"] = payload["plan"]
    control = payload.get("control", {})
    if "requires_observation" in control:
        metadata["requires_observation"] = control["requires_observation"]
    if "clarify_if_ambiguous" in control:
        metadata["clarify_if_ambiguous"] = control["clarify_if_ambiguous"]
    if "confidence" in control:
        metadata["confidence"] = control["confidence"]
    if "requires_human_confirmation" in control:
        metadata["requires_human_confirmation"] = control["requires_human_confirmation"]
    return ParsedCommand(intent=intent, args=args, metadata=metadata)
