# Operations Hand-off

## Run
```sh
submission/bin/run-scenario scenario.json out-trace.jsonl
```
The executable requires Python 3.12 and only the standard library. It opens no network connection and does not call the original program or oracle.

## Validate
```sh
python3 -m unittest discover -s submission/tests -v
python3 harness/score.py --suite-root harness/suite --candidate-command submission/bin/run-scenario --candidate-cwd . --out harness-out/public.json
```

## Operational characteristics
Trace generation streams JSONL and uses memory proportional to live game entities, not total frames. Repeated runs are byte-deterministic. Invalid scenarios fail before a successful trace is claimed.

## Current evidence
The offline suite passes. The official public harness score is recorded in `harness-out/public.json`. Calibration results were used only to establish rules and constants; no oracle traces or original resources are part of the submission.

## Known risk
Hidden seeds may differ in exact random spawn positions, subtype selection, sun target positions, and callback phase. These are documented deterministic approximations in `submission/RULES.md`.
