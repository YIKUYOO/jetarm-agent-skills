# Archive provenance and third-party boundary

This snapshot is a sanitized archive of the project's `jetarm_agent` prototype, maintained separately from the later RDK X5 branch. The original Python metadata names `jetarm-demo-agent` version `0.1.0`. An unrelated, empty npm metadata file contained `license: ISC`; this archive preserves that license choice with an explicit ISC license for the project-authored material. The npm file itself is excluded because it has no functional JavaScript application and its test command is only a placeholder.

The retained source consists of project schemas, orchestration, wrappers, observation/action protocols, cloud API clients, UI markup, tests and selected original design records. No files are taken from the manufacturer's source or tutorial directories. Historical records are summarized in README rather than republishing private logs.

The board wrappers import the following manufacturer interfaces at runtime, among others: `jetarm_sdk.bus_servo_control`, `hiwonder_interfaces`, `vision_utils` (including `pixels_to_world` and `extristric_plane_shift`), `color_tracker`, and installed action/kinematics scripts. Those algorithms and packages are **not** copied into or licensed by this archive. ROS1, OpenCV on the board, camera firmware and calibration are supplied separately by the operator.

The locally available ROS1 manufacturer distribution was screened against the retained source: none of its 150 Python files shared a continuous window of 12 normalized nonempty noncomment lines with the archive's `src` or `remote` files. This is a duplicate-code screening result, not a legal determination or proof that no conceptual similarity exists. Runtime imports and integration conventions retain their upstream origins.

Python dependencies are installed separately and keep their upstream licenses. The historical `claude-code-fork` bootstrap script is omitted; no third-party agent source or installer is included. API/provider names identify supported interfaces and imply no endorsement.

Public edits are limited to removing local endpoint information, explicit SSH-target configuration, strict host-key verification, loopback Web binding, direct inline image transport instead of the historical fixed upload proxy, readable licensing and archive documentation. An optional explicitly configured uploader uses a separate credential. Tests with sample secrets use visibly artificial values. The original experimental command behavior remains visible, including low-level live/full-control interfaces; see README before any board use.
