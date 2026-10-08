# Release scope and source inventory

Release v0.3.0 provides seven separately documented software components from the JetArm research project. Source, runtime assumptions, dependency declarations, usage instructions, source/provenance notes and the relevant offline tests are included. An archive's presence does not prove it implements the original planned Atlas-based local-SLM system or has passed new robot acceptance.

| Source component | Public location | Scope |
| --- | --- | --- |
| Current `jetarm_agent_vla` helper and skill implementation | Repository root `scripts`, `skills`, plugin metadata | 13 task scripts, shared connection helper, four skills and 20 tests |
| Earlier `jetarm_agent` package | `legacy/jetarm-agent` | Web/CLI, cloud parsing/vision, adapters, board wrappers, selected design/config fixtures and 196 tests |
| `jetarm_vla` and `jetarm_vla_common` | `legacy/jetarm-vla-bridge` | Capture/data schema, transformation/annotation, HTTP/mock interfaces and 16 tests |
| `jetarm_rdkx5_minimal` | `legacy/rdk-minimal` | Status/deployment/SDK wrapper and 8 tests |
| Separate `agent_cli` | `legacy/full-control-cli` | Standalone board-local CLI, three skills, project-only installer and 8 tests |
| `rdk_tools/minimal_ros2` | `legacy/rdk-migration-tools` | Twelve earlier migration scripts, reconstructed environment example and 6 new checks |
| Recovered `jetarm_minimal_control` deployment source | `board/jetarm_minimal_control` | Four entry points, three launch files, presets, isolated authored readback guard and 12 new checks |

The board package was recovered from an ignored deployment staging directory, not regenerated from prose. Its six implementation modules and three launch files retain the recovered source behavior. Source identity is tied to that snapshot; there is no claim that every byte of a currently installed board is identical. Metadata, declared launch dependencies and distribution documentation were updated. Its ROS interfaces and device configuration still require the appropriate externally installed platform.

Excluded material has a specific boundary:

- Manufacturer ROS workspaces, complete patched vendor files, firmware, driver binaries, manuals and installation images are external prerequisites with their own terms. Necessary authored integration logic is supplied independently where identifiable, with location and application notes.
- Third-party reference repositories and the separate experimental `free-code` integration are not dependencies of these seven components. They are not represented as project-authored software achievements.
- Actual API credentials, device addresses, raw camera data, personal records, proposals, closeout documents, scene logs and private calibration records are not public source requirements. Documentation gives configuration variables and dependency interfaces instead.
- Model weights, a trained VLA policy and a large training dataset were not formed or validated in the project evidence; the release does not imply their existence.
- OriginCar is a separate project and has not been copied into this repository. Shared RDK X5 experience does not turn its competition entry into a JetArm result.

Publication establishes inspectable source delivery. It is not software copyright registration, a vendor redistribution license, a hardware safety certificate or evidence that every original research target was completed.
