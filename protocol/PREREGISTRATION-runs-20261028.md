# PvZ Level 4 REA experiment: preregistration (runs-20261028)

Target: Xi-Gong/Plants-Vs-Zombies @ cbc4c83, operator-built for AArch64, stripped ELF
SHA-256 04c83db7...cc424. Sealed truth: sealed/src (not visible to arms).

## Arms (x3 replicates, 12 runs)

- R: TASK, docs (scenario format, trace schema), 3 public scenario+trace, 5 calibration
  scenarios (no traces), public-only scorer.
- A: R + stripped ELF/libs/Resources (may run under Xvfb) + trace oracle service
  (30 accepted queries, end_frame <= 12000, <= 40 actions, hidden seeds rejected).
  No disassemblers/decompilers/debuggers/tracers.
- B: A + REA 6.7.0 / Ghidra 12.1.4 static analysis.
- C: B + AI-DLC v2.9.0 workflow with fixed approvals.

Agent: gpt-5.6-sol, reasoning high, standalone `kirocrew` template, max 600 tool calls,
~180 min guidance, no memory/lessons/project context, no content steering. Interventions
logged as I1 (shared infra) only.

Oracle access decision (user, 2026-10-28): A gets the full internal-state trace oracle.
Consequence: A's gain over R includes direct visibility of internal state; report it as
such, not as pure black-box I/O.

## Isolation

Shim + symbol table held in daemon memfds; operator/, sealed/, smoke/ and the earlier
source-derived web prototype chmod 000 for the whole run. Same-uid isolation is not a
hard boundary: transcripts are audited for reads of other runs, operator paths,
/proc/<pid>/fd, network and upstream source. Violations disqualify the run.

## Evaluation (after all 12 return)

Freeze submissions (per-file SHA-256, chmod a-w), blind per-replicate W/X/Y/Z, audit
(no ELF/trace embedding, stdlib only), then operator/evaluator/score.py on all 16
scenarios; hidden (8) is the primary metric, run twice for determinism. Report completion
rate separately; empty/timeout/refused submissions are disqualified, not scored low.
Paired contrasts A-R, B-A, C-B per replicate with bootstrap CI. Recall-contamination flag
if R >= 0.5 x A on hidden (score above the static-game baseline 0.313). Then two
independent blind scorers rate RULES.md against sealed source.
