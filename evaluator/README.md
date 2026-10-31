# PVZ REA scenario suite and evaluator

## Scope

The suite targets Level 4 of `Xi-Gong/Plants-Vs-Zombies` at commit `cbc4c83dee9407dc3d82ca869ebf13b450bab382`. The oracle always runs the immutable stripped AArch64 ELF with SHA-256 `04c83db7035365985e2d9f5c00adfb401cc97ede12e3c2172532345d415cc424`.

- **public (3):** examples whose scenario and oracle trace may be given to every arm.
- **calibration (5):** development scenarios used while implementing; expected traces may be queried under a fixed budget.
- **hidden (8):** held-out seeds, plans, cooldown pressure, shield-heavy waves and long-run drift. Oracle traces and raw replays stay operator-only.

Every scenario has a semantic `scenario.json`, an operator bot source `bot.txt`, a raw-input `replay.txt`, an oracle `trace.jsonl`, and `meta.json`. Materialization first runs the high-level bot, captures all post-level mouse events, then runs the raw replay. With `--verify`, generation fails unless both traces are byte-identical.

## Generate

```bash
python3 /home/ubuntu/workspace/rea-pvz-experiment/operator/scenarios/generate_scenarios.py \
  --materialize --verify --jobs 4
```

The semantic contract uses zero-based rows/columns and the card names `sunflower`, `peashooter`, and `wallnut`. Frames are 16 ms. Actions that occur during cooldown or target an occupied cell are intentional.

## Candidate interface

A submission provides a deterministic headless scenario runner:

```text
run-scenario <scenario.json> <output-trace.jsonl>
```

Each output line is one JSON object with a strictly increasing integer `f`. It should use the oracle trace schema: global state (`sun`, `ts`, wave fields and end state), cards, plants, zombies, bullets, suns and cars. Object IDs are not scored; objects are matched by semantic identity, lane and position.

## Score

```bash
python3 /home/ubuntu/workspace/rea-pvz-experiment/operator/evaluator/score.py \
  --suite-root /home/ubuntu/workspace/rea-pvz-experiment/operator/scenario-suite \
  --candidate-command ./run-scenario \
  --candidate-cwd /absolute/submission/path \
  --out /absolute/result.json
```

The evaluator runs each candidate scenario twice and disqualifies nondeterministic output. It samples every 10 frames, permits at most two frames of alignment, and reports both an overall score and subsystem scores.

| Subsystem | Weight |
|---|---:|
| Global economy/wave/end state | 20% |
| Cards/cooldowns | 10% |
| Plants/HP/placement | 15% |
| Zombies/movement/shields/eating | 25% |
| Bullets | 10% |
| Suns | 10% |
| Mowers | 10% |

Position, timer and progress fields use narrow documented tolerances; discrete state, costs, HP steps and lifecycle flags remain exact. A missing frame receives zero for every subsystem. Hidden results are reported separately from public/calibration results and must be the release gate.
