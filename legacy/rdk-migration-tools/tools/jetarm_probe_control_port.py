#!/usr/bin/env python3
"""Probe possible JetArm control-board serial ports with read-only servo queries."""

import argparse
import glob
import json
import multiprocessing as mp
import os
import subprocess
import traceback
from typing import Dict, List


DEFAULT_USB_PATTERNS = ["/dev/rrc", "/dev/ttyUSB*", "/dev/ttyACM*", "/dev/serial/by-id/*"]
ONBOARD_UARTS = ["/dev/ttyS1", "/dev/ttyS5"]
ALL_TTY_PATTERNS = [
    "/dev/ttyUSB*",
    "/dev/ttyACM*",
    "/dev/serial/by-id/*",
    "/dev/ttyS*",
    "/dev/ttyTHS*",
    "/dev/ttyAMA*",
    "/dev/ttymxc*",
]


def unique_existing(paths: List[str]) -> List[str]:
    seen = set()
    result = []
    for path in paths:
        for expanded in glob.glob(path):
            real = os.path.realpath(expanded)
            if expanded not in seen and real not in seen and os.path.exists(expanded):
                seen.add(expanded)
                seen.add(real)
                result.append(expanded)
    return result


def describe_path(path: str) -> Dict[str, str]:
    payload = {"path": path, "realpath": os.path.realpath(path)}
    try:
        payload["ls"] = subprocess.check_output(["ls", "-l", path], text=True).strip()
    except Exception as exc:
        payload["ls_error"] = str(exc)
    try:
        payload["udev"] = subprocess.check_output(
            ["udevadm", "info", "--query=property", "--name", path],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=1,
        ).strip()
    except Exception as exc:
        payload["udev_error"] = str(exc)
    return payload


def _probe_one_blocking(path: str, baudrate: int, timeout: float, ids: List[int]) -> Dict[str, object]:
    result: Dict[str, object] = {"path": path, "baudrate": baudrate, "timeout": timeout}
    board = None
    try:
        from ros_robot_controller.ros_robot_controller_sdk import Board

        board = Board(device=path, baudrate=baudrate, timeout=timeout)
        result["open_ok"] = True
        reads = {}
        for servo_id in ids:
            try:
                reads[str(servo_id)] = board.bus_servo_read_id(servo_id)
            except Exception as exc:
                reads[str(servo_id)] = {"error": str(exc)}
        result["bus_servo_read_id"] = reads
        result["detected"] = any(value is not None and not isinstance(value, dict) for value in reads.values())
    except Exception as exc:
        result["open_ok"] = False
        result["error"] = str(exc)
        result["detected"] = False
    finally:
        if board is not None:
            try:
                board.enable_reception(False)
            except Exception:
                pass
            try:
                board.port.close()
            except Exception:
                pass
    return result


def _probe_worker(queue: "mp.Queue[Dict[str, object]]", path: str, baudrate: int, timeout: float, ids: List[int]) -> None:
    try:
        queue.put(_probe_one_blocking(path, baudrate, timeout, ids))
    except Exception as exc:
        queue.put(
            {
                "path": path,
                "baudrate": baudrate,
                "timeout": timeout,
                "open_ok": False,
                "detected": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )


def probe_one(path: str, baudrate: int, timeout: float, ids: List[int], hard_timeout: float) -> Dict[str, object]:
    queue: "mp.Queue[Dict[str, object]]" = mp.Queue()
    process = mp.Process(target=_probe_worker, args=(queue, path, baudrate, timeout, ids))
    process.start()
    process.join(hard_timeout)
    if process.is_alive():
        process.terminate()
        process.join(1.0)
        return {
            "path": path,
            "baudrate": baudrate,
            "timeout": timeout,
            "hard_timeout": hard_timeout,
            "open_ok": True,
            "detected": False,
            "timed_out": True,
            "error": "read-only probe timed out; likely no JetArm servo bus response on this port",
        }
    if process.exitcode not in (0, None):
        return {
            "path": path,
            "baudrate": baudrate,
            "timeout": timeout,
            "hard_timeout": hard_timeout,
            "open_ok": False,
            "detected": False,
            "exitcode": process.exitcode,
            "error": "probe worker exited unexpectedly",
        }
    if queue.empty():
        return {
            "path": path,
            "baudrate": baudrate,
            "timeout": timeout,
            "hard_timeout": hard_timeout,
            "open_ok": False,
            "detected": False,
            "error": "probe worker returned no result",
        }
    result = queue.get()
    result["hard_timeout"] = hard_timeout
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-onboard-uarts", action="store_true", help="Also probe /dev/ttyS1 and /dev/ttyS5.")
    parser.add_argument("--include-all-ttys", action="store_true", help="Also include common USB and board UART tty patterns.")
    parser.add_argument("--candidate", action="append", default=[], help="Extra serial path to probe.")
    parser.add_argument("--baudrate", type=int, default=1_000_000)
    parser.add_argument("--timeout", type=float, default=0.08)
    parser.add_argument("--hard-timeout", type=float, default=2.0, help="Maximum seconds to wait per candidate.")
    parser.add_argument("--read-ids", default="1,2,3,4,5,10")
    parser.add_argument("--read", action="store_true", help="Send read-only servo ID queries. Default only lists candidates.")
    parser.add_argument("--link-rrc", action="store_true", help="If exactly one candidate is detected, create /dev/rrc symlink.")
    args = parser.parse_args()

    patterns = list(DEFAULT_USB_PATTERNS) + args.candidate
    if args.include_onboard_uarts:
        patterns.extend(ONBOARD_UARTS)
    if args.include_all_ttys:
        patterns.extend(ALL_TTY_PATTERNS)
    candidates = unique_existing(patterns)
    ids = [int(item.strip()) for item in args.read_ids.split(",") if item.strip()]

    payload: Dict[str, object] = {
        "mode": "read" if args.read else "list",
        "candidates": [describe_path(path) for path in candidates],
        "probes": [],
    }

    if args.read:
        probes = [probe_one(path, args.baudrate, args.timeout, ids, args.hard_timeout) for path in candidates]
        payload["probes"] = probes
        detected = [item["path"] for item in probes if item.get("detected")]
        payload["detected_candidates"] = detected
        if args.link_rrc:
            if len(detected) == 1:
                target = os.path.realpath(detected[0])
                subprocess.check_call(["sudo", "ln", "-sfn", target, "/dev/rrc"])
                payload["linked_rrc_to"] = target
            else:
                payload["link_rrc_skipped"] = "expected exactly one detected candidate"

    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
