from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from jetarm_demo_agent.config import Settings


class DeepSeekClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def _build_payload(self, command: str, stream: bool = False) -> dict[str, Any]:
        payload = {
            "model": self.settings.deepseek_model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the conversational understanding and planning layer of a constrained robot demo system. "
                        "Return JSON only, with no markdown and no extra commentary. "
                        "First classify the user turn into one interaction_type: chat, task, clarify, abort. "
                        "Allowed intents: chat, go_home, detect_color, check_color, pick_color, pick_and_place_color, observe_environment, pick_lift_place_red_block, clarify, abort. "
                        "Allowed colors: red, green, blue. "
                        "Allowed destinations: left. "
                        "Allowed return_policy values for pick_lift_place_red_block: pick_xy. "
                        "For observe_environment, the plan may only use actions: scan_scene, summarize_scene. "
                        "For pick_lift_place_red_block, the plan may only use actions: find_red_block, pick_red_block, lift_red_block, place_red_block_back_to_pick_xy. "
                        "For chat, answer naturally as 'JetArm 机械臂智能助手'. "
                        "You can explain who you are, what you can currently do, the current demo limits, and what is happening now. "
                        "Never output ROS commands, topic names, service names, action names, coordinates, servo parameters, motion mode, or control values. "
                        "Required JSON shape: "
                        "{\"interaction_type\":\"chat|task|clarify|abort\",\"intent\":\"...\",\"args\":{\"target_color\":\"red|green|blue optional\",\"destination\":\"left optional\",\"return_policy\":\"pick_xy optional\"},"
                        "\"control\":{\"requires_observation\":true|false,\"clarify_if_ambiguous\":true|false,\"confidence\":0.0},"
                        "\"display\":{\"intent_label\":\"short Chinese label\",\"steps\":[\"step1\",\"step2\",\"step3\"],\"llm_summary\":\"one short Chinese sentence\",\"chat_reply\":\"natural Chinese assistant reply for chat mode optional\",\"capability_summary\":\"short Chinese summary optional\"},"
                        "\"plan\":{\"goal\":\"short Chinese goal\",\"constraints\":[\"...\"],\"steps\":[{\"action\":\"...\",\"description\":\"...\"}],\"safety_notes\":[\"...\"]}}. "
                        "For chat, set interaction_type=chat and intent=chat, provide display.chat_reply, and leave plan empty. "
                        "For task, provide a constrained executable plan. "
                        "For detect_color, steps should emphasize detection result. "
                        "For check_color, steps should emphasize yes/no checking. "
                        "For pick_and_place_color, describe a constrained pick-and-place task without exposing low-level controls. "
                        "For observe_environment, the robot should scan the environment and summarize what it sees. "
                        "For pick_lift_place_red_block, the robot should search for the front red block, pick it, lift it for display, and place it back to the original pick XY. "
                        "For this task, set args.return_policy=pick_xy. "
                        "When information is missing inside the constrained world, prefer interaction_type=clarify and intent=clarify. "
                        "When the user is chatting rather than assigning a task, prefer interaction_type=chat instead of forcing a task. "
                        "When the request is outside the constrained world but still conversational, answer in chat mode and explain the current limits. "
                        "Use abort only for clearly unsafe or non-responsive cases."
                    ),
                },
                {"role": "user", "content": command},
            ],
            "response_format": {"type": "json_object"},
        }
        if stream:
            payload["stream"] = True
        return payload

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

    def enrich_command(self, command: str) -> dict[str, Any] | None:
        if not self.settings.deepseek_api_key:
            return None

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self.settings.deepseek_base_url}/chat/completions",
                    json=self._build_payload(command),
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
            content = data["choices"][0]["message"]["content"]
            return httpx.Response(200, content=content).json()
        except (httpx.HTTPError, KeyError, ValueError):
            return None

    def stream_enrich_command(self, command: str) -> Iterator[dict[str, Any]]:
        if not self.settings.deepseek_api_key:
            yield {"type": "result", "payload": None}
            return

        chunks: list[str] = []
        try:
            with httpx.Client(timeout=20.0) as client:
                with client.stream(
                    "POST",
                    f"{self.settings.deepseek_base_url}/chat/completions",
                    json=self._build_payload(command, stream=True),
                    headers=self._headers(),
                ) as response:
                    response.raise_for_status()
                    for raw_line in response.iter_lines():
                        line = raw_line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        payload = json.loads(data)
                        delta = payload["choices"][0]["delta"].get("content", "")
                        if delta:
                            chunks.append(delta)
                            yield {"type": "display_delta", "text": delta}
            content = "".join(chunks).strip()
            yield {"type": "result", "payload": json.loads(content) if content else None}
        except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
            yield {"type": "result", "payload": self.enrich_command(command)}
