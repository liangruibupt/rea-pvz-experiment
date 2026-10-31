# Invalid pilot: A/B/C in runs-20261028

All nine A/B/C runs (rep1-3 x A/B/C) are INVALID and are not scored.

Cause (infrastructure, not agent behaviour): the trace oracle service ran 2 shared slots
for 9 concurrent runs at ~3 min per query. Queueing reached 6-12 minutes within 18
minutes and kept growing; only 10 queries were accepted in total. rep3-A finished at
12 min with 0 oracle traces. Oracle access therefore depended on arrival order and
patience, not on the arm, so condition comparisons would be confounded.

Action: at 02:41 UTC all still-running A/B/C runs were steered to STOP; all eight
confirmed "STOPPED" (rep3-A had already ended). The service was stopped and 30 queued
requests were marked `.cancelled`. Their workspaces are kept as-is for audit.

Valid and kept: rep1-R, rep2-R, rep3-R (never used the oracle; inputs identical to the
other runs). Public scores 0.937 / 0.942 / 0.953.

Fix for the rerun: one serialized oracle slot per run (no cross-run queueing), A/B/C run
in waves of three, fresh workspaces from the same frozen inputs.
