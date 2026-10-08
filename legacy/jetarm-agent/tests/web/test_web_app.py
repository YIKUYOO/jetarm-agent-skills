import asyncio

from jetarm_demo_agent.schemas import ExecutionMode, TaskIntent, TaskRequest
from jetarm_demo_agent.config import Settings
from jetarm_demo_agent.web import CHAT_HTML, BoardVideoServerCameraProvider, create_app


class FakeWebDispatcher:
    def stream_understand(self, raw_command: str):
        if "你是谁" in raw_command:
            task = TaskRequest(
                task_id="t_chat",
                intent=TaskIntent.CHAT,
                source={"raw_command": raw_command, "parsed_by": "llm", "llm_used_for_display": True},
                display={
                    "chat_reply": "我是 JetArm 机械臂智能助手，目前可以观察周围环境，以及抓起前方红色木块举起后放回原处附近。",
                    "llm_summary": "用户在询问机器人身份与当前演示能力。",
                },
            )
            yield {"type": "llm_stream_delta", "text": '{"interaction_type":"chat"'}
            yield {
                "type": "understanding_ready",
                "data": {
                    "raw_command": raw_command,
                    "llm_understanding": {
                        "interaction_type": "chat",
                        "intent": "chat",
                        "args": {},
                        "steps": [],
                        "llm_summary": "用户在询问机器人身份与当前演示能力。",
                        "chat_reply": task.display["chat_reply"],
                    },
                    "approved_task": task,
                },
            }
            return

        if "木块放到左边" in raw_command and "红" not in raw_command:
            task = TaskRequest(
                task_id="t_clarify",
                intent=TaskIntent.CLARIFY,
                source={"raw_command": raw_command, "parsed_by": "rule+llm", "llm_used_for_display": True},
            )
            yield {"type": "llm_stream_delta", "text": '{"intent":"clarify"'}
            yield {
                "type": "understanding_ready",
                "data": {
                    "raw_command": raw_command,
                    "llm_understanding": {
                        "intent": "clarify",
                        "args": {},
                        "steps": ["需要颜色"],
                        "llm_summary": "需要先补充颜色",
                    },
                    "approved_task": task,
                },
            }
            return

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
                    "steps": ["先检测", "再执行"],
                    "llm_summary": "将红色木块移动到左边",
                },
                "approved_task": task,
            },
        }

    def understand(self, raw_command: str):
        raise AssertionError("web mode should use stream_understand")

    def execute_task(self, task: TaskRequest):
        if task.intent is TaskIntent.DETECT_COLOR:
            return {
                "health": {"ok": True, "single_block_demo_mode": True},
                "execution_result": {
                    "ok": True,
                    "task_id": task.task_id,
                    "executor_state": "SUCCEEDED",
                    "mode": "safe",
                    "intent": "detect_color",
                    "result": {"summary": "checked", "detected": True, "target_color": "red", "motion_executed": False},
                    "telemetry": {},
                    "error": None,
                },
            }
        return {
            "health": {"ok": True, "single_block_demo_mode": True},
            "execution_result": {
                "ok": True,
                "task_id": task.task_id,
                "executor_state": "DRY_RUN_COMPLETED",
                "mode": "dry_run",
                "intent": task.intent.value,
                "result": {"summary": "ok", "motion_executed": False},
                "telemetry": {},
                "error": None,
            },
        }


class FakeCameraProvider:
    def camera_frame(self, stream: str):
        return {
            "content": b"jpeg-bytes",
            "media_type": "image/jpeg",
            "stream": stream,
        }


class FailingCameraProvider:
    def camera_frame(self, stream: str):
        raise RuntimeError("camera capture failed")


class StreamingCameraProvider(FakeCameraProvider):
    def camera_stream(self, stream: str):
        def iterator():
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\nchunk\r\n"

        return iterator(), "multipart/x-mixed-replace; boundary=frame"


class DepthFallbackCameraProvider(FakeCameraProvider):
    def camera_stream(self, stream: str):
        if stream == "depth":
            raise RuntimeError("depth stream unsupported")
        def iterator():
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\ncolor\r\n"

        return iterator(), "multipart/x-mixed-replace; boundary=frame"


class DepthVizFallbackCameraProvider(FakeCameraProvider):
    def __init__(self):
        self.depth_viz_ready_calls = 0

    def ensure_depth_viz_stream_ready(self):
        self.depth_viz_ready_calls += 1


class _FakeRequestsResponse:
    def __init__(self, content: bytes, content_type: str = "image/jpeg"):
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None


def test_web_root_returns_minimal_chat_ui():
    app = create_app(dispatcher=FakeWebDispatcher(), camera_provider=FakeCameraProvider())
    index_route = next(route for route in app.routes if route.path == "/")
    response = index_route.endpoint()

    assert response == CHAT_HTML
    assert "JetArm 智能助手" in response
    assert "云端理解" in response
    assert "结构化计划" in response
    assert 'id="conversation"' in response
    assert 'id="session-state"' in response
    assert 'id="llm-understanding"' in response
    assert 'id="structured-plan"' in response
    assert 'id="current-step"' in response
    assert 'id="camera-feed"' in response
    assert 'id="camera-stream"' in response
    assert 'id="motion-mode"' in response
    assert 'id="vlm-object-preview"' in response
    assert 'id="confirm-motion"' in response
    assert "人工确认" in response
    assert "调试详情" in response
    assert "setInterval(refreshCameraFrame" not in response
    assert "scheduleCameraRetry" in response
    assert 'id="approved-task"' not in response


