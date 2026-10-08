from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from jetarm_agent.adapter import Phase2BoardAdapter, Phase2BoardAdapterConfig
from jetarm_agent.cli_transport import CliBoardTransport, CliBoardTransportConfig, LocalShellRunner, SshShellRunner
from jetarm_agent.profile_registry import load_active_profile_document, load_profile_document
from jetarm_agent.schemas import DetectedTarget, PickPlaceRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Phase 2 canonical board transport smoke.")
    parser.add_argument("--mode", choices=("ssh_shell", "local_shell"), default="ssh_shell")
    parser.add_argument("--host", help="Operator-configured board host; no bundled default")
    parser.add_argument("--user")
    parser.add_argument("--password")
    parser.add_argument("--password-file")
    parser.add_argument("--connect-timeout", type=int, default=5)
    parser.add_argument("--command-timeout", type=int, default=20)
    parser.add_argument("--grasp-timeout", type=int, default=90)
    parser.add_argument("--profile-name")
    parser.add_argument("--target-color")
    parser.add_argument("--destination-zone")
    parser.add_argument("--request-id", default="phase2-smoke-1")
    return parser


def load_password(args: argparse.Namespace) -> str | None:
    if args.password:
        return args.password
    if not args.password_file:
        return None
    password_file = Path(args.password_file)
    if not password_file.exists():
        raise FileNotFoundError(f"password file not found: {password_file}")
    for line in password_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("密码"):
            return line.split(":", 1)[1].strip()
    raise ValueError(f"no password entry found in {password_file}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.mode == "ssh_shell" and (not args.host or not args.user):
        parser.error("--host and --user are required for ssh_shell mode")
    password = load_password(args)
    profile_document = load_profile_document(args.profile_name) if args.profile_name else load_active_profile_document()
    profile = profile_document.to_calibration_profile()
    target_color = args.target_color or profile_document.observation.default_target_color
    destination_zone = args.destination_zone or profile_document.metadata.default_destination_zone
    runner = (
        SshShellRunner(
            host=args.host,
            user=args.user,
            connect_timeout_seconds=args.connect_timeout,
            password=password,
        )
        if args.mode == "ssh_shell"
        else LocalShellRunner()
    )
    transport = CliBoardTransport(
        runner=runner,
        config=CliBoardTransportConfig(
            command_timeout_seconds=args.command_timeout,
            grasp_result_timeout_seconds=args.grasp_timeout,
        ),
    )
    adapter = Phase2BoardAdapter(
        transport=transport,
        config=Phase2BoardAdapterConfig(default_target_color=target_color),
    )
    request = PickPlaceRequest(
        request_id=args.request_id,
        profile=profile,
        target=DetectedTarget(
            entity_id=f"smoke-{target_color}-block",
            object_class="color_block",
            color=target_color,
            confidence=1.0,
            source_timestamp=datetime.now(timezone.utc),
            pose={"frame": "base_link"},
        ),
        destination_zone=destination_zone,
    )
    result = adapter.execute_pick_place(request)
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if result.status.value == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
