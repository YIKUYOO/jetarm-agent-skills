from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel
import requests

from jetarm_demo_agent.agent_runtime import AgentRuntime
from jetarm_demo_agent.config import Settings
from jetarm_demo_agent.executor.ssh_transport import SSHExecutorTransport, build_camera_unavailable_payload
from jetarm_demo_agent.orchestration.dispatcher import Dispatcher


CHAT_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>JetArm 智能助手</title>
  <style>
    :root {
      --bg: #0b1020;
      --bg-soft: rgba(15, 23, 42, 0.82);
      --panel: rgba(15, 23, 42, 0.74);
      --border: rgba(148, 163, 184, 0.18);
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #f97316;
      --accent-soft: rgba(249, 115, 22, 0.16);
      --assistant: rgba(30, 41, 59, 0.88);
      --success: #22c55e;
      --danger: #f87171;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(249,115,22,0.14), transparent 28%),
        radial-gradient(circle at top right, rgba(59,130,246,0.14), transparent 32%),
        linear-gradient(180deg, #0f172a 0%, #020617 100%);
    }
    .wrap { max-width: 1420px; margin: 0 auto; padding: 24px; }
    .hero { margin-bottom: 18px; }
    .hero h1 { margin: 0 0 8px; font-size: 30px; font-weight: 700; }
    .hero p { margin: 0; color: var(--muted); line-height: 1.6; }
    .layout { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(360px, 0.9fr); gap: 18px; align-items: start; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 20px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
      backdrop-filter: blur(12px);
    }
    .chat-panel { padding: 18px; }
    .chat-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
    .chat-badges { display: flex; flex-wrap: wrap; gap: 8px; }
    .tag {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      color: #fdba74;
      background: rgba(249, 115, 22, 0.12);
      border: 1px solid rgba(249, 115, 22, 0.18);
    }
    .chat-title { font-size: 18px; font-weight: 600; }
    #conversation {
      height: 64vh;
      overflow-y: auto;
      padding: 8px 2px 2px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .message-row { display: flex; }
    .message-row.user { justify-content: flex-end; }
    .message-row.assistant,
    .message-row.system { justify-content: flex-start; }
    .bubble {
      max-width: 88%;
      padding: 14px 16px;
      border-radius: 18px;
      line-height: 1.65;
      white-space: pre-wrap;
      word-break: break-word;
      border: 1px solid transparent;
    }
    .bubble.user {
      background: var(--accent-soft);
      border-color: rgba(249, 115, 22, 0.18);
      border-bottom-right-radius: 8px;
    }
    .bubble.assistant {
      background: var(--assistant);
      border-color: rgba(148, 163, 184, 0.12);
      border-bottom-left-radius: 8px;
    }
    .bubble.system {
      background: rgba(15, 23, 42, 0.56);
      border-color: rgba(148, 163, 184, 0.08);
      color: #cbd5e1;
      font-size: 14px;
      border-bottom-left-radius: 8px;
    }
    .composer {
      margin-top: 18px;
      padding-top: 16px;
      border-top: 1px solid rgba(148, 163, 184, 0.14);
    }
    .composer-hint { color: var(--muted); font-size: 13px; margin-bottom: 10px; }
    .row { display: flex; gap: 12px; }
    input, select, button {
      font: inherit;
    }
    input {
      flex: 1;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px solid rgba(148, 163, 184, 0.2);
      background: rgba(15, 23, 42, 0.9);
      color: var(--text);
      outline: none;
    }
    input:focus { border-color: rgba(249, 115, 22, 0.55); box-shadow: 0 0 0 4px rgba(249, 115, 22, 0.14); }
    button {
      border: 0;
      border-radius: 16px;
      padding: 0 20px;
      min-width: 96px;
      color: white;
      font-weight: 600;
      background: linear-gradient(135deg, #ea580c, #fb923c);
      cursor: pointer;
    }
    button:disabled { opacity: 0.6; cursor: wait; }
    .sidebar { display: grid; gap: 14px; }
    .card { padding: 16px; }
    .card-title {
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .card-body {
      background: rgba(15, 23, 42, 0.9);
      border: 1px solid rgba(148, 163, 184, 0.1);
      border-radius: 14px;
      padding: 12px;
      min-height: 52px;
      line-height: 1.6;
      white-space: pre-wrap;
      font-size: 14px;
    }
    .camera-frame {
      width: 100%;
      display: block;
      border-radius: 14px;
      border: 1px solid rgba(148, 163, 184, 0.14);
      background: #020617;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      margin-bottom: 10px;
    }
    #structured-plan .plan-step {
      display: flex;
      gap: 10px;
      padding: 9px 0;
      border-bottom: 1px solid rgba(148, 163, 184, 0.08);
    }
    #structured-plan .plan-step:last-child { border-bottom: 0; }
    .step-index {
      width: 24px;
      height: 24px;
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: rgba(59, 130, 246, 0.16);
      color: #bfdbfe;
      font-size: 12px;
      flex: 0 0 24px;
      margin-top: 2px;
    }
    .step-status {
      display: inline-block;
      margin-top: 4px;
      font-size: 12px;
      color: var(--muted);
    }
    details.debug {
      border-top: 1px solid rgba(148, 163, 184, 0.12);
      padding-top: 12px;
    }
    details.debug summary {
      cursor: pointer;
      color: var(--muted);
      font-size: 13px;
      user-select: none;
    }
    pre.debug-json {
      margin: 10px 0 0;
      padding: 10px;
      border-radius: 12px;
      background: rgba(2, 6, 23, 0.9);
      border: 1px solid rgba(148, 163, 184, 0.12);
      color: #cbd5e1;
      overflow: auto;
      font-size: 12px;
      line-height: 1.55;
    }
    .status-ok { color: var(--success); }
    .status-fail { color: var(--danger); }
    @media (max-width: 1000px) {
      .layout { grid-template-columns: 1fr; }
      #conversation { height: 48vh; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>JetArm 智能助手</h1>
      <p>你可以像和 AI 助手聊天一样与机械臂交互。当前演示支持观察周围环境，以及抓起前方红色木块举起展示后放回原处附近。</p>
    </div>
    <div class="layout">
      <div class="panel chat-panel">
        <div class="chat-header">
          <div>
            <div class="chat-title">对话区</div>
            <div class="composer-hint">先聊天，识别出明确任务时才会进入计划与执行。</div>
          </div>
          <div class="chat-badges">
            <span class="tag">云端理解</span>
            <span class="tag">结构化计划</span>
            <span class="tag">板端执行</span>
          </div>
        </div>
        <div id="conversation"></div>
        <div class="composer">
          <div class="row">
            <input id="message" placeholder="输入中文消息">
            <button id="send">发送</button>
          </div>
        </div>
      </div>
      <div class="sidebar">
        <div class="panel card">
          <div class="card-title">实时相机</div>
          <img id="camera-feed" class="camera-frame" alt="JetArm camera feed">
          <div class="row" style="margin-top: 0; margin-bottom: 10px;">
            <select id="camera-stream" style="flex:1;padding:10px 12px;border-radius:12px;border:1px solid rgba(148,163,184,0.18);background:rgba(15,23,42,0.9);color:var(--text);">
              <option value="color">彩色通道</option>
              <option value="depth">深度通道</option>
            </select>
          </div>
          <div id="camera-status" class="card-body">正在连接相机…</div>
        </div>
        <div class="panel card">
          <div class="card-title">云端理解</div>
          <div id="llm-understanding" class="card-body">等待输入</div>
        </div>
        <div class="panel card">
          <div class="card-title">结构化计划</div>
          <div id="structured-plan" class="card-body">当前没有执行计划</div>
        </div>
        <div class="panel card">
          <div class="card-title">执行状态</div>
          <div id="motion-mode" class="card-body">当前模式：未知</div>
          <div id="session-state" class="card-body">waiting_for_user_input</div>
          <div id="current-step" class="card-body" style="margin-top:10px;">尚未开始</div>
          <div id="latest-result" class="card-body" style="margin-top:10px;">尚无结果</div>
          <div id="vlm-object-preview" class="card-body" style="margin-top:10px;">尚无 VLM 物体框选结果</div>
          <button id="confirm-motion" style="width:100%;height:44px;margin-top:10px;" disabled>等待人工确认</button>
          <details class="debug" id="debug-details">
            <summary>调试详情</summary>
            <pre id="debug-json" class="debug-json">暂无调试信息</pre>
          </details>
        </div>
      </div>
    </div>
  </div>
  <script>
    const sessionId = "web-demo";
    const state = {
      interactionType: "chat",
      plan: null,
      planStatuses: {},
      currentStep: null,
      cameraBoundSrc: "",
      cameraFallbackActive: false,
      cameraRetryTimer: null,
      debug: {},
    };

    const conversation = document.getElementById("conversation");
    const input = document.getElementById("message");
    const send = document.getElementById("send");
    const cameraFeed = document.getElementById("camera-feed");
    const cameraStream = document.getElementById("camera-stream");
    const cameraStatus = document.getElementById("camera-status");
    const sessionState = document.getElementById("session-state");
    const motionMode = document.getElementById("motion-mode");
    const llmUnderstanding = document.getElementById("llm-understanding");
    const structuredPlan = document.getElementById("structured-plan");
    const currentStep = document.getElementById("current-step");
    const latestResult = document.getElementById("latest-result");
    const vlmObjectPreview = document.getElementById("vlm-object-preview");
    const confirmMotion = document.getElementById("confirm-motion");
    const debugJson = document.getElementById("debug-json");

    function escapeHtml(text) {
      return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    function appendMessage(role, text) {
      const row = document.createElement("div");
      row.className = "message-row " + role;
      const bubble = document.createElement("div");
      bubble.className = "bubble " + role;
      bubble.textContent = text;
      row.appendChild(bubble);
      conversation.appendChild(row);
      conversation.scrollTop = conversation.scrollHeight;
    }

    function setCard(node, value) {
      node.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    }

    function renderPlan(plan, currentStepName) {
      if (!plan || !Array.isArray(plan.steps) || !plan.steps.length) {
        structuredPlan.textContent = state.interactionType === "chat" ? "当前处于聊天模式，无执行计划" : "当前没有执行计划";
        return;
      }
      const html = plan.steps.map((step, index) => {
        const action = step.action || "step";
        const description = step.description || action;
        let status = state.planStatuses[action] || "pending";
        if (currentStepName && currentStepName === action) status = "running";
        return `
          <div class="plan-step">
            <div class="step-index">${index + 1}</div>
            <div>
              <div>${escapeHtml(description)}</div>
              <div class="step-status">动作：${escapeHtml(action)} · 状态：${escapeHtml(status)}</div>
            </div>
          </div>
        `;
      }).join("");
      structuredPlan.innerHTML = html;
    }

    function setDebug(label, value) {
      state.debug[label] = value;
      debugJson.textContent = JSON.stringify(state.debug, null, 2);
    }

    function bindCameraStream(force = false) {
      const stream = cameraStream.value;
      const src = "/api/camera/stream?stream=" + encodeURIComponent(stream);
      if (!force && state.cameraBoundSrc === src) return;
      state.cameraBoundSrc = src;
      state.cameraFallbackActive = false;
      if (state.cameraRetryTimer) {
        clearTimeout(state.cameraRetryTimer);
        state.cameraRetryTimer = null;
      }
      cameraStatus.textContent = "正在连接 " + (stream === "depth" ? "深度通道" : "彩色通道") + "…";
      cameraFeed.src = src;
    }

    function scheduleCameraRetry() {
      if (state.cameraRetryTimer) return;
      state.cameraRetryTimer = setTimeout(() => {
        state.cameraRetryTimer = null;
        if (state.cameraFallbackActive) bindCameraStream(true);
      }, 5000);
    }

    function fallbackCameraFrame() {
      if (state.cameraFallbackActive) return;
      state.cameraFallbackActive = true;
      const stream = cameraStream.value;
      cameraStatus.textContent = "实时流暂时不可用，已切换到单帧降级画面";
      cameraFeed.src = "/api/camera/frame?stream=" + encodeURIComponent(stream) + "&t=" + Date.now();
      scheduleCameraRetry();
    }

    function summarizeUnderstanding(understanding, interactionType) {
      if (interactionType === "chat") {
        return understanding.llm_summary || understanding.chat_reply || "当前是正常聊天模式。";
      }
      const summary = understanding.llm_summary || "已识别任务意图";
      const steps = (understanding.steps || []).length ? "\\n步骤预期：" + understanding.steps.join(" -> ") : "";
      return summary + steps;
    }

    function summarizeResult(result) {
      if (!result) return "尚无结果";
      if (result.message) return result.message;
      if (result.execution_result && result.execution_result.result && result.execution_result.result.summary) {
        return result.execution_result.result.summary;
      }
      if (result.result && result.result.summary) {
        return result.result.summary;
      }
      if (result.status === "completed" && result.interaction_type === "chat") {
        return "聊天回复已完成";
      }
      return JSON.stringify(result, null, 2);
    }

    function renderVlmObjects(objects) {
      if (!Array.isArray(objects) || !objects.length) {
        vlmObjectPreview.textContent = "尚无 VLM 物体框选结果";
        return;
      }
      vlmObjectPreview.textContent = objects.map((obj) => {
        const bbox = obj.bbox_xyxy_norm ? " bbox=" + obj.bbox_xyxy_norm.map((v) => Number(v).toFixed(2)).join(",") : "";
        const conf = obj.confidence !== undefined ? " 置信度=" + Number(obj.confidence).toFixed(2) : "";
        return `${obj.name || "unknown"}${conf}${bbox}`;
      }).join("\\n");
    }

    function renderEvent(event) {
      const p = event.payload || {};
      setDebug("last_event", event);

      if (event.event === "user_message_received") {
        appendMessage("user", p.text);
        return;
      }

      if (event.event === "state_changed") {
        setCard(sessionState, p.state);
        if (p.state === "understanding") setCard(latestResult, "正在理解你的输入…");
        if (p.state === "responding") setCard(latestResult, "正在组织回复…");
        if (p.state === "executing") setCard(latestResult, "开始执行计划…");
        return;
      }

      if (event.event === "understanding_ready") {
        state.interactionType = p.interaction_type || (p.llm_understanding && p.llm_understanding.interaction_type) || "task";
        setCard(llmUnderstanding, summarizeUnderstanding(p.llm_understanding || {}, state.interactionType));
        setDebug("understanding", p);
        if (state.interactionType === "task") {
          const summary = p.llm_understanding && p.llm_understanding.llm_summary ? p.llm_understanding.llm_summary : "我已经理解你的任务。";
          appendMessage("assistant", summary);
        }
        if (state.interactionType === "chat") {
          renderPlan(null, null);
          setCard(currentStep, "当前处于聊天模式");
        }
        return;
      }

      if (event.event === "chat_reply_ready") {
        appendMessage("assistant", p.message);
        setCard(latestResult, p.message);
        renderPlan(null, null);
        setCard(currentStep, "当前处于聊天模式");
        setDebug("chat_reply", p);
        return;
      }

      if (event.event === "plan_ready") {
        state.plan = p.plan || {steps: (p.steps || []).map((step) => ({action: step, description: step}))};
        state.planStatuses = {};
        const goal = state.plan && state.plan.goal ? "我计划这样完成：\\n" + state.plan.goal : "我已经生成执行计划。";
        appendMessage("assistant", goal);
        renderPlan(state.plan, null);
        setDebug("plan", p);
        return;
      }

      if (event.event === "clarification_requested") {
        appendMessage("assistant", p.question);
        renderPlan(null, null);
        setCard(currentStep, "等待你补充信息");
        setCard(latestResult, p.question);
        return;
      }

      if (event.event === "planner_note") {
        appendMessage("system", p.message);
        setCard(latestResult, p.message);
        return;
      }

      if (event.event === "step_started") {
        state.currentStep = p.step;
        state.planStatuses[p.step] = "running";
        renderPlan(state.plan, p.step);
        setCard(currentStep, "正在执行：" + p.step);
        appendMessage("system", "正在执行：" + p.step);
        return;
      }

      if (event.event === "step_result") {
        const ok = p.result && p.result.ok;
        const needsConfirmation = p.result && p.result.error_code === "HUMAN_CONFIRMATION_REQUIRED";
        if (state.currentStep) state.planStatuses[state.currentStep] = needsConfirmation ? "waiting_confirmation" : (ok ? "done" : "failed");
        renderPlan(state.plan, null);
        if (p.result && p.result.mode) motionMode.textContent = "当前模式：" + p.result.mode;
        if (p.result && p.result.result && p.result.result.objects) renderVlmObjects(p.result.result.objects);
        const summary = p.result && p.result.result && p.result.result.summary ? p.result.result.summary : (p.result && p.result.summary ? p.result.summary : (ok ? "步骤完成" : "步骤失败"));
        setCard(latestResult, summary);
        if (!ok && !needsConfirmation) appendMessage("assistant", "这一步执行失败：" + summary);
        return;
      }

      if (event.event === "scene_objects_detected") {
        const observation = p.observation || {};
        renderVlmObjects(observation.vlm_objects || []);
        setCard(latestResult, observation.summary || "VLM 已返回候选物体框。");
        setDebug("scene_observation", observation);
        return;
      }

      if (event.event === "confirmation_required") {
        confirmMotion.disabled = false;
        confirmMotion.textContent = "人工确认：" + (p.goal && p.goal.source_object ? p.goal.source_object.name : "待确认") + " -> " + (p.goal && p.goal.target_object_or_region ? p.goal.target_object_or_region.name : "目标");
        appendMessage("assistant", p.message || "开放桌面任务需要人工确认后才能继续。");
        setCard(latestResult, p.skill_result ? p.skill_result.summary : "等待人工确认");
        setDebug("confirmation_required", p);
        return;
      }

      if (event.event === "turn_completed") {
        const summary = summarizeResult(p);
        if (p.interaction_type !== "chat") {
          appendMessage("assistant", p.status === "completed" ? "我已经完成这轮处理。" + (summary ? "\\n" + summary : "") : "这轮处理失败。" + (summary ? "\\n" + summary : ""));
        }
        setCard(latestResult, summary);
      }
    }

    async function sendMessage() {
      const message = input.value.trim();
      if (!message) return;
      input.value = "";
      send.disabled = true;
      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({session_id: sessionId, message})
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const {value, done} = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, {stream: true});
          const lines = buffer.split("\\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (!line.trim()) continue;
            renderEvent(JSON.parse(line));
          }
        }
        if (buffer.trim()) renderEvent(JSON.parse(buffer));
      } finally {
        send.disabled = false;
      }
    }

    send.addEventListener("click", sendMessage);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") sendMessage();
    });
    cameraStream.addEventListener("change", () => bindCameraStream(true));
    cameraFeed.addEventListener("load", () => {
      cameraStatus.textContent = state.cameraFallbackActive ? "当前显示单帧降级画面" : "相机画面已连接";
    });
    cameraFeed.addEventListener("error", fallbackCameraFrame);

    bindCameraStream(true);
  </script>
