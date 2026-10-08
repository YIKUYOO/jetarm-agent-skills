from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PickPlaceStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class DetectedTarget(BaseModel):
    entity_id: str
    object_class: str
    color: str | None = None
    confidence: float
    source_timestamp: datetime
    pose: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return value


class CalibrationOffsets(BaseModel):
    pick: dict[str, float] = Field(default_factory=dict)
    place: dict[str, float] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class WorkcellConstraints(BaseModel):
    allowed_object_classes: list[str] = Field(default_factory=list)
    destination_zones: dict[str, dict[str, Any]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_zones(self) -> "WorkcellConstraints":
        if not self.destination_zones:
            raise ValueError("destination_zones must not be empty")
        return self


class CalibrationProfile(BaseModel):
    profile_name: str
    camera_frame: str
    base_frame: str
    offsets: CalibrationOffsets = Field(default_factory=CalibrationOffsets)
    workcell: WorkcellConstraints

    model_config = ConfigDict(extra="forbid")


class PickPlaceRequest(BaseModel):
    request_id: str
    profile: CalibrationProfile
    target: DetectedTarget
    destination_zone: str

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_request(self) -> "PickPlaceRequest":
        if self.destination_zone not in self.profile.workcell.destination_zones:
            raise ValueError("destination_zone must exist in profile.workcell.destination_zones")
        if self.target.object_class not in self.profile.workcell.allowed_object_classes:
            raise ValueError("target.object_class must be allowed by the calibration profile")
        return self


class PickPlaceResult(BaseModel):
    request_id: str
    status: PickPlaceStatus
    failure_stage: str | None = None
    telemetry: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
