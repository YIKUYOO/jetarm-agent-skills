# 0.3.0 recovered board package and source inventory — 2026-10-08

- Added the recovered `jetarm_minimal_control` ROS2 package: four entry points, three launch files, authored validation/service wrappers and attributed vendor posture parameters. The deployment source behavior is retained; account metadata and omitted launch dependency declarations are corrected.
- Added the separately authored board-local full-control CLI and its three skills, and the twelve earlier RDK migration/diagnostic scripts. The CLI's private provider endpoint and third-party automatic installer are removed; the replacement installer keeps existing installations intact.
- Preserved an isolated authored unsigned-readback helper with integration notes instead of redistributing the patched manufacturer driver. Added reconstructed environment setup and explicit external SDK/camera/configuration dependencies.
- Added three independent CI jobs: full-control CLI 8 checks (7 historical plus 1 public configuration check), migration tools 6 new checks, board package 12 new checks (10 preset/action and 2 readback checks), plus Python/Bash syntax validation. The four earlier suites remain separate and unchanged.
- Documented the seven-component source scope and exclusions. Raw full-control behavior, ROS-connected dry-run commands and historical hardware limitations remain explicit. No ROS build, hardware motion, training acceptance or software copyright registration is claimed by these offline checks.

# 0.2.0 experimental archive expansion — 2026-10-08

- Added three sanitized project archives: the Jetson/ROS1 Web agent, RGB-D data/VLA-interface bridge, and minimal RDK X5 wrapper. The main helper implementation and draft plugin version remain 0.1.0.
- Preserved the Web agent's nested ISC license; the main branch and VLA/minimal wrappers use MIT. Manufacturer implementations, models, private proposals/reports, credentials and raw workcell data are excluded.
- Removed private device defaults and the historical fixed image-upload proxy. Optional image upload uses an explicitly configured endpoint and separate credential. Required SSH host-key verification and loopback server defaults are documented.
- Added independent CI jobs: main branch 20 tests; archived agent 194 historical plus 2 privacy checks; VLA bridge 12 historical plus 4 mock API checks; minimal wrapper 8 historical checks. Root pytest collection is restricted to the main tests.
- Documented live/full-control legacy interfaces, default-position fallback and stop-command limitations, missing model/training evidence, and external ROS/vendor dependencies. No physical robot or training acceptance is implied by this archive release.

# 0.1.0 public research snapshot — 2026-10-08

- Packaged 13 experimental helpers and four skill workflows from the May 2026 RDK X5 branch.
- Added shared explicit SSH settings, key authentication and rejection of unknown host keys.
- Removed default credentials, device addresses, personal paths, raw experiments and private evidence.
- Changed four motion entry points to offline preview by default, with explicit `--execute` gating.
- Propagated connection settings through scanner and no-motion observation-cycle child processes.
- Added a driver-node check and numerical pulse/duration validation; bounded the place IK wait.
- Replaced the inlined manufacturer coordinate transform with runtime SDK calls.
- Added offline tests and CI. Public packaging has not been physically revalidated.

Historical outcome: a single red-block lift was documented on the RDK setup. Multi-position reliability, general-object grasping and VLA training remain unproven.
