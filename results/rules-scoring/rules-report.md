# PvZ Level 4: blind RULES.md scoring against the sealed source

## Method
- Truth rubric: 50 rules from sealed/src @cbc4c83, each with file:line citations (`rubric.json`, `rubric.md`).
  Tier 1 = visible in the 3 public traces (24 rules), tier 2 = needs more traces or config data (6), tier 3 = needs program logic (20). Weights 1-3, total 118.
  The rubric author saw only sealed source, arm task docs, shim and frozen oracle traces; all submissions were locked (mode 000) while it worked.
- Blinding: `redact.py` removed "Evidence:" clauses, paths, tool names (REA/Ghidra/decompile), function names/addresses, oracle/query and AI-DLC wording, and dropped tool-evidence sections. Rule content was kept. Docs were shuffled across replicates as D01-D10. Mapping held in `operator-only/doc-mapping.json`.
  Residual leak: some content still implies method (e.g. "Park-Miller minstd_rand engine").
- Two independent scorers (gpt-5.6-terra, gpt-5.6-luna) marked each doc x rule correct/partial/wrong/absent. Score = weighted mean with correct=1, partial=0.5, wrong/absent=0, averaged over both scorers.
- rep1-B and rep1-C have no RULES.md (empty submissions, disqualified); not scored.

## Inter-rater agreement
Exact agreement 75.4%, Cohen's kappa 0.617. Most disagreements are partial vs absent (62 of 123) and wrong vs partial (19).
Neither scorer reported contradicted claims outside the rubric.

## Per run (mean of two scorers)

| Run | Doc | All | T1 | T2 | T3 | Terra | Luna | Wrong (avg) | T3 correct (avg) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rep1-R | D08 | 0.411 | 0.589 | 0.288 | 0.240 | 0.343 | 0.479 | 3.0 | 0.5 |
| rep1-A | D05 | 0.426 | 0.607 | 0.346 | 0.240 | 0.419 | 0.432 | 0.0 | 0.0 |
| rep2-R | D02 | 0.424 | 0.625 | 0.231 | 0.245 | 0.403 | 0.445 | 1.5 | 0.5 |
| rep2-A | D06 | 0.428 | 0.638 | 0.231 | 0.240 | 0.424 | 0.432 | 2.0 | 0.0 |
| rep2-B | D01 | 0.447 | 0.647 | 0.308 | 0.255 | 0.462 | 0.432 | 0.5 | 0.0 |
| rep2-C | D07 | 0.460 | 0.612 | 0.385 | 0.306 | 0.453 | 0.466 | 1.0 | 0.5 |
| rep3-R | D03 | 0.407 | 0.621 | 0.269 | 0.199 | 0.394 | 0.419 | 1.5 | 0.0 |
| rep3-A | D10 | 0.411 | 0.616 | 0.308 | 0.204 | 0.390 | 0.432 | 4.0 | 0.0 |
| rep3-B | D04 | 0.377 | 0.580 | 0.192 | 0.194 | 0.331 | 0.424 | 1.0 | 0.0 |
| rep3-C | D09 | 0.413 | 0.580 | 0.404 | 0.224 | 0.449 | 0.377 | 3.0 | 0.5 |

## Per arm (median of valid runs)

| Arm | n | All | T1 | T2 | T3 |
|---|---:|---:|---:|---:|---:|
| R | 3 | 0.411 | 0.621 | 0.269 | 0.240 |
| A | 3 | 0.426 | 0.616 | 0.308 | 0.240 |
| B | 2 | 0.412 | 0.614 | 0.250 | 0.224 |
| C | 2 | 0.436 | 0.596 | 0.394 | 0.265 |

## Findings
- All ten documents score 0.38-0.46. Arm medians differ by at most 0.025, smaller than the spread within R (0.407-0.424) plus scorer disagreement (up to 0.14 on one doc).
- Tier 3 is almost entirely missed: at most 0.5 tier-3 rules marked fully correct per doc, tier-3 scores 0.19-0.31 come from partial credit. No doc recovered the glibc rand() design (R42), pea-shot reseeding (R43), per-zombie engine schedule (R46) or the full rand() consumer order (R47).
- rep2-C (REA + AI-DLC, the run that reported REA-identified minstd_rand) is the top doc overall and on tier 3, and rep2 is the only replicate ordered C > B > A ~ R. rep3-B, which used neither oracle nor REA, is the lowest. This is consistent with "REA helps when actually used", but it rests on one replicate and is within noise.
- The wrong-loss-threshold claim (UserLose 430; the loader never reads it, true threshold x<0) was marked wrong as expected.
- Conclusion matches the mechanical hidden scoring: no measurable arm effect on recovered rules in this setup.

## Limits
- Scorers ran fast (2-3 min) and quotes are often abbreviated; 59% (terra) and 47% (luna) of non-absent quotes match the doc text verbatim. Spot checks show paraphrase, not invention, but per-rule verdicts are coarse.
- Blinding is imperfect: method-revealing rule content survives redaction.
- n = 2-3 per arm.
