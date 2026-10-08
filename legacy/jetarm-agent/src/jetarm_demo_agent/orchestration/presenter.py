import json


def render_cli_output(result: dict) -> str:
    parts = [
        f"原始命令: {result['raw_command']}",
        "DeepSeek理解（展示层）:",
        json.dumps(result["llm_understanding"], ensure_ascii=False, indent=2),
        "批准后的任务对象:",
        json.dumps(result["approved_task"], ensure_ascii=False, indent=2),
        "执行结果:",
        json.dumps(result["execution_result"], ensure_ascii=False, indent=2),
    ]
    return "\n".join(parts)


def render_cli_event(event: dict) -> str | None:
    event_type = event["event"]
    payload = event["payload"]
    if event_type == "state_changed":
        return f"状态: {payload['state']}"
    if event_type == "user_message_received":
        return f"用户输入: {payload['text']}"
    if event_type == "llm_stream_delta":
        return f"LLM流式理解（展示层）: {payload['text']}"
    if event_type == "understanding_ready":
        parts = [
            "LLM最终理解（展示层）:",
            json.dumps(payload["llm_understanding"], ensure_ascii=False, indent=2),
            "批准后的任务对象:",
            json.dumps(payload["approved_task"], ensure_ascii=False, indent=2),
        ]
        return "\n".join(parts)
    if event_type == "plan_ready":
        return "计划步骤:\n{}".format(json.dumps(payload, ensure_ascii=False, indent=2))
    if event_type == "planner_note":
        return f"调度说明: {payload['message']}"
    if event_type == "clarification_requested":
        return f"需要澄清: {payload['question']}"
    if event_type == "step_started":
        return f"当前步骤: {payload['step']}"
    if event_type == "step_result":
        return "步骤结果:\n{}".format(json.dumps(payload["result"], ensure_ascii=False, indent=2))
    if event_type == "turn_completed":
        return "本轮结果:\n{}".format(json.dumps(payload, ensure_ascii=False, indent=2))
    return None
