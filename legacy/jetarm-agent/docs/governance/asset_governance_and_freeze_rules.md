# Asset Governance And Freeze Rules

## Purpose

This document defines the long-term governance rules for all project assets.
It is not a phase-specific note. It applies to validation work, adapter work, runtime work, cloud work, refactors, and future architecture changes.

## Canonical Sources

The project has four governance-level sources of truth:

1. `docs/architecture/final_agent_system_architecture.md`
2. `docs/governance/asset_governance_and_freeze_rules.md`
3. `docs/governance/project_asset_registry.yaml`
4. `doc/开发任务拆解_v_1.md`

The registry file is the canonical machine-readable truth.
Human-readable summaries may derive from it, but they do not override it.
The development breakdown document is the canonical phase and OpenSpec sequencing guide.

## Asset Classes

All project assets must be classified.
This includes:

- services
- topics
- launch files
- scripts
- workflows
- configs
- runtime modules
- data structures
- cloud objects
- documents

## Status Classes

Every asset must have exactly one status:

- `verified_frozen`
  - verified with sufficient evidence
  - safe to use as a stable implementation basis
- `verified_not_frozen`
  - verified in some form
  - still missing repeatability, observation, or boundary evidence
  - must not be silently treated as stable
- `documented_not_verified`
  - supported by official documents or repository inspection
  - not yet validated on the active board/runtime
- `legacy_reference`
  - kept only as reference from demo or historical work
  - not allowed to silently become formal mainline dependency
- `deferred`
  - intentionally postponed and out of the current stage

## Encapsulation Levels

Every technical asset must also declare how it may be used:

- `mainline_wrapper`
  - acceptable as a formal mainline foundation
- `adapter_internal_only`
  - may be used only inside the board adapter boundary
- `legacy_reference_only`
  - may be read for evidence, but not used as a mainline dependency
- `deferred`
  - not allowed in the current implementation stage
- `governing_source`
  - only for source-of-truth governance documents

## Evidence Types

Allowed evidence categories are:

- `official_doc`
- `repo_static`
- `board_readonly`
- `board_control_plane`
- `board_motion`
- `board_repeatability`
- `operator_visual`

An asset is not frozen just because one evidence type exists.
The freeze gate must explain what evidence is still missing.

## Freeze Rules

### General Rule

An asset may become `verified_frozen` only when its current stage requires it and the required evidence is present.

### Motion Rule

For motion-capable assets:

- board control-plane success is not enough
- one successful run is not enough
- repeatability and, when relevant, direct operator observation are required before freezing

### Adapter Rule

Raw board primitives may still become `verified_frozen`, but remain `adapter_internal_only`.
Frozen does not mean “public.”

### Workflow Rule

A workflow such as `pick_place` remains `verified_not_frozen` until:

- enter / execute / exit semantics are clear
- failure modes are known
- repeated supervised runs are successful

## Change Governance Rule

All new OpenSpec changes created after the governance freeze must include:

- `Upstream References`
- `Asset Impact`
- `Freeze Delta`

And they must reference:

- `docs/architecture/final_agent_system_architecture.md`
- `docs/governance/asset_governance_and_freeze_rules.md`
- `docs/governance/project_asset_registry.yaml`
- `doc/开发任务拆解_v_1.md`

## Conflict Handling

If a planned implementation conflicts with the current governance or architecture documents:

1. update the governing documents first, or
2. record an explicit conflict and why the asset state is changing

Code, tests, or changes must not silently redefine asset state.

## Historical Exemptions

Changes created before the governance freeze are historical artifacts.
They do not need to be rewritten retroactively, but they also do not override the new governance system.

## Current Governance Cutover

The governance cutover date is:

- `2026-03-29`

All changes created after this cutover must follow these rules by default.
