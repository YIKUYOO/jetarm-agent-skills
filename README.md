# JetArm Agent Skills

Experimental, evidence-oriented JetArm / RDK X5 helpers for a Codex skill workflow: inspect state, capture RGB-D and side views, plan a bounded tabletop action, and evaluate the visible result.

This is a research software snapshot. Release **v0.2.0** adds three separately documented historical software archives; the current RDK X5 helpers and draft plugin retain version **0.1.0**. The main branch contains 13 original task scripts plus one shared SSH/safety helper, four skill definitions, and 20 offline regression tests. No trained VLA policy, autonomous general-purpose grasping system, robot simulator, or manufacturer ROS workspace is included.

## What has been demonstrated

| Capability | Evidence and boundary |
| --- | --- |
| RDK X5 + JetArm control integration | Project records describe ROS2 bringup, servo readback and real motion on 20 May 2026. |
| Red wooden block grasp | One successful grasp-and-lift baseline has before/after photographs in the private project archive. |
| Multi-view observation | RGB-D, local webcam and CSI capture helpers; conservative spatial relation and depth-quality checks. |
| Multiple positions and objects | Exploratory trials include failures. A success rate above 85% has **not** been established. |
| VLA | Interface and evidence collection preparation only; no trained weights or training result are included. |
| Earlier platform prototype | March–April 2026 project records describe a web/cloud language-and-vision demonstration and four supervised sorting rounds. The sanitized ROS1 implementation is archived under `legacy/jetarm-agent`; these records do not establish current RDK multi-position performance. |

The public packaging changes (key-based SSH, explicit execution gate and runtime SDK calibration adapter) have been checked offline. They have **not** been revalidated on a physical robot. Historical device evidence applies to the original experimental snapshot. Raw logs and photographs are intentionally absent because they contain workstation/network context.

## Installation and offline use

Requires Python 3.10+ (tested locally with 3.12), NumPy, OpenCV, Paramiko and PyYAML. PowerShell webcam helpers require Windows. ROS2 Humble/TROS, JetArm manufacturer packages, calibration files and camera drivers must already be installed on the board.

```sh
python -m pip install -r requirements.txt
python scripts/local/jetarm_servo_publish.py --goal 10:200
python scripts/local/jetarm_tabletop_place.py --x 0.18 --y 0.02
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The main branch's motion commands default to a JSON request preview with **no SSH connection and no physical motion**. This preview does not solve IK or prove collision freedom. `jetarm_tabletop_motion.py`, `jetarm_tabletop_place.py`, `jetarm_servo_publish.py` and `jetarm_tabletop_scan.py` require `--execute` to enable physical execution. `--dry-run` remains accepted by the scan script and cannot be combined with `--execute`. Archived entry points have their own behavior: some retain historical live/full-control defaults. Read the archive README before using them.

Offline image analysis:

```sh
python scripts/local/evaluate_local_red_block.py --help
python scripts/local/jetarm_triview_relation.py --csi-image sample.png --output relation.json
```

The red-block lift classifier has pixel thresholds calibrated to the original camera framing; recalibrate them before interpreting a different camera. A relation score is an advisory observation, not a safety-certified interlock or automatic permission to close the gripper.

## Board configuration

Set `JETARM_HOST` and `JETARM_USER` for your own board, or use `--host` and `--username`. Optionally set `JETARM_SSH_KEY` (or `--key-file`) and `JETARM_KNOWN_HOSTS`. Authentication uses SSH keys/agent only. Host keys must be independently verified and already present in your known-hosts file; unknown keys are rejected. No address, password, API credential or personal helper path is bundled. Scanner and observation-cycle child commands receive the same connection settings.

The current adapter expects the operator's board workspace at `~/jetarm_ros2_ws`, the ROS setup at `/opt/ros/humble/setup.bash`, and optional TROS at `/opt/tros/humble/setup.bash`. Adapt these paths to your installed stack. The board's `sdk.common.pixels_to_world(pixels, K, T)` and `extristric_plane_shift` are imported at runtime; they are not redistributed here. The calibration file is read from `~/jetarm_ros2_ws/src/bringup/config/config.yaml`.

Before explicitly enabling motion: verify a clear workcell, one control stack, valid servo readback, current camera evidence, calibration and an available physical stop. Execution also checks that `/ros_robot_controller` is present. Servo values are limited to supported IDs and the numerical 0–1000 range; these checks do not model collisions or the mechanical limits of every setup. Keep all physical experiments supervised.

## Contents

- `scripts/local/`: capture, perception, relation analysis and explicit-motion helpers.
- `skills/`: state sensing, visual observation, task evaluation and tabletop pick workflows.
- `.codex-plugin/plugin.json`: draft discovery metadata. Native installation in a Codex release is not part of the validated acceptance.
- `docs/`: maturity boundaries, provenance and release changes.
- `tests/`: offline guards, synthetic perception and syntax regression checks.
- `legacy/`: independently tested historical ROS1/Web, RGB-D data/interface, and minimal ROS2 wrappers; see below.

Use the skill files directly from a skill-aware agent. Installing the draft plugin depends on your host's supported plugin format.

## Historical software archives in v0.2.0

| Directory | Retained scope | Independent offline tests | License |
| --- | --- | --- | --- |
| [legacy/jetarm-agent](legacy/jetarm-agent) | March–April Jetson/ROS1 Web, LLM/VLM integration, plans, SSH and board adapters | 194 historical + 2 upload-privacy checks = 196 | Nested ISC |
| [legacy/jetarm-vla-bridge](legacy/jetarm-vla-bridge) | RGB-D capture/data format, annotation/conversion scaffolding, HTTP and hold-pose mock | 12 historical + 4 mock API checks = 16 | MIT |
| [legacy/rdk-minimal](legacy/rdk-minimal) | Historical ROS2 status, SDK startup and servo-command wrapper | 8 historical | MIT |

Run each archive's installation and test command from its own directory and environment. The root `python -m pytest -q` intentionally collects only the 20 main-branch tests; CI runs four separate jobs. These counts describe software checks, not robot trials. The archives contain no raw experiment logs, private proposal/report files, photographs, training datasets or model weights. Mock VLA returns a bounded copy of the current state and does not interpret language or perform grasping. Optional training and checkpoint code is unvalidated experimental scaffolding.

Public packaging removed private configuration and the legacy fixed image-upload proxy, made SSH host-key verification strict, and documented external vendor dependencies. These changes have only been checked offline. See the [release changes](docs/CHANGELOG.md) and each component's README for the remaining device and capability limitations.

## License

Original main-branch material and the VLA/minimal wrappers are provided under the [MIT License](LICENSE). The earlier Web/ROS1 archive retains its separate [ISC License](legacy/jetarm-agent/LICENSE). Manufacturer SDKs, ROS, TROS, camera drivers and Python dependencies retain their own licenses and must be obtained separately. See [third-party boundaries](docs/THIRD_PARTY.md). This release makes no claim of software copyright registration.
