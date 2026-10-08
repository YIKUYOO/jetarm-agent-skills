from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RobotToolMode(str, Enum):
    DRY_RUN = "dry_run"
    SAFE = "safe"
    LIVE = "live"
    FULL_CONTROL = "full_control"


class RobotToolRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SkillInstallState(str, Enum):
    QUARANTINED = "quarantined"
    ACTIVE = "active"
    DISABLED = "disabled"


class RobotToolCall(BaseModel):
    tool_name: str
    mode: RobotToolMode = RobotToolMode.SAFE
    args: dict[str, Any] = Field(default_factory=dict)
    risk_level: RobotToolRiskLevel = RobotToolRiskLevel.LOW
    session_id: str = "default"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    operator_visible_summary: str = ""

    model_config = ConfigDict(extra="forbid")

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tool_name must not be empty")
        return value.strip()


class RobotToolResult(BaseModel):
    ok: bool
    stage: str
    motion_executed: bool = False
    stdout: str = ""
    stderr: str = ""
    telemetry: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    next_recovery_hint: str | None = None

    model_config = ConfigDict(extra="forbid")


class RobotToolTranscriptEntry(BaseModel):
    call: RobotToolCall
    result: RobotToolResult
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(extra="forbid")


class SkillManifest(BaseModel):
    name: str
    description: str
    version: str = "0.1.0"
    source: str = "local"
    allowed_tools: list[str] = Field(default_factory=list)
    risk_level: RobotToolRiskLevel = RobotToolRiskLevel.MEDIUM
    install_state: SkillInstallState = SkillInstallState.QUARANTINED
    review_notes: str = ""

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("skill name must not be empty")
        if any(char in normalized for char in "\\/:*?\"<>|"):
            raise ValueError("skill name must be filesystem-safe")
        return normalized

    @model_validator(mode="after")
    def validate_active_review(self) -> "SkillManifest":
        if self.install_state is SkillInstallState.ACTIVE and not self.review_notes.strip():
            raise ValueError("active skills require review_notes")
        return self


class OpenWorldTaskState(BaseModel):
    user_goal: str
    scene_observation: dict[str, Any] = Field(default_factory=dict)
    target_candidates: list[dict[str, Any]] = Field(default_factory=list)
    chosen_target: dict[str, Any] | None = None
    plan: list[str] = Field(default_factory=list)
    execution_trace: list[RobotToolTranscriptEntry] = Field(default_factory=list)
    verification_result: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class RobotToolSpec(BaseModel):
    name: str
    group: Literal["robot_safe_tools", "robot_raw_tools"]
    description: str
    default_mode: RobotToolMode
    risk_level: RobotToolRiskLevel

    model_config = ConfigDict(extra="forbid")
