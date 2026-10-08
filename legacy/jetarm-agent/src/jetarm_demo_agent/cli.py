from __future__ import annotations

import argparse
import sys

from jetarm_demo_agent.agent_runtime import AgentRuntime
from jetarm_demo_agent.config import Settings
from jetarm_demo_agent.executor.ssh_transport import SSHExecutorTransport
from jetarm_demo_agent.orchestration.dispatcher import Dispatcher
from jetarm_demo_agent.orchestration.presenter import render_cli_event, render_cli_output


def build_dispatcher(allow_live_motion: bool = False) -> Dispatcher:
    settings = Settings()
    if allow_live_motion:
        settings.allow_live_motion = True
    return Dispatcher(transport=SSHExecutorTransport(settings=settings), settings=settings)


def run_command(command: str, dispatcher: Dispatcher | None = None, allow_live_motion: bool = False) -> str:
    active_dispatcher = dispatcher or build_dispatcher(allow_live_motion=allow_live_motion)
    result = active_dispatcher.handle(command)
    return render_cli_output(result)


def run_interactive_session(
    dispatcher: Dispatcher | None = None,
    input_fn=input,
    output_fn=print,
    session_id: str = "default",
    allow_live_motion: bool = False,
) -> int:
    active_dispatcher = dispatcher or build_dispatcher(allow_live_motion=allow_live_motion)
    runtime = AgentRuntime(dispatcher=active_dispatcher)
    output_fn("JetArm Agent v1 会话已启动。输入 exit / quit / 退出 结束。")
    dispatcher_settings = getattr(active_dispatcher, "settings", None)
    if getattr(dispatcher_settings, "allow_live_motion", False):
        output_fn("当前动作为 live 模式。动作类任务会真实驱动机械臂。")
    else:
        output_fn("当前动作为 dry-run 模式。动作类任务不会驱动机械臂；如需真实执行，请使用 --live 启动。")
    while True:
        try:
            message = input_fn("你> ")
        except EOFError:
            output_fn("会话结束。")
            return 0

        if not message.strip():
            continue
        if message.strip().lower() in {"exit", "quit", "退出"}:
            output_fn("会话结束。")
            return 0

        for event in runtime.handle_message(session_id, message):
            rendered = render_cli_event(event)
            if rendered:
                output_fn(rendered)
        output_fn("等待下一次输入...")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Enable real motion for motion tasks.")
    parser.add_argument("command", nargs="?")
    args = parser.parse_args(argv or sys.argv[1:])

    if not args.command:
        return run_interactive_session(allow_live_motion=args.live)

    print(run_command(args.command, allow_live_motion=args.live))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
