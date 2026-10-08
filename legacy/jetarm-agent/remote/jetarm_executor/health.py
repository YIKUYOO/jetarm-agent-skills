try:
    from .ros_adapters import check_ros_nodes
except ImportError:
    from ros_adapters import check_ros_nodes


def get_health() -> dict:
    ros_context = check_ros_nodes()
    return {
        "ok": True,
        "single_block_demo_mode": True,
        "ros_context": ros_context,
    }
