## Upstream References

- `docs/architecture/final_agent_system_architecture.md`
- `docs/governance/asset_governance_and_freeze_rules.md`
- `docs/governance/project_asset_registry.yaml`
- `doc/开发任务拆解_v_1.md`

## Context

The repository already has point solutions for:

- baseline board audit
- low-level control classification
- control-stack hierarchy
- supervised validation preparation
- one live board session

Those assets are useful, but they are not yet governed by a single long-lived source of truth. The next risk is not implementation difficulty; it is asset drift. Different future changes could reinterpret board assets, legacy references, and freeze state inconsistently.

## Goals / Non-Goals

**Goals:**

- freeze the final architecture and governance rules as project-level documents
- create a canonical asset registry with explicit status and encapsulation rules
- consolidate Phase 1 validation into one complete matrix
- add lightweight automated enforcement for post-cutover OpenSpec changes

**Non-Goals:**

- implement the formal board adapter
- add new intelligence features
- re-run every non-Phase-1 official example on hardware
- rewrite all historical changes

## Decisions

1. **Make the registry canonical.**
   Human-readable docs are required, but the registry is the machine-readable source of truth.

2. **Separate status from encapsulation.**
   An asset may be fully verified yet still remain adapter-internal.

3. **Treat Phase 1 completion as a classified matrix, not a binary pass/fail.**
   Some assets can freeze now, others can remain verified but not frozen, and many non-essential official workflows can remain documented but not verified.

4. **Only enforce governance forward.**
   Historical changes are exempt; all post-cutover changes must carry the new required sections.

## Asset Impact

- Governing documents become first-class frozen assets.
- Existing baseline docs become subordinate to the registry and architecture docs.
- Legacy demo assets are explicitly demoted to reference-only status.
- Future cloud and runtime objects are registered now as deferred assets so they stop living only in chat context.

## Freeze Delta

- Frozen:
  - architecture source of truth
  - governance source of truth
  - registry schema and status taxonomy
  - phase1 validation matrix
- Not frozen:
  - official pick-place workflow foundation
  - direct pose-target solver usage
  - several phase1-adjacent official workflows not yet exercised directly
