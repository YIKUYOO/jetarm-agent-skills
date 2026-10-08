#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path


VALID_REASONS = {
    "success",
    "missed_block",
    "wrong_direction",
    "too_small_motion",
    "gripper_failed",
    "unsafe_drift",
    "timeout",
    "operator_stop",
    "other",
}


def main():
    parser = argparse.ArgumentParser(description="Apply manual labels to JetArm rollout meta.json files.")
    parser.add_argument("--root", default=str(Path.home() / "jetarm_vla_data/rollouts/raw"))
    parser.add_argument("--labels-json", required=True, help="JSON object mapping episode_id to failure_reason.")
    args = parser.parse_args()

    root = Path(args.root)
    labels = json.loads(Path(args.labels_json).read_text(encoding="utf-8"))
    for episode_id, reason in sorted(labels.items()):
        if reason not in VALID_REASONS:
            raise SystemExit("invalid reason for {}: {}".format(episode_id, reason))
        meta_path = root / episode_id / "meta.json"
        if not meta_path.exists():
            raise SystemExit("missing meta.json for {}".format(episode_id))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["success"] = reason == "success"
        meta["failure_reason"] = reason
        meta["label_timestamp"] = time.time()
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("{} -> {}".format(episode_id, reason))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
