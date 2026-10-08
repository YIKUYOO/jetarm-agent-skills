from __future__ import annotations

import base64
import io
import os
import threading
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import numpy as np
from PIL import Image


class SelectActionRequest(BaseModel):
    language_instruction: str
    rgb_front: str | None = Field(default=None, alias="observation.images.rgb_front")
    depth_front_vis: str | None = Field(default=None, alias="observation.images.depth_front_vis")
    state: list[float] = Field(alias="observation.state")

    class Config:
        populate_by_name = True


class SelectActionResponse(BaseModel):
    action: list[float]
    timestamp: float
    confidence: float
    mode: str
    message: str
    debug: dict[str, Any] = Field(default_factory=dict)


class HoldActionBackend:
    mode = "hold-current-pose"

    def __init__(self) -> None:
        self.loaded = True

    def select_action(self, request: SelectActionRequest) -> tuple[list[float], dict[str, Any]]:
        action = [float(min(1.0, max(0.0, value))) for value in request.state[:6]]
        return action, {"instruction": request.language_instruction}


class SmolVLABackend:
    mode = "smolvla-checkpoint"

    def __init__(self) -> None:
        # Heavy LeRobot imports are intentionally lazy so the mock server keeps
        # working on machines that only have FastAPI installed.
        import torch
        from lerobot.policies import get_policy_class, make_pre_post_processors
        from lerobot.policies.utils import prepare_observation_for_inference

        self.torch = torch
        self.prepare_observation_for_inference = prepare_observation_for_inference
        self.device = torch.device(os.getenv("VLA_DEVICE", "cuda" if torch.cuda.is_available() else "cpu"))
        self.policy_path = os.getenv(
            "VLA_POLICY_PATH",
            "",
        )
        if not os.path.isdir(self.policy_path):
            raise RuntimeError(f"Set VLA_POLICY_PATH to an existing, separately supplied checkpoint: {self.policy_path}")

        policy_cls = get_policy_class("smolvla")
        self.policy = policy_cls.from_pretrained(self.policy_path)
        self.policy.to(self.device)
        self.policy.eval()
        self.policy.reset()
        self.preprocessor, self.postprocessor = make_pre_post_processors(
            self.policy.config,
            pretrained_path=self.policy_path,
            preprocessor_overrides={"device_processor": {"device": str(self.device)}},
            postprocessor_overrides={"device_processor": {"device": "cpu"}},
        )
        self.lock = threading.Lock()
        self.loaded = True

    def select_action(self, request: SelectActionRequest) -> tuple[list[float], dict[str, Any]]:
        if request.rgb_front is None or request.depth_front_vis is None:
            raise HTTPException(status_code=400, detail="smolvla mode requires RGB and depth visualization images")
        if len(request.state) != 13:
            raise HTTPException(status_code=400, detail="smolvla mode requires observation.state length 13")

        observation = {
            "observation.images.rgb_front": decode_png_to_rgb(request.rgb_front),
            "observation.images.depth_front_vis": decode_png_to_rgb(request.depth_front_vis),
            "observation.state": np.asarray(request.state, dtype=np.float32),
        }
        started = time.perf_counter()
        with self.lock, self.torch.inference_mode():
            batch = self.prepare_observation_for_inference(
                observation,
                self.device,
                task=request.language_instruction,
                robot_type="jetarm",
            )
            batch = self.preprocessor(batch)
            action = self.policy.select_action(batch)
            action = self.postprocessor(action)
        latency_ms = (time.perf_counter() - started) * 1000.0
        values = action.squeeze(0).detach().cpu().numpy().astype(np.float32)
        values = np.clip(values, 0.0, 1.0).round(6).tolist()
        return values, {"latency_ms": round(latency_ms, 2), "policy_path": self.policy_path}


app = FastAPI(title="JetArm VLA Server", version="0.1.0")
_backend: HoldActionBackend | SmolVLABackend | None = None
_backend_lock = threading.Lock()


def backend() -> HoldActionBackend | SmolVLABackend:
    global _backend
    with _backend_lock:
        if _backend is None:
            mode = os.getenv("VLA_MODE", "mock").strip().lower()
            if mode in {"mock", "hold", "hold-current-pose"}:
                _backend = HoldActionBackend()
            elif mode in {"smolvla", "real"}:
                _backend = SmolVLABackend()
            else:
                raise RuntimeError(f"Unsupported VLA_MODE={mode!r}")
        return _backend


def decode_png_to_rgb(value: str) -> np.ndarray:
    if "," in value and value.lstrip().startswith("data:"):
        value = value.split(",", 1)[1]
    try:
        raw = base64.b64decode(value, validate=True)
        image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:  # noqa: BLE001 - surface a clean HTTP error.
        raise HTTPException(status_code=400, detail=f"invalid base64 PNG image: {exc}") from exc
    if image.size != (640, 400):
        image = image.resize((640, 400), Image.Resampling.BILINEAR)
    return np.asarray(image, dtype=np.uint8)


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        active = backend()
    except Exception as exc:  # noqa: BLE001 - health should report load failures.
        return {"ok": False, "mode": os.getenv("VLA_MODE", "mock"), "error": str(exc), "timestamp": time.time()}
    return {"ok": True, "mode": active.mode, "loaded": active.loaded, "timestamp": time.time()}


@app.post("/select_action", response_model=SelectActionResponse)
def select_action(request: SelectActionRequest) -> SelectActionResponse:
    if len(request.state) < 6:
        raise HTTPException(status_code=400, detail="observation.state must contain at least 6 values")

    active = backend()
    action, debug = active.select_action(request)
    return SelectActionResponse(
        action=action,
        timestamp=time.time(),
        confidence=0.0 if active.mode == "hold-current-pose" else 1.0,
        mode=active.mode,
        message="safe hold action" if active.mode == "hold-current-pose" else "SmolVLA checkpoint action",
        debug=debug,
    )
