import json
from pathlib import Path


REGISTRY_PATH = Path("docs/governance/project_asset_registry.yaml")
VALID_STATUSES = {
    "verified_frozen",
    "verified_not_frozen",
    "documented_not_verified",
    "legacy_reference",
    "deferred",
}
VALID_ASSET_TYPES = {
    "service",
    "topic",
    "launch",
    "script",
    "workflow",
    "config",
    "runtime_module",
    "data_structure",
    "cloud_object",
    "document",
}
VALID_ENCAPSULATION_LEVELS = {
    "mainline_wrapper",
    "adapter_internal_only",
    "legacy_reference_only",
    "deferred",
    "governing_source",
}
PHASE1_REQUIRED_ASSETS = {
    "board.launch.app_bringup",
    "board.launch.sdk_node_6dof",
    "board.topic.serial_servo_move",
    "board.topic.serial_servo_stop",
    "board.topic.controllers_multi_id_pos_dur",
    "board.service.kinematics_get_current_pose",
    "board.service.kinematics_get_joint_range",
    "board.service.kinematics_set_joint_value_target",
    "board.service.kinematics_set_pose_target",
    "board.camera.rgb_camera_info",
    "board.camera.depth_camera_info",
    "board.workflow.object_tracking_control_plane",
    "board.workflow.color_detection",
    "board.workflow.pixel_coordinate_calculation",
    "board.workflow.object_attitude_calculation",
    "board.workflow.coordinate_system_transformation",
    "board.workflow.path_planning",
    "board.workflow.positioning_clamp",
    "board.workflow.color_sorting_pick_place",
    "board.workflow.object_sortting_and_grasp",
}


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_project_asset_registry_has_valid_schema_and_unique_asset_ids():
    payload = load_registry()
    assets = payload["assets"]
    asset_ids = [asset["asset_id"] for asset in assets]

    assert payload["schema_version"] == 1
    assert len(asset_ids) == len(set(asset_ids))
    for asset in assets:
        assert asset["status"] in VALID_STATUSES
        assert asset["asset_type"] in VALID_ASSET_TYPES
        assert asset["encapsulation_level"] in VALID_ENCAPSULATION_LEVELS
        assert asset["phase_scope"]
        assert asset["entrypoints"]
        assert asset["freeze_gate"]
        assert asset["evidence"]


def test_project_asset_registry_covers_all_phase1_required_assets():
    payload = load_registry()
    asset_ids = {asset["asset_id"] for asset in payload["assets"]}

    assert PHASE1_REQUIRED_ASSETS <= asset_ids


def test_phase1_pick_place_foundation_is_now_verified_frozen():
    payload = load_registry()
    asset = next(item for item in payload["assets"] if item["asset_id"] == "board.workflow.color_sorting_pick_place")

    assert asset["status"] == "verified_frozen"
    assert "satisfied the hard freeze threshold" in asset["freeze_gate"].lower()


def test_phase1_closeout_assets_are_present_and_locked():
    payload = load_registry()
    assets = {asset["asset_id"]: asset for asset in payload["assets"]}

    assert assets["document.phase1_closeout_validation_log"]["status"] == "verified_frozen"
    assert assets["document.pick_place_freeze_validation_log"]["status"] == "verified_frozen"
    assert assets["document.redefined_pick_place_freeze_validation_log"]["status"] == "verified_frozen"
    assert assets["document.positioning_clamp_place_analysis_log"]["status"] == "verified_frozen"
    assert assets["document.positioning_clamp_place_cause_isolation_log"]["status"] == "verified_frozen"
    assert assets["document.pick_place_foundation_redefinition_log"]["status"] == "verified_frozen"
    assert assets["document.phase1_exit_gate"]["status"] == "verified_frozen"
    assert assets["document.phase2_board_observation_smoke_log"]["status"] == "verified_frozen"
    assert assets["board.service.kinematics_set_pose_target"]["status"] == "verified_frozen"
    assert assets["board.workflow.path_planning"]["status"] == "verified_not_frozen"
    assert assets["board.workflow.positioning_clamp"]["status"] == "verified_not_frozen"
    assert assets["board.script.lab_config_client"]["status"] == "verified_not_frozen"


