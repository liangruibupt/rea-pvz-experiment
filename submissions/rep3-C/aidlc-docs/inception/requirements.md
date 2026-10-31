# Requirements Analysis

## Intent

Create an independent, deterministic, headless Python 3.12 simulator for Level 4 whose JSONL state traces approximate the supplied AArch64 game's traces closely enough for frame-sampled comparison.

Approval gate: **Approved as written. Proceed to the next stage.** No additional human input is available; unknowns are assumptions to validate from public traces, calibration oracle experiments, or REA.

## Functional requirements

- **FR1 Scenario ingestion.** Validate and load schema-1, level-4 scenarios containing seeds, frame timing, an end frame, collection policy, and scheduled plant actions.
- **FR2 Frame simulation.** Emit one state object for every frame from zero through the scenario stop condition, with fixed 16 ms updates and deterministic ordering.
- **FR3 Economy and cards.** Reproduce starting sun, plant costs, card readiness, cooldown overlays, affordability/enabled state, cursor-held state, placement acceptance, and sun collection.
- **FR4 Plants.** Reproduce sunflower, peashooter, and wallnut placement, grid identity, health, production, targeting, and attack timing.
- **FR5 Zombies and waves.** Reproduce wave timing, seeded spawn count/type/lane/position, hidden startup delay, movement, eating, shields, death, and win conditions.
- **FR6 Projectiles.** Reproduce pea creation, movement, collision, damage, used state, and removal.
- **FR7 Suns.** Reproduce seeded sky-sun positions, fall motion, sunflower-produced suns, enabled lifetime, click collection, and removal.
- **FR8 Mowers.** Reproduce mower initialization, row trigger, movement, zombie kills, lifecycle, and exhausted-row loss behavior.
- **FR9 Trace serialization.** Emit the exact fields and numeric conventions required by `docs/TRACE_SCHEMA.md`; object IDs may be implementation-local because they are not scored.
- **FR10 Run command.** Provide executable `submission/bin/run-scenario <scenario.json> <out-trace.jsonl>`.

## Non-functional requirements

- **NFR1 Determinism.** Two runs for identical input must produce byte-identical output.
- **NFR2 Performance.** Every scenario of at most 18,000 frames must complete in less than 180 seconds.
- **NFR3 Runtime constraints.** Python 3.12 standard library only; no network and no original binary, library, or resource use at build or runtime.
- **NFR4 Independence.** The implementation may encode measured constants and general rules but no embedded frame-by-frame oracle data.
- **NFR5 Maintainability.** Rules, state transitions, and deterministic random sources must be separated enough to test independently.
- **NFR6 Trace completeness.** No requested frame may be omitted before the stop condition.

## Constraints and assumptions

- The supplied public traces and allowed oracle/REA tools are the only behavioral evidence.
- Scenario actions model their mouse-event expansion exactly as specified; card selection takes effect on action frame + 4 and placement on action frame + 15 in observed traces.
- The simulator targets scoring fidelity rather than rendering or menu behavior.
- Unknown randomization details will use deterministic approximations tied to both supplied seeds and will be documented in `submission/RULES.md`.

## Out of scope

- Levels other than Level 4, graphics, audio, menus, save data, arbitrary mouse input, and reuse of the original executable or assets.
- Exact internal object IDs, because the scorer explicitly excludes them.

## Acceptance

- The command is executable and writes valid JSONL.
- Offline tests pass.
- Public harness scoring completes, is deterministic, and is recorded in the hand-off.
