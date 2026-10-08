from jetarm_agent.baseline.control_inventory import (
    ControlBoundaryClassification,
    ControlEndpoint,
    ControlEndpointKind,
    ControlRiskLevel,
    ControlValidationResult,
)


def test_control_endpoint_models_raw_servo_topic():
    endpoint = ControlEndpoint(
        name="/jetarm_sdk/serial_servo/move",
        kind=ControlEndpointKind.TOPIC,
        boundary=ControlBoundaryClassification.RAW_LOW_LEVEL,
        source_layer="jetarm_sdk",
        supports_motion=True,
        supports_gripper=False,
        supports_stop=False,
        notes="Direct servo move topic",
    )

    assert endpoint.kind is ControlEndpointKind.TOPIC
    assert endpoint.boundary is ControlBoundaryClassification.RAW_LOW_LEVEL
    assert endpoint.supports_motion is True


def test_validation_result_preserves_risk_and_follow_up():
    result = ControlValidationResult(
        endpoint_name="/controllers/multi_id_pos_dur",
        validation_mode="non_destructive",
        passed=True,
        evidence=["topic listed", "official action script uses this topic"],
        risk_level=ControlRiskLevel.GUARDED,
        follow_up=["verify go_home under human supervision"],
    )

    assert result.passed is True
    assert result.risk_level is ControlRiskLevel.GUARDED
    assert "verify go_home under human supervision" in result.follow_up
