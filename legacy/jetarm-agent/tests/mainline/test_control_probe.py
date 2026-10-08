from jetarm_agent.baseline.control_inventory import ControlBoundaryClassification, ControlEndpointKind
from jetarm_agent.baseline.control_probe import collect_control_inventory, render_control_markdown_report


def test_collect_control_inventory_defaults_to_non_destructive_mode():
    outputs = {
        "rostopic list": "/jetarm_sdk/serial_servo/move\n/controllers/multi_id_pos_dur\n/jetarm_sdk/serial_servo/stop\n",
        "rosservice list": "/kinematics/set_pose_target\n/kinematics/get_current_pose\n",
        "find ~/jetarm/src -path '*actions.py' -o -path '*launch/*.launch' | sort": "/home/ubuntu/jetarm/src/jetarm_6dof/jetarm_6dof_app/scripts/actions.py\n/home/ubuntu/jetarm/src/jetarm_bringup/launch/app_bringup.launch\n",
    }

    snapshot = collect_control_inventory(command_runner=outputs.__getitem__)

    assert snapshot.motion_checks_performed is False
    assert any(endpoint.name == "/jetarm_sdk/serial_servo/move" for endpoint in snapshot.endpoints)
    assert any(endpoint.kind is ControlEndpointKind.SCRIPT for endpoint in snapshot.endpoints)


def test_collect_control_inventory_classifies_known_endpoint_layers():
    outputs = {
        "rostopic list": "/jetarm_sdk/serial_servo/move\n/controllers/multi_id_pos_dur\n/jetarm_sdk/serial_servo/stop\n",
        "rosservice list": "/kinematics/set_pose_target\n/kinematics/get_current_pose\n",
        "find ~/jetarm/src -path '*actions.py' -o -path '*launch/*.launch' | sort": "/home/ubuntu/jetarm/src/jetarm_6dof/jetarm_6dof_app/scripts/actions.py\n/home/ubuntu/jetarm/src/jetarm_bringup/launch/app_bringup.launch\n",
    }

    snapshot = collect_control_inventory(command_runner=outputs.__getitem__)
    move_topic = next(endpoint for endpoint in snapshot.endpoints if endpoint.name == "/jetarm_sdk/serial_servo/move")
    action_script = next(endpoint for endpoint in snapshot.endpoints if endpoint.name.endswith("actions.py"))

    assert move_topic.boundary is ControlBoundaryClassification.RAW_LOW_LEVEL
    assert action_script.boundary is ControlBoundaryClassification.MAINLINE_SAFE_WRAPPER


def test_render_control_markdown_report_includes_inventory_and_validation_sections():
    outputs = {
        "rostopic list": "/jetarm_sdk/serial_servo/move\n/controllers/multi_id_pos_dur\n/jetarm_sdk/serial_servo/stop\n",
        "rosservice list": "/kinematics/set_pose_target\n/kinematics/get_current_pose\n",
        "find ~/jetarm/src -path '*actions.py' -o -path '*launch/*.launch' | sort": "/home/ubuntu/jetarm/src/jetarm_6dof/jetarm_6dof_app/scripts/actions.py\n/home/ubuntu/jetarm/src/jetarm_bringup/launch/app_bringup.launch\n",
    }

    snapshot = collect_control_inventory(command_runner=outputs.__getitem__)
    report = render_control_markdown_report(snapshot)

    assert "# Low-Level Control Inventory" in report
    assert "/jetarm_sdk/serial_servo/move" in report
    assert "Motion checks performed" in report
