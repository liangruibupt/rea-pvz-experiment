# Unit Decomposition

## Approved decomposition

Approval gate: **Approved as written. Proceed to the next stage.** The design uses small embedded units with an acyclic dependency graph.

| Unit ID | Directory | Kind | Responsibility | Complexity |
|---|---|---|---|---|
| U1 | `u1-simulation-core` | library | Scenario model, deterministic frame clock, entities, combat, waves, economy, suns, mowers, and trace snapshots | XL |
| U2 | `u2-cli-runner` | packaging | Argument validation, simulator invocation, JSONL streaming, executable entry point, and failure codes | S |

## Boundaries

### U1 simulation-core

Owns all game-domain state and behavior. It accepts an already parsed scenario mapping and yields schema-conformant frame dictionaries. It does not read the original program or public traces at runtime.

### U2 cli-runner

Owns filesystem I/O and the external command contract. It imports U1 but contains no game rules.

## Dependency DAG

```yaml
units:
  - name: simulation-core
    kind: library
    depends_on: []
  - name: cli-runner
    kind: packaging
    depends_on: [simulation-core]
```

U2 depends on U1 through the `run_scenario()` iterator. No reverse dependency exists.

## Requirement allocation

- U1: FR1-FR9, NFR1-NFR6.
- U2: FR1, FR9, FR10, NFR1-NFR3, NFR6.
- Cross-unit tests verify that U2 serializes every U1 frame without mutation or omission.

## Delivery plan

One Bolt, meaning one build pass ending in runnable software, implements U1 first and U2 second because U2's only dependency is U1. Definition of Done: unit tests pass, the executable runs all public scenarios, repeated output hashes match, and the public scorer completes.
