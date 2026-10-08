from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize labeled JetArm rollout evaluation results.")
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for episode_dir in sorted(path for path in args.raw_root.iterdir() if path.is_dir()):
        if args.prefix and not episode_dir.name.startswith(args.prefix):
            continue
        meta_path = episode_dir / "meta.json"
        frames_path = episode_dir / "frames.jsonl"
        if not meta_path.exists() or not frames_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        records = [json.loads(line) for line in frames_path.read_text(encoding="utf-8").splitlines()]
        latencies = [
            record.get("metadata.policy.latency_ms")
            for record in records
            if isinstance(record.get("metadata.policy.latency_ms"), (int, float))
        ]
        rejected = [record for record in records if record.get("metadata.safety.rejected")]
        rows.append(
            {
                "episode_id": episode_dir.name,
                "success": bool(meta.get("success")),
                "failure_reason": meta.get("failure_reason", ""),
                "frames": len(records),
                "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else None,
                "rejected": len(rejected),
            }
        )

    success_count = sum(1 for row in rows if row["success"])
    summary = {
        "episodes": len(rows),
        "success_count": success_count,
        "success_rate": success_count / len(rows) if rows else 0.0,
        "rows": rows,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if rows:
        with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
