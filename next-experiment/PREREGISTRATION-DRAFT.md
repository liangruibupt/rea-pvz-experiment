# Draft preregistration: REA uplift on an unseen native program

Status: **DRAFT, not frozen.** Items marked _(open)_ need a decision before freezing.
When frozen, this file gets a SHA-256 recorded in the run ledger, and any change after
the first run starts is logged as a deviation.

## 1. Why a new experiment

The PvZ Level 4 experiment (this repo) found no arm effect, but four design problems
make that result uninformative about REA itself:

| Problem in PvZ run | Fix in this design |
|---|---|
| Public target in a well-known genre; docs-only arm R matched the binary arm A | Fresh private target written for this experiment, with rules that cannot be guessed (section 3) |
| A's oracle exposed full internal state | A gets observable I/O only (section 4) |
| Lenient scorer: erased-state trace scored 0.569 | Strict scorer with gated reference points (section 6) |
| B/C runs skipped REA or stalled ~2 h in one command | REA snapshot pre-built by the harness, per-command time limit, uptake reported and per-protocol analysis (sections 4-5) |
| 9 runs shared 2 oracle slots | Oracle is a cheap local CLI, one process per query, no shared queue |
| No retained transcripts | Transcripts exported at each completion event (section 7) |

## 2. Hypotheses

- **H1 (primary):** B (binary + I/O oracle + REA) scores higher than A (binary + I/O
  oracle) on the hidden suite under the strict scorer.
- **H2:** B recovers more tier-3 rules (rules that need program logic) than A in blind
  `RULES.md` scoring.
- **H3 (validity check, must hold for H1/H2 to be interpretable):** R (docs only) stays
  near the floor: R's hidden score above the frozen-program baseline is below 0.5 x A's.

## 3. Target program

- A new program written for this experiment by an operator-side agent and never published
  before the analysis is complete. Proposed form: a deterministic, headless tick-based
  simulation in C (about 2,000-4,000 lines of game logic) that reads a scenario file and
  prints the observable state each tick. Statically linked against at least one ordinary
  library (for example zlib or a small JSON parser) so that the game code is a minority
  of the procedures, as in a real binary.
- Built host-native with `gcc -O2 -s` on AArch64. No cross toolchain, no linker-script
  changes.
- Designed so that hidden behaviour depends on logic no trace can show quickly. At least
  12 of the planned rules must be tier 3, including:
  - a non-standard PRNG (custom xorshift/LCG variant with unusual constants) that is
    reseeded on specific game events;
  - fixed-point arithmetic with an unusual rounding rule;
  - thresholds and constants that appear in no data file;
  - at least two rare branches (for example an overflow wrap, a tie-break order) that
    only the hidden scenarios trigger;
  - one deliberate quirk that an agent cannot predict from genre knowledge.
- The rule rubric (rule list, tiers, weights, source citations) is written from the
  source **before any run starts**, then frozen and hashed with this file.
- _(open)_ Domain of the simulation: a game-like simulation keeps continuity with PvZ;
  a non-game domain (for example a queueing or inventory simulator) reduces genre prior
  further.

## 4. Arms

| Arm | Gets |
|---|---|
| R | Task, I/O format docs, 3 public scenarios with oracle outputs, 5 calibration scenarios without outputs, public-only scorer |
| A | R + stripped binary (runnable) + oracle CLI that runs the binary on any submitted scenario and returns its printed output only. Budget 200 queries, each under 2 s. No disassemblers, decompilers, debuggers or tracers |
| B | A + REA / Ghidra, with a REA analysis snapshot of the binary built by the harness before the run starts (identical bytes for every B run) |

- A and B can already run the binary themselves; the oracle exists so query counts can
  be logged and capped. Because the binary is headless and fast, there is no shared queue.
- _(open)_ Whether to keep arm C (B + AI-DLC). Dropping it saves about 5 x 550 credits
  and keeps the primary B-A contrast at full replication. The PvZ run showed no C effect.

## 5. Runs

