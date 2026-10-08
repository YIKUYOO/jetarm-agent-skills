# Final Agent System Architecture

## Purpose

This document is the long-lived source of truth for the JetArm project's final system target.
All future OpenSpec changes, validation plans, adapter implementations, runtime work, and cloud integration work must align with this document.

## Final Goal

The project goal is not a demo-only command wrapper and not a pure control-stack integration project.
The first-class product goal is a formal JetArm embodied agent system that can talk with people in natural language, understand intent, plan tasks, and complete complex work safely.

The final product must:

- interact with humans through natural language dialogue
- understand user intent instead of relying on fixed command keywords
- clarify ambiguous goals and maintain multi-turn task context
- convert natural-language requests into structured task goals, constraints, and execution steps
- reason over a world state instead of raw ROS topics
- automatically plan and execute multi-step tasks
- adjust execution according to perception feedback and runtime state
- run safe board-side execution through constrained adapters
- use cloud cognition and optional VLA assistance without moving low-level control out of the board safety boundary

The final system must be able to explain:

- what it is trying to do
- what it sees
- what it believes the user asked for
- what it can execute safely
- what failed and why
- which assets are frozen and which are still provisional

## System Architecture

### North-Star Capability

The north-star capability is:

- a human gives a natural-language task
- the system understands the intent and constraints
- the system produces a safe execution plan
- the board executes the plan against the current environment
- the system reports progress, asks for clarification when needed, and explains failures

All lower-level engineering work exists to support this capability.

### Cloud Responsibilities

Cloud services are responsible for:

- natural-language dialogue management
- intent parsing and task structuring
- long-horizon task understanding
- constrained plan generation
- structured behavior-tree or execution-plan output
- optional VLA assistance for future non-rigid or contact-rich tasks
- maintaining high-level semantic context, but not issuing raw servo commands

Cloud services must never directly control:

- bus-servo topics
- low-level stop topics
- raw ROS motion primitives

### Board Responsibilities

The board is the only place allowed to:

- interface with official control nodes and launch files
- read cameras and official perception topics
- maintain the operational world state
- enforce workcell constraints and safety checks
- execute skills and runtime logic
- ground high-level plans into board-safe actions
- reject unsafe or out-of-contract cloud outputs

The board remains the hard execution boundary even after cloud cognition is added.

### Formal Runtime Layers

The long-term runtime is organized as:

1. `official control and perception baseline`
2. `board adapter layer`
3. `skill layer`
4. `world state layer`
5. `board runtime / behavior tree layer`
6. `cloud cognition, dialogue, planning, and optional VLA layer`

The current repository is still below layer 2 completion. Official baseline and validation assets must be frozen before the adapter layer is allowed to grow.

## Mainline And Legacy Boundary

### Formal Mainline

The formal mainline is everything that exists to support the long-term board and cloud agent architecture.

Current formal mainline roots are:

- `src/jetarm_agent`
- `docs/architecture`
- `docs/governance`
- `docs/baseline`
- `openspec/changes/*` created after governance freeze

### Legacy / Demo

The following remain legacy reference assets:

- `src/jetarm_demo_agent`
- `remote/jetarm_executor`
- the validated 2026-03-31 meeting-demo slice built on top of those packages
- demo-oriented research notes and plans that were written for the group-meeting version

Legacy assets may be read, mined for evidence, or used as operational reference. They must not silently become the formal mainline.

## Phase Map

### Phase 0

- baseline environment audit
- official capability inventory
- control-stack hierarchy clarification

### Phase 1

- full validation of the official board-side control and grasp chain
- phase-1 asset freeze matrix
- board-side baseline assets classified into frozen vs not frozen

### Phase 2

- formal board adapter implementation
- calibration and config assets stabilized
- detection output and pick-place request/result contracts frozen

### Phase 3

- skill layer and world state layer
- behavior-tree runtime takes over task execution

### Phase 4

- cloud planner integration
- constrained cloud objects such as `TaskIntent`, `ExecutionPlan`, and `BehaviorTreePlan`

### Phase 5

- end-to-end system hardening
- repeatability, recovery, and demonstration freeze

## Current Project Stage

The project is currently in:

- `Phase 2 formal board adapter implementation`

Current priorities are:

- continue the formal board adapter against the frozen active-board official `pick_place foundation`
- stabilize Phase 2 request/result contracts, calibration/config boundaries, and board-backed execution paths
- keep meeting-demo assets explicitly isolated from the formal runtime and cloud protocol
- use governance documents and the registry as the only source of truth for what is formal vs demo-only

The project is explicitly not yet in:

- behavior-tree runtime implementation
- cloud cognition implementation
- VLA execution integration

## Frozen And Not Frozen Rules

At the architecture level:

- the cloud-edge split is frozen
- the board execution boundary is frozen
- the mainline vs legacy boundary is frozen
- the requirement that all future work use the asset registry is frozen

At the capability level:

- raw low-level control may be validated yet still remain adapter-internal
- one successful pick-place round does not freeze the official pick-place foundation
- any motion-capable asset that lacks repeatability or direct observation evidence remains not frozen

## Long-Term Source Of Truth Rule

If future work conflicts with this architecture document:

1. update this document first, or
2. record an explicit conflict and why the architecture is changing

No implementation change is allowed to silently drift away from this document.
