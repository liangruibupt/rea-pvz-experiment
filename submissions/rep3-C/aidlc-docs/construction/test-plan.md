# Construction Test Plan

## Strategy

Approval gate: **Approved as written. Proceed to the next stage.** Tests use Python's standard-library `unittest` and are written before implementation. The design favors requirement-driven tests plus public-trace regression sampling.

## Unit tests

- Validate splitmix64 against independently calculated known draws.
- Validate startup card cooldown interpolation and transition frames.
- Validate action timing, costs, placement, cooldown reset, occupied-cell rejection, and affordability.
- Validate plant/grid serialization and fixed health values.
- Validate bullet speed, hit damage, and cleanup lifecycle.
- Validate zombie movement/eating damage and mower transitions.
- Validate sun motion, lifetime, and scripted collection.
- Validate scenario input errors and exact frame count.

Run: `python3 -m unittest discover -s submission/tests -p 'test_*.py'`.

## Integration and regression tests

- Run each public scenario through `submission/bin/run-scenario`.
- Compare selected public frames for global state, card state, plants, and startup entities.
- Run the same scenario twice and compare SHA-256 hashes.
- Run `python3 harness/score.py --suite-root harness/suite --candidate-command submission/bin/run-scenario --candidate-cwd . --out harness-out/public.json`.

## Quality targets

- All local tests pass.
- Identical input produces byte-identical JSONL.
- The public scorer reports all scenarios completed, with no missing frames or timeout.
- A synthetic 18,000-frame run completes under 180 seconds.

## Evidence recording

Final command results and public score are recorded in `submission/aidlc-docs/construction/build-and-test.md`; remaining fidelity limitations are carried into `submission/aidlc-docs/operations-hand-off.md` and `submission/RULES.md`.
