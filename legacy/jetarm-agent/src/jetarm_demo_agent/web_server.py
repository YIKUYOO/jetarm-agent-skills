from __future__ import annotations

import argparse

import uvicorn

from jetarm_demo_agent.cli import build_dispatcher
from jetarm_demo_agent.web import create_app


def build_web_app(allow_live_motion: bool = False):
    return create_app(dispatcher=build_dispatcher(allow_live_motion=allow_live_motion))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--live", action="store_true", help="Enable real motion for motion tasks.")
    args = parser.parse_args(argv)

    uvicorn.run(
        build_web_app(allow_live_motion=args.live),
        host=args.host,
        port=args.port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