def test_positioning_clamp_is_now_explicitly_tracked_as_pick_only_on_active_board():
    payload = load_registry()
    assets = {asset["asset_id"]: asset for asset in payload["assets"]}

    positioning_clamp = assets["board.workflow.positioning_clamp"]
    assert positioning_clamp["status"] == "verified_not_frozen"
    assert "pick-only" in positioning_clamp["freeze_gate"].lower()


def test_redefined_pick_place_foundation_is_explicitly_tracked():
    payload = load_registry()
    assets = {asset["asset_id"]: asset for asset in payload["assets"]}

    color_sorting = assets["board.workflow.color_sorting_pick_place"]
    object_sortting = assets["board.workflow.object_sortting_and_grasp"]

    assert color_sorting["status"] == "verified_frozen"
    assert object_sortting["status"] == "verified_frozen"
    assert "satisfied the hard freeze threshold" in color_sorting["freeze_gate"].lower()
    assert "satisfied the hard freeze threshold" in object_sortting["freeze_gate"].lower()


def test_redefined_foundation_campaign_result_is_locked_as_phase2_unlock():
    payload = load_registry()
    assets = {asset["asset_id"]: asset for asset in payload["assets"]}

    campaign_log = assets["document.redefined_pick_place_freeze_validation_log"]
    color_sorting = assets["board.workflow.color_sorting_pick_place"]
    object_sortting = assets["board.workflow.object_sortting_and_grasp"]

    assert campaign_log["status"] == "verified_frozen"
    assert "corrected binary freeze result" in campaign_log["freeze_gate"].lower()
    assert color_sorting["status"] == "verified_frozen"
    assert object_sortting["status"] == "verified_frozen"


def test_governing_docs_are_present_as_frozen_sources():
    payload = load_registry()
    assets = {asset["asset_id"]: asset for asset in payload["assets"]}

    architecture = assets["document.final_agent_system_architecture"]
    development_norm = assets["document.development_breakdown_and_openspec_norm"]
    governance = assets["asset_governance_and_freeze_rules"]
    post_demo_reset = assets["document.post_demo_mainline_reset"]

    assert architecture["status"] == "verified_frozen"
    assert architecture["encapsulation_level"] == "governing_source"
    assert development_norm["status"] == "verified_frozen"
    assert development_norm["encapsulation_level"] == "governing_source"
    assert governance["status"] == "verified_frozen"
    assert post_demo_reset["status"] == "verified_frozen"
    assert post_demo_reset["encapsulation_level"] == "governing_source"


def test_cloud_planned_demo_web_agent_assets_are_tracked_without_changing_formal_phase2_state():
    payload = load_registry()
    assets = {asset["asset_id"]: asset for asset in payload["assets"]}

    demo_runtime = assets["runtime.demo_cloud_planned_web_agent"]
    demo_log = assets["document.cloud_planned_demo_web_agent_validation_log"]
    color_sorting = assets["board.workflow.color_sorting_pick_place"]

    assert demo_runtime["status"] == "verified_not_frozen"
    assert demo_runtime["encapsulation_level"] == "legacy_reference_only"
    assert "demo-layer" in demo_runtime["freeze_gate"].lower()
    assert "retained" in demo_runtime["notes"].lower()
    assert demo_log["status"] == "verified_frozen"
    assert color_sorting["status"] == "verified_frozen"


