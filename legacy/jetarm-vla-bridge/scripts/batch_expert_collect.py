#!/usr/bin/env python3
import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
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
    parser = argparse.ArgumentParser(description="Collect JetArm expert demonstrations with official JetArm nodes.")
    parser.add_argument("--target-successes", type=int, default=30)
    parser.add_argument("--max-attempts", type=int, default=45)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--prefix", default="ep_expert_red")
    parser.add_argument("--output-dir", default=str(Path.home() / "jetarm_vla_data/expert/raw/jetarm_pick_place_expert_v2"))
    parser.add_argument("--instruction", default="pick the red block and place it in the box")
    parser.add_argument("--expert-source", choices=["track_and_grab", "object_sortting"], default="track_and_grab")
    parser.add_argument(
        "--object-sortting-mode",
        choices=["resident", "launch"],
        default="resident",
        help="Use the app_bringup resident /object_sortting service, or launch a temporary node.",
    )
    parser.add_argument("--target-color", default="red")
    parser.add_argument("--enable-disp", action="store_true")
    parser.add_argument("--source-image-topic", default="/rgbd_cam/color/image_rect_color")
    parser.add_argument("--camera-info-topic", default="/rgbd_cam/color/camera_info")
    parser.add_argument("--service-wait-s", type=int, default=25)
    parser.add_argument("--post-cycle-capture-s", type=float, default=3.0)
    parser.add_argument(
        "--color-sortting-offset",
        type=float,
        nargs=3,
        metavar=("X", "Y", "Z"),
        default=None,
        help="Temporarily override /positions/color_sortting/offset for this run, then restore it.",
    )
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--duration-s", type=float, default=45.0)
    parser.add_argument("--capture-lead-s", type=float, default=2.0)
    parser.add_argument("--writer-queue-size", type=int, default=300)
    parser.add_argument("--png-compress-level", type=int, default=0)
    parser.add_argument("--query-ee-pose", action="store_true")
    parser.add_argument("--countdown-s", type=int, default=10)
    parser.add_argument("--summary-dir", default=str(Path.home() / "jetarm_vla_data/expert/summaries"))
    parser.add_argument("--overwrite-existing", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    summary_dir = Path(args.summary_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_stem = "{}_{}".format(args.prefix, time.strftime("%Y%m%d_%H%M%S"))
    jsonl_path = summary_dir / "{}.jsonl".format(summary_stem)
    csv_path = summary_dir / "{}.csv".format(summary_stem)

    successes = 0
    attempts = 0
    rows = []
    while successes < args.target_successes and attempts < args.max_attempts:
        episode_index = args.start_index + successes
        episode_id = "{}_{:03d}".format(args.prefix, episode_index)
        attempt_id = attempts + 1
        print("\n=== Expert attempt {} -> {} (success {}/{}) ===".format(
            attempt_id, episode_id, successes, args.target_successes
        ), flush=True)
        prepare_episode_dir(output_dir / episode_id, args.overwrite_existing)
        countdown(args.countdown_s)
        started = time.time()
        exit_code = run_expert_episode(args, episode_id)
        elapsed = time.time() - started
        meta = read_meta(output_dir / episode_id)
        frame_count = int(meta.get("total_frames", 0)) if meta else 0
        reason = prompt_reason(episode_id, exit_code, frame_count)
        success = reason == "success"
        note = prompt_note()
        update_meta(output_dir / episode_id, success=success, failure_reason=reason, note=note)
        record_expert_metadata(output_dir / episode_id, args)

        row = {
            "attempt": attempt_id,
            "episode_id": episode_id,
            "success": success,
            "failure_reason": reason,
            "frames": frame_count,
            "exit_code": exit_code,
            "elapsed_s": round(elapsed, 3),
            "expert_source": args.expert_source,
            "color_sortting_offset": format_offset(args.color_sortting_offset),
        }
        rows.append(row)
        append_jsonl(jsonl_path, row)
        write_csv(csv_path, rows)
        print("labeled {} success={} reason={} frames={}".format(episode_id, success, reason, frame_count), flush=True)
        if success:
            successes += 1
        else:
            move_failed_attempt(output_dir, episode_id, reason, attempt_id)
        attempts += 1

    print("\nsummary_jsonl={}".format(jsonl_path), flush=True)
    print("summary_csv={}".format(csv_path), flush=True)
    print("successes={} attempts={}".format(successes, attempts), flush=True)
    return 0 if successes >= args.target_successes else 4


def prepare_episode_dir(episode_dir, overwrite):
    if not episode_dir.exists():
        return
    if overwrite:
        shutil.rmtree(str(episode_dir))
        return
    raise SystemExit("episode already exists: {}; pass --overwrite-existing or change --start-index".format(episode_dir))


def countdown(seconds):
    print("COUNTDOWN_START", flush=True)
    for value in range(max(0, seconds), 0, -1):
        print("expert_starting_in={}".format(value), flush=True)
        time.sleep(1)


def run_expert_episode(args, episode_id):
    capture_duration_s = max(1, int(round(args.duration_s + args.capture_lead_s)))
    timeout_s = max(1, int(round(capture_duration_s + args.service_wait_s + 20)))
    if args.expert_source == "object_sortting":
        expert_command = build_object_sortting_command(args)
        stop_object_sortting = "true" if args.object_sortting_mode == "launch" else "false"
    else:
        expert_command = build_track_and_grab_command(args)
        stop_object_sortting = "false"
    command = """
source /opt/ros/melodic/setup.bash
if [ -z "$JETARM_ROS_SETUP" ] || [ -z "$JETARM_VLA_SETUP" ]; then
  echo 'Set JETARM_ROS_SETUP and JETARM_VLA_SETUP' >&2
  exit 2
fi
source "$JETARM_ROS_SETUP"
source "$JETARM_VLA_SETUP"
rosnode kill /jetarm_vla_capture >/dev/null 2>&1 || true
rosnode kill /track_and_grab >/dev/null 2>&1 || true
if {stop_object_sortting}; then
  rosnode kill /object_sortting >/dev/null 2>&1 || true
fi
{color_sortting_param_setup}
roslaunch jetarm_vla capture.launch \\
  output_dir:={output_dir} \\
  episode_id:={episode_id} \\
  instruction:="{instruction}" \\
  fps:={fps} \\
  duration_s:={capture_duration_s} \\
  success:=false \\
  failure_reason:=not_labeled \\
  query_ee_pose:={query_ee_pose} \\
  capture_source:=official_{expert_source} \\
  writer_queue_size:={writer_queue_size} \\
  png_compress_level:={png_compress_level} &
CAPTURE_PID=$!
sleep {capture_lead_s}
{expert_command}
wait "$CAPTURE_PID"
CAPTURE_RC=$?
rosnode kill /jetarm_vla_capture >/dev/null 2>&1 || true
rosnode kill /track_and_grab >/dev/null 2>&1 || true
if {stop_object_sortting}; then
  rosnode kill /object_sortting >/dev/null 2>&1 || true
fi
exit "$CAPTURE_RC"
""".format(
        output_dir=args.output_dir,
        episode_id=episode_id,
        instruction=args.instruction.replace('"', '\\"'),
        fps=args.fps,
        capture_duration_s=capture_duration_s,
        capture_lead_s=max(0.0, float(args.capture_lead_s)),
        query_ee_pose=str(bool(args.query_ee_pose)).lower(),
        expert_source=args.expert_source,
        writer_queue_size=args.writer_queue_size,
        png_compress_level=args.png_compress_level,
        color_sortting_param_setup=build_color_sortting_param_setup(args),
        stop_object_sortting=stop_object_sortting,
        expert_command=expert_command,
    )
    return subprocess.call(["timeout", "{}s".format(timeout_s), "bash", "-lc", command])


def build_track_and_grab_command(args):
    return """
rosrun jetarm_6dof_rgbd_cam track_and_grab.py _target_color:={target_color} _enable_disp:={enable_disp} &
EXPERT_PID=$!
sleep {duration_s}
kill "$EXPERT_PID" >/dev/null 2>&1 || true
rosnode kill /track_and_grab >/dev/null 2>&1 || true
""".format(
        target_color=args.target_color,
        enable_disp=str(bool(args.enable_disp)).lower(),
        duration_s=max(1.0, float(args.duration_s)),
    )


def build_color_sortting_param_setup(args):
    if args.color_sortting_offset is None:
        return "echo color_sortting_offset=default"
    x, y, z = [float(value) for value in args.color_sortting_offset]
    return f"""
COLOR_SORTTING_ORIGINAL=/tmp/color_sortting_original_$$.yaml
rosparam get /positions/color_sortting > "$COLOR_SORTTING_ORIGINAL"
restore_color_sortting_params() {{
  rosparam load "$COLOR_SORTTING_ORIGINAL" /positions/color_sortting >/dev/null 2>&1 || true
}}
trap restore_color_sortting_params EXIT
rosparam set /positions/color_sortting/offset "[{x:.6f}, {y:.6f}, {z:.6f}]"
echo color_sortting_offset="[{x:.6f},{y:.6f},{z:.6f}]"
"""


def build_object_sortting_command(args):
    if args.object_sortting_mode == "resident":
        return build_resident_object_sortting_command(args)
    return build_launched_object_sortting_command(args)


def build_launched_object_sortting_command(args):
    # object_sortting is loop-capable. Stop it after one pick/place cycle so a
    # single episode does not silently contain multiple expert attempts.
    return """
roslaunch jetarm_6dof_app object_sortting.launch \\
  source_image_topic:={source_image_topic} \\
  camera_info_topic:={camera_info_topic} &
EXPERT_PID=$!
READY=0
for i in $(seq 1 {service_wait_s}); do
  if rosservice list | grep -q '^/object_sortting/enter$'; then READY=1; break; fi
  sleep 1
done
echo object_sortting_service_ready=$READY
if [ "$READY" = "1" ]; then
  rosservice call /object_sortting/enter "{{}}" || true
  sleep 1
  rosservice call /object_sortting/set_color_target "data_str: '{target_color}'
data_bool: true" || true
  sleep 1
  rosservice call /object_sortting/enable_sortting "data: true" || true
  timeout {duration_s}s rostopic echo -n 2 /grasp/result >/tmp/object_sortting_grasp_result.log 2>&1 || true
  sleep {post_cycle_capture_s}
  rosservice call /object_sortting/enable_sortting "data: false" >/dev/null 2>&1 || true
  rosservice call /object_sortting/exit "{{}}" >/dev/null 2>&1 || true
else
  sleep {duration_s}
fi
kill "$EXPERT_PID" >/dev/null 2>&1 || true
rosnode kill /object_sortting >/dev/null 2>&1 || true
""".format(
        source_image_topic=args.source_image_topic,
        camera_info_topic=args.camera_info_topic,
        service_wait_s=max(1, int(args.service_wait_s)),
        target_color=args.target_color,
        duration_s=max(1.0, float(args.duration_s)),
        post_cycle_capture_s=max(0.0, float(args.post_cycle_capture_s)),
    )


def build_resident_object_sortting_command(args):
    # app_bringup can keep /object_sortting alive with respawn. In that mode we
    # must reuse its services instead of launching a second node with the same name.
    return """
READY=0
for i in $(seq 1 {service_wait_s}); do
  if rosservice list | grep -q '^/object_sortting/enter$'; then READY=1; break; fi
  sleep 1
done
echo resident_object_sortting_ready=$READY
if [ "$READY" = "1" ]; then
  rosservice call /object_sortting/enable_sortting "data: false" >/dev/null 2>&1 || true
  rosservice call /object_sortting/exit "{{}}" >/dev/null 2>&1 || true
  sleep 1
  rosservice call /object_sortting/enter "{{}}" || true
  sleep 1
  rosservice call /object_sortting/set_color_target "data_str: '{target_color}'
data_bool: true" || true
  sleep 1
  rosservice call /object_sortting/enable_sortting "data: true" || true
  timeout {duration_s}s rostopic echo -n 2 /grasp/result >/tmp/object_sortting_grasp_result.log 2>&1 || true
  sleep {post_cycle_capture_s}
  rosservice call /object_sortting/enable_sortting "data: false" >/dev/null 2>&1 || true
  rosservice call /object_sortting/exit "{{}}" >/dev/null 2>&1 || true
else
  sleep {duration_s}
fi
""".format(
        service_wait_s=max(1, int(args.service_wait_s)),
        target_color=args.target_color,
        duration_s=max(1.0, float(args.duration_s)),
        post_cycle_capture_s=max(0.0, float(args.post_cycle_capture_s)),
    )


def prompt_reason(episode_id, exit_code, frame_count):
    print("\nLabel {}: exit_code={} frames={}".format(episode_id, exit_code, frame_count), flush=True)
    print("Valid labels: {}".format(", ".join(FAILURE_REASONS)), flush=True)
    while True:
        try:
            value = input("failure_reason (use success for a successful expert demo): ").strip()
        except EOFError:
            value = "operator_stop"
        if value in FAILURE_REASONS:
            return value
        print("invalid label: {}".format(value), flush=True)


def prompt_note():
    try:
        return input("中文备注，可留空: ").strip()
    except EOFError:
        return ""


def read_meta(episode_dir):
    path = episode_dir / "meta.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def update_meta(episode_dir, success, failure_reason, note):
    path = episode_dir / "meta.json"
    meta = read_meta(episode_dir)
    meta["success"] = bool(success)
    meta["failure_reason"] = failure_reason
    meta["label_timestamp"] = time.time()
    if note:
        meta["label_note_zh"] = note
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def record_expert_metadata(episode_dir, args):
    path = episode_dir / "meta.json"
    meta = read_meta(episode_dir)
    meta.setdefault("annotations", {})
    meta["annotations"]["expert_source"] = args.expert_source
    meta["annotations"]["target_color"] = args.target_color
    if args.color_sortting_offset is not None:
        meta["annotations"]["color_sortting_offset"] = [float(value) for value in args.color_sortting_offset]
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def format_offset(offset):
    if offset is None:
        return ""
    return ",".join("{:.6f}".format(float(value)) for value in offset)


def move_failed_attempt(output_dir, episode_id, reason, attempt_id):
    source = output_dir / episode_id
    if not source.exists():
        return
    failed_root = output_dir.parent / "{}_failed_attempts".format(output_dir.name)
    failed_root.mkdir(parents=True, exist_ok=True)
    target = failed_root / "{}_attempt_{:03d}_{}".format(episode_id, attempt_id, reason)
    if target.exists():
        shutil.rmtree(str(target))
    shutil.move(str(source), str(target))
    print("moved_failed_attempt={}".format(target), flush=True)


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
