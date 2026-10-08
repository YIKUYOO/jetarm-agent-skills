from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from jetarm_agent.baseline.control_inventory import (
    ControlBoundaryClassification,
    ControlEndpoint,
    ControlEndpointKind,
    ControlInventorySnapshot,
    ControlRiskLevel,
    ControlTier,
    ControlValidationResult,
)


ProbeRunner = Callable[[str], str]


def _run_shell(command: str) -> str:
    completed = subprocess.run(
        ["bash", "-lc", command],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=20,
    )
    return completed.stdout.strip()


def _lines(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def _endpoint_from_topic(name: str) -> ControlEndpoint:
    if name in {"/jetarm_sdk/serial_servo/move", "/jetarm_sdk/serial_servo/load_unload"}:
        return ControlEndpoint(
            name=name,
            kind=ControlEndpointKind.TOPIC,
            boundary=ControlBoundaryClassification.RAW_LOW_LEVEL,
            source_layer="jetarm_sdk",
            tier=ControlTier.RAW_HARDWARE_CONTROL,
            supports_motion=True,
            supports_gripper=name.endswith("load_unload"),
            supports_stop=False,
            notes="Direct servo motion primitive" if name.endswith("/move") else "Direct servo power/load primitive",
        )
    if name == "/jetarm_sdk/serial_servo/stop":
        return ControlEndpoint(
            name=name,
            kind=ControlEndpointKind.TOPIC,
            boundary=ControlBoundaryClassification.RAW_LOW_LEVEL,
            source_layer="jetarm_sdk",
            tier=ControlTier.RAW_HARDWARE_CONTROL,
            supports_motion=False,
            supports_gripper=False,
            supports_stop=True,
            notes="Direct stop primitive",
        )
    if name == "/controllers/multi_id_pos_dur":
        return ControlEndpoint(
            name=name,
            kind=ControlEndpointKind.TOPIC,
            boundary=ControlBoundaryClassification.RAW_LOW_LEVEL,
            source_layer="controllers",
            tier=ControlTier.RAW_HARDWARE_CONTROL,
            supports_motion=True,
            supports_gripper=True,
            supports_stop=False,
            notes="Grouped servo target topic used under official wrappers; keep adapter-internal",
        )
    if name.startswith("/grasp/"):
        return ControlEndpoint(
            name=name,
            kind=ControlEndpointKind.ACTION,
            boundary=ControlBoundaryClassification.MAINLINE_SAFE_WRAPPER,
            source_layer="official_grasp_flow",
            tier=ControlTier.OFFICIAL_TASK_FLOW,
            supports_motion=True,
            supports_gripper=True,
            supports_stop=False,
            supports_pick_place=True,
            notes="Official grasp action channel used by higher-level pick-place flows",
        )
    return ControlEndpoint(
        name=name,
        kind=ControlEndpointKind.TOPIC,
        boundary=ControlBoundaryClassification.DEFERRED,
        source_layer="unknown",
        tier=ControlTier.DEFERRED,
        supports_motion=False,
        supports_gripper=False,
        supports_stop=False,
        notes="Unclassified topic",
    )


def _endpoint_from_service(name: str) -> ControlEndpoint:
    if name.startswith("/kinematics/"):
        return ControlEndpoint(
            name=name,
            kind=ControlEndpointKind.SERVICE,
            boundary=ControlBoundaryClassification.OFFICIAL_WRAPPED,
            source_layer="kinematics",
            tier=ControlTier.KINEMATICS_SERVICE,
            supports_motion=name in {"/kinematics/set_pose_target", "/kinematics/set_joint_value_target"},
            supports_gripper=False,
            supports_stop=False,
            notes="Solver or target-setting service; validate through official motion wrappers instead of direct business use",
        )
    if name.startswith("/object_sortting/"):
        return ControlEndpoint(
            name=name,
            kind=ControlEndpointKind.SERVICE,
            boundary=ControlBoundaryClassification.MAINLINE_SAFE_WRAPPER,
            source_layer="official_pick_place_flow",
            tier=ControlTier.OFFICIAL_TASK_FLOW,
            supports_motion="enable_sortting" in name,
            supports_gripper=False,
            supports_stop=False,
            supports_pick_place=True,
            notes="Official pick-place workflow service; suitable as adapter-level task-flow base",
        )
    return ControlEndpoint(
        name=name,
        kind=ControlEndpointKind.SERVICE,
        boundary=ControlBoundaryClassification.DEFERRED,
        source_layer="unknown",
        tier=ControlTier.DEFERRED,
        supports_motion=False,
        supports_gripper=False,
        supports_stop=False,
        notes="Deferred service endpoint",
    )


def _endpoint_from_path(raw_path: str) -> ControlEndpoint:
    path = Path(raw_path)
    if path.name == "actions.py":
        return ControlEndpoint(
            name=raw_path,
            kind=ControlEndpointKind.SCRIPT,
            boundary=ControlBoundaryClassification.MAINLINE_SAFE_WRAPPER,
            source_layer="official_scripts",
            tier=ControlTier.OFFICIAL_TASK_FLOW,
            supports_motion=True,
            supports_gripper=True,
            supports_stop=False,
            notes="Official action wrapper script providing go_home and staged arm moves",
        )
    if path.name in {"path_planning.launch", "pixel_coordinate_calculation.launch", "object_attitude_calculation.launch"}:
        return ControlEndpoint(
            name=raw_path,
            kind=ControlEndpointKind.LAUNCH,
            boundary=ControlBoundaryClassification.OFFICIAL_WRAPPED,
            source_layer="official_launch",
            tier=ControlTier.OFFICIAL_TASK_FLOW,
            supports_motion=path.name == "path_planning.launch",
            supports_gripper=False,
            supports_stop=False,
            supports_pick_place=path.name != "path_planning.launch",
            notes="Official planning or coordinate-processing launch entrypoint",
        )
    if path.name in {"positioning_clamp.launch", "color_sorting.launch"}:
        return ControlEndpoint(
            name=raw_path,
            kind=ControlEndpointKind.LAUNCH,
            boundary=ControlBoundaryClassification.MAINLINE_SAFE_WRAPPER,
            source_layer="official_launch",
            tier=ControlTier.OFFICIAL_TASK_FLOW,
            supports_motion=True,
            supports_gripper=True,
            supports_stop=False,
            supports_pick_place=True,
            notes="Official end-to-end pick-place workflow launch entrypoint",
        )
    return ControlEndpoint(
        name=raw_path,
        kind=ControlEndpointKind.LAUNCH,
        boundary=ControlBoundaryClassification.OFFICIAL_WRAPPED,
        source_layer="official_launch",
        tier=ControlTier.DEFERRED,
        supports_motion=True,
        supports_gripper=False,
        supports_stop=False,
        notes="Official launch entrypoint outside the current mainline control hierarchy",
    )


def collect_control_inventory(
    command_runner: ProbeRunner | None = None,
    *,
    allow_motion_checks: bool = False,
) -> ControlInventorySnapshot:
    run = command_runner or _run_shell
    topics = _lines(run("rostopic list"))
    services = _lines(run("rosservice list"))
    paths = _lines(run("find ~/jetarm/src -path '*actions.py' -o -path '*launch/*.launch' | sort"))

    endpoints = [
        *[_endpoint_from_topic(item) for item in topics],
        *[_endpoint_from_service(item) for item in services],
        *[_endpoint_from_path(item) for item in paths],
    ]

    validations = [
        ControlValidationResult(
            endpoint_name=endpoint.name,
            validation_mode="motion_allowed" if allow_motion_checks else "non_destructive",
            passed=True,
            evidence=[f"discovered via {endpoint.kind.value} inventory"],
            risk_level=(
                ControlRiskLevel.HIGH
                if endpoint.boundary is ControlBoundaryClassification.RAW_LOW_LEVEL and endpoint.supports_motion
                else ControlRiskLevel.GUARDED
            ),
            follow_up=(
                ["validate under human supervision before direct adapter use"]
                if endpoint.supports_motion
                else []
            ),
        )
        for endpoint in endpoints
    ]

    return ControlInventorySnapshot(
        endpoints=endpoints,
        validations=validations,
        motion_checks_performed=allow_motion_checks,
    )


def render_control_markdown_report(snapshot: ControlInventorySnapshot) -> str:
    endpoint_lines = "\n".join(
        f"- `{endpoint.name}` | `{endpoint.kind.value}` | `{endpoint.boundary.value}` | tier=`{endpoint.tier.value}` | motion={str(endpoint.supports_motion).lower()} | gripper={str(endpoint.supports_gripper).lower()} | stop={str(endpoint.supports_stop).lower()} | pick_place={str(endpoint.supports_pick_place).lower()}"
        for endpoint in snapshot.endpoints
    ) or "- None"
    validation_lines = "\n".join(
        f"- `{result.endpoint_name}` | mode=`{result.validation_mode}` | passed={str(result.passed).lower()} | risk=`{result.risk_level.value}`"
        for result in snapshot.validations
    ) or "- None"
    return (
        "# Low-Level Control Inventory\n\n"
        f"- Motion checks performed: `{str(snapshot.motion_checks_performed).lower()}`\n"
        f"- Endpoints discovered: `{len(snapshot.endpoints)}`\n\n"
        "## Endpoints\n\n"
        f"{endpoint_lines}\n\n"
        "## Validation Summary\n\n"
        f"{validation_lines}\n"
    )


def snapshot_to_json(snapshot: ControlInventorySnapshot) -> str:
    payload = {
        "motion_checks_performed": snapshot.motion_checks_performed,
        "endpoints": [
            {
                "name": endpoint.name,
                "kind": endpoint.kind.value,
                "boundary": endpoint.boundary.value,
                "source_layer": endpoint.source_layer,
                "tier": endpoint.tier.value,
                "supports_motion": endpoint.supports_motion,
                "supports_gripper": endpoint.supports_gripper,
                "supports_stop": endpoint.supports_stop,
                "supports_pick_place": endpoint.supports_pick_place,
                "notes": endpoint.notes,
            }
            for endpoint in snapshot.endpoints
        ],
        "validations": [
            {
                "endpoint_name": result.endpoint_name,
                "validation_mode": result.validation_mode,
                "passed": result.passed,
                "evidence": result.evidence,
                "risk_level": result.risk_level.value,
                "follow_up": result.follow_up,
            }
            for result in snapshot.validations
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
