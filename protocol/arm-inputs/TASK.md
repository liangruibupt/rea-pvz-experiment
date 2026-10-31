# Task (identical for every arm)

The program under study is a Linux build of a small Plants-vs-Zombies-style lawn defence
game (cocos2d-x, AArch64). Only its **Level 4** matters here: a 5-row by 9-column lawn,
three plant cards (`sunflower`, `peashooter`, `wallnut`), falling sun, card cooldowns,
zombies arriving in waves, and one lawn mower per row.

Write a new, **headless, deterministic simulator** of Level 4 that, given a scenario
(seeds plus a schedule of player actions), produces the same frame-by-frame state trace as
the original program does when the same scenario is played on it.

- Scenario input format: `docs/SCENARIO_FORMAT.md`
- Trace output format: `docs/TRACE_SCHEMA.md`
- Worked examples (scenario plus the original program's trace): `public/`
- Extra scenarios without traces, for your own development: `calibration/`

What else you may use is listed in `ARM.md`; that file is the only one that differs
between arms.

## Deliverables

- `submission/bin/run-scenario`: executable, `run-scenario <scenario.json> <out-trace.jsonl>`.
  It must finish each scenario in under 180 seconds and must be deterministic.
- `submission/src/`: all source, in **Python 3.12, standard library only**.
- `submission/RULES.md`: the game rules and constants you established (costs, cooldowns,
  HP, damage, speeds, timers, spawn and wave rules, sun, mowers, win/loss), each with the
  evidence you relied on (a public trace frame, an experiment, or an analysis step).
- `submission/tests/`: your own tests (optional, must run offline).

## How you are scored

A hidden set of scenarios you have never seen (other seeds, other action schedules, runs
up to 18,000 frames, including losses) is run through your `run-scenario` twice;
non-identical output disqualifies that scenario. Each trace is compared with the original
program's trace every 10 frames, allowing at most two frames of alignment, across seven
subsystems: global economy/wave/end state 20%, cards/cooldowns 10%, plants 15%, zombies
25%, bullets 10%, suns 10%, mowers 10%. Positions and timers have narrow tolerances;
discrete state, costs and HP steps must match exactly. A missing frame scores zero.

Run `python3 harness/score.py --suite-root harness/suite --candidate-command submission/bin/run-scenario --candidate-cwd . --out harness-out/public.json`
to score yourself on the public examples (same scorer as the hidden evaluation).

## Forbidden (any of these disqualifies the submission)

- Calling, wrapping, linking, embedding or copying the original program, its libraries
  or its resources in the submission, at build time or at run time.
- Embedding oracle traces (or data derived from them frame by frame) in the submission
  as lookup tables. Constants and rules you measured are fine.
- Network access. Fetching or recalling the source code, symbols or developer
  documentation of the original program or of the project it is derived from.
- Reading or writing anything outside this workspace, except the tools `ARM.md` names.
- Calling `work_brief` or `work_report`.

There is no human in the loop. Do not ask questions; record assumptions in `RULES.md`.
