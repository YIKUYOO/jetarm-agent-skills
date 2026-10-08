from __future__ import annotations

import json
from typing import Any

from jetarm_demo_agent.schemas import ObjectRef, SceneObservation


def _strip_markdown_json(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _center_from_bbox(bbox: list[float], image_size: tuple[int, int]) -> list[int]:
    width, height = image_size
    x1, y1, x2, y2 = bbox
    return [int(round((x1 + x2) * 0.5 * width)), int(round((y1 + y2) * 0.5 * height))]


def parse_scene_objects_payload(
    raw_payload: str | dict[str, Any],
    image_size: tuple[int, int] = (640, 480),
    frames: list[dict[str, Any]] | None = None,
) -> SceneObservation:
    data = raw_payload if isinstance(raw_payload, dict) else json.loads(_strip_markdown_json(raw_payload))
    objects = data.get("objects")
    if not isinstance(objects, list):
        raise ValueError("scene observation payload must contain an objects list")

    parsed_objects = []
    for item in objects:
        bbox = item.get("bbox_xyxy_norm") or item.get("bbox")
        if bbox is None:
            raise ValueError("object is missing bbox_xyxy_norm")
        bbox = [float(value) for value in bbox]
        center_px = item.get("center_px") or _center_from_bbox(bbox, image_size)
        parsed_objects.append(
            ObjectRef(
                name=str(item.get("name") or item.get("label") or "unknown"),
                bbox_xyxy_norm=bbox,
                center_px=[int(center_px[0]), int(center_px[1])],
                world_pose_optional=item.get("world_pose_optional") or item.get("world_pose"),
                confidence=float(item.get("confidence", 0.0)),
                source=str(item.get("source", "vlm")),
            )
        )

    return SceneObservation(
        frames=frames or data.get("frames", []),
        camera_info=data.get("camera_info"),
        depth_optional=data.get("depth_optional"),
        vlm_objects=parsed_objects,
        calibration_version=data.get("calibration_version", "jetarm-rgbd-v1"),
        timestamp=data.get("timestamp"),
    )
