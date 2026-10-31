# Unit Decomposition

Approval: Approved as written. Proceed to the next stage.

| Unit ID | Directory | Kind | Responsibility | Depends on |
|---|---|---|---|---|
| U1 | `u1-scenario-model` | spec | Validate scenario input and normalize scripted actions. | none |
| U2 | `u2-simulation-core` | library | Own deterministic clocks, entities, rules, interactions, and entropy. | U1 |
| U3 | `u3-trace-cli` | service | Drive the frame loop and serialize schema-compliant JSONL through the executable entry point. | U1, U2 |

## Dependency DAG
```yaml
units:
  - name: scenario-model
    kind: spec
    depends_on: []
  - name: simulation-core
    kind: library
    depends_on: [scenario-model]
  - name: trace-cli
    kind: service
    depends_on: [scenario-model, simulation-core]
```

## Boundaries
U1 owns trust-boundary validation. U2 owns all mutable game state but no file I/O. U3 owns paths, streaming output, process exit status, and command-line diagnostics.

## Traceability
- U1: FR1, NFR3
- U2: FR2, FR3, FR4, NFR1, NFR5
- U3: FR5, FR6, NFR2, NFR3, NFR4
