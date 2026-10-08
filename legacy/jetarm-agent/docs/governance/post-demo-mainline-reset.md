# Post-Demo Mainline Reset

## Purpose

This document is the formal reset point after the 2026-03-31 meeting demo.
Its job is to tell later implementers what remains demo-only, what is already formal and frozen, and what the formal mainline is allowed to do next.

## Current Formal State

- current formal stage: `Phase 2`
- `Phase 1`: complete
- `Phase 2 allowed`: `Yes`
- active-board official `pick_place foundation`: `verified_frozen`
- `positioning_clamp`: excluded from the formal active-board foundation

The meeting demo does not reopen `Phase 1`, and it does not redefine the formal runtime or cloud boundary.

## Demo Assets Retained After The Meeting

The following meeting-demo assets remain available for demonstrations and regression reference:

- `src/jetarm_demo_agent`
- `remote/jetarm_executor`
- `logs/2026-03-31-cloud-planned-demo-web-agent-validation.md`

The retained demo slice includes:

- normal chat replies such as identity / capability answers
- `观察周围环境都有什么`
- `抓起面前的红色木块并举起来，再放下`

These are retained as demo-layer capabilities only.
They must not be treated as a frozen formal runtime, formal cloud-board protocol, or formal Phase 3+ behavior contract.

## Formal Inputs Already Frozen For Phase 2

The following are already safe to use as formal Phase 2 inputs:

- `docs/baseline/phase1_exit_gate.md`
- `docs/interfaces/skill_contract_v1.md`
- active-board official `pick_place foundation`
- `Phase2BoardAdapter` core slice and board CLI transport as `verified_not_frozen` implementation assets

This means the formal mainline may continue Phase 2 adapter work, transport hardening, config/calibration stabilization, and board-backed integration.

## Next Allowed Mainline Work

The next formal mainline work should stay inside `Phase 2` and focus on:

- expanding the formal board adapter against the frozen foundation
- promoting current `verified_not_frozen` Phase 2 implementation assets through stronger board-backed validation
- stabilizing formal request/result contracts and calibration/config assets

The next formal mainline work should not focus on:

- new meeting-demo capabilities
- formal runtime / behavior-tree implementation
- formal cloud planner or cloud-board protocol design
- using demo-layer orchestration as the default implementation path for the mainline

## Rule For Future Changes

If a future change wants to build on meeting-demo assets, it must explicitly declare one of the following:

1. the change is demo maintenance only, or
2. the change is formally promoting a demo asset into mainline status through governance and validation

No future implementation may silently treat demo-layer code or prompts as formal Phase 2+ source of truth.
