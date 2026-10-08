from enum import Enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


VALID_COLORS = {"red", "green", "blue"}
VALID_DESTINATIONS = {"left"}
VALID_HINT_SECTORS = {"left", "front", "right"}
VALID_PLACEMENT_RELATIONS = {"near", "left", "right", "inside"}


class TaskIntent(str, Enum):
    CHAT = "chat"
    GO_HOME = "go_home"
    DETECT_COLOR = "detect_color"
    CHECK_COLOR = "check_color"
    PICK_COLOR = "pick_color"
    PICK_AND_PLACE_COLOR = "pick_and_place_color"
    OBSERVE_ENVIRONMENT = "observe_environment"
    PICK_LIFT_PLACE_RED_BLOCK = "pick_lift_place_red_block"
    SCAN_SCENE = "scan_scene"
    SUMMARIZE_SCENE = "summarize_scene"
    FIND_RED_BLOCK = "find_red_block"
    PICK_RED_BLOCK = "pick_red_block"
    LIFT_RED_BLOCK = "lift_red_block"
    PLACE_RED_BLOCK_NEAR_ORIGIN = "place_red_block_near_origin"
    PLACE_RED_BLOCK_BACK_TO_PICK_XY = "place_red_block_back_to_pick_xy"
    OPEN_DESKTOP_MANIPULATION = "open_desktop_manipulation"
    CLARIFY = "clarify"
    ABORT = "abort"


class ExecutionMode(str, Enum):
    SAFE = "safe"
    DRY_RUN = "dry_run"
    LIVE = "live"


class SessionStatus(str, Enum):
    WAITING_FOR_USER_INPUT = "waiting_for_user_input"
    UNDERSTANDING = "understanding"
    RESPONDING = "responding"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class TaskRequest(BaseModel):
    task_id: str
    intent: TaskIntent
    args: dict[str, Any] = Field(default_factory=dict)
    control: dict[str, Any] = Field(default_factory=dict)
    mode: ExecutionMode | None = None
    source: dict[str, Any] = Field(default_factory=dict)
    display: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=False)

    @model_validator(mode="after")
    def validate_args(self) -> "TaskRequest":
        if self.intent in {
            TaskIntent.DETECT_COLOR,
            TaskIntent.CHECK_COLOR,
            TaskIntent.PICK_COLOR,
            TaskIntent.PICK_AND_PLACE_COLOR,
        }:
            color = self.args.get("target_color")
            if color not in VALID_COLORS:
                raise ValueError("target_color must be one of red/green/blue")

        if self.intent is TaskIntent.PICK_AND_PLACE_COLOR:
            destination = self.args.get("destination")
            if destination not in VALID_DESTINATIONS:
                raise ValueError("destination must be left")

        if self.intent in {TaskIntent.PICK_LIFT_PLACE_RED_BLOCK, TaskIntent.FIND_RED_BLOCK}:
            color = self.args.get("target_color")
            if color and color not in VALID_COLORS:
                raise ValueError("target_color must be one of red/green/blue")
            sector = self.args.get("target_hint_sector")
            if sector is not None and sector not in VALID_HINT_SECTORS:
                raise ValueError("target_hint_sector must be one of left/front/right")

        if self.intent is TaskIntent.OPEN_DESKTOP_MANIPULATION:
            if not self.args.get("source_object"):
                raise ValueError("source_object is required")
            if not self.args.get("target_object"):
                raise ValueError("target_object is required")
            relation = self.args.get("placement_relation")
            if relation not in VALID_PLACEMENT_RELATIONS:
                raise ValueError("placement_relation must be one of near/left/right/inside")

        return self


class SessionState(BaseModel):
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: SessionStatus = SessionStatus.WAITING_FOR_USER_INPUT
    last_user_message: str | None = None
    waiting_for_clarification: bool = False
    pending_task: TaskRequest | None = None
    recent_observation: dict[str, Any] | None = None
    recent_execution: dict[str, Any] | None = None
    recent_plan: dict[str, Any] | None = None
    recent_chat_reply: str | None = None
    recent_target_context: dict[str, Any] | None = None
    recent_transitions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=False)


class ExecutorError(BaseModel):
    type: str
    code: str
    message: str
    retryable: bool = False


class ExecutorResult(BaseModel):
    ok: bool
    task_id: str
    executor_state: str
    mode: str
    intent: str
    result: dict[str, Any] = Field(default_factory=dict)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    error: ExecutorError | None = None


class DemoPlanStep(BaseModel):
    action: str
    description: str
    status: str | None = None


class DemoPlan(BaseModel):
    goal: str
    steps: list[DemoPlanStep] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class ObjectRef(BaseModel):
    name: str
    bbox_xyxy_norm: list[float]
    center_px: list[int] | None = None
    world_pose_optional: list[float] | None = None
    confidence: float = 0.0
    source: str = "vlm"

    @field_validator("bbox_xyxy_norm")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        if len(value) != 4:
            raise ValueError("bbox_xyxy_norm must contain four numbers")
        x1, y1, x2, y2 = value
        if any(point < 0 or point > 1 for point in value) or x1 >= x2 or y1 >= y2:
            raise ValueError("bbox_xyxy_norm must be normalized [x1,y1,x2,y2] within 0..1")
        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if value < 0 or value > 1:
            raise ValueError("confidence must be within 0..1")
        return value


class SceneObservation(BaseModel):
    frames: list[dict[str, Any]] = Field(default_factory=list)
    camera_info: dict[str, Any] | None = None
    depth_optional: dict[str, Any] | None = None
    vlm_objects: list[ObjectRef] = Field(default_factory=list)
    calibration_version: str = "unknown"
    timestamp: str | None = None


class ManipulationGoal(BaseModel):
    action: str
    source_object: ObjectRef
    target_object_or_region: ObjectRef
    placement_relation: str
    constraints: list[str] = Field(default_factory=list)
    requires_human_confirmation: bool = True

    @field_validator("placement_relation")
    @classmethod
    def validate_relation(cls, value: str) -> str:
        if value not in VALID_PLACEMENT_RELATIONS:
            raise ValueError("placement_relation must be one of near/left/right/inside")
        return value


class SkillResult(BaseModel):
    ok: bool
    stage: str
    motion_executed: bool
    object_locked: bool = False
    pose: list[float] | None = None
    summary: str
    error_code: str | None = None
    evidence_frames: list[str] = Field(default_factory=list)
