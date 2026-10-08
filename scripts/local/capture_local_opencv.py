"""Capture a local Windows webcam frame using OpenCV."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2


BACKENDS = [
    ("default", None),
    ("dshow", cv2.CAP_DSHOW),
    ("msmf", cv2.CAP_MSMF),
]


def open_capture(index: int, backend: int | None) -> cv2.VideoCapture:
    if backend is None:
        return cv2.VideoCapture(index)
    return cv2.VideoCapture(index, backend)


def capture_one(
    *,
    output: Path,
    index: int | None,
    width: int,
    height: int,
    fps: float,
    warmup_frames: int,
) -> dict:
    candidates = []
    indices = [index] if index is not None else list(range(0, 8))
    for backend_name, backend in BACKENDS:
        for camera_index in indices:
            cap = open_capture(camera_index, backend)
            opened = bool(cap.isOpened())
            detail = {"backend": backend_name, "index": camera_index, "opened": opened, "read_ok": False}
            if not opened:
                cap.release()
                candidates.append(detail)
                continue

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            frame = None
            ok = False
            for _ in range(max(1, warmup_frames)):
                ok, frame = cap.read()
                time.sleep(0.03)
            detail.update(
                {
                    "read_ok": bool(ok and frame is not None),
                    "actual_width": float(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0.0),
                    "actual_height": float(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0.0),
                    "actual_fps": float(cap.get(cv2.CAP_PROP_FPS) or 0.0),
                }
            )
            if ok and frame is not None:
                output.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(output), frame)
                cap.release()
                return {"ok": True, "output": str(output), "selected": detail, "attempts": candidates + [detail]}
            cap.release()
            candidates.append(detail)

    return {"ok": False, "output": str(output), "attempts": candidates}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--warmup-frames", type=int, default=8)
    args = parser.parse_args()
    result = capture_one(
        output=args.output,
        index=args.index,
        width=args.width,
        height=args.height,
        fps=args.fps,
        warmup_frames=args.warmup_frames,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
