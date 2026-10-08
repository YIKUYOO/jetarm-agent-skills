# Third-party boundaries and provenance

The main-branch scripts and workflow descriptions originate from the project's experimental `jetarm_agent_vla` workspace. They implement orchestration, observation capture, simple color/geometry heuristics and task-evidence assessment. Release v0.2.0 also contains separately documented, sanitized historical project code under `legacy/`. All manufacturer source archives, installation images, manuals, screenshots, personal records, raw experiment data and model weights remain excluded.

The original coordinate adapter followed Hiwonder's JetArm Position & Picking / Color Sorting approach. The public version removes the inlined pixel-to-world implementation and imports `pixels_to_world` and `extristric_plane_shift` from the independently installed `sdk.common` on the robot. Its three-argument `pixels_to_world(pixels, K, T)` interface was checked against the local manufacturer ROS2 distribution. Coordinate conventions and calibration remain specific to that SDK and workcell. Verify this adapter on your device before physical use.

External software is not covered by this repository's MIT grant:

- Hiwonder JetArm SDK, kinematics, servo interfaces and vendor configuration, obtained from the manufacturer.
- ROS2 / TROS and D-Robotics camera/runtime packages, installed on the board.
- NumPy, OpenCV, Paramiko, PyYAML and pytest, installed by their package names.

No third-party library is vendored. Refer to each upstream distribution for its license and required notices. Names identify compatible external components and do not imply endorsement.

## Historical archive license boundaries

- `legacy/jetarm-agent` preserves the historical project's ISC choice with its own LICENSE and [provenance record](../legacy/jetarm-agent/PROVENANCE.md). The parent MIT grant does not replace that nested license. Its ROS1 board wrappers import manufacturer interfaces at runtime. The former fixed image uploader and private host defaults were removed; cloud providers and Python libraries remain external dependencies.
- `legacy/jetarm-vla-bridge` contains project-authored capture/data/interface helpers and tests under MIT. [Third-party notes](../legacy/jetarm-vla-bridge/THIRD_PARTY.md) identify ROS1 manufacturer runtime packages, LeRobot, SmolVLA and Python dependencies. No vendor grasping implementation, training data or model weights are redistributed.
- `legacy/rdk-minimal` contains project-authored ROS2 orchestration and command-checking wrappers under MIT. Its [third-party notes](../legacy/rdk-minimal/THIRD_PARTY.md) identify the separately supplied JetArm/TROS runtime.

Local duplicate-code screening and source inspection supported the archive allowlists. These checks are not a legal determination or a complete chain-of-title proof. The available manufacturer source bundles lacked a single license clearly covering every component, so they were excluded rather than relicensed. Original research directories were preserved privately; the release is a sanitized copy.
