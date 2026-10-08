# Archived JetArm Web / ROS1 Agent Prototype

This directory archives the project's **March–April 2026 Jetson / ROS1 Melodic prototype**. It is independent of the repository's later RDK X5 / ROS2 skill helpers. The Python project version remains `0.1.0`; the archive packaging date is 2026-10-08.

The retained software implements a web/chat demonstration, constrained natural-language plans, cloud vision integration, an SSH executor, and formal board-adapter experiments. It is provided for source inspection and offline reproduction of **194 original regression tests plus 2 archive privacy checks**. It does not implement an Atlas 200i DK deployment, a trained VLA model, or a portable production robot controller.

## Historical evidence and scope

Private project records describe:

- 2026-03-30: four supervised sorting / grasp-and-place rounds on the then-active ROS1 board (two `color_sortting` and two `object_sortting + /grasp` rounds), with scene reset and operator observation.
- 2026-03-31: a web/cloud demonstration for scene scanning and Chinese vision summary, and a red-block detect/pick/lift/place-near-origin command sequence.
- 2026-04-02: formal fixed-front red-target observation and persisted calibration-profile smoke checks.

These are historical, platform-specific records, not new hardware acceptance of this archive. They do not establish arbitrary-object grasping or a statistical multi-position success rate. The packaging changes below have only been checked offline. Raw logs, credentials, scene images and hardware source distributions are not included.

## Installation and offline tests

Use a separate Python 3.11+ environment (validated with Python 3.12). From **this directory**, not from the parent ROS2 project:

```sh
python -m venv .venv
# Activate this environment using the command for your shell.
python -m pip install -r requirements-dev.txt
python -m pytest -q -p no:cacheprovider
```

The tests load the local `src` tree and use mocked executors, cloud clients and board calls. They do not need a robot, API key or ROS installation. A standalone CI recipe is in `.github/workflows/archive-offline.yml`; when nested in a monorepo, the root workflow must invoke these commands with this directory as its working directory.

For the historical Web interface, install the local Python project and run:

```sh
python -m pip install .
python -m jetarm_demo_agent.web_server --host 127.0.0.1 --port 8000
```

Use the Web/demo entry point for interface exploration. Motion tasks in this entry point remain dry-run unless `--live` or the corresponding explicit configuration enables them. Cloud interpretation requires separately configured API credentials. Camera or diagnostic operations may contact an explicitly configured board and can invoke historical camera recovery; the entire application must not be described as network-free or read-only.

The lower-level `jetarm_agent.agent_cli`, board validation/smoke scripts, `remote/jetarm_agent_bridge/agent_tool_bridge.py` and direct `ros_adapters` functions retain historical operator-level interfaces. Some default to live/full-control and can execute ROS or shell commands. They are archived research tools, not protected Web endpoints. Inspect them before use, keep the workcell supervised and clear, and do not expose them as a public service. No robot is required for the offline tests above.

## Configuration

The demo settings read environment variables prefixed with `JETARM_`, including `JETARM_SSH_HOST`, `JETARM_SSH_USER`, `JETARM_SSH_PASSWORD`, `JETARM_DEEPSEEK_API_KEY` and `JETARM_OPENAI_API_KEY`. All credential values default to unset. The historical account-file loader is retained for compatibility, but no account file is distributed; keep any such file outside the repository and set `JETARM_ACCOUNT_FILE` to its private path.

Vision images default to inline data URLs sent with the request to the configured vision API. The original fixed image-upload proxy has been removed. If your own provider requires a separate uploader, explicitly configure `JETARM_VISION_UPLOAD_URL`; its optional credential is `JETARM_VISION_UPLOAD_API_KEY`, separate from the vision API key. No image proxy is contacted by default.

SSH host keys must already be independently verified in the user's known-hosts file. Unknown keys are rejected in the archived public copy. The shell-runner supports an identity file or explicitly provided password; the demo transport retains its original explicit-password configuration. Do not share credentials, captures or transcripts.

Live board use expects separately installed ROS1 Melodic, Hiwonder JetArm packages, calibration and camera drivers under the operator's `~/jetarm` workspace. Local orchestration and the board runtime can have different Python versions. The bundled profile is a historical workcell reference and must be recalibrated for another scene.

## Retained components

- `src/jetarm_demo_agent`: CLI/Web UI, LLM and vision clients, plans, session state, safety decisions and SSH orchestration.
- `src/jetarm_agent`: schemas, profile registry, adapter/transport, control validation, skill protocol and lower-level tool experiments.
- `remote/`: custom board-side bridges and wrappers around externally installed vendor interfaces.
- `tests/`: the 194 original regression cases, with only sample-address/credential text and strict-host-key expectations adjusted.
- `configs/`: historical profile structure needed by the adapter and tests.
- `docs/`, `doc/`, `openspec/`: only the minimal design/governance fixtures read by the retained tests. Their internal statuses and old evidence paths describe the archived snapshot; absent log paths are historical references, not public evidence files.

## Public packaging changes

No control algorithms or plan semantics were rewritten. Device addresses were removed from defaults and replaced with documentation-only addresses in mocked tests. A provider-specific account-file sentinel and test URL were replaced with `example.invalid`. SSH host-key verification is strict, and the Web server now binds to loopback by default. Two board smoke scripts require explicit host/user in SSH mode. Test expectations track the stricter host-key setting. The vision uploader defaults to direct inline images, with an optional explicitly configured upload endpoint and separate upload credentials.

The unrelated `claude-code-fork` bootstrap installer, npm placeholder project, virtual environments, caches, raw logs, account files, generated package metadata, original proposal/report documents and manufacturer materials are excluded.

## License and provenance

This archive uses the [ISC License](LICENSE), retaining the permissive license label in the legacy project's original npm metadata. It is a separate license boundary from the newer MIT-licensed RDK X5 code. Only project-authored code and documentation are granted here. Manufacturer SDKs, ROS, camera drivers and Python dependencies retain their own licenses. No third-party implementation is vendored; see [PROVENANCE.md](PROVENANCE.md).
