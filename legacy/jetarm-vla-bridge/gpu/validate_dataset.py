import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


ROLLOUT_METADATA_KEYS = [
    "metadata.policy.raw_action",
    "metadata.policy.safe_action",
    "metadata.policy.latency_ms",
    "metadata.policy.mode",
    "metadata.policy.message",
    "metadata.safety.executed",
    "metadata.safety.rejected",
    "metadata.safety.reject_reason",
]

VALID_LABELS = {
    "success",
    "missed_block",
    "wrong_direction",
    "too_small_motion",
    "gripper_failed",
    "unsafe_drift",
    "timeout",
    "operator_stop",
    "other",
    "not_labeled",
    "smoke_unlabeled",
}


def validate_dataset(root, require_rollout_metadata=False, min_frames=0, forbid_not_labeled=False):
    errors = []
    if (root / "meta.json").exists():
        episode_dirs = [root]
    else:
        episode_dirs = sorted(path for path in root.iterdir() if path.is_dir())
    for episode_dir in episode_dirs:
        meta_path = episode_dir / "meta.json"
        frames_path = episode_dir / "frames.jsonl"
        if not meta_path.exists():
            errors.append(f"{episode_dir.name}: missing meta.json")
            continue
        if not frames_path.exists():
            errors.append(f"{episode_dir.name}: missing frames.jsonl")
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        failure_reason = meta.get("failure_reason", "")
        if forbid_not_labeled and failure_reason in {"", "not_labeled"}:
            errors.append(f"{episode_dir.name}: missing manual label")
        if failure_reason and failure_reason not in VALID_LABELS and not failure_reason.startswith("smoke_"):
            errors.append(f"{episode_dir.name}: unknown failure_reason {failure_reason}")
        frame_count = 0
        for line_number, line in enumerate(frames_path.read_text(encoding="utf-8").splitlines(), start=1):
            frame_count += 1
            record = json.loads(line)
            for key in [
                "observation.images.rgb_front",
                "observation.images.depth_front_vis",
                "observation.depth.raw_mm",
            ]:
                image_path = episode_dir / record[key]
                if not image_path.exists():
                    errors.append(f"{episode_dir.name}:{line_number}: missing {key} {image_path}")
            if len(record.get("observation.state", [])) != 13:
                errors.append(f"{episode_dir.name}:{line_number}: invalid state length")
            if len(record.get("action", [])) != 6:
                errors.append(f"{episode_dir.name}:{line_number}: invalid action length")
            if require_rollout_metadata:
                for key in ROLLOUT_METADATA_KEYS:
                    if key not in record:
                        errors.append(f"{episode_dir.name}:{line_number}: missing rollout metadata {key}")
            try:
                depth = np.asarray(Image.open(episode_dir / record["observation.depth.raw_mm"]))
                if depth.ndim != 2:
                    errors.append(f"{episode_dir.name}:{line_number}: raw depth is not 2-D")
                elif depth.min() < 0 or depth.max() > 65535:
                    errors.append(f"{episode_dir.name}:{line_number}: raw depth exceeds uint16 range")
            except Exception as exc:
                errors.append(f"{episode_dir.name}:{line_number}: depth read failed: {exc}")
        if meta.get("total_frames") != frame_count:
            errors.append(f"{episode_dir.name}: meta total_frames does not match frames.jsonl")
        if min_frames and frame_count < min_frames:
            errors.append(f"{episode_dir.name}: expected at least {min_frames} frames, got {frame_count}")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--require-rollout-metadata", action="store_true")
    parser.add_argument("--min-frames", type=int, default=0)
    parser.add_argument("--forbid-not-labeled", action="store_true")
    args = parser.parse_args()
    errors = validate_dataset(
        args.root,
        require_rollout_metadata=args.require_rollout_metadata,
        min_frames=args.min_frames,
        forbid_not_labeled=args.forbid_not_labeled,
    )
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"validated raw JetArm VLA dataset: {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
