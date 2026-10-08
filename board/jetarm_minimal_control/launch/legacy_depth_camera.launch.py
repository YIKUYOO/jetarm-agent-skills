import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    orbbec_launch = os.path.join(
        get_package_share_directory("orbbec_camera"),
        "launch",
        "astra_stereo_u3.launch.py",
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("camera_name", default_value="depth_cam"),
            DeclareLaunchArgument("color_width", default_value="640"),
            DeclareLaunchArgument("color_height", default_value="480"),
            DeclareLaunchArgument("color_fps", default_value="30"),
            DeclareLaunchArgument("color_format", default_value="MJPG"),
            DeclareLaunchArgument("depth_width", default_value="640"),
            DeclareLaunchArgument("depth_height", default_value="400"),
            DeclareLaunchArgument("depth_fps", default_value="30"),
            DeclareLaunchArgument("depth_format", default_value="Y11"),
            DeclareLaunchArgument("ir_width", default_value="640"),
            DeclareLaunchArgument("ir_height", default_value="400"),
            DeclareLaunchArgument("ir_fps", default_value="30"),
            DeclareLaunchArgument("enable_point_cloud", default_value="false"),
            DeclareLaunchArgument("enable_colored_point_cloud", default_value="false"),
            DeclareLaunchArgument("enable_soft_filter", default_value="false"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(orbbec_launch),
                launch_arguments={
                    "camera_name": LaunchConfiguration("camera_name"),
                    "color_width": LaunchConfiguration("color_width"),
                    "color_height": LaunchConfiguration("color_height"),
                    "color_fps": LaunchConfiguration("color_fps"),
                    "color_format": LaunchConfiguration("color_format"),
                    "enable_color": "true",
                    "depth_width": LaunchConfiguration("depth_width"),
                    "depth_height": LaunchConfiguration("depth_height"),
                    "depth_fps": LaunchConfiguration("depth_fps"),
                    "depth_format": LaunchConfiguration("depth_format"),
                    "enable_depth": "true",
                    "ir_width": LaunchConfiguration("ir_width"),
                    "ir_height": LaunchConfiguration("ir_height"),
                    "ir_fps": LaunchConfiguration("ir_fps"),
                    "enable_ir": "false",
                    "enable_point_cloud": LaunchConfiguration("enable_point_cloud"),
                    "enable_colored_point_cloud": LaunchConfiguration("enable_colored_point_cloud"),
                    "enable_soft_filter": LaunchConfiguration("enable_soft_filter"),
                }.items(),
            )
        ]
    )
