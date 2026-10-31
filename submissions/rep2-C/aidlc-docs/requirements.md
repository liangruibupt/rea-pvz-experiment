# Requirements Analysis

## Intent
Build a clean-room, headless simulator for Level 4 that converts a documented scenario into a deterministic frame-by-frame JSONL trace matching the observed program.

## Functional requirements
- **FR1** Parse schema-1 Level 4 scenarios and reject unsupported schema, level, frame duration, actions, or collection modes.
- **FR2** Simulate every frame from frame 0 through `end_frame`, stopping 60 frames after a decided result when earlier.
- **FR3** Model card readiness, affordability, selection, placement, occupied-cell rejection, cooldowns, and refunds.
- **FR4** Model plants, zombie waves, zombie movement/eating/damage/death, projectiles, suns, and lawn mowers.
- **FR5** Emit every field and collection required by `docs/TRACE_SCHEMA.md` in deterministic JSONL.
- **FR6** Provide the executable contract `submission/bin/run-scenario <scenario.json> <out-trace.jsonl>`.

## Non-functional requirements
- **NFR1** Identical input must produce byte-identical output.
- **NFR2** An 18,000-frame run must finish within 180 seconds.
- **NFR3** Runtime code uses Python 3.12 standard library only and no network access.
- **NFR4** The submission must not call, embed, or copy the original program, libraries, resources, or oracle traces.
- **NFR5** Constants must be centralized and evidence documented in `submission/RULES.md`.

## Constraints
The task statement, scenario schema, trace schema, public traces, calibration oracle, and REA evidence are authoritative. Oracle use is capped at 30 queries. The implementation must be clean-room and self-contained.

## Assumptions
- Floating-point values are rounded to three decimals at trace serialization.
- Where exact random seeding was not recovered, a documented deterministic approximation is preferable to seed-specific lookup data.
- Fixed approval text applies: Approved as written. Proceed to the next stage.

## Out of scope
Menus, levels other than Level 4, rendering, audio, real mouse input, and original executable/resource integration.

## Open questions resolved by fixed approval
No additional input. Use best judgement, record assumptions, and proceed.