</body>
</html>
"""


class ChatRequest(BaseModel):
    session_id: str
    message: str


def _ndjson(events: Iterator[dict]) -> Iterator[str]:
    for event in events:
        yield json.dumps(event, ensure_ascii=False) + "\n"


class BoardVideoServerCameraProvider:
    def __init__(self, settings: Settings, fallback_provider=None):
        self.settings = settings
        self.fallback_provider = fallback_provider
        host = (settings.ssh_host or "127.0.0.1").strip()
        self.base_url = f"http://{host}:8080"

    def _topic(self, stream: str) -> str:
        return "/jetarm_demo/depth_viz/image_raw" if stream == "depth" else "/rgbd_cam/color/image_raw"

    def _prepare_depth_stream(self) -> None:
        preparer = getattr(self.fallback_provider, "ensure_depth_viz_stream_ready", None)
        if callable(preparer):
            preparer()

    def _snapshot_url(self, stream: str) -> str:
        return f"{self.base_url}/snapshot?topic={self._topic(stream)}"

    def _stream_url(self, stream: str) -> str:
        return f"{self.base_url}/stream?topic={self._topic(stream)}"

    def camera_frame(self, stream: str = "color") -> dict:
        if stream == "depth":
            try:
                self._prepare_depth_stream()
            except Exception:
                if self.fallback_provider is not None:
                    return self.fallback_provider.camera_frame(stream)
                raise
        try:
            response = requests.get(self._snapshot_url(stream), timeout=5)
            response.raise_for_status()
            return {
                "content": response.content,
                "media_type": response.headers.get("content-type", "image/jpeg"),
                "stream": stream,
            }
        except Exception as exc:
            if self.fallback_provider is not None:
                return self.fallback_provider.camera_frame(stream)
            return build_camera_unavailable_payload(str(exc)[:160], stream)

    def camera_stream(self, stream: str = "color"):
        if stream == "depth":
            self._prepare_depth_stream()
        response = requests.get(self._stream_url(stream), timeout=(5, None), stream=True)
        response.raise_for_status()
        media_type = response.headers.get("content-type", "multipart/x-mixed-replace; boundary=boundarydonotcross")

        def iter_chunks():
            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            finally:
                response.close()

        return iter_chunks(), media_type


def create_app(dispatcher=None, camera_provider=None) -> FastAPI:
    app = FastAPI(title="JetArm Agent v1")
    active_dispatcher = dispatcher or Dispatcher(transport=SSHExecutorTransport())
    runtime = AgentRuntime(dispatcher=active_dispatcher)
    transport_camera_provider = getattr(active_dispatcher, "transport", None) or SSHExecutorTransport()
    active_camera_provider = camera_provider or BoardVideoServerCameraProvider(Settings(), fallback_provider=transport_camera_provider)
    app.state.runtime = runtime
    app.state.dispatcher = active_dispatcher
    app.state.camera_provider = active_camera_provider

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return CHAT_HTML

    @app.post("/api/chat")
    def chat(request: ChatRequest):
        return StreamingResponse(
            _ndjson(runtime.handle_message(request.session_id, request.message)),
            media_type="application/x-ndjson",
        )

    @app.get("/api/session/{session_id}")
    def session_snapshot(session_id: str):
        session = runtime.session_store.get_or_create(session_id)
        return session.model_dump(mode="json")

    @app.get("/api/camera/frame")
    def camera_frame(stream: str = "color"):
        try:
            payload = active_camera_provider.camera_frame(stream)
        except Exception as exc:
            payload = build_camera_unavailable_payload(str(exc)[:160], stream)
        return Response(content=payload["content"], media_type=payload["media_type"])

    @app.get("/api/camera/stream")
    def camera_stream(stream: str = "color"):
        if hasattr(active_camera_provider, "camera_stream"):
            try:
                iterator, media_type = active_camera_provider.camera_stream(stream)
                return StreamingResponse(iterator, media_type=media_type)
            except Exception:
                pass

        async def iter_stream():
            while True:
                try:
                    payload = active_camera_provider.camera_frame(stream)
                except Exception as exc:
                    payload = build_camera_unavailable_payload(str(exc)[:160], stream)
                try:
                    yield b"--frame\r\n"
                    yield f"Content-Type: {payload['media_type']}\r\n\r\n".encode("utf-8")
                    yield payload["content"]
                    yield b"\r\n"
                except (GeneratorExit, asyncio.CancelledError):
                    return
                await asyncio.sleep(0.8)

        return StreamingResponse(iter_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

    return app


app = create_app()
