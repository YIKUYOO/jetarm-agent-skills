# Archived RDK X5 / JetArm ROS2 migration tools

This directory preserves twelve project-authored scripts from the May 2026 migration experiment: workspace/device/ROS status, RGB fallback startup, core startup, process cleanup, hardware wait, RGB and observation capture, serial-port probing, servo publishing, joint nudging and a combined verification path. It is separate from `../rdk-minimal` and the later root observation helpers.

## Offline validation

```sh
python -m pip install -r requirements-offline.txt
python -m pytest -q -p no:cacheprovider
```

Six new archive checks cover numeric parsing and the missing-control-board publication gate using stub ROS modules. Python syntax and Bash `-n` are also checked in CI. These checks do not execute the ROS scripts or contact hardware. There were no historical automated tests for this directory; do not count these checks as robot experiments.

## Dependencies and board setup

The scripts expect a separately obtained and built Hiwonder JetArm ROS2 workspace with `ros_robot_controller_msgs`, `servo_controller_msgs`, `kinematics_msgs`, `interfaces`, `ros_robot_controller`, `servo_controller`, `kinematics`, `sdk`, `peripherals` and `bringup`. The board also needs ROS2 Humble/TROS, `rclpy`, `sensor_msgs`, OpenCV, NumPy, USB/serial devices and its own calibrated camera setup. Manufacturer package code is not redistributed.

Set `JETARM_WS` to your workspace; its default is `$HOME/jetarm_ros2_ws`. `tools/jetarm_env.sh` sources `$JETARM_WS/jetarm_rdk_env.sh` and the built install space. A reconstructed **configuration example**, `config/jetarm_rdk_env.sh.example`, explains the required environment; inspect and adapt it before installing it at that path. It is not the original board file and has not been verified on a robot.

The historical migration required compatibility changes in independently supplied vendor packages: remove the unused `nav2_common` requirement and optional chassis lookup from `sdk/launch/jetarm_sdk.launch.py`; add `get_package_share_directory` and a default `need_compile` in the servo-controller launch file; add default `need_compile` and `CAMERA_TYPE` in the depth-camera launch file. Check the vendor version before applying equivalent changes. No patched vendor files are included or relicensed.

After preparing your board, inspect `tools/jetarm_status.sh` first. The RGB fallback uses `CAMERA_TYPE=USB`, `/depth_cam/rgb/image_raw` and `/depth_cam/rgb/camera_info`. Capture scripts write image data plus camera/state metadata to an operator-selected path. `jetarm_minimal_verify.sh` starts and stops nodes and writes observations even without its motion flag, so it is not a read-only command.

## Preserved experimental boundaries

- `jetarm_safe_servo_move.py` defaults to request preview but imports ROS at startup. Real publishing requires `--execute`; `/dev/rrc` is checked unless the operator explicitly bypasses it with `--allow-without-rrc`.
- `jetarm_joint_nudge_test.py` connects to ROS to obtain state even in dry-run mode. Its `--execute` mode nudges and returns joints. It has no collision model, force feedback or proof that software state equals actual motion.
- Historical input checks are incomplete, including non-finite numbers and duration limits; nominal clamp functions are not certified motion safeguards.
- Startup scripts can start vendor processes; `jetarm_cleanup.sh` terminates matching processes and is intended only for a dedicated experiment board. The serial probe sends status queries and can access onboard UARTs; it is not suitable for an unknown device without operator inspection.
- Raw workspace paths, USB identifiers, message layouts and camera calibration are platform-specific. Historical evidence does not prove the public sanitized copy on another board.

## Source and license

These are project orchestration, observation and diagnostic wrappers under the parent MIT license. They call ROS/vendor interfaces at runtime and contain no vendor workspace, camera firmware, trained model, credentials or raw experiment data. Public edits replace the personal workspace default, supply documentation/configuration examples and add isolated offline checks; control semantics remain historical.

The separate board package `jetarm_minimal_control`, used by later experiment notes, is now published at [`../../board/jetarm_minimal_control`](../../board/jetarm_minimal_control). It provides the named launch/action commands. These twelve earlier migration scripts are a separate implementation; neither should be substituted for the other without checking the experiment version.
