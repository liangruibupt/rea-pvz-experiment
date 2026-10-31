# REA on a native game binary: PvZ Level 4 experiment (results)

This repo holds the protocol, harness code, scorer, scores and reports of one controlled
experiment run on 2026-10-26 to 2026-10-29. The question was whether reverse-engineering
tooling (REA + Ghidra) helps an AI agent rebuild the behaviour of a native program that
it gets only as a stripped binary.

**Short answer: in this setup it did not.** No arm beat the documentation-only arm, on
either the hidden behaviour scenarios or the rule-recovery scoring. The setup also had
weaknesses, listed below, that keep this from being a clean negative result about REA.

## What was tested

- **Target program:** Level 4 of [Xi-Gong/Plants-Vs-Zombies](https://github.com/Xi-Gong/Plants-Vs-Zombies)
  at commit `cbc4c83`, a C++17 / cocos2d-x fan reimplementation. It was built for Linux
  AArch64 and stripped (about 14,000 procedures, game code plus statically linked engine).
  The source was sealed: no agent under test could read it.
- **Task given to every run:** write a headless simulator in standard-library Python,
  called as `run-scenario <scenario.json> <trace.jsonl>`, that reproduces the original
  game's frame-by-frame state (sun, plants, zombies, bullets, suns, lawn mowers, waves)
  for a scripted sequence of clicks. Also write a `RULES.md` with evidence for every rule.
- **Agent:** GPT-5.6 Sol, high reasoning, 600 tool calls, about 180 minutes, no memory or
  project context, no content steering.

| Arm | Gets |
|---|---|
| R | Task text, scenario and trace format docs, 3 public scenarios with oracle traces, 5 calibration scenarios without traces, a public-only scorer |
| A | R + the stripped binary with libs and assets (runnable under Xvfb) + a trace oracle: 30 queries returning the full internal-state trace for any scenario the run submits. No disassemblers or debuggers |
| B | A + REA 6.7.0 / Ghidra 12.1.4 |
| C | B + the AI-DLC workflow with fixed approvals |

3 replicates per arm, 12 runs. The first A/B/C batch was invalid because 9 runs shared
2 oracle slots and got oracle data by timing, not by arm; it was discarded and rerun
with one oracle slot per run, in 3 waves (see `protocol/INVALID-PILOT-ABC.md`).

## Results

### Hidden scenarios (primary metric)

8 hidden scenarios, 4 of them losses, up to 18,000 frames. Score 1.0 = identical trace.

| Arm | rep1 | rep2 | rep3 | Median of valid runs | Completed |
|---|---:|---:|---:|---:|---:|
| R | 0.657 | 0.717 | 0.736 | 0.717 | 3/3 |
| A | 0.713 | 0.680 | 0.678 | 0.680 | 3/3 |
| B | DQ | 0.733 | 0.633 | 0.683 | 2/3 |
| C | DQ | 0.692 | 0.728 | 0.710 | 2/3 |

Reference points: a frozen game scores 0.292, and a trace with all suns, plants,
zombies and bullets erased scores 0.569. DQ = timed out with an empty submission.

Every pairwise arm contrast (A-R, B-A, C-B) flips sign in another replicate. The
preregistered recall-contamination flag fired: R did at least as well as A, so the
model's prior knowledge of this kind of game plus 3 public traces matched what program
access gave.

### Rule recovery (blind `RULES.md` scoring)

50 rules from the sealed source, in three tiers: visible in public traces (24), needs more
traces or config data (6), needs program logic (20). Two independent scorers (GPT-5.6 Terra
and Luna, Cohen's kappa 0.62) graded redacted, shuffled documents.

| Arm | All | Tier 1 | Tier 2 | Tier 3 |
|---|---:|---:|---:|---:|
| R | 0.411 | 0.621 | 0.269 | 0.240 |
| A | 0.426 | 0.616 | 0.308 | 0.240 |
| B | 0.412 | 0.614 | 0.250 | 0.224 |
| C | 0.436 | 0.596 | 0.394 | 0.265 |

No run fully recovered the program-logic rules REA should help with most: the glibc
`rand()` design, the fact that every pea shot reseeds the generator, the per-zombie
random schedule and the `rand()` call order.

### How the REA arms used their tools

| Run | Oracle queries | REA outputs | Minutes |
|---|---:|---:|---:|
| rep1-B / rep2-B / rep3-B | 9 / 22 / 0 | 10 / 16 / 0 | 180 (timeout) / 115 / 5 |
| rep1-C / rep2-C / rep3-C | 9 / 5 / 10 | 21 / yes / 10 | 180 (timeout) / 171 / 55 |

rep3-B used neither tool. rep1-B and rep1-C each stalled for about 2 hours in one long
command. The runs that used REA most (rep2-B, rep2-C) were among the best, but that is
one replicate. B/C runs cost about 500-570 credits each against 70-180 for R/A.

## Why this is not a clean verdict on REA

- The target is a public open-source project in a genre the model knows well.
- A's oracle exposed full internal state, much more than a real black box.
- The trace scorer is lenient: valid submissions are only 0.06-0.17 above an erased-state trace.
- Uptake of the treatment was inconsistent, and there were only 2-3 valid runs per arm.
- The runtime kept no sub-agent transcripts, so the planned transcript audit for reads
  outside each workspace could not be done. Isolation relied on file permissions
  (operator trees mode 000 during runs) and a source audit of submissions.

A draft preregistration for a follow-up that addresses these points is in
[`next-experiment/PREREGISTRATION-DRAFT.md`](next-experiment/PREREGISTRATION-DRAFT.md).

## Repo layout

| Path | Contents |
|---|---|
| `protocol/` | Preregistration, invalid-pilot note, and the exact task, arm and format docs every run received (`arm-inputs/`) |
| `harness/oracle/` | LD_PRELOAD shim: virtual 16 ms clock, controlled entropy, XTest input at frame boundaries, per-frame JSON state trace |
| `harness/oracle-service/` | Oracle daemon with one serialized slot per run, and the `oracle-query` client |
| `harness/build/` | Pinned AArch64 rebuilds of glfw / libuv / libwebsockets / freetype, and a silent FMOD stub |
| `harness/scenarios/` | Scenario generator (bot policy, raw-input replay, byte-identical double-run check) and boot macro |
| `harness/*.py, *.sh` | Run workspace setup, freeze-and-blind, batch scoring |
| `scenarios/` | The 16 scenario inputs (3 public, 5 calibration, 8 hidden) with seeds, bot and replay inputs, and the freeze manifest |
| `evaluator/` | Trace scorer (7 weighted subsystems, nondeterminism check) and gate candidates |
| `tests/` | Unit tests for the generator and scorer: `python3 -m unittest discover -s tests` |
| `submissions/<rep>-<arm>/` | The 12 frozen submissions, unblinded (simulator, `RULES.md`, tests) |
| `results/` | Mechanical report, per-run scores, freeze manifest, blind mapping |
| `results/rules-scoring/` | Rule rubric, redaction script, blinded documents, both scorers' verdicts, report |

## What is not in this repo

- Oracle traces (`trace.jsonl`), the game binary and libraries, the shim build output
  and the symbol table.
- The game's `Resources/` (textures, Spine animations, audio). They carry no open
  licence and are marked study-only by the upstream author.
- The sealed upstream source. The rubric cites it by file and line; get it from the
  upstream repo at `cbc4c83`.

Because traces and the binary are omitted, the scorer cannot be rerun from this repo
alone. Reproducing the scores needs a local build of the upstream commit, the shim and
`harness/scenarios/generate_scenarios.py` to regenerate the traces. The scenario freeze
manifest lists the expected trace hashes.

Harness scripts contain absolute paths from the original machine
(`/home/ubuntu/workspace/...`); adjust them before running elsewhere.

## Licence

Apache-2.0, the same as the upstream code. The upstream game assets are not covered and
not included.
