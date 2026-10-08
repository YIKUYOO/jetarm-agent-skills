import pytest

from jetarm_demo_agent.understanding.vlm_scene import parse_scene_objects_payload


def test_parse_scene_objects_payload_accepts_markdown_json_and_normalizes_objects():
    payload = """
```json
{
  "summary": "桌面上有药盒和碗。",
  "objects": [
    {"name": "药盒", "bbox_xyxy_norm": [0.1, 0.2, 0.4, 0.6], "confidence": 0.88},
    {"name": "碗", "bbox_xyxy_norm": [0.55, 0.3, 0.85, 0.7], "confidence": 0.91}
  ]
}
```
"""

    observation = parse_scene_objects_payload(payload, image_size=(640, 480), frames=[{"label": "center"}])

    assert observation.vlm_objects[0].name == "药盒"
    assert observation.vlm_objects[0].center_px == [160, 192]
    assert observation.vlm_objects[1].name == "碗"
    assert observation.vlm_objects[1].center_px == [448, 240]


def test_parse_scene_objects_payload_rejects_missing_objects():
    with pytest.raises(ValueError, match="objects"):
        parse_scene_objects_payload('{"summary":"empty"}', image_size=(640, 480), frames=[])
