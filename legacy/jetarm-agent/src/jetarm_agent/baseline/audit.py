from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable


AuditRunner = Callable[[str], str]


@dataclass
class BoardEnvironmentSnapshot:
    ros_distro: str
    ros_master_uri: str
    working_directory: str
    workspace_packages: list[str]
    nodes: list[str]
    services: list[str]
    topics: list[str]


def _run_shell(command: str) -> str:
    completed = subprocess.run(
        ["bash", "-lc", command],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=15,
    )
    return completed.stdout.strip()


def _lines(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def collect_board_environment(command_runner: AuditRunner | None = None) -> BoardEnvironmentSnapshot:
    run = command_runner or _run_shell
    return BoardEnvironmentSnapshot(
        ros_distro=run("echo ${ROS_DISTRO:-}").strip(),
        ros_master_uri=run("echo ${ROS_MASTER_URI:-}").strip(),
        working_directory=run("pwd").strip(),
        workspace_packages=_lines(run("ls ~/jetarm/src")),
        nodes=_lines(run("rosnode list")),
        services=_lines(run("rosservice list")),
        topics=_lines(run("rostopic list")),
    )


def render_markdown_report(snapshot: BoardEnvironmentSnapshot) -> str:
    package_lines = "\n".join(f"- `{item}`" for item in snapshot.workspace_packages) or "- None"
    node_lines = "\n".join(f"- `{item}`" for item in snapshot.nodes) or "- None"
    service_lines = "\n".join(f"- `{item}`" for item in snapshot.services) or "- None"
    topic_lines = "\n".join(f"- `{item}`" for item in snapshot.topics) or "- None"

    return (
        "# Board Environment Audit\n\n"
        "## Runtime Facts\n\n"
        f"- ROS distro: `{snapshot.ros_distro or 'unknown'}`\n"
        f"- ROS master URI: `{snapshot.ros_master_uri or 'unknown'}`\n"
        f"- Working directory: `{snapshot.working_directory or 'unknown'}`\n\n"
        "## Workspace Packages\n\n"
        f"{package_lines}\n\n"
        "## ROS Nodes\n\n"
        f"{node_lines}\n\n"
        "## ROS Services\n\n"
        f"{service_lines}\n\n"
        "## ROS Topics\n\n"
        f"{topic_lines}\n"
    )
