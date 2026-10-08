# Archived JetArm board-local full-control CLI

This is a separate historical Jetson / ROS1 experiment, not the Web/ROS1 package in `../jetarm-agent`. It provides an OpenAI-compatible chat client, board-local raw shell/Python/ROS tools, transcript records, a REPL and three authored skills. Version `0.1.0` and the historical control semantics are retained. It is an experimental operator tool with unrestricted execution; the current repository's `--execute` guard does not apply to it.

## Offline inspection and tests

From this directory, using Python 3.12:

```sh
python -m pip install -r requirements-offline.txt
python -m pytest -q -p no:cacheprovider
python agent_cli/jetarm_full_control_agent.py --help
```

The seven historical tests exercise tool enumeration, a benign local subprocess, transcript redaction, skill storage and mocked chat dispatch. One additional release test checks that no provider endpoint is configured by default. No test contacts an API, ROS, camera, Jetson or robot. Python 3.6 was the original target; this packaging has not been rerun under the original Jetson runtime.

The standalone CLI uses only the Python standard library. Robot tools require separately installed ROS1 Melodic and the Hiwonder JetArm workspace at `~/jetarm`, including `rospy`, `hiwonder_interfaces`, `jetarm_sdk`, camera drivers, NumPy and OpenCV. Those libraries and robot algorithms are not included here.

## Installation and configuration

`agent_cli/bootstrap_jetson.sh` installs only this project's CLI and skills into `JETARM_AGENT_ROOT` (default `~/.jetarm_agent`). The public installer refuses an existing installation and no longer clones third-party coding agents. Set a new root to install alongside an existing setup. The installer itself has not been run on Jetson during release validation.

```sh
export JETARM_AGENT_ROOT="$HOME/.jetarm_agent_archive"
bash agent_cli/bootstrap_jetson.sh
source "$JETARM_AGENT_ROOT/env.sh"
jetarm-agent --help
```

For an optional cloud chat provider, configure `JETARM_LLM_MODEL`, `JETARM_LLM_BASE_URL` and `JETARM_LLM_API_KEY` yourself. The public copy leaves the endpoint unset; no account file, API key or private URL is shipped. A local `secrets.env` is never release material. Only configure a provider to which you intend to transmit prompts, tool descriptions and results.

## Operational boundary

Raw `shell`, `python_script`, ROS tools and chat-selected calls may execute immediately. `servo_debug`, home and gripper commands can move the robot without another confirmation. Skill text and model output are not hardware interlocks. `stop_all` is a best-effort process cleanup, not a physical emergency stop. Historical numeric/coordinate assumptions are workcell-specific and have not been revalidated. Transcript redaction covers selected key names, not arbitrary secrets echoed by shell commands; keep transcripts private. Do not run this archive as a public service.

`agent_cli/skills/` retains three historical authored workflow descriptions and their manifests. Their instructions describe the original experiment, not new acceptance or a trained grasping capability.

## Provenance and release changes

The CLI, tests and skills are project-authored wrappers and workflow material. They are released under the repository MIT license; external ROS, vendor SDKs, cloud services and Python software keep their own terms. No third-party agent code, model or vendor implementation is distributed. The former `free-code` integration patch is a separate unvalidated integration experiment, not a dependency of this standalone CLI or the seven published components.

Public changes remove the private API endpoint, replace the original installer with a project-only non-overwriting installer, add the release check and explain runtime boundaries. Command behavior is otherwise retained. Neither historical robot records nor offline tests certify this sanitized copy on hardware.
