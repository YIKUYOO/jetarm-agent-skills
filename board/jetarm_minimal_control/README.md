# JetArm minimal ROS2 control package

This is the project's `jetarm_minimal_control` board package from the May 2026 RDK X5 experiment, recovered from its local deployment staging copy. It supplies the actual four console entry points used by the historical project instructions: `jetarm_action_runner`, `jetarm_preset_server`, `jetarm_safe_nudge` and `jetarm_status_check`, plus three launch files. Package version remains `0.1.0`.

The package provides a ROS wrapper, preset validation/message construction, named action services, device state queries and coordinated driver/camera startup. Nine stored action presets use Hiwonder-documented pulse parameters; these are compatibility parameters, not a new inverse-kinematics or grasping algorithm. See `THIRD_PARTY.md`. No trained VLA model, vendor workspace, calibration file or camera driver is bundled.

## Offline checks

Use Python 3.12 from this directory:

```sh
python -m pip install -r requirements-offline.txt
python -m pytest -q -p no:cacheprovider
```

The 12 release tests include 10 preset/action-contract checks and 2 unsigned-readback checks. The preset/action tests use stub ROS messages and check preset ranges/aliases, rejected malformed steps and the action runner's default no-publish path. They do not start ROS, connect a device or validate physical movement. Python syntax checks accompany them in CI. The original board snapshot had no automated test suite. Public packaging has not been revalidated on RDK X5.

## External runtime and build

Prepare ROS2 Humble/TROS and a legally obtained Hiwonder JetArm ROS2 workspace first. Required interfaces include `interfaces`, `ros_robot_controller_msgs`, `servo_controller_msgs`, `std_srvs` and `control_msgs`; required running components include `ros_robot_controller`, `servo_controller` and `kinematics`. Launch also uses `ament_index_python`, `launch` and `launch_ros`. These dependencies are declared in `package.xml`.

`control_bringup.launch.py` reads the external `servo_controller/config/servo_controller.yaml`. Its optional camera path requires a compatible external `orbbec_camera` package containing `launch/astra_stereo_u3.launch.py`. The historical camera workspace used a legacy Orbbec driver. Match camera model and installed launch arguments before use. If your board distribution lacks `control_msgs`, obtain the appropriate ROS Humble upstream package independently; no third-party source is redistributed here.

Copy this directory to your overlay's `src/jetarm_minimal_control`, then use paths for your own installations:

```sh
source /opt/tros/humble/setup.bash
source "$JETARM_VENDOR_WS/install/setup.bash"
source "$ORBBEC_WS/install/setup.bash"
cd "$JETARM_OVERLAY_WS"
colcon build --symlink-install --packages-select jetarm_minimal_control
source install/setup.bash
ros2 run jetarm_minimal_control jetarm_action_runner --list
```

The variables above are operator-supplied workspace paths, not shipped configuration. Camera setup is optional when no camera is launched. The public launch/source package is complete; the separately supplied vendor configuration and device calibration remain environment prerequisites.

## Bringup and behavior

After inspecting the clear workcell and your driver setup, the historical entry is:

```sh
ros2 launch jetarm_minimal_control control_bringup.launch.py dry_run:=true start_depth_camera:=true
ros2 run jetarm_minimal_control jetarm_status_check --require-camera --require-actions
ros2 run jetarm_minimal_control jetarm_action_runner go_home
```

`dry_run` prevents this package's preset publication. It does **not** make bringup offline: the launch can start drivers/controllers/cameras, and action/status/nudge commands connect to ROS. If a driver already runs, set `start_driver:=false` and inspect other start flags to avoid duplicate stacks. Real action publication uses explicit `--execute` or a preset server configured with `dry_run:=false`.

Camera defaults are color 640×480 and depth 640×400, with point-cloud generation disabled. Those dimensions do not prove depth/color registration. Status checks establish discovered endpoints and parameters only; they do not prove real servo motion, grasp retention, calibrated geometry or a healthy device.

Historical low-level limitations remain: nudge duration and measured pulse values are not fully validated for physical suitability; action subscriber discovery is not a collision or driver-health check; the software has no force limit or physical emergency stop. Preset values are workcell-specific. Keep robot acceptance separate from offline software validation.

## Publication provenance

The original deployment package declared MIT in `setup.py` and `package.xml`; this archive adds the full MIT text for project-authored material. The 6 implementation modules and 3 launch files retain their original control behavior. Packaging edits replace placeholder device-account metadata, declare omitted launch dependencies and install the README/license/provenance files. The independently authored historical readback guard is included under `integration/` with application notes; the full vendor driver is excluded. No robot was connected or moved during this release process.
