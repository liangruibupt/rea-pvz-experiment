# Arm C: Arm B plus the AI-DLC workflow

You have everything Arm B has (the program, the trace oracle with the same 30-query
budget, REA / Ghidra, see `rea/REA.md`) and you must follow the AI-DLC workflow in
`aidlc/` (pinned awslabs/aidlc-workflows v2.9.0, `core/aidlc-common`). Start from
`aidlc/aidlc-common/conductor.md`.

Run the Inception and Construction phases and keep their artifacts under
`submission/aidlc-docs/`: requirements, unit decomposition, a design per unit, and a test
plan written before implementation, then code and tests. Finish with a short Operations
hand-off note.

Human approval gates: there is no human in the loop. Every gate is approved with the
fixed text in `aidlc/APPROVALS.md`. Treat that text as the approval and continue; no
other human input will arrive.