- Agent: GPT-5.6 Sol, reasoning high, standalone `kirocrew` template (not
  `kirocrew-worker`), no memory, lessons or project context. Tasks forbid
  `work_brief` / `work_report` and forbid spawning sub-agents.
- Limits: 600 tool calls, 180 minutes. Every shell command is told to run under a
  10-minute `timeout`; the task text states this as a rule.
- Replicates: **5 per arm** (15 runs with R/A/B). With 5 paired replicates, "B > A in
  all 5" has probability 1/32 under no effect.
- Scheduling: all arms of one replicate run in the same wave, so host load is balanced
  across arms. Check host memory before each wave.
- Inputs frozen per run directory (per-file SHA-256, read-only), with `diff -qr` across
  run directories to prove only the arm-specific files differ.
- Interventions: only I1 (shared infrastructure), applied identically to every affected
  run, with no content steering. Each one is logged.

## 6. Scoring

### Mechanical (primary)

- Hidden suite: 12 scenarios, written with the source so that each tier-3 rule is
  exercised by at least 2 scenarios, plus long runs (10,000+ ticks).
- Strict scorer: per tick and per field exact match on integers, and exact match on
  fixed-point values. Scenario score = mean over subsystems of (matched ticks before
  first divergence / total ticks). One divergence in RNG state then costs the rest of
  the scenario, which is the point.
- Gates that must pass before launch, or the scorer is revised and the gates rerun:
  - identity copy = 1.000;
  - frozen program (initial state repeated) <= 0.10;
  - erased-state candidate <= 0.15;
  - a simulator written by the operator that knows all tier-1 rules but uses a wrong
    PRNG <= 0.40 on hidden.
- Each submission runs twice; differing output disqualifies it for nondeterminism.

### Rule recovery (secondary)

- Same procedure as PvZ: redaction script, shuffled labels, two independent scorers
  (GPT-5.6 Terra and Luna), verdicts correct / partial / wrong / absent.
- New: every non-absent verdict must quote the document verbatim. Quotes are checked
  automatically; a scorer whose verbatim rate is under 90% is rerun once on its
  failing items.

## 7. Analysis plan

- **Completion:** reported per arm. Empty, refused or timed-out-empty submissions are
  disqualified, not scored 0, and excluded from score comparisons.
- **H1 decision rule:** supported if the mean paired B-A hidden difference across
  replicates has a 95% hierarchical bootstrap CI above 0 (resampling replicates, then
  scenarios) **and** B > A in at least 4 of 5 replicates. Disqualified pairs are
  dropped from the contrast and reported.
- **H2 decision rule:** the same rule applied to tier-3 rule scores.
- **H3:** if it fails, H1/H2 are reported as observations only, flagged as
  contamination, with no causal REA claim.
- **Intention-to-treat** is primary. **Per-protocol** (B runs with at least one REA
  query after the snapshot, A runs with at least one oracle query) is secondary.
- **Transcript audit:** each run's transcript is exported with `spawn_status` as soon as
  its completion event arrives. Reads of operator paths, other run directories,
  `/proc/<pid>/fd`, the network or the source disqualify the run. A run whose transcript
  could not be exported is flagged and reported both ways.
- No metric, scenario or threshold changes after the first run starts. Any change is a
  deviation, reported with its reason.

## 8. Isolation

- Source, rubric, hidden scenarios and operator tools stay mode 000 while runs are active.
- All runs execute as the same Linux user, so permissions are not a hard boundary; the
  transcript audit is the second line.
- The parent session (operator) does not read decompiled pseudocode, and does not edit
  run workspaces after launch.

## 9. Budget estimate

From PvZ costs: R about 85, A about 150, B about 550 credits per run. 5 replicates of
R/A/B is about 3,900 credits; adding C is about 2,750 more. Wall time is about 3 hours
per wave, 5 waves, so 15 hours or more.

## 10. Open decisions before freezing

1. Keep or drop arm C.
2. Game-like or non-game simulation domain for the target.
3. 5 replicates (about 15 hours) or 3 (about 9 hours, weaker decision rule).
4. Whether to publish the target source after analysis, so the result can be checked.
