import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    servo_config = os.path.join(
        get_package_share_directory("servo_controller"),
        "config",
        "servo_controller.yaml",
    )
    depth_launch = os.path.join(
        get_package_share_directory("jetarm_minimal_control"),
        "launch",
        "legacy_depth_camera.launch.py",
    )

    start_driver = LaunchConfiguration("start_driver")
    start_servo_controller = LaunchConfiguration("start_servo_controller")
    start_kinematics = LaunchConfiguration("start_kinematics")
    start_preset_server = LaunchConfiguration("start_preset_server")
    start_depth_camera = LaunchConfiguration("start_depth_camera")
    dry_run = LaunchConfiguration("dry_run")
    topic = LaunchConfiguration("topic")
    base_frame = LaunchConfiguration("base_frame")
    chassis_type = LaunchConfiguration("chassis_type")
    camera_type = LaunchConfiguration("camera_type")
    need_compile = LaunchConfiguration("need_compile")
    color_fps = LaunchConfiguration("color_fps")
    depth_fps = LaunchConfiguration("depth_fps")
    enable_point_cloud = LaunchConfiguration("enable_point_cloud")

    return LaunchDescription(
        [
            DeclareLaunchArgument("need_compile", default_value="True"),
            DeclareLaunchArgument("chassis_type", default_value="None"),
            DeclareLaunchArgument("camera_type", default_value="GEMINI"),
            DeclareLaunchArgument("start_driver", default_value="true"),
            DeclareLaunchArgument("start_servo_controller", default_value="true"),
            DeclareLaunchArgument("start_kinematics", default_value="true"),
            DeclareLaunchArgument("start_preset_server", default_value="true"),
            DeclareLaunchArgument("start_depth_camera", default_value="false"),
            DeclareLaunchArgument("dry_run", default_value="true"),
            DeclareLaunchArgument("topic", default_value="/servo_controller"),
            DeclareLaunchArgument("base_frame", default_value=""),
            DeclareLaunchArgument("color_fps", default_value="30"),
            DeclareLaunchArgument("depth_fps", default_value="30"),
            DeclareLaunchArgument("enable_point_cloud", default_value="false"),
            SetEnvironmentVariable("need_compile", need_compile),
            SetEnvironmentVariable("CHASSIS_TYPE", chassis_type),
            SetEnvironmentVariable("CAMERA_TYPE", camera_type),
            Node(
                package="ros_robot_controller",
                executable="ros_robot_controller",
                output="screen",
                condition=IfCondition(start_driver),
            ),
            TimerAction(
                period=2.0,
                actions=[
                    Node(
                        package="servo_controller",
                        executable="servo_controller",
                        output="screen",
                        parameters=[servo_config, {"base_frame": base_frame}],
                        condition=IfCondition(start_servo_controller),
                    ),
                    Node(
                        package="servo_controller",
                        executable="grasp",
                        output="screen",
                        condition=IfCondition(start_servo_controller),
                    ),
                ],
            ),
            TimerAction(
                period=4.0,
                actions=[
                    Node(
                        package="kinematics",
                        executable="search_kinematics_solutions",
                        output="screen",
                        condition=IfCondition(start_kinematics),
                    )
                ],
            ),
            TimerAction(
                period=5.0,
                actions=[
                    Node(
                        package="jetarm_minimal_control",
                        executable="jetarm_preset_server",
                        output="screen",
                        parameters=[{"dry_run": dry_run, "topic": topic}],
                        condition=IfCondition(start_preset_server),
                    )
                ],
            ),
            TimerAction(
                period=6.0,
                actions=[
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(depth_launch),
                        launch_arguments={
                            "color_fps": color_fps,
                            "depth_fps": depth_fps,
                            "enable_point_cloud": enable_point_cloud,
                        }.items(),
                        condition=IfCondition(start_depth_camera),
                    )
                ],
            ),
        ]
    )
