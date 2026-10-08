from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jetarm_agent.adapter import Phase2BoardAdapter
from jetarm_agent.agent_protocol import RobotToolMode, SkillInstallState, SkillManifest
from jetarm_agent.agent_tools import RobotToolRegistry, render_tool_result
from jetarm_agent.cli_transport import CliBoardTransport, CliBoardTransportConfig, LocalShellRunner
from jetarm_agent.profile_registry import load_active_profile
from jetarm_agent.skill_store import SkillStore


def build_default_registry(*, transcript_path: Path | None = None) -> RobotToolRegistry:
    runner = LocalShellRunner()
    transport = CliBoardTransport(runner=runner, config=CliBoardTransportConfig())
    adapter = Phase2BoardAdapter(transport=transport)
    try:
        profile = load_active_profile()
    except Exception:
        profile = None
    return RobotToolRegistry(
        adapter=adapter,
        runner=runner,
        default_profile=profile,
        transcript_path=transcript_path,
    )


def _load_args_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--args-json must be valid JSON: {exc}") from exc


def _default_skill_body(name: str, description: str) -> str:
    return f"""---
name: {name}
description: "{description}"
---

# {name}

Use this skill from the JetArm full-control agent when the task matches the description.

## Safety

- Prefer `stop_all` before and after risky experiments.
- Record commands, observations, failures, and recovery actions in the session transcript.
- In `full-control` mode, raw ROS and shell tools are allowed, but results must be inspected before retrying motion.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jetarm-agent")
    parser.add_argument("--transcript", type=Path, default=Path("logs/agent/full-control-transcript.jsonl"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-tools")

    call_parser = subparsers.add_parser("call-tool")
    call_parser.add_argument("tool_name")
    call_parser.add_argument("--args-json", default="{}")
    call_parser.add_argument("--session-id", default="default")
    call_parser.add_argument("--mode", choices=[item.value for item in RobotToolMode], default=None)

    skills_parser = subparsers.add_parser("init-skills")
    skills_parser.add_argument("--root", type=Path, default=Path(".claude/skills"))

    list_skills_parser = subparsers.add_parser("list-skills")
    list_skills_parser.add_argument("--root", type=Path, default=Path(".claude/skills"))

    create_skill_parser = subparsers.add_parser("create-skill")
    create_skill_parser.add_argument("name")
    create_skill_parser.add_argument("--description", default="JetArm operator skill")
    create_skill_parser.add_argument("--root", type=Path, default=Path(".claude/skills"))

    activate_skill_parser = subparsers.add_parser("activate-skill")
    activate_skill_parser.add_argument("name")
    activate_skill_parser.add_argument("--review-notes", required=True)
    activate_skill_parser.add_argument("--root", type=Path, default=Path(".claude/skills"))

    args = parser.parse_args(argv or sys.argv[1:])

    if args.command == "list-tools":
        registry = build_default_registry(transcript_path=args.transcript)
        for spec in registry.list_tools():
            print(json.dumps(spec.model_dump(mode="json"), ensure_ascii=False))
        return 0

    if args.command == "call-tool":
        registry = build_default_registry(transcript_path=args.transcript)
        result = registry.call(
            args.tool_name,
            _load_args_json(args.args_json),
            session_id=args.session_id,
            mode=args.mode,
        )
        print(render_tool_result(result))
        return 0 if result.ok else 2

    if args.command == "init-skills":
        SkillStore(root=args.root).ensure_layout()
        print(f"initialized skill store at {args.root}")
        return 0

    if args.command == "list-skills":
        for manifest in SkillStore(root=args.root).list_manifests():
            print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False))
        return 0

    if args.command == "create-skill":
        manifest = SkillManifest(
            name=args.name,
            description=args.description,
            source="local",
            install_state=SkillInstallState.QUARANTINED,
            allowed_tools=["list_tools", "shell", "rostopic", "rosservice", "stop_all"],
        )
        path = SkillStore(root=args.root).create_local_skill(
            manifest,
            _default_skill_body(args.name, args.description),
        )
        print(f"created quarantined skill at {path}")
        return 0

    if args.command == "activate-skill":
        path = SkillStore(root=args.root).activate_skill(args.name, review_notes=args.review_notes)
        print(f"activated skill at {path}")
        return 0

    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