def test_web_chat_streams_events_and_keeps_same_session_for_clarification():
    app = create_app(dispatcher=FakeWebDispatcher(), camera_provider=FakeCameraProvider())
    runtime = app.state.runtime

    first_events = list(runtime.handle_message("demo", "把前面的木块放到左边"))
    assert any(event["event"] == "clarification_requested" for event in first_events)

    second_events = list(runtime.handle_message("demo", "红色"))
    assert any(event["event"] == "llm_stream_delta" for event in second_events)
    assert any(event["event"] == "turn_completed" for event in second_events)


def test_web_chat_mode_does_not_emit_plan_or_execution_events_for_identity_question():
    app = create_app(dispatcher=FakeWebDispatcher(), camera_provider=FakeCameraProvider())
    runtime = app.state.runtime

    events = list(runtime.handle_message("demo", "你是谁？"))

    assert any(event["event"] == "chat_reply_ready" for event in events)
    assert not any(event["event"] == "plan_ready" for event in events)
    assert not any(event["event"] == "step_started" for event in events)


def test_web_session_snapshot_exposes_current_runtime_state():
    app = create_app(dispatcher=FakeWebDispatcher(), camera_provider=FakeCameraProvider())
    runtime = app.state.runtime
    list(runtime.handle_message("demo", "把前面的木块放到左边"))

    session_route = next(route for route in app.routes if route.path == "/api/session/{session_id}")
    response = session_route.endpoint("demo")

    assert response["session_id"] == "demo"
    assert response["status"] == "awaiting_clarification"
    assert response["waiting_for_clarification"] is True
    assert response["pending_task"]["intent"] == "clarify"


def test_web_camera_frame_route_uses_camera_provider():
    app = create_app(dispatcher=FakeWebDispatcher(), camera_provider=FakeCameraProvider())
    route = next(route for route in app.routes if route.path == "/api/camera/frame")

    response = route.endpoint(stream="depth")

    assert response.media_type == "image/jpeg"
    assert response.body == b"jpeg-bytes"


def test_web_camera_frame_route_falls_back_when_camera_provider_raises():
    app = create_app(dispatcher=FakeWebDispatcher(), camera_provider=FailingCameraProvider())
    route = next(route for route in app.routes if route.path == "/api/camera/frame")

    response = route.endpoint(stream="color")

    assert response.media_type == "image/svg+xml"
    assert b"JetArm camera unavailable" in response.body
    assert b"camera capture failed" in response.body


def test_web_camera_stream_route_exposes_multipart_stream():
    app = create_app(dispatcher=FakeWebDispatcher(), camera_provider=StreamingCameraProvider())
    route = next(route for route in app.routes if route.path == "/api/camera/stream")

    response = route.endpoint(stream="color")

    assert "multipart/x-mixed-replace" in response.media_type


def test_web_camera_stream_route_falls_back_to_polled_frames_for_depth():
    app = create_app(dispatcher=FakeWebDispatcher(), camera_provider=DepthFallbackCameraProvider())
    route = next(route for route in app.routes if route.path == "/api/camera/stream")

    response = route.endpoint(stream="depth")

    async def collect_first_chunks():
        chunks = []
        try:
            async for chunk in response.body_iterator:
                chunks.append(chunk)
                if len(chunks) == 3:
                    break
        finally:
            await response.body_iterator.aclose()
        return chunks

    first, second, third = asyncio.run(collect_first_chunks())

    assert "multipart/x-mixed-replace" in response.media_type
    assert first == b"--frame\r\n"
    assert b"Content-Type: image/jpeg" in second
    assert third == b"jpeg-bytes"


def test_depth_camera_frame_prefers_depth_viz_topic_and_prepares_bridge(monkeypatch):
    calls = []

    def fake_get(url, timeout=None, stream=False):
        calls.append(url)
        return _FakeRequestsResponse(b"depth-jpeg")

    monkeypatch.setattr("jetarm_demo_agent.web.requests.get", fake_get)
    fallback = DepthVizFallbackCameraProvider()
    provider = BoardVideoServerCameraProvider(
        Settings(account_file="/tmp/does-not-exist-account.txt", ssh_host="192.0.2.10"),
        fallback_provider=fallback,
    )

    payload = provider.camera_frame("depth")

    assert payload["content"] == b"depth-jpeg"
    assert fallback.depth_viz_ready_calls == 1
    assert calls == ["http://192.0.2.10:8080/snapshot?topic=/jetarm_demo/depth_viz/image_raw"]


def test_depth_camera_stream_prefers_depth_viz_topic_and_prepares_bridge(monkeypatch):
    calls = []

    class _StreamingResponse(_FakeRequestsResponse):
        def iter_content(self, chunk_size=8192):
            yield b"frame-bytes"

        def close(self):
            return None

    def fake_get(url, timeout=None, stream=False):
        calls.append((url, stream))
        return _StreamingResponse(b"", content_type="multipart/x-mixed-replace;boundary=boundarydonotcross")

    monkeypatch.setattr("jetarm_demo_agent.web.requests.get", fake_get)
    fallback = DepthVizFallbackCameraProvider()
    provider = BoardVideoServerCameraProvider(
        Settings(account_file="/tmp/does-not-exist-account.txt", ssh_host="192.0.2.10"),
        fallback_provider=fallback,
    )

    iterator, media_type = provider.camera_stream("depth")
    first = next(iterator)

    assert first == b"frame-bytes"
    assert "multipart/x-mixed-replace" in media_type
    assert fallback.depth_viz_ready_calls == 1
    assert calls == [("http://192.0.2.10:8080/stream?topic=/jetarm_demo/depth_viz/image_raw", True)]
