# Third-party boundaries and provenance

The released scripts and workflow descriptions originate from the project's experimental `jetarm_agent_vla` workspace. They implement orchestration, observation capture, simple color/geometry heuristics and task-evidence assessment. The public snapshot excludes the legacy prototype repositories, all manufacturer source archives, installation images, manuals, screenshots, personal records and model weights.

The original coordinate adapter followed Hiwonder's JetArm Position & Picking / Color Sorting approach. The public version removes the inlined pixel-to-world implementation and imports `pixels_to_world` and `extristric_plane_shift` from the independently installed `sdk.common` on the robot. Its three-argument `pixels_to_world(pixels, K, T)` interface was checked against the local manufacturer ROS2 distribution. Coordinate conventions and calibration remain specific to that SDK and workcell. Verify this adapter on your device before physical use.

External software is not covered by this repository's MIT grant:

- Hiwonder JetArm SDK, kinematics, servo interfaces and vendor configuration, obtained from the manufacturer.
- ROS2 / TROS and D-Robotics camera/runtime packages, installed on the board.
- NumPy, OpenCV, Paramiko, PyYAML and pytest, installed by their package names.

No third-party library is vendored. Refer to each upstream distribution for its license and required notices. Names identify compatible external components and do not imply endorsement.
