import os
from glob import glob
from setuptools import find_packages, setup

package_name = "jetarm_minimal_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml", "README.md", "LICENSE", "THIRD_PARTY.md"]),
        (os.path.join("share", package_name, "launch"), glob(os.path.join("launch", "*.launch.py"))),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="JetArm contributors",
    maintainer_email="maintainers@example.invalid",
    description="Minimal JetArm preset motion bridge for RDK X5 ROS2/TROS.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "jetarm_action_runner = jetarm_minimal_control.action_runner:main",
            "jetarm_preset_server = jetarm_minimal_control.preset_server:main",
            "jetarm_safe_nudge = jetarm_minimal_control.safe_nudge:main",
            "jetarm_status_check = jetarm_minimal_control.status_check:main",
        ],
    },
)
