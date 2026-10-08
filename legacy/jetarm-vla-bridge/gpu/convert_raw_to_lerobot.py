from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert raw JetArm episodes into a LeRobot dataset.")
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--repo-id", required=True, help="Local or Hub repo id, e.g. your-account/jetarm_rgbd_pick_place")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--robot-type", default="jetarm_6dof_rgbd")
    parser.add_argument(
        "--lerobot-home",
        type=Path,
        default=Path(os.environ.get("HF_LEROBOT_HOME", str(Path.home() / ".cache/huggingface/lerobot"))),
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--success-only", action="store_true", help="Only convert episodes with meta.success=true.")
    parser.add_argument(
        "--episode-id",
        action="append",
        default=[],
        help="Episode id to include. Can be passed multiple times.",
    )
    parser.add_argument(
        "--episode-list",
        type=Path,
        default=None,
        help="Text file containing episode ids to include, one per line.",
    )
    args = parser.parse_args()

    os.environ["HF_LEROBOT_HOME"] = str(args.lerobot_home)
    dataset_root = args.lerobot_home / args.repo_id
    if dataset_root.exists():
        if not args.overwrite:
            raise SystemExit(f"dataset already exists: {dataset_root}; pass --overwrite to replace it")
        shutil.rmtree(dataset_root)

    try:
        from lerobot.datasets import LeRobotDataset
    except ImportError as exc:
        raise SystemExit("Install LeRobot before conversion: python -m pip install -e '.[smolvla]'") from exc

    features = {
        "observation.images.rgb_front": {
            "dtype": "image",
            "shape": (400, 640, 3),
            "names": ["height", "width", "channels"],
        },
        "observation.images.depth_front_vis": {
            "dtype": "image",
            "shape": (400, 640, 3),
            "names": ["height", "width", "channels"],
        },
        "observation.state": {"dtype": "float32", "shape": (13,)},
        "action": {"dtype": "float32", "shape": (6,)},
        "language_instruction": {"dtype": "string", "shape": (1,)},
    }
    dataset = LeRobotDataset.create(
        repo_id=args.repo_id,
        fps=args.fps,
        features=features,
        robot_type=args.robot_type,
        use_videos=True,
        image_writer_threads=4,
    )

    converted = 0
    for episode_dir in select_episode_dirs(
        args.raw_root,
        success_only=args.success_only,
        episode_ids=load_episode_ids(args.episode_id, args.episode_list),
    ):
        frames_path = episode_dir / "frames.jsonl"
        if not frames_path.exists():
            continue
        for line in frames_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            dataset.add_frame(
                {
                    "observation.images.rgb_front": np.asarray(Image.open(episode_dir / record["observation.images.rgb_front"])),
                    "observation.images.depth_front_vis": np.asarray(Image.open(episode_dir / record["observation.images.depth_front_vis"])),
                    "observation.state": np.asarray(record["observation.state"], dtype=np.float32),
                    "action": np.asarray(record["action"], dtype=np.float32),
                    "language_instruction": record["language_instruction"],
                    "task": record["language_instruction"],
                }
            )
        dataset.save_episode()
        converted += 1
    if converted == 0:
        raise SystemExit("no episodes matched conversion filters")
    dataset.finalize()
    print(f"converted {converted} episodes from {args.raw_root} -> {dataset_root}")
    return 0


def load_episode_ids(cli_episode_ids, episode_list):
    episode_ids = set(cli_episode_ids or [])
    if episode_list is not None:
        for line in episode_list.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                episode_ids.add(value)
    return episode_ids


def select_episode_dirs(raw_root, success_only=False, episode_ids=None):
    episode_ids = set(episode_ids or [])
    missing = set(episode_ids)
    selected = []
    for episode_dir in sorted(path for path in raw_root.iterdir() if path.is_dir()):
        meta_path = episode_dir / "meta.json"
        if not meta_path.exists():
            continue
        if episode_ids and episode_dir.name not in episode_ids:
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if success_only and not bool(meta.get("success", False)):
            continue
        selected.append(episode_dir)
        missing.discard(episode_dir.name)
    if missing:
        raise SystemExit("missing requested episodes: {}".format(", ".join(sorted(missing))))
    return selected


if __name__ == "__main__":
    raise SystemExit(main())
