from jetarm_agent.baseline.control_inventory import (
    ControlBoundaryClassification,
    ControlEndpointKind,
    ControlTier,
)
from jetarm_agent.baseline.control_probe import collect_control_inventory, render_control_markdown_report


def build_outputs():
    return {
        "rostopic list": "/jetarm_sdk/serial_servo/move\n/controllers/multi_id_pos_dur\n/jetarm_sdk/serial_servo/stop\n/grasp/goal\n/grasp/result\n",
        "rosservice list": "/kinematics/set_pose_target\n/kinematics/get_current_pose\n/object_sortting/set_color_target\n/object_sortting/enable_sortting\n",
        "find ~/jetarm/src -path '*actions.py' -o -path '*launch/*.launch' | sort": (
            "/home/ubuntu/jetarm/src/jetarm_6dof/jetarm_6dof_app/scripts/actions.py\n"
            "/home/ubuntu/jetarm/src/jetarm_example/src/8.Path_planning/path_planning.launch\n"
            "/home/ubuntu/jetarm/src/jetarm_example/src/9.Positioning_clamp/positioning_clamp.launch\n"
            "/home/ubuntu/jetarm/src/jetarm_6dof/jetarm_6dof_functions/launch/color_sorting.launch\n"
        ),
    }


def test_collect_control_inventory_classifies_three_control_tiers():
    snapshot = collect_control_inventory(command_runner=build_outputs().__getitem__)

    move_topic = next(endpoint for endpoint in snapshot.endpoints if endpoint.name == "/jetarm_sdk/serial_servo/move")
    ik_service = next(endpoint for endpoint in snapshot.endpoints if endpoint.name == "/kinematics/set_pose_target")
    sorting_launch = next(endpoint for endpoint in snapshot.endpoints if endpoint.name.endswith("color_sorting.launch"))

    assert move_topic.tier is ControlTier.RAW_HARDWARE_CONTROL
    assert ik_service.tier is ControlTier.KINEMATICS_SERVICE
    assert sorting_launch.tier is ControlTier.OFFICIAL_TASK_FLOW


def test_collect_control_inventory_marks_pick_place_foundation_endpoints():
    snapshot = collect_control_inventory(command_runner=build_outputs().__getitem__)

    sorting_launch = next(endpoint for endpoint in snapshot.endpoints if endpoint.name.endswith("color_sorting.launch"))
    positioning_launch = next(endpoint for endpoint in snapshot.endpoints if endpoint.name.endswith("positioning_clamp.launch"))
    action_script = next(endpoint for endpoint in snapshot.endpoints if endpoint.name.endswith("actions.py"))

    assert sorting_launch.supports_pick_place is True
    assert positioning_launch.supports_pick_place is True
    assert action_script.boundary is ControlBoundaryClassification.MAINLINE_SAFE_WRAPPER


def test_render_control_markdown_report_mentions_control_tiers_and_pick_place():
    snapshot = collect_control_inventory(command_runner=build_outputs().__getitem__)
    report = render_control_markdown_report(snapshot)

    assert "tier=" in report
    assert "pick_place=true" in report
    assert "color_sorting.launch" in report
