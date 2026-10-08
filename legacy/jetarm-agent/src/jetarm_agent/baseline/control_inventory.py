from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ControlEndpointKind(str, Enum):
    TOPIC = "topic"
    SERVICE = "service"
    SCRIPT = "script"
    ACTION = "action"
    LAUNCH = "launch"


class ControlBoundaryClassification(str, Enum):
    RAW_LOW_LEVEL = "raw_low_level"
    OFFICIAL_WRAPPED = "official_wrapped"
    MAINLINE_SAFE_WRAPPER = "mainline_safe_wrapper"
    DEFERRED = "deferred"


class ControlRiskLevel(str, Enum):
    LOW = "low"
    GUARDED = "guarded"
    HIGH = "high"


class ControlTier(str, Enum):
    RAW_HARDWARE_CONTROL = "raw_hardware_control"
    KINEMATICS_SERVICE = "kinematics_service"
    OFFICIAL_TASK_FLOW = "official_task_flow"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class ControlEndpoint:
    name: str
    kind: ControlEndpointKind
    boundary: ControlBoundaryClassification
    source_layer: str
    supports_motion: bool
    supports_gripper: bool
    supports_stop: bool
    tier: ControlTier = ControlTier.DEFERRED
    supports_pick_place: bool = False
    notes: str = ""


@dataclass(frozen=True)
class ControlValidationResult:
    endpoint_name: str
    validation_mode: str
    passed: bool
    evidence: list[str] = field(default_factory=list)
    risk_level: ControlRiskLevel = ControlRiskLevel.GUARDED
    follow_up: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ControlInventorySnapshot:
    endpoints: list[ControlEndpoint]
    validations: list[ControlValidationResult]
    motion_checks_performed: bool
