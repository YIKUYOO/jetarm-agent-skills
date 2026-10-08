from datetime import datetime, timedelta, timezone

from jetarm_agent.closed_loop import BoardClosedLoopService
from jetarm_agent.adapter import (
    Phase2BoardAdapter,
    Phase2BoardAdapterConfig,
    SkillName,
)
from jetarm_agent.skill_contract import (
    AdapterCapabilityLevel,
    CheckTargetRequest,
    DetectTargetRequest,
    GripperRequest,
    GoHomeRequest,
    PickRequest,
    PlaceRequest,
    RecoverRequest,
    SkillErrorCode,
    SkillStatus,
    StopRequest,
)
from jetarm_agent.schemas import (
    CalibrationOffsets,
    CalibrationProfile,
    DetectedTarget,
    PickPlaceRequest,
    PickPlaceResult,
    PickPlaceStatus,
    WorkcellConstraints,
)


def build_profile() -> CalibrationProfile:
    return CalibrationProfile(
        profile_name="lab-a",
        camera_frame="rgbd_cam_color_optical_frame",
        base_frame="base_link",
        offsets=CalibrationOffsets(),
        workcell=WorkcellConstraints(
            allowed_object_classes=["color_block"],
            destination_zones={"left_bin": {"frame": "base_link", "x": 0.25, "y": 0.12, "z": 0.08}},
        ),
    )


def build_target(entity_id: str = "block-red-1") -> DetectedTarget:
    return DetectedTarget(
        entity_id=entity_id,
        object_class="color_block",
        color="red",
        confidence=0.96,
        source_timestamp=datetime(2026, 3, 30, tzinfo=timezone.utc),
        pose={"frame": "base_link", "x": 0.12, "y": 0.08, "z": 0.03},
    )


def build_request() -> PickPlaceRequest:
    return PickPlaceRequest(
        request_id="req-1",
        profile=build_profile(),
        target=build_target(),
        destination_zone="left_bin",
    )


class FakeBoardTransport:
    def __init__(self, *, observed_targets=None, pick_place_result=None):
        self.observed_targets = observed_targets or [build_target()]
        self.pick_place_result = pick_place_result or PickPlaceResult(
            request_id="req-1",
            status=PickPlaceStatus.SUCCEEDED,
            failure_stage=None,
            telemetry={"release_confirmed": True, "continue_ready": True},
            artifacts={"workflow": "object_sortting"},
        )
        self.calls = []

    def observe_scene(self, profile: CalibrationProfile):
        self.calls.append(("observe_scene", profile.profile_name))
        return list(self.observed_targets)

    def run_object_sortting_pick_place(self, request: PickPlaceRequest, *, target_color: str):
        self.calls.append(("run_object_sortting_pick_place", request.request_id, target_color))
        return self.pick_place_result.model_copy(update={"request_id": request.request_id})

    def go_home(self):
        self.calls.append(("go_home",))
        return {"final_pose_summary": "home"}

    def set_gripper(self, *, opened: bool):
        self.calls.append(("set_gripper", opened))
        return {"gripper_state": "open" if opened else "closed"}

    def stop_all(self):
        self.calls.append(("stop_all",))
        return {"continue_ready": False}

    def recover(self, *, last_error_code=None):
        self.calls.append(("recover", last_error_code.value if last_error_code else None))
        return {"continue_ready": True}


def build_adapter(transport: FakeBoardTransport | None = None) -> Phase2BoardAdapter:
    return Phase2BoardAdapter(
        transport=transport or FakeBoardTransport(),
        config=Phase2BoardAdapterConfig(),
    )


def test_phase2_adapter_capabilities_distinguish_frozen_and_provisional_paths():
    adapter = build_adapter()
    capabilities = adapter.capabilities()

    assert capabilities[SkillName.PICK_PLACE] is AdapterCapabilityLevel.FROZEN
    assert capabilities[SkillName.OBSERVE_SCENE] is AdapterCapabilityLevel.PROVISIONAL
    assert capabilities[SkillName.GO_HOME] is AdapterCapabilityLevel.PROVISIONAL
    assert capabilities[SkillName.PICK] is AdapterCapabilityLevel.PROVISIONAL


def test_detect_target_returns_unique_match_from_observed_scene():
    adapter = build_adapter()

    result = adapter.detect_target(
        DetectTargetRequest(
            profile=build_profile(),
            object_class="color_block",
            color="red",
            minimum_confidence=0.8,
        )
    )

    assert result.status is SkillStatus.SUCCEEDED
    assert result.payload.target.entity_id == "block-red-1"


def test_detect_target_rejects_multiple_matches():
    transport = FakeBoardTransport(observed_targets=[build_target("a"), build_target("b")])
    adapter = build_adapter(transport)

    result = adapter.detect_target(
        DetectTargetRequest(
            profile=build_profile(),
            object_class="color_block",
            color="red",
            minimum_confidence=0.8,
        )
    )

    assert result.status is SkillStatus.FAILED
    assert result.error_code is SkillErrorCode.TARGET_NOT_UNIQUE


def test_execute_pick_place_uses_object_sortting_as_the_only_canonical_route():
    transport = FakeBoardTransport()
    adapter = build_adapter(transport)

    result = adapter.execute_pick_place(build_request())

    assert result.status is PickPlaceStatus.SUCCEEDED
    assert transport.calls == [("run_object_sortting_pick_place", "req-1", "red")]


