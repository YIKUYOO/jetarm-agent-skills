from __future__ import annotations

import argparse
from pathlib import Path

from jetarm_agent.baseline.audit import collect_board_environment, render_markdown_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown-out", help="Optional markdown output path.")
    args = parser.parse_args()

    snapshot = collect_board_environment()
    report = render_markdown_report(snapshot)
    if args.markdown_out:
        output_path = Path(args.markdown_out)
        output_path.write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
