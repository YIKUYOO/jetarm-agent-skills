from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Read one batch from a LeRobot dataset.")
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--batch-size", type=int, default=1)
    args = parser.parse_args()

    try:
        import torch
        from torch.utils.data import DataLoader
        from lerobot.datasets import LeRobotDataset
    except ImportError as exc:
        raise SystemExit(f"missing LeRobot/PyTorch dependency: {exc}") from exc

    kwargs = {"repo_id": args.repo_id}
    if args.root is not None:
        kwargs["root"] = args.root
    kwargs["video_backend"] = "pyav"
    dataset = LeRobotDataset(**kwargs)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False)
    batch = next(iter(loader))

    print("dataset_frames", len(dataset))
    for key in [
        "observation.images.rgb_front",
        "observation.images.depth_front_vis",
        "observation.state",
        "action",
        "language_instruction",
        "task",
    ]:
        value = batch.get(key)
        if value is None:
            print(key, "MISSING")
        elif hasattr(value, "shape"):
            print(key, tuple(value.shape), getattr(value, "dtype", ""))
        else:
            print(key, type(value).__name__, value[:1] if isinstance(value, list) else value)
    if hasattr(torch, "cuda"):
        print("cuda_available", torch.cuda.is_available())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
