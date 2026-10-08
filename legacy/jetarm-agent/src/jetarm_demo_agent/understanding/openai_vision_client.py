from __future__ import annotations

import base64
from typing import Any

import httpx

from jetarm_demo_agent.config import Settings
from jetarm_demo_agent.understanding.vlm_scene import parse_scene_objects_payload


class OpenAIVisionClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
        }

    def _chat_base_url(self) -> str:
        return self.settings.openai_base_url.rstrip("/")

    def _upload_frame(self, client: httpx.Client, frame: dict[str, Any]) -> str:
        image_b64 = frame.get("image_base64")
        if not image_b64:
            raise ValueError("frame missing image_base64")
        binary = base64.b64decode(image_b64)
        if not self.settings.vision_upload_url:
            return "data:{};base64,{}".format(frame.get("media_type", "image/jpeg"), image_b64)
        files = {
            "file": (
                f"{frame.get('label', 'frame')}.jpg",
                binary,
                frame.get("media_type", "image/jpeg"),
            )
        }
        response = client.post(
            self.settings.vision_upload_url,
            headers={"Authorization": f"Bearer {self.settings.vision_upload_api_key}"} if self.settings.vision_upload_api_key else {},
            files=files,
        )
        response.raise_for_status()
        data = response.json()
        candidates = [
            data.get("url"),
            data.get("link"),
            (data.get("data") or {}).get("url") if isinstance(data.get("data"), dict) else None,
            (data.get("data") or {}).get("link") if isinstance(data.get("data"), dict) else None,
        ]
        image_url = next((candidate for candidate in candidates if candidate), None)
        if not image_url:
            raise ValueError(f"upload response missing image url: {data}")
        return image_url

    def summarize_scene(self, frames: list[dict[str, Any]], prompt: str) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            return {
                "ok": False,
                "summary": "未配置 OpenAI 视觉 API Key，无法生成云端视觉总结。",
                "objects": [],
                "frames_used": len(frames),
                "error": "OPENAI_API_KEY_MISSING",
            }

        try:
            with httpx.Client(timeout=30.0) as client:
                uploaded_urls = [self._upload_frame(client, frame) for frame in frames if frame.get("image_base64")]
                content: list[dict[str, Any]] = [
                    {
                        "type": "text",
                        "text": (
                            "请用简洁中文总结这些机械臂扫描关键帧里看到了什么。"
                            "优先描述工作区中的方块、机械臂、自身姿态和显著物体。"
                            f" 用户请求：{prompt}"
                        ),
                    }
                ]
                for image_url in uploaded_urls:
                    content.append({"type": "image_url", "image_url": {"url": image_url}})
                payload = {
                    "model": self.settings.openai_model,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": content}],
                }
                response = client.post(
                    f"{self._chat_base_url()}/v1/chat/completions" if not self._chat_base_url().endswith("/v1") else f"{self._chat_base_url()}/chat/completions",
                    json=payload,
                    headers={**self._headers(), "Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
            summary = data["choices"][0]["message"]["content"].strip()
            return {
                "ok": True,
                "summary": summary,
                "objects": [],
                "frames_used": len(uploaded_urls),
                "raw": data,
                "model": data.get("model", self.settings.openai_model),
            }
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            return {
                "ok": False,
                "summary": f"云端视觉总结失败：{exc}",
                "objects": [],
                "frames_used": len(frames),
                "error": "OPENAI_VISION_FAILED",
            }

    def locate_scene_objects(self, frames: list[dict[str, Any]], prompt: str, image_size: tuple[int, int] = (640, 480)) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            return {
                "ok": False,
                "summary": "未配置 OpenAI 视觉 API Key，无法进行开放桌面目标定位。",
                "vlm_objects": [],
                "frames": frames,
                "error": "OPENAI_API_KEY_MISSING",
            }

        try:
            with httpx.Client(timeout=30.0) as client:
                uploaded_urls = [self._upload_frame(client, frame) for frame in frames if frame.get("image_base64")]
                content: list[dict[str, Any]] = [
                    {
                        "type": "text",
                        "text": (
                            "你是 JetArm 机械臂开放桌面任务的视觉定位模块。"
                            "请从图像中找出用户任务涉及的物体，严格输出 JSON，不要输出 Markdown。"
                            "格式：{\"summary\": string, \"objects\": [{\"name\": string, "
                            "\"bbox_xyxy_norm\": [x1,y1,x2,y2], \"confidence\": number}]}。"
                            "bbox 坐标必须归一化到 0..1。"
                            f" 用户任务：{prompt}"
                        ),
                    }
                ]
                for image_url in uploaded_urls:
                    content.append({"type": "image_url", "image_url": {"url": image_url}})
                payload = {
                    "model": self.settings.openai_model,
                    "temperature": 0.1,
                    "messages": [{"role": "user", "content": content}],
                }
                response = client.post(
                    f"{self._chat_base_url()}/v1/chat/completions" if not self._chat_base_url().endswith("/v1") else f"{self._chat_base_url()}/chat/completions",
                    json=payload,
                    headers={**self._headers(), "Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
            observation = parse_scene_objects_payload(text, image_size=image_size, frames=frames)
            result = observation.model_dump(mode="json")
            result["ok"] = True
            result["summary"] = text
            result["raw"] = data
            result["model"] = data.get("model", self.settings.openai_model)
            return result
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            return {
                "ok": False,
                "summary": f"云端目标定位失败：{exc}",
                "vlm_objects": [],
                "frames": frames,
                "error": "OPENAI_VLM_LOCATE_FAILED",
            }
