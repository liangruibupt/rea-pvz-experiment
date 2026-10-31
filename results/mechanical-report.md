# PvZ Level 4 REA experiment: mechanical results (hidden suite)

Target: Xi-Gong/Plants-Vs-Zombies @ cbc4c83, stripped AArch64 ELF. Agent: gpt-5.6-sol,
high reasoning. R runs from runs-20261028; A/B/C runs from runs-20261028-abc (rerun after
the invalid A/B/C pilot). All 12 submissions frozen (SHA-256 trees, read-only), blinded per
replicate, then scored by operator/evaluator/score.py on 16 scenarios, each run twice.
Hidden (8 scenarios, 4 of them losses, up to 18,000 frames) is the primary metric.

## Hidden score per run

| Arm | rep1 | rep2 | rep3 | Median, valid runs | Valid runs |
|---|---:|---:|---:|---:|---:|
| R docs only | 0.657 | 0.717 | 0.736 | 0.717 | 3/3 |
| A + program + trace oracle | 0.713 | 0.680 | 0.678 | 0.680 | 3/3 |
| B + REA/Ghidra | DQ (timeout, empty) | 0.733 | 0.633 | 0.683 | 2/3 |
| C + AI-DLC | DQ (timeout, empty) | 0.692 | 0.728 | 0.710 | 2/3 |

Scorer reference points on hidden: identity 1.000; a trace with sun, plants, zombies and
bullets erased 0.569; a frozen game 0.292. Every valid submission lies between 0.63
and 0.74, so they are only 0.06-0.17 above an obviously broken candidate.

## Paired contrasts (mean over the 8 hidden scenarios, 95% bootstrap CI)

| Replicate | A-R | B-A | C-B |
|---|---|---|---|
| rep1 | +5.6 pp [+1.7, +9.4] | B disqualified | both disqualified |
| rep2 | -3.7 pp [-5.7, -1.4] | +5.3 pp [+2.6, +7.6] | -4.1 pp [-7.4, -0.7] |
| rep3 | -5.9 pp [-9.8, -2.3] | -4.5 pp [-8.8, -0.5] | +9.5 pp [+6.0, +12.9] |

No contrast keeps its sign across replicates. Same-condition spread (R: 0.657-0.736) is
as large as every between-arm difference.

## Tool uptake (as treated)

| Run | Oracle queries | REA outputs | Minutes |
|---|---:|---:|---:|
| rep1-A / rep2-A / rep3-A | 8 / 5 / 6 | n/a | 34 / 20 / 16 |
| rep1-B / rep2-B / rep3-B | 9 / 22 / 0 | 10 / 16 / 0 | 180 (timeout) / 115 / 5 (after I1 resume) |
| rep1-C / rep2-C / rep3-C | 9 / 5 / 10 | 21 / yes / 10 | 180 (timeout) / 171 / 55 |

rep3-B used neither the oracle nor REA, so in practice it was an R run. Intention-to-treat
is reported above; as-treated, the only B run that actually used REA (rep2-B, 0.733)
is the second-best submission, but n = 1.

## Preregistered judgements

- Recall-contamination flag: **triggered strongly**. R reaches 0.717 against A's 0.680; above the
  frozen-game baseline that is R 0.425 vs A 0.388, i.e. R >= A, far past the 0.5 x A
  threshold. The model already knows enough about this kind of game, or reads enough from
  three public traces, that program access adds nothing measurable here.
- Black-box uplift (A-R): not shown. REA uplift (B-A): not shown. AI-DLC uplift (C-B): not shown.
- Completion: R 3/3, A 3/3, B 2/3, C 2/3. Both failures were REA arms that stalled in a
  single long command for about 2 hours before the 180-minute limit.

## Integrity and limits

- Audit: every valid submission has `bin/run-scenario`, standard-library imports only,
  largest file 38 KB, no reference to the original program, oracle, traces or other
  workspaces in source (flagged strings were usage text, test-only `subprocess`, and paths
  embedded in a stray `__pycache__`).
- The runtime retained no subagent transcripts, so the planned transcript audit of reads
  outside each workspace could not be done; isolation rests on permissions (operator trees
  mode 000 during all runs) and the source audit.
- I1 interventions: rep3-B resumed once after a 20-second zero-work turn end.
- Oracle-access design (full internal-state trace) means A's information was stronger than a
  real black box; even so it did not beat R.
- The scorer's tolerance is generous (erased-state candidate 0.569); a stricter metric might
  separate arms more, but would be a post-hoc change and is not applied here.
