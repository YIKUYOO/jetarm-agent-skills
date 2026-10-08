from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from jetarm_agent.schemas import CalibrationProfile


DEFAULT_PROFILE_REGISTRY_PATH = Path("configs/phase2/profiles/index.yaml")
VALID_PROFILE_STATUSES = {
    "verified_frozen",
    "verified_not_frozen",
    "documented_not_verified",
    "legacy_reference",
    "deferred",
}


class ProfileRegistryError(RuntimeError):
    """Raised when Phase 2 profile registry assets are missing or invalid."""


class ProfileObservationConfig(BaseModel):
    default_target_color: str
    minimum_confidence: float
    max_target_age_seconds: float
    mode: str

    model_config = ConfigDict(extra="forbid")


class ProfileMetadata(BaseModel):
    status: str
    validated_on: str
    default_destination_zone: str
    notes: str = ""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_status(self) -> "ProfileMetadata":
        if self.status not in VALID_PROFILE_STATUSES:
            raise ValueError(f"unsupported profile status: {self.status}")
        return self


class ProfileDocument(BaseModel):
    profile_name: str
    camera_frame: str
    base_frame: str
    offsets: dict
    workcell: dict
    observation: ProfileObservationConfig
    metadata: ProfileMetadata

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_default_destination_zone(self) -> "ProfileDocument":
        destination_zones = self.workcell.get("destination_zones", {})
        if self.metadata.default_destination_zone not in destination_zones:
            raise ValueError("metadata.default_destination_zone must exist in workcell.destination_zones")
        return self

    def to_calibration_profile(self) -> CalibrationProfile:
        return CalibrationProfile.model_validate(
            {
                "profile_name": self.profile_name,
                "camera_frame": self.camera_frame,
                "base_frame": self.base_frame,
                "offsets": self.offsets,
                "workcell": self.workcell,
            }
        )


class ProfileRegistryEntry(BaseModel):
    profile_name: str
    path: str
    status: str
    description: str

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_status(self) -> "ProfileRegistryEntry":
        if self.status not in VALID_PROFILE_STATUSES:
            raise ValueError(f"unsupported profile status: {self.status}")
        return self


class ProfileRegistry(BaseModel):
    schema_version: int
    active_profile: str
    profiles: list[ProfileRegistryEntry]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_active_profile(self) -> "ProfileRegistry":
        names = {entry.profile_name for entry in self.profiles}
        if self.active_profile not in names:
            raise ValueError("active_profile must exist in profiles")
        return self

    def get_entry(self, profile_name: str) -> ProfileRegistryEntry:
        for entry in self.profiles:
            if entry.profile_name == profile_name:
                return entry
        raise ProfileRegistryError(f"profile not found: {profile_name}")


def _load_yaml_subset(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProfileRegistryError(f"profile asset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileRegistryError(
            f"profile asset must use the Phase 2 JSON-compatible YAML subset: {path}"
        ) from exc


def load_profile_registry(path: Path | None = None) -> ProfileRegistry:
    registry_path = path or DEFAULT_PROFILE_REGISTRY_PATH
    try:
        return ProfileRegistry.model_validate(_load_yaml_subset(registry_path))
    except ValidationError as exc:
        raise ProfileRegistryError(f"invalid profile registry: {registry_path}") from exc


def load_profile_document(profile_name: str, registry_path: Path | None = None) -> ProfileDocument:
    loaded_registry = load_profile_registry(registry_path)
    entry = loaded_registry.get_entry(profile_name)
    base_dir = (registry_path or DEFAULT_PROFILE_REGISTRY_PATH).parent
    profile_path = base_dir / entry.path
    try:
        return ProfileDocument.model_validate(_load_yaml_subset(profile_path))
    except ValidationError as exc:
        raise ProfileRegistryError(f"invalid profile document: {profile_path}") from exc


def load_active_profile_document(registry_path: Path | None = None) -> ProfileDocument:
    loaded_registry = load_profile_registry(registry_path)
    return load_profile_document(loaded_registry.active_profile, registry_path)


def load_profile(profile_name: str, registry_path: Path | None = None) -> CalibrationProfile:
    return load_profile_document(profile_name, registry_path).to_calibration_profile()


def load_active_profile(registry_path: Path | None = None) -> CalibrationProfile:
    return load_active_profile_document(registry_path).to_calibration_profile()