def test_phase2_transport_and_adapter_notes_include_provisional_board_actions():
    payload = load_registry()
    assets = {asset["asset_id"]: asset for asset in payload["assets"]}

    transport = assets["runtime.phase2_board_cli_transport"]
    adapter_core = assets["runtime.phase2_board_adapter_core"]

    assert transport["status"] == "verified_not_frozen"
    assert "provisional" in transport["notes"].lower()
    assert "go_home" in transport["notes"]
    assert "gripper" in transport["notes"].lower()
    assert "stop_all" in transport["notes"]
    assert "recover" in transport["notes"]
    assert "observe_scene" in transport["notes"]
    assert "detect_target" in transport["notes"]
    assert adapter_core["status"] == "verified_not_frozen"
    assert "provisional actions" in adapter_core["notes"].lower()
    assert "observe_scene" in adapter_core["notes"]
    assert "detect_target" in adapter_core["notes"]


def test_phase2_observation_smoke_log_is_present_and_transport_references_it():
    payload = load_registry()
    assets = {asset["asset_id"]: asset for asset in payload["assets"]}

    observation_log = assets["document.phase2_board_observation_smoke_log"]
    strict_check_log = assets["document.phase2_strict_target_check_smoke_log"]
    transport = assets["runtime.phase2_board_cli_transport"]
    adapter_core = assets["runtime.phase2_board_adapter_core"]

    assert observation_log["status"] == "verified_frozen"
    assert strict_check_log["status"] == "verified_frozen"
    assert "observation path" in observation_log["freeze_gate"].lower()
    assert any("2026-04-02-phase2-board-observation-smoke.md" in item["source"] for item in transport["evidence"])
    assert any("2026-04-02-phase2-board-observation-smoke.md" in item["source"] for item in adapter_core["evidence"])


def test_phase2_runtime_notes_include_stricter_target_checking():
    payload = load_registry()
    assets = {asset["asset_id"]: asset for asset in payload["assets"]}

    transport = assets["runtime.phase2_board_cli_transport"]
    adapter_core = assets["runtime.phase2_board_adapter_core"]
    strict_check_log = assets["document.phase2_strict_target_check_smoke_log"]

    assert "freshness" in transport["notes"].lower()
    assert "pose-validity" in adapter_core["notes"].lower()
    assert "freshness checks" in strict_check_log["freeze_gate"].lower()


def test_phase2_profile_registry_assets_are_present_and_consistent():
    payload = load_registry()
    assets = {asset["asset_id"]: asset for asset in payload["assets"]}

    profile_doc = assets["document.phase2_profile_registry"]
    registry_index = assets["config.phase2_profile_registry_index"]
    active_profile = assets["config.phase2_profile_bench_red_block_v1"]
    draft_profile = assets["config.phase2_profile_bench_red_block_draft_v0"]
    loader = assets["runtime.phase2_profile_registry_loader"]
    smoke_log = assets["document.phase2_profile_registry_smoke_log"]

    assert profile_doc["status"] == "verified_frozen"
    assert registry_index["status"] == "verified_frozen"
    assert active_profile["status"] == "verified_frozen"
    assert draft_profile["status"] == "documented_not_verified"
    assert smoke_log["status"] == "verified_frozen"
    assert loader["status"] == "verified_not_frozen"
    assert "default active phase 2 board profile" in registry_index["notes"].lower()
    assert "default formal phase 2 profile" in active_profile["notes"].lower()
    assert "named registry entry" in draft_profile["freeze_gate"].lower()
    assert "smoke scripts now use it" in loader["notes"].lower()
    assert "persisted active phase 2 profile" in smoke_log["freeze_gate"].lower()


def test_governing_docs_consistently_state_phase2_after_demo():
    architecture = Path("docs/architecture/final_agent_system_architecture.md").read_text(encoding="utf-8")
    breakdown = Path("doc/开发任务拆解_v_1.md").read_text(encoding="utf-8")
    post_demo = Path("docs/governance/post-demo-mainline-reset.md").read_text(encoding="utf-8")

    assert "Phase 2 formal board adapter implementation" in architecture
    assert "Phase 1 validation freeze" not in architecture.split("## Current Project Stage", 1)[1]
    assert "`Phase 2：正式 board adapter 与配置资产冻结`" in breakdown
    assert "当前项目状态仍然是：" not in breakdown
    assert "current formal stage: `Phase 2`" in post_demo
