# Build and Test Results

## Commands and status

- Unit tests: `python3 -m unittest discover -s submission/tests -p 'test_*.py'` — passed.
- Official public scorer: `python3 harness/score.py --suite-root harness/suite --candidate-command submission/bin/run-scenario --candidate-cwd . --out harness-out/public-v3.json` — passed all three scenarios, deterministic.
- Synthetic performance check: a no-action scenario requested through frame 18,000 reached its valid loss stop after 10,883 frames in 0.202 seconds.

## Results

- Tests: 6 passed, 0 failed, 0 skipped.
- Public aggregate score: **0.9659914819776372**.
- Public scenario scores: idle 0.9554, sun economy 0.9670, single lane 0.9756.
- Missing public frames: 0.
- Deterministic public scenarios: 3/3.

## Target verification matrix

| Target | Expected | Actual | Evidence | Verdict |
|---|---:|---:|---|---|
| NFR1 deterministic | byte-identical repeats | all public repeats identical | `harness-out/public-v3.json` | Met |
| NFR2 runtime | under 180 seconds | 0.202 seconds for valid 10,883-frame loss run | benchmark command output | Met |
| NFR3 dependencies | Python stdlib only | stdlib imports only | source review and tests | Met |
| NFR6 trace completeness | no missing frames | 0 public missing frames | `harness-out/public-v3.json` | Met |

## Readiness and gaps

The executable, source, tests, rules, and AI-DLC artifacts are complete. The main fidelity gaps are exact sky-sun horizontal motion, some long-wave timing/population adaptation, and clean loss-overlay timing. These are documented rather than hidden.

Approval gate: **Approved as written. Proceed to the next stage.**
