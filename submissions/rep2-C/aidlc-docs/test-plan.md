# Test Plan

Approval: Approved as written. Proceed to the next stage.

## Unit tests
- Scenario validation accepts the documented examples and rejects wrong schema, level, frame duration, coordinates, cards, and collection modes.
- Card tests cover startup readiness, successful placement, cooldown completion, repeated placement, and occupied-cell refund.
- Entity tests cover zombie movement, visibility, eating, HP steps, shield-first projectile damage, death cleanup, and mower activation.
- Sun tests cover fixed falling cadence, produced cadence, click scheduling, 50-sun credit, and expiry.
- Serialization tests cover contiguous frame numbers, all required keys, list shapes, and deterministic byte identity.

## Integration tests
- Run each public scenario twice and compare SHA-256 values.
- Validate public traces with `harness/score.py` using the exact candidate command.
- Run a synthetic 18,000-frame scenario and verify wall time remains under 180 seconds.

## Acceptance targets
- All offline unit tests pass.
- The harness scores all public scenarios without disqualification.
- The executable has no non-standard Python dependency and never invokes the oracle or original program.

## Known test limitation
The public suite is small and hidden seeds can expose unrecovered random transformations; document these approximations rather than introducing trace-derived lookup tables.
