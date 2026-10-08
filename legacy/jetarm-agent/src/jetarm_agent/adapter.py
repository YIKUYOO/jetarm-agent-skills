from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from jetarm_agent.schemas import CalibrationProfile, DetectedTarget, PickPlaceRequest, PickPlaceResult, PickPlaceStatus
from jetarm_agent.skill_contract import (
    AdapterCapabilityLevel,
    CheckTargetRequest,
    DetectTargetRequest,
    GoHomeRequest,
    GripperRequest,
    PickRequest,
    PlaceRequest,
    RecoverRequest,
    SkillErrorCode,
    SkillResult,
    SkillStatus,
    SkillTargetPayload,
    StopRequest,
)


class SkillName(str, Enum):
    GO_HOME = "go_home"
    OBSERVE_SCENE = "observe_scene"
    DETECT_TARGET = "detect_target"
    CHECK_TARGET = "check_target"
    OPEN_GRIPPER = "open_gripper"
    CLOSE_GRIPPER = "close_gripper"
    PICK = "pick"
    PLACE = "place"
    RECOVER = "recover"
    STOP_ALL = "stop_all"
    PICK_PLACE = "pick_place"


class Phase2BoardAdapterConfig(BaseModel):
    default_target_color: str = "red"

    model_config = ConfigDict(extra="forbid")


class BoardTransport(Protocol):
    def observe_scene(self, profile: CalibrationProfile) -> list[DetectedTarget]:
        """Return structured targets for the current scene."""

    def run_object_sortting_pick_place(self, request: PickPlaceRequest, *, target_color: str) -> PickPlaceResult:
        """Execute the canonical Phase 2 fixed-scene pick/place workflow."""

    def go_home(self) -> dict:
        """Execute the current provisional go_home path."""

    def set_gripper(self, *, opened: bool) -> dict:
        """Move the gripper to the requested provisional state."""

    def stop_all(self) -> dict:
        """Interrupt active motion and workflows."""

    def recover(self, *, last_error_code: SkillErrorCode | None = None) -> dict:
        """Attempt to restore the board to a continue-ready state."""


