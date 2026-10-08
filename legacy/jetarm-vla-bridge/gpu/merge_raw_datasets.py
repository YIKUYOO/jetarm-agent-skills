from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge raw JetArm episode directories into one raw dataset.")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.output_root.exists():
        if not args.overwrite:
            raise SystemExit(f"output already exists: {args.output_root}; pass --overwrite")
        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)

    copied = 0
    for source in args.source:
        if not source.exists():
            raise SystemExit(f"missing source dataset: {source}")
        for episode_dir in sorted(path for path in source.iterdir() if path.is_dir()):
            if not (episode_dir / "meta.json").exists():
                continue
            target = args.output_root / episode_dir.name
            if target.exists():
                raise SystemExit(f"duplicate episode id: {episode_dir.name}")
            shutil.copytree(episode_dir, target)
            copied += 1
    print(f"merged {copied} episodes -> {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
