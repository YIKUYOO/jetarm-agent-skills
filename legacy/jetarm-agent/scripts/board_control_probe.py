from __future__ import annotations

import argparse
from pathlib import Path

from jetarm_agent.baseline.control_probe import (
    collect_control_inventory,
    render_control_markdown_report,
    snapshot_to_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-motion-checks", action="store_true", help="Enable supervised motion validation mode.")
    parser.add_argument("--json-out", help="Optional JSON output path.")
    parser.add_argument("--markdown-out", help="Optional markdown output path.")
    args = parser.parse_args()

    snapshot = collect_control_inventory(allow_motion_checks=args.allow_motion_checks)
    json_payload = snapshot_to_json(snapshot)
    markdown_payload = render_control_markdown_report(snapshot)

    if args.json_out:
        Path(args.json_out).write_text(json_payload, encoding="utf-8")
    if args.markdown_out:
        Path(args.markdown_out).write_text(markdown_payload, encoding="utf-8")
    if not args.json_out and not args.markdown_out:
        print(json_payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
