## Upstream References

- `docs/architecture/final_agent_system_architecture.md`
- `docs/governance/asset_governance_and_freeze_rules.md`
- `docs/governance/project_asset_registry.yaml`
- `doc/开发任务拆解_v_1.md`

## Why

The repository already has multiple completed baseline and validation changes, but it still lacks a project-wide source of truth that freezes the final system architecture, asset-governance rules, and the complete Phase 1 official validation picture. Without that layer, future changes can still drift independently and re-interpret the same board assets differently.

We need one governance cutover change that:

- creates the final architecture and governance source documents
- classifies all relevant official and legacy assets under a unified registry
- consolidates Phase 1 validation into one frozen matrix with explicit frozen vs not-frozen conclusions

## What Changes

- Add long-term project-governing documents for final architecture and asset freeze rules.
- Add a canonical project asset registry with unified status classification.
- Add a full Phase 1 validation matrix and dated validation report.
- Add governance enforcement tests for the registry and for post-cutover OpenSpec change structure.

## Asset Impact

- Introduces the project-wide canonical asset classification system.
- Re-classifies existing baseline, legacy, and future-planned assets under explicit governance states.
- Freezes the architecture and governance documents themselves as governing sources.
- Marks the official `pick_place` foundation as verified but not frozen.

## Freeze Delta

- Newly frozen:
  - project architecture boundary
  - project asset governance rules
  - canonical asset registry structure
  - phase1 validation matrix as a maintained project asset
- Still not frozen:
  - official `pick_place` workflow foundation
  - direct `set_pose_target` service usage as a stable basis
  - advanced coordinate/planning example launches not yet directly exercised
