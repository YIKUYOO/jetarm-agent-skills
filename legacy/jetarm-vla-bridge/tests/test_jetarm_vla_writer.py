import json

import numpy as np
from PIL import Image

from jetarm_vla_common.dataset_writer import EpisodeWriter
from jetarm_vla_common.schema import DatasetFrame


def _frame(index: int) -> DatasetFrame:
    rgb = np.full((3, 4, 3), index, dtype=np.uint8)
    depth_raw = np.full((3, 4), 1000 + index, dtype=np.uint16)
    depth_vis = np.full((3, 4, 3), 20 + index, dtype=np.uint8)
    return DatasetFrame(
        timestamp=float(index),
        language_instruction="pick the red block and place it in the box",
        rgb=rgb,
        depth_raw_mm=depth_raw,
        depth_vis=depth_vis,
        state=np.zeros(13, dtype=np.float32),
        action=np.ones(6, dtype=np.float32) * 0.5,
        ee_pose=np.zeros(7, dtype=np.float32),
        color_camera_info={"width": 4, "height": 3},
        depth_camera_info={"width": 4, "height": 3},
        extra_metadata={"metadata.policy.latency_ms": 12.5},
    )


def test_episode_writer_persists_metadata_frames_and_png_images(tmp_path):
    writer = EpisodeWriter(
        root=tmp_path,
        episode_id="ep_test",
        language_instruction="pick the red block and place it in the box",
        fps=10,
    )

    writer.add_frame(_frame(0))
    writer.close(success=True, failure_reason="")

    episode_dir = tmp_path / "ep_test"
    meta = json.loads((episode_dir / "meta.json").read_text(encoding="utf-8"))
    records = (episode_dir / "frames.jsonl").read_text(encoding="utf-8").strip().splitlines()

    assert meta["schema_version"] == "jetarm-vla-rgbd-v1"
    assert meta["success"] is True
    assert len(records) == 1
    assert json.loads(records[0])["metadata.policy.latency_ms"] == 12.5
    assert (episode_dir / "rgb" / "frame_000000.png").exists()
    assert (episode_dir / "depth_vis" / "frame_000000.png").exists()
    assert (episode_dir / "depth_raw_mm" / "frame_000000.png").exists()
    assert np.asarray(Image.open(episode_dir / "depth_raw_mm" / "frame_000000.png")).dtype == np.uint16
