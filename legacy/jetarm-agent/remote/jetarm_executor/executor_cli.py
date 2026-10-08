import argparse
import json
from typing import Optional, Sequence

try:
    from .health import get_health
    from .ros_adapters import (
        capture_camera_frame,
        detect_color,
        find_red_block,
        go_home,
        lift_red_block,
        pick_and_place_color,
        pick_red_block,
        debug_move_to_pick_pose,
        place_red_block_back_to_pick_xy,
        place_red_block_near_origin,
        scan_scene,
    )
except ImportError:
    from health import get_health
    from ros_adapters import (
        capture_camera_frame,
        detect_color,
        find_red_block,
        go_home,
        lift_red_block,
        pick_and_place_color,
        pick_red_block,
        debug_move_to_pick_pose,
        place_red_block_back_to_pick_xy,
        place_red_block_near_origin,
        scan_scene,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--camera-frame", action="store_true")
    parser.add_argument("--stream", default="color")
    args = parser.parse_args(argv)
    if args.health:
        print(json.dumps(get_health(), ensure_ascii=False))
        return 0
    if args.camera_frame:
        print(json.dumps(capture_camera_frame(args.stream), ensure_ascii=False))
        return 0

    if not args.request_json:
        raise SystemExit("--request-json or --health or --camera-frame is required")

    request = json.loads(args.request_json)
    mode = request.get("mode", "safe")
    intent = request["intent"]
    result = {
        "summary": "remote executor placeholder",
        "motion_executed": mode == "live",
        "target_color": request.get("args", {}).get("target_color"),
        "destination": request.get("args", {}).get("destination"),
    }

    if intent == "detect_color":
        result = detect_color(request.get("args", {}).get("target_color", "red"))
    elif intent == "go_home":
        result = go_home()
    elif intent == "pick_and_place_color":
        result = pick_and_place_color(
            request.get("args", {}).get("target_color"),
            request.get("args", {}).get("destination"),
            mode,
            request.get("context", {}).get("single_block_demo_mode", False),
        )
    elif intent == "scan_scene":
        result = scan_scene(mode)
    elif intent == "find_red_block":
        result = find_red_block(
            target_hint_sector=request.get("args", {}).get("target_hint_sector"),
            search_strategy=request.get("args", {}).get("search_strategy", "directional_scan"),
            mode=mode,
        )
    elif intent == "pick_red_block":
        result = pick_red_block(
            mode,
            locked_pose=request.get("args", {}).get("locked_pose"),
            locked_align_angle=request.get("args", {}).get("locked_align_angle"),
        )
    elif intent == "lift_red_block":
        result = lift_red_block(mode)
    elif intent == "debug_move_to_pick_pose":
        result = debug_move_to_pick_pose(
            mode,
            locked_pose=request.get("args", {}).get("locked_pose"),
            locked_align_angle=request.get("args", {}).get("locked_align_angle"),
        )
    elif intent == "place_red_block_back_to_pick_xy":
        result = place_red_block_back_to_pick_xy(
            mode,
            pick_pose=request.get("args", {}).get("pick_pose"),
            pick_align_angle=request.get("args", {}).get("pick_align_angle"),
        )
    elif intent == "place_red_block_near_origin":
        result = place_red_block_near_origin(mode)

    ok = True
    if intent == "scan_scene":
        ok = bool(result.get("frames"))
    elif intent == "find_red_block":
        ok = bool(result.get("detected"))
    elif intent in {"pick_red_block", "place_red_block_near_origin", "debug_move_to_pick_pose"}:
        ok = bool(result.get("complete"))
    elif intent == "place_red_block_back_to_pick_xy":
        ok = bool(result.get("complete"))

    executor_state = "DRY_RUN_COMPLETED" if mode == "dry_run" else ("SUCCEEDED" if ok else "FAILED")

    response = {
        "ok": ok,
        "task_id": request["task_id"],
        "executor_state": executor_state,
        "mode": mode,
        "intent": intent,
        "result": result,
        "telemetry": {
            "single_block_demo_mode": request.get("context", {}).get("single_block_demo_mode", False),
            "ros_context": get_health().get("ros_context", {}),
        },
        "error": None if ok else {"type": "EXECUTOR_ERROR", "code": "DEMO_STEP_FAILED", "message": result.get("summary", "demo step failed"), "retryable": True},
    }
    print(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
