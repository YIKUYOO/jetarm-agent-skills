from jetarm_demo_agent.schemas import SessionState, SessionStatus, TaskIntent, TaskRequest


def test_session_state_defaults_to_waiting_for_user_input():
    session = SessionState(session_id="s1")

    assert session.status == SessionStatus.WAITING_FOR_USER_INPUT
    assert session.waiting_for_clarification is False
    assert session.pending_task is None


def test_session_state_can_track_pending_task():
    task = TaskRequest(
        task_id="t1",
        intent=TaskIntent.CLARIFY,
        control={"clarify_if_ambiguous": True, "requires_observation": False, "confidence": 0.5},
    )
    session = SessionState(session_id="s1", pending_task=task, waiting_for_clarification=True)

    assert session.pending_task is task
    assert session.waiting_for_clarification is True

