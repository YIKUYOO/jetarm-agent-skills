from pathlib import Path

import pytest

from jetarm_agent.profile_registry import (
    DEFAULT_PROFILE_REGISTRY_PATH,
    ProfileRegistryError,
    load_active_profile,
    load_active_profile_document,
    load_profile,
    load_profile_document,
    load_profile_registry,
)


def test_default_profile_registry_exists_and_loads_active_profile():
    registry = load_profile_registry()
    active_document = load_active_profile_document()
    active_profile = load_active_profile()

    assert DEFAULT_PROFILE_REGISTRY_PATH.exists()
    assert registry.active_profile == active_document.profile_name
    assert active_profile.profile_name == active_document.profile_name
    assert active_document.metadata.status == "verified_frozen"
    assert active_document.observation.mode == "fixed_front"
    assert active_document.observation.max_target_age_seconds == 5.0


def test_profile_registry_supports_loading_non_active_draft_profile():
    draft_document = load_profile_document("bench_red_block_draft_v0")
    draft_profile = load_profile("bench_red_block_draft_v0")

    assert draft_document.metadata.status == "documented_not_verified"
    assert draft_profile.profile_name == "bench_red_block_draft_v0"
    assert "sorting_bin_red" in draft_profile.workcell.destination_zones


def test_loading_unknown_profile_raises_stable_registry_error(tmp_path: Path):
    registry_path = tmp_path / "profiles.yaml"
    registry_path.write_text(
        '{"schema_version": 1, "active_profile": "bench_red_block_v1", "profiles": []}',
        encoding="utf-8",
    )

    with pytest.raises(ProfileRegistryError):
        load_profile_registry(registry_path)


def test_profile_document_rejects_unknown_default_destination_zone(tmp_path: Path):
    registry_dir = tmp_path / "profiles"
    registry_dir.mkdir()
    (registry_dir / "broken.yaml").write_text(
        """
{
  "profile_name": "broken",
  "camera_frame": "rgbd_cam_color_optical_frame",
  "base_frame": "base_link",
  "offsets": {"pick": {}, "place": {}},
  "workcell": {
    "allowed_object_classes": ["color_block"],
    "destination_zones": {
      "left_bin": {"frame": "base_link", "x": 0.25, "y": 0.12, "z": 0.08}
    }
  },
  "observation": {
    "default_target_color": "red",
    "minimum_confidence": 0.5,
    "mode": "fixed_front"
  },
  "metadata": {
    "status": "verified_frozen",
    "validated_on": "2026-04-02",
    "default_destination_zone": "right_bin",
    "notes": "broken"
  }
}
        """.strip(),
        encoding="utf-8",
    )
    registry_path = registry_dir / "index.yaml"
    registry_path.write_text(
        '{"schema_version": 1, "active_profile": "broken", "profiles": [{"profile_name": "broken", "path": "broken.yaml", "status": "verified_frozen", "description": "broken"}]}',
        encoding="utf-8",
    )

    with pytest.raises(ProfileRegistryError):
        load_active_profile_document(registry_path)
