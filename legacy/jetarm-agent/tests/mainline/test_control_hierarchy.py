from jetarm_agent.baseline.control_inventory import (
    ControlBoundaryClassification,
    ControlEndpoint,
    ControlEndpointKind,
    ControlTier,
)


def test_control_endpoint_models_raw_hardware_tier():
    endpoint = ControlEndpoint(
        name="/jetarm_sdk/serial_servo/move",
        kind=ControlEndpointKind.TOPIC,
        tier=ControlTier.RAW_HARDWARE_CONTROL,
        boundary=ControlBoundaryClassification.RAW_LOW_LEVEL,
        source_layer="jetarm_sdk",
        supports_motion=True,
        supports_gripper=False,
        supports_stop=False,
        supports_pick_place=False,
        notes="Direct servo motion primitive",
    )

    assert endpoint.tier is ControlTier.RAW_HARDWARE_CONTROL
    assert endpoint.supports_pick_place is False


def test_control_endpoint_models_official_pick_place_flow_tier():
    endpoint = ControlEndpoint(
        name="jetarm_6dof_functions/color_sorting.launch",
        kind=ControlEndpointKind.LAUNCH,
        tier=ControlTier.OFFICIAL_TASK_FLOW,
        boundary=ControlBoundaryClassification.MAINLINE_SAFE_WRAPPER,
        source_layer="jetarm_6dof_functions",
        supports_motion=True,
        supports_gripper=True,
        supports_stop=False,
        supports_pick_place=True,
        notes="Official color sorting flow",
    )

    assert endpoint.tier is ControlTier.OFFICIAL_TASK_FLOW
    assert endpoint.boundary is ControlBoundaryClassification.MAINLINE_SAFE_WRAPPER
    assert endpoint.supports_pick_place is True
