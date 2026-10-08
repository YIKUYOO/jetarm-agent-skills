from jetarm_agent.baseline.audit import collect_board_environment, render_markdown_report


def test_collect_board_environment_uses_command_runner_output():
    outputs = {
        "echo ${ROS_DISTRO:-}": "melodic",
        "echo ${ROS_MASTER_URI:-}": "http://localhost:11311",
        "pwd": "/home/ubuntu",
        "ls ~/jetarm/src": "jetarm_bringup\njetarm_example\nhiwonder_grasp\n",
        "rosnode list": "/jetarm_sdk\n/kinematics\n/object_sortting\n",
        "rosservice list": "/kinematics/get_current_pose\n/object_sortting/enable_sortting\n",
        "rostopic list": "/rgbd_cam/color/image_rect_color\n/grasp/result\n",
    }

    snapshot = collect_board_environment(command_runner=outputs.__getitem__)

    assert snapshot.ros_distro == "melodic"
    assert "jetarm_example" in snapshot.workspace_packages
    assert "/object_sortting" in snapshot.nodes


def test_render_markdown_report_includes_key_sections():
    outputs = {
        "echo ${ROS_DISTRO:-}": "melodic",
        "echo ${ROS_MASTER_URI:-}": "http://localhost:11311",
        "pwd": "/home/ubuntu",
        "ls ~/jetarm/src": "jetarm_bringup\njetarm_example\nhiwonder_grasp\n",
        "rosnode list": "/jetarm_sdk\n/kinematics\n/object_sortting\n",
        "rosservice list": "/kinematics/get_current_pose\n/object_sortting/enable_sortting\n",
        "rostopic list": "/rgbd_cam/color/image_rect_color\n/grasp/result\n",
    }

    snapshot = collect_board_environment(command_runner=outputs.__getitem__)
    report = render_markdown_report(snapshot)

    assert "# Board Environment Audit" in report
    assert "ROS distro" in report
    assert "/kinematics/get_current_pose" in report
