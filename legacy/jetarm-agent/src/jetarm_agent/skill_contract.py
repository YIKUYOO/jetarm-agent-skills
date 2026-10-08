from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jetarm_agent.schemas import CalibrationProfile, DetectedTarget


class SkillStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class SkillErrorCode(str, Enum):
    SKILL_PRECONDITION_FAILED = "SKILL_PRECONDITION_FAILED"
    SKILL_TIMEOUT = "SKILL_TIMEOUT"
    FOUNDATION_UNAVAILABLE = "FOUNDATION_UNAVAILABLE"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_NOT_UNIQUE = "TARGET_NOT_UNIQUE"
    TARGET_CHECK_FAILED = "TARGET_CHECK_FAILED"
    GRIPPER_NOT_READY = "GRIPPER_NOT_READY"
    PICK_FAILED = "PICK_FAILED"
    PLACE_FAILED = "PLACE_FAILED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    STOP_REQUESTED = "STOP_REQUESTED"
    ADAPTER_INTERNAL_ERROR = "ADAPTER_INTERNAL_ERROR"


class AdapterCapabilityLevel(str, Enum):
    FROZEN = "frozen"
    PROVISIONAL = "provisional"


T = TypeVar("T")


class SkillResult(BaseModel, Generic[T]):
    status: SkillStatus
    error_code: SkillErrorCode | None = None
    message: str = ""
    telemetry: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    payload: T | None = None

    model_config = ConfigDict(extra="forbid")


class SkillTargetPayload(BaseModel):
    target: DetectedTarget

    model_config = ConfigDict(extra="forbid")


class GoHomeRequest(BaseModel):
    reason: str = ""

    model_config = ConfigDict(extra="forbid")


class ObserveSceneRequest(BaseModel):
    profile: CalibrationProfile

    model_config = ConfigDict(extra="forbid")


class DetectTargetRequest(BaseModel):
    profile: CalibrationProfile
    object_class: str
    color: str | None = None
    minimum_confidence: float = 0.0

    model_config = ConfigDict(extra="forbid")

    @field_validator("minimum_confidence")
    @classmethod
    def validate_minimum_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("minimum_confidence must be between 0.0 and 1.0")
        return value


class CheckTargetRequest(BaseModel):
    profile: CalibrationProfile
    target: DetectedTarget
    required_zone: str | None = None
    required_color: str | None = None
    maximum_target_age_seconds: float = 5.0
    reference_time: datetime | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_required_zone(self) -> "CheckTargetRequest":
        if self.required_zone and self.required_zone not in self.profile.workcell.destination_zones:
            raise ValueError("required_zone must exist in profile.workcell.destination_zones")
        if self.maximum_target_age_seconds <= 0:
            raise ValueError("maximum_target_age_seconds must be greater than 0")
        return self


class GripperRequest(BaseModel):
    reason: str = ""

    model_config = ConfigDict(extra="forbid")


class PickRequest(BaseModel):
    request_id: str
    profile: CalibrationProfile
    target: DetectedTarget

    model_config = ConfigDict(extra="forbid")


class PlaceRequest(BaseModel):
    request_id: str
    profile: CalibrationProfile
    target: DetectedTarget
    destination_zone: str

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_destination_zone(self) -> "PlaceRequest":
        if self.destination_zone not in self.profile.workcell.destination_zones:
            raise ValueError("destination_zone must exist in profile.workcell.destination_zones")
        return self


class RecoverRequest(BaseModel):
    reason: str = ""
    last_error_code: SkillErrorCode | None = None

    model_config = ConfigDict(extra="forbid")


class StopRequest(BaseModel):
    reason: str = ""

    model_config = ConfigDict(extra="forbid")
