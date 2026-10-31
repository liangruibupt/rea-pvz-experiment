# U2 CLI Runner Code Summary

## Delivered

- `submission/src/cli.py`: argument handling, UTF-8 JSON parsing, compact deterministic JSONL streaming, and errors.
- `submission/bin/run-scenario`: executable Python launcher that imports only submission source.

## Verification

The official public harness invoked the executable twice per scenario and reported deterministic output for all three public scenarios. No installation, network access, external package, or original-game runtime dependency is used.

Approval gate: **Approved as written. Proceed to the next stage.**