class Phase2BoardAdapter:
    def __init__(self, *, transport: BoardTransport, config: Phase2BoardAdapterConfig | None = None):
        self.transport = transport
        self.config = config or Phase2BoardAdapterConfig()

    def capabilities(self) -> dict[SkillName, AdapterCapabilityLevel]:
        return {
            SkillName.GO_HOME: AdapterCapabilityLevel.PROVISIONAL,
            SkillName.OBSERVE_SCENE: AdapterCapabilityLevel.PROVISIONAL,
            SkillName.DETECT_TARGET: AdapterCapabilityLevel.PROVISIONAL,
            SkillName.CHECK_TARGET: AdapterCapabilityLevel.PROVISIONAL,
            SkillName.OPEN_GRIPPER: AdapterCapabilityLevel.PROVISIONAL,
            SkillName.CLOSE_GRIPPER: AdapterCapabilityLevel.PROVISIONAL,
            SkillName.PICK: AdapterCapabilityLevel.PROVISIONAL,
            SkillName.PLACE: AdapterCapabilityLevel.PROVISIONAL,
            SkillName.RECOVER: AdapterCapabilityLevel.PROVISIONAL,
            SkillName.STOP_ALL: AdapterCapabilityLevel.PROVISIONAL,
            SkillName.PICK_PLACE: AdapterCapabilityLevel.FROZEN,
        }

    def observe_scene(self, profile: CalibrationProfile) -> list[DetectedTarget]:
        return list(self.transport.observe_scene(profile))

    def detect_target(self, request: DetectTargetRequest) -> SkillResult[SkillTargetPayload]:
        try:
            observed_scene = self.observe_scene(request.profile)
        except NotImplementedError:
            return SkillResult(
                status=SkillStatus.FAILED,
                error_code=SkillErrorCode.FOUNDATION_UNAVAILABLE,
                message="board-backed observe_scene is not implemented in this transport slice",
            )
        except Exception as exc:
            return SkillResult(
                status=SkillStatus.FAILED,
                error_code=SkillErrorCode.FOUNDATION_UNAVAILABLE,
                message=str(exc),
            )
        observed = [
            target
            for target in observed_scene
            if target.object_class == request.object_class
            and target.confidence >= request.minimum_confidence
            and (request.color is None or target.color == request.color)
        ]
        if not observed:
            return SkillResult(
                status=SkillStatus.FAILED,
                error_code=SkillErrorCode.TARGET_NOT_FOUND,
                message="no matching target found",
            )
        if len(observed) > 1:
            return SkillResult(
                status=SkillStatus.FAILED,
                error_code=SkillErrorCode.TARGET_NOT_UNIQUE,
                message="multiple targets matched the requested filters",
                telemetry={"match_count": len(observed)},
            )
        return SkillResult(
            status=SkillStatus.SUCCEEDED,
            message="target detected",
            telemetry={"match_count": 1},
            payload=SkillTargetPayload(target=observed[0]),
        )

    def check_target(self, request: CheckTargetRequest) -> SkillResult[SkillTargetPayload]:
        target_pose = request.target.pose
        pose_frame = target_pose.get("frame")
        coordinates = [target_pose.get(axis) for axis in ("x", "y", "z")]
        coordinates_valid = all(isinstance(value, (int, float)) and math.isfinite(value) for value in coordinates)
        reference_time = request.reference_time or datetime.now(timezone.utc)
        target_timestamp = request.target.source_timestamp
        if target_timestamp.tzinfo is None:
            target_timestamp = target_timestamp.replace(tzinfo=timezone.utc)
        target_age_seconds = max((reference_time - target_timestamp).total_seconds(), 0.0)
        checks = {
            "allowed_object_class": request.target.object_class in request.profile.workcell.allowed_object_classes,
            "required_zone_known": request.required_zone is None
            or request.required_zone in request.profile.workcell.destination_zones,
            "required_color_matches": request.required_color is None or request.target.color == request.required_color,
            "pose_frame_matches_base": pose_frame == request.profile.base_frame,
            "pose_coordinates_valid": coordinates_valid,
            "target_fresh_enough": target_age_seconds <= request.maximum_target_age_seconds,
        }
        if not all(checks.values()):
            return SkillResult(
                status=SkillStatus.FAILED,
                error_code=SkillErrorCode.TARGET_CHECK_FAILED,
                message="target check failed",
                telemetry={
                    "checks": checks,
                    "required_zone": request.required_zone,
                    "required_color": request.required_color,
                    "target_age_seconds": target_age_seconds,
                    "maximum_target_age_seconds": request.maximum_target_age_seconds,
                },
            )
        return SkillResult(
            status=SkillStatus.SUCCEEDED,
            message="target check passed",
            telemetry={
                "required_zone": request.required_zone,
                "required_color": request.required_color,
                "checks": checks,
                "target_age_seconds": target_age_seconds,
                "maximum_target_age_seconds": request.maximum_target_age_seconds,
            },
            payload=SkillTargetPayload(target=request.target),
        )

    def go_home(self, request: GoHomeRequest) -> SkillResult[None]:
        try:
            telemetry = self.transport.go_home()
        except NotImplementedError:
            return SkillResult(
                status=SkillStatus.BLOCKED,
                error_code=SkillErrorCode.FOUNDATION_UNAVAILABLE,
                message="board-backed go_home is not implemented in this transport slice",
            )
        except Exception as exc:
            return SkillResult(
                status=SkillStatus.FAILED,
                error_code=SkillErrorCode.ADAPTER_INTERNAL_ERROR,
                message=str(exc),
            )
        return SkillResult(
            status=SkillStatus.SUCCEEDED,
            message=request.reason or "go_home completed",
            telemetry=dict(telemetry),
        )

    def open_gripper(self, request: GripperRequest) -> SkillResult[None]:
        try:
            telemetry = self.transport.set_gripper(opened=True)
        except NotImplementedError:
            return SkillResult(
                status=SkillStatus.BLOCKED,
                error_code=SkillErrorCode.FOUNDATION_UNAVAILABLE,
                message="board-backed open_gripper is not implemented in this transport slice",
            )
        except Exception as exc:
            return SkillResult(
                status=SkillStatus.FAILED,
                error_code=SkillErrorCode.GRIPPER_NOT_READY,
                message=str(exc),
            )
        return SkillResult(
            status=SkillStatus.SUCCEEDED,
            message=request.reason or "gripper opened",
            telemetry=dict(telemetry),
        )

    def close_gripper(self, request: GripperRequest) -> SkillResult[None]:
        try:
            telemetry = self.transport.set_gripper(opened=False)
        except NotImplementedError:
            return SkillResult(
                status=SkillStatus.BLOCKED,
                error_code=SkillErrorCode.FOUNDATION_UNAVAILABLE,
                message="board-backed close_gripper is not implemented in this transport slice",
            )
        except Exception as exc:
            return SkillResult(
                status=SkillStatus.FAILED,
                error_code=SkillErrorCode.GRIPPER_NOT_READY,
                message=str(exc),
            )
        return SkillResult(
            status=SkillStatus.SUCCEEDED,
            message=request.reason or "gripper closed",
            telemetry=dict(telemetry),
        )

    def pick(self, request: PickRequest) -> SkillResult[None]:
        return SkillResult(
            status=SkillStatus.BLOCKED,
            error_code=SkillErrorCode.FOUNDATION_UNAVAILABLE,
            message="standalone pick is not exposed by the Phase 2 core adapter; use execute_pick_place",
            telemetry={"request_id": request.request_id},
        )

    def place(self, request: PlaceRequest) -> SkillResult[None]:
        return SkillResult(
            status=SkillStatus.BLOCKED,
            error_code=SkillErrorCode.FOUNDATION_UNAVAILABLE,
            message="standalone place is not exposed by the Phase 2 core adapter; use execute_pick_place",
            telemetry={"request_id": request.request_id, "destination_zone": request.destination_zone},
        )

    def recover(self, request: RecoverRequest) -> SkillResult[None]:
        try:
            telemetry = self.transport.recover(last_error_code=request.last_error_code)
        except NotImplementedError:
            return SkillResult(
                status=SkillStatus.BLOCKED,
                error_code=SkillErrorCode.FOUNDATION_UNAVAILABLE,
                message="board-backed recover is not implemented in this transport slice",
            )
        except Exception as exc:
            return SkillResult(
                status=SkillStatus.FAILED,
                error_code=SkillErrorCode.RECOVERY_REQUIRED,
                message=str(exc),
            )
        return SkillResult(
            status=SkillStatus.SUCCEEDED,
            message=request.reason or "recover completed",
            telemetry=dict(telemetry),
        )

    def stop_all(self, request: StopRequest) -> SkillResult[None]:
        try:
            telemetry = self.transport.stop_all()
        except NotImplementedError:
            return SkillResult(
                status=SkillStatus.BLOCKED,
                error_code=SkillErrorCode.FOUNDATION_UNAVAILABLE,
                message="board-backed stop_all is not implemented in this transport slice",
            )
        except Exception as exc:
            return SkillResult(
                status=SkillStatus.FAILED,
                error_code=SkillErrorCode.RECOVERY_REQUIRED,
                message=str(exc),
            )
        return SkillResult(
            status=SkillStatus.SUCCEEDED,
            message=request.reason or "stop_all completed",
            telemetry=dict(telemetry),
        )

    def execute_pick_place(self, request: PickPlaceRequest) -> PickPlaceResult:
        target_color = request.target.color or self.config.default_target_color
        if not target_color:
            return PickPlaceResult(
                request_id=request.request_id,
                status=PickPlaceStatus.BLOCKED,
                failure_stage="detect",
                telemetry={"error_code": SkillErrorCode.FOUNDATION_UNAVAILABLE.value},
                artifacts={"message": "no target color available for canonical object_sortting path"},
            )
        return self.transport.run_object_sortting_pick_place(request, target_color=target_color)
