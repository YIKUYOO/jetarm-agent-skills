from uuid import uuid4

from jetarm_demo_agent.schemas import TaskIntent, TaskRequest
from jetarm_demo_agent.understanding.rule_parser import ParsedCommand


def _coerce_candidate(candidate: ParsedCommand) -> ParsedCommand:
    intents_requiring_color = {
        "detect_color",
        "check_color",
        "pick_color",
        "pick_and_place_color",
    }
    if candidate.intent in intents_requiring_color and not candidate.args.get("target_color"):
        metadata = dict(candidate.metadata)
        metadata.setdefault("clarify_slot", "target_color")
        metadata.setdefault("clarify_if_ambiguous", True)
        return ParsedCommand(intent="clarify", args={}, metadata=metadata)
    return candidate


def normalize_candidate(
    raw_command: str,
    candidate: ParsedCommand,
    parsed_by: str,
    llm_used_for_display: bool = False,
) -> TaskRequest:
    safe_candidate = _coerce_candidate(candidate)
    return TaskRequest(
        task_id=f"t_{uuid4().hex[:8]}",
        intent=TaskIntent(safe_candidate.intent),
        args=dict(safe_candidate.args),
        control={
            "requires_observation": safe_candidate.metadata.get("requires_observation", False),
            "clarify_if_ambiguous": safe_candidate.metadata.get("clarify_if_ambiguous", False),
            "confidence": safe_candidate.metadata.get("confidence"),
            "clarify_slot": safe_candidate.metadata.get("clarify_slot"),
            "requires_human_confirmation": safe_candidate.metadata.get("requires_human_confirmation", False),
        },
        source={
            "raw_command": raw_command,
            "parsed_by": parsed_by,
            "llm_used_for_display": llm_used_for_display,
            "clarify_slot": safe_candidate.metadata.get("clarify_slot"),
            "interaction_type": safe_candidate.metadata.get("interaction_type"),
        },
        display={
            "intent_label": safe_candidate.intent,
            "steps": safe_candidate.metadata.get("steps", []),
            "llm_summary": safe_candidate.metadata.get("llm_summary"),
            "chat_reply": safe_candidate.metadata.get("chat_reply"),
            "capability_summary": safe_candidate.metadata.get("capability_summary"),
            "clarify_slot": safe_candidate.metadata.get("clarify_slot"),
            "plan": safe_candidate.metadata.get("plan"),
        },
    )
