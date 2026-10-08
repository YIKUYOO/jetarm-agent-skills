from jetarm_demo_agent.executor.result_parser import parse_executor_result


def test_parse_success_result():
    result = parse_executor_result(
        {
            "ok": True,
            "task_id": "t1",
            "executor_state": "SUCCEEDED",
            "mode": "safe",
            "intent": "go_home",
            "result": {"summary": "done"},
            "telemetry": {},
            "error": None,
        }
    )
    assert result.ok is True
    assert result.intent == "go_home"


def test_parse_detect_color_result_keeps_detected_field():
    result = parse_executor_result(
        {
            "ok": True,
            "task_id": "t2",
            "executor_state": "SUCCEEDED",
            "mode": "safe",
            "intent": "detect_color",
            "result": {"summary": "detected", "detected": True, "target_color": "red"},
            "telemetry": {},
            "error": None,
        }
    )
    assert result.result["detected"] is True
