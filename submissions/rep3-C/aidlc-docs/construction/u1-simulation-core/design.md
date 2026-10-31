# U1 Simulation Core Design

## Responsibilities and interfaces

Approval gate: **Approved as written. Proceed to the next stage.**

`run_scenario(scenario)` is a deterministic iterator of frame dictionaries. A `Game` aggregate owns the frame counter, economy, wave controller, cards, plants, zombies, bullets, suns, mowers, pending input events, and seeded random state.

## Entities

- `Card`: tag, cost, initial recharge, post-use recharge, ready/enabled state, overlay percentage.
- `Plant`: kind, grid column/row, health, and kind-specific timer.
- `Zombie`: kind, lane, position, health/shields, visibility, speed, eat/death state, and timers.
- `Bullet`: lane, position, used flag, and cleanup timer.
- `Sun`: position, source, motion phase, enabled state, lifetime, and collection state.
- `Mower`: lane, tag, state, live flag, position, and trigger/exhaustion state.
- `WaveController`: start/dead flags, timer, released-wave count, and pending spawn schedule.

## State transitions

1. Expand scheduled player actions into card-select and lawn-release events.
2. At each frame, process input effects, timers, producers, bullets, zombies, mowers, wave state, and sun collection in a fixed order inferred from traces.
3. Round only serialized coordinates/timers to three decimals; retain internal floating-point values.
4. Emit the end-of-frame snapshot.
5. Stop at `end_frame` or 60 frames after an end result.

Placement succeeds only when the selected card is ready/enabled, the target cell is empty, and the player has already paid the cost at selection. Failed lawn placement clears the held card without starting cooldown; observed unaffordable/cooldown card presses do not select.

## Determinism and randomization

A local splitmix64 implementation exactly follows the scenario specification. Any secondary pseudo-random stream is local to the `Game` object, never uses wall-clock time, and consumes draws in a stable order. Object containers preserve insertion order.

## Error handling

Reject malformed JSON, unsupported schema/level/frame duration, invalid action coordinates/cards, or unwritable output with a non-zero exit. Do not emit partial success claims.

## Traceability

FR2-FR9 map to the simulator module and its tests. NFR1 maps to repeat-hash tests; NFR2 maps to the public harness timing; NFR3/NFR4 are enforced by imports and runtime architecture.
