import json
from pathlib import Path

import numpy as np
from PIL import Image

from . import SCHEMA_VERSION
from .schema import DatasetFrame


class EpisodeWriter:
    """Persist one JetArm RGB-D VLA episode as images plus JSONL frame records."""

    def __init__(
        self,
        root,
        episode_id,
        language_instruction,
        fps,
        png_compress_level=1,
    ):
        self.root = Path(root)
        self.episode_id = episode_id
        self.language_instruction = language_instruction
        self.fps = fps
        self.png_compress_level = int(png_compress_level)
        self.episode_dir = self.root / episode_id
        self.rgb_dir = self.episode_dir / "rgb"
        self.depth_vis_dir = self.episode_dir / "depth_vis"
        self.depth_raw_dir = self.episode_dir / "depth_raw_mm"
        for directory in (self.rgb_dir, self.depth_vis_dir, self.depth_raw_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self._frames_path = self.episode_dir / "frames.jsonl"
        self._frame_file = self._frames_path.open("w", encoding="utf-8")
        self._frame_count = 0

    def add_frame(self, frame):
        frame.validate()
        index = self._frame_count
        basename = f"frame_{index:06d}.png"
        rgb_path = self.rgb_dir / basename
        depth_vis_path = self.depth_vis_dir / basename
        depth_raw_path = self.depth_raw_dir / basename

        Image.fromarray(frame.rgb).save(rgb_path, compress_level=self.png_compress_level)
        Image.fromarray(frame.depth_vis).save(depth_vis_path, compress_level=self.png_compress_level)
        Image.fromarray(frame.depth_raw_mm).save(depth_raw_path, compress_level=self.png_compress_level)

        record = {
            "frame_index": index,
            "timestamp": frame.timestamp,
            "language_instruction": frame.language_instruction,
            "observation.images.rgb_front": _rel(self.episode_dir, rgb_path),
            "observation.images.depth_front_vis": _rel(self.episode_dir, depth_vis_path),
            "observation.depth.raw_mm": _rel(self.episode_dir, depth_raw_path),
            "observation.state": _tolist(frame.state),
            "action": _tolist(frame.action),
            "metadata.ee_pose": _tolist(frame.ee_pose),
            "metadata.camera.color_info": frame.color_camera_info,
            "metadata.camera.depth_info": frame.depth_camera_info,
        }
        record.update(frame.extra_metadata)
        self._frame_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._frame_file.flush()
        self._frame_count += 1

    def close(self, success, failure_reason=""):
        if not self._frame_file.closed:
            self._frame_file.close()
        meta = {
            "schema_version": SCHEMA_VERSION,
            "episode_id": self.episode_id,
            "language_instruction": self.language_instruction,
            "fps": self.fps,
            "total_frames": self._frame_count,
            "success": bool(success),
            "failure_reason": failure_reason,
        }
        (self.episode_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self._frame_file.closed:
            self.close(success=False, failure_reason=str(exc) if exc else "closed without explicit status")


def _rel(root, path):
    return path.relative_to(root).as_posix()


def _tolist(array):
    return np.asarray(array, dtype=np.float32).round(6).tolist()