def test_pick_and_place_are_explicitly_blocked_as_standalone_skills_in_phase2_core():
    adapter = build_adapter()
    profile = build_profile()
    target = build_target()

    pick_result = adapter.pick(PickRequest(request_id="pick-1", profile=profile, target=target))
    place_result = adapter.place(
        PlaceRequest(
            request_id="place-1",
            profile=profile,
            target=target,
            destination_zone="left_bin",
        )
    )

    assert pick_result.status is SkillStatus.BLOCKED
    assert pick_result.error_code is SkillErrorCode.FOUNDATION_UNAVAILABLE
    assert place_result.status is SkillStatus.BLOCKED
    assert place_result.error_code is SkillErrorCode.FOUNDATION_UNAVAILABLE


def test_provisional_go_home_still_executes_through_transport():
    transport = FakeBoardTransport()
    adapter = build_adapter(transport)

    result = adapter.go_home(GoHomeRequest(reason="reset before next request"))

    assert result.status is SkillStatus.SUCCEEDED
    assert transport.calls == [("go_home",)]


def test_provisional_open_close_stop_and_recover_execute_through_transport():
    transport = FakeBoardTransport()
    adapter = build_adapter(transport)

    open_result = adapter.open_gripper(GripperRequest(reason="open"))
    close_result = adapter.close_gripper(GripperRequest(reason="close"))
    stop_result = adapter.stop_all(StopRequest(reason="stop"))
    recover_result = adapter.recover(RecoverRequest(reason="recover", last_error_code=SkillErrorCode.STOP_REQUESTED))

    assert open_result.status is SkillStatus.SUCCEEDED
    assert close_result.status is SkillStatus.SUCCEEDED
    assert stop_result.status is SkillStatus.SUCCEEDED
    assert recover_result.status is SkillStatus.SUCCEEDED
    assert transport.calls == [
        ("set_gripper", True),
        ("set_gripper", False),
        ("stop_all",),
        ("recover", "STOP_REQUESTED"),
    ]


class BrokenBoardTransport(FakeBoardTransport):
    def go_home(self):
        raise RuntimeError("transport failed")


def test_adapter_maps_transport_runtime_error_to_failed_result():
    adapter = build_adapter(BrokenBoardTransport())

    result = adapter.go_home(GoHomeRequest(reason="reset before next request"))

    assert result.status is SkillStatus.FAILED
    assert result.error_code is SkillErrorCode.ADAPTER_INTERNAL_ERROR


class BrokenObservationTransport(FakeBoardTransport):
    def observe_scene(self, profile: CalibrationProfile):
        raise RuntimeError("camera pipeline unavailable")


def test_detect_target_maps_observation_transport_error_to_foundation_unavailable():
    adapter = build_adapter(BrokenObservationTransport())

    result = adapter.detect_target(
        DetectTargetRequest(
            profile=build_profile(),
            object_class="color_block",
            color="red",
            minimum_confidence=0.8,
        )
    )

    assert result.status is SkillStatus.FAILED
    assert result.error_code is SkillErrorCode.FOUNDATION_UNAVAILABLE
    assert "camera pipeline unavailable" in result.message


def test_check_target_reports_required_zone_in_telemetry_when_present():
    target = build_target()
    adapter = build_adapter()

    result = adapter.check_target(
        CheckTargetRequest(
            profile=build_profile(),
            target=target,
            required_zone="left_bin",
            reference_time=target.source_timestamp,
        )
    )

    assert result.status is SkillStatus.SUCCEEDED
    assert result.telemetry["required_zone"] == "left_bin"
    assert result.telemetry["checks"]["allowed_object_class"] is True


def test_check_target_rejects_stale_target():
    adapter = build_adapter()
    stale_target = build_target().model_copy(
        update={"source_timestamp": datetime.now(timezone.utc) - timedelta(seconds=30)}
    )

    result = adapter.check_target(
        CheckTargetRequest(
            profile=build_profile(),
            target=stale_target,
            maximum_target_age_seconds=5.0,
        )
    )

    assert result.status is SkillStatus.FAILED
    assert result.error_code is SkillErrorCode.TARGET_CHECK_FAILED
    assert result.telemetry["checks"]["target_fresh_enough"] is False


def test_check_target_rejects_color_mismatch_when_required_color_is_set():
    adapter = build_adapter()
    blue_target = build_target().model_copy(update={"color": "blue"})

    result = adapter.check_target(
        CheckTargetRequest(
            profile=build_profile(),
            target=blue_target,
            required_color="red",
        )
    )

    assert result.status is SkillStatus.FAILED
    assert result.error_code is SkillErrorCode.TARGET_CHECK_FAILED
    assert result.telemetry["checks"]["required_color_matches"] is False


def test_check_target_rejects_target_with_invalid_pose_coordinates():
    adapter = build_adapter()
    invalid_pose_target = build_target().model_copy(
        update={"pose": {"frame": "base_link", "x": 0.1, "y": "bad", "z": 0.3}}
    )

    result = adapter.check_target(
        CheckTargetRequest(
            profile=build_profile(),
            target=invalid_pose_target,
        )
    )

    assert result.status is SkillStatus.FAILED
    assert result.error_code is SkillErrorCode.TARGET_CHECK_FAILED
    assert result.telemetry["checks"]["pose_coordinates_valid"] is False


def test_closed_loop_service_remains_compatible_with_phase2_adapter():
    transport = FakeBoardTransport()
    adapter = build_adapter(transport)
    service = BoardClosedLoopService(adapter=adapter)

    observed = service.observe_scene(build_profile())
    result = service.run_pick_place(build_request())

    assert observed[0].entity_id == "block-red-1"
    assert result.status is PickPlaceStatus.SUCCEEDED
    assert transport.calls == [
        ("observe_scene", "lab-a"),
        ("run_object_sortting_pick_place", "req-1", "red"),
    ]
