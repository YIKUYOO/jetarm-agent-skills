from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from jetarm_agent.adapter import Phase2BoardAdapter, Phase2BoardAdapterConfig
from jetarm_agent.cli_transport import CliBoardTransport, CliBoardTransportConfig, LocalShellRunner, SshShellRunner
from jetarm_agent.profile_registry import load_active_profile_document, load_profile_document
from jetarm_agent.skill_contract import CheckTargetRequest, DetectTargetRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Phase 2 board-backed observation smoke.")
    parser.add_argument("--mode", choices=("ssh_shell", "local_shell"), default="ssh_shell")
    parser.add_argument("--host", help="Operator-configured board host; no bundled default")
    parser.add_argument("--user")
    parser.add_argument("--password")
    parser.add_argument("--password-file")
    parser.add_argument("--connect-timeout", type=int, default=5)
    parser.add_argument("--command-timeout", type=int, default=20)
    parser.add_argument("--observe-timeout", type=int, default=20)
    parser.add_argument("--profile-name")
    parser.add_argument("--target-color")
    parser.add_argument("--minimum-confidence", type=float)
    parser.add_argument("--destination-zone")
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
    minimum_confidence = (
        args.minimum_confidence
        if args.minimum_confidence is not None
        else profile_document.observation.minimum_confidence
    )
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
            observe_target_color=target_color,
            observe_timeout_seconds=args.observe_timeout,
        ),
    )
    adapter = Phase2BoardAdapter(
        transport=transport,
        config=Phase2BoardAdapterConfig(default_target_color=target_color),
    )
    observed = adapter.observe_scene(profile)
    detect_result = adapter.detect_target(
        DetectTargetRequest(
            profile=profile,
            object_class="color_block",
            color=target_color,
            minimum_confidence=minimum_confidence,
        )
    )
    check_result = None
    if detect_result.status.value == "succeeded" and detect_result.payload is not None:
        check_result = adapter.check_target(
            CheckTargetRequest(
                profile=profile,
                target=detect_result.payload.target,
                required_zone=destination_zone,
                required_color=target_color,
                maximum_target_age_seconds=profile_document.observation.max_target_age_seconds,
            )
        )

    payload = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "profile_name": profile.profile_name,
        "target_color": target_color,
        "minimum_confidence": minimum_confidence,
        "destination_zone": destination_zone,
        "observed_targets": [item.model_dump(mode="json") for item in observed],
        "detect_result": detect_result.model_dump(mode="json"),
        "check_result": check_result.model_dump(mode="json") if check_result is not None else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    ok = (
        bool(observed)
        and detect_result.status.value == "succeeded"
        and check_result is not None
        and check_result.status.value == "succeeded"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
