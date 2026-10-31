# Operations Hand-off

Run `submission/bin/run-scenario <scenario.json> <out-trace.jsonl>` from the workspace. It needs Python 3.12 and no packages, services, network, original executable, or original resources.

Verify with `python3 -m unittest discover -s submission/tests -p 'test_*.py'`, then the scorer command in `submission/aidlc-docs/construction/build-and-test.md`. The latest public aggregate is 0.9659914819776372 with deterministic output and no missing frames.

Known gaps: sky-sun x/arc randomization, later-wave adaptive timing/counts, some plant animation emission phases, and exact loss overlay timing. `submission/RULES.md` identifies each approximation and its evidence.
