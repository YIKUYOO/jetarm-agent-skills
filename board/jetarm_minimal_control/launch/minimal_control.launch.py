from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("dry_run", default_value="true"),
            DeclareLaunchArgument("topic", default_value="/servo_controller"),
            Node(
                package="jetarm_minimal_control",
                executable="jetarm_preset_server",
                output="screen",
                parameters=[
                    {
                        "dry_run": LaunchConfiguration("dry_run"),
                        "topic": LaunchConfiguration("topic"),
                    }
                ],
            ),
        ]
    )
