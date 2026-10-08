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
