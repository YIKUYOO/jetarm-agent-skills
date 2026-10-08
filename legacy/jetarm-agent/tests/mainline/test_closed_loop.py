from datetime import datetime, timezone

from jetarm_agent.closed_loop import BoardClosedLoopService
from jetarm_agent.schemas import (
    CalibrationProfile,
    CalibrationOffsets,
    DetectedTarget,
    PickPlaceRequest,
    PickPlaceResult,
    PickPlaceStatus,
    WorkcellConstraints,
)


class FakeAdapter:
    def observe_scene(self, profile: CalibrationProfile):
        return [
            DetectedTarget(
                entity_id="block-red-1",
                object_class="color_block",
                color="red",
                confidence=0.95,
                source_timestamp=datetime(2026, 3, 29, tzinfo=timezone.utc),
                pose={"frame": "camera", "x": 0.1, "y": 0.2, "z": 0.3},
            )
        ]

    def execute_pick_place(self, request: PickPlaceRequest) -> PickPlaceResult:
        return PickPlaceResult(
            request_id=request.request_id,
            status=PickPlaceStatus.SUCCEEDED,
            failure_stage=None,
            telemetry={"adapter": "fake"},
            artifacts={"summary": f"moved {request.target.entity_id}"},
        )


def build_request() -> PickPlaceRequest:
    profile = CalibrationProfile(
        profile_name="lab-a",
        camera_frame="rgbd_cam_color_optical_frame",
        base_frame="base_link",
        offsets=CalibrationOffsets(),
        workcell=WorkcellConstraints(
            allowed_object_classes=["color_block"],
            destination_zones={"left_bin": {"frame": "base_link", "x": 0.25, "y": 0.12, "z": 0.08}},
        ),
    )
    return PickPlaceRequest(
        request_id="req-1",
        profile=profile,
        target=DetectedTarget(
            entity_id="block-red-1",
            object_class="color_block",
            color="red",
            confidence=0.9,
            source_timestamp=datetime(2026, 3, 29, tzinfo=timezone.utc),
            pose={"frame": "camera", "x": 0.1, "y": 0.2, "z": 0.3},
        ),
        destination_zone="left_bin",
    )


def test_closed_loop_service_normalizes_observation_and_execution():
    service = BoardClosedLoopService(adapter=FakeAdapter())

    observed = service.observe_scene(build_request().profile)
    result = service.run_pick_place(build_request())

    assert observed[0].entity_id == "block-red-1"
    assert result.status is PickPlaceStatus.SUCCEEDED
    assert result.telemetry["adapter"] == "fake"
