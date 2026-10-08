#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


FAILURE_REASONS = [
    "success",
    "missed_block",
    "wrong_direction",
    "too_small_motion",
    "gripper_failed",
    "unsafe_drift",
    "timeout",
    "operator_stop",
    "other",
]


def main():
    parser = argparse.ArgumentParser(description="Collect labeled JetArm VLA rollout episodes.")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--prefix", default="ep_vla_batch_v2")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--duration-s", type=float, default=90.0)
    parser.add_argument("--output-dir", default=str(Path.home() / "jetarm_vla_data/rollouts/raw"))
    parser.add_argument("--instruction", default="pick the red block and place it in the box")
    parser.add_argument("--server-url", default="http://127.0.0.1:18008/select_action")
    parser.add_argument("--health-url", default="http://127.0.0.1:18008/health")
    parser.add_argument("--rate-hz", type=float, default=0.15)
    parser.add_argument("--max-step", type=float, default=0.08)
    parser.add_argument("--action-duration-ms", type=int, default=1000)
    parser.add_argument("--request-timeout-s", type=float, default=25.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary-dir", default=str(Path.home() / "jetarm_vla_data/rollouts/summaries"))
    parser.add_argument("--stop-after-unsafe", type=int, default=3)
    args = parser.parse_args()

    check_health(args.health_url)
    output_dir = Path(args.output_dir)
    summary_dir = Path(args.summary_dir)
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_stem = "{}_{}".format(args.prefix, time.strftime("%Y%m%d_%H%M%S"))
    jsonl_path = summary_dir / "{}.jsonl".format(summary_stem)
    csv_path = summary_dir / "{}.csv".format(summary_stem)

    consecutive_unsafe = 0
    rows = []
    for offset in range(args.count):
        episode_index = args.start_index + offset
        episode_id = "{}_{:03d}".format(args.prefix, episode_index)
        print("\n=== Collecting {} ({}/{}) ===".format(episode_id, offset + 1, args.count), flush=True)
        started = time.time()
        exit_code = run_episode(args, episode_id)
        elapsed = time.time() - started
        meta = read_meta(output_dir / episode_id)
        frame_count = int(meta.get("total_frames", 0)) if meta else 0
        reason = prompt_reason(episode_id, exit_code, frame_count)
        success = reason == "success"
        if reason in ("unsafe_drift", "operator_stop"):
            consecutive_unsafe += 1
        else:
            consecutive_unsafe = 0

        update_meta(output_dir / episode_id, success=success, failure_reason=reason)
        row = {
            "episode_id": episode_id,
            "success": success,
            "failure_reason": reason,
            "exit_code": exit_code,
            "elapsed_s": round(elapsed, 3),
            "frames": frame_count,
            "dry_run": bool(args.dry_run),
            "rate_hz": args.rate_hz,
            "max_step": args.max_step,
            "action_duration_ms": args.action_duration_ms,
        }
        append_jsonl(jsonl_path, row)
        rows.append(row)
        write_csv(csv_path, rows)
        print("labeled {} success={} reason={} frames={}".format(episode_id, success, reason, frame_count), flush=True)

        if consecutive_unsafe >= args.stop_after_unsafe:
            print(
                "stopping after {} consecutive unsafe/operator-stop labels".format(consecutive_unsafe),
                file=sys.stderr,
                flush=True,
            )
            return 3

    print("\nsummary_jsonl={}".format(jsonl_path), flush=True)
    print("summary_csv={}".format(csv_path), flush=True)
    return 0


def check_health(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    if payload.get("mode") != "smolvla-checkpoint":
        raise SystemExit("unexpected health mode from {}: {}".format(url, payload))
    print("health ok: {}".format(payload), flush=True)


def run_episode(args, episode_id):
    command = """
source /opt/ros/melodic/setup.bash
if [ -z "$JETARM_ROS_SETUP" ] || [ -z "$JETARM_VLA_SETUP" ]; then
  echo 'Set JETARM_ROS_SETUP and JETARM_VLA_SETUP' >&2
  exit 2
fi
source "$JETARM_ROS_SETUP"
source "$JETARM_VLA_SETUP"
rosnode kill /jetarm_vla_client >/dev/null 2>&1 || true
timeout {timeout_s}s roslaunch jetarm_vla client.launch \\
  server_url:={server_url} \\
  instruction:="{instruction}" \\
  dry_run:={dry_run} \\
  record_rollout:=true \\
  output_dir:={output_dir} \\
  episode_id:={episode_id} \\
  success:=false \\
  failure_reason:=not_labeled \\
  rate_hz:={rate_hz} \\
  request_timeout_s:={request_timeout_s} \\
  max_step:={max_step} \\
  action_duration_ms:={action_duration_ms}
code=$?
rosnode kill /jetarm_vla_client >/dev/null 2>&1 || true
if [ "$code" = "124" ]; then
  exit 0
fi
exit "$code"
""".format(
        timeout_s=max(1, int(round(args.duration_s))),
        server_url=args.server_url,
        instruction=args.instruction.replace('"', '\\"'),
        dry_run=str(bool(args.dry_run)).lower(),
        output_dir=args.output_dir,
        episode_id=episode_id,
        rate_hz=args.rate_hz,
        request_timeout_s=args.request_timeout_s,
        max_step=args.max_step,
        action_duration_ms=args.action_duration_ms,
    )
    return subprocess.call(["bash", "-lc", command])


def prompt_reason(episode_id, exit_code, frame_count):
    print("\nLabel {}: exit_code={} frames={}".format(episode_id, exit_code, frame_count), flush=True)
    print("Valid labels: {}".format(", ".join(FAILURE_REASONS)), flush=True)
    while True:
        try:
            value = input("failure_reason (use success for a successful rollout): ").strip()
        except EOFError:
            value = "operator_stop"
        if value in FAILURE_REASONS:
            return value
        print("invalid label: {}".format(value), flush=True)


def read_meta(episode_dir):
    path = episode_dir / "meta.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def update_meta(episode_dir, success, failure_reason):
    path = episode_dir / "meta.json"
    meta = read_meta(episode_dir)
    meta["success"] = bool(success)
    meta["failure_reason"] = failure_reason
    meta["label_timestamp"] = time.time()
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path, row):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
