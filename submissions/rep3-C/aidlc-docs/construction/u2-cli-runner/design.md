# U2 CLI Runner Design

## Responsibilities and interface

Approval gate: **Approved as written. Proceed to the next stage.**

The executable accepts exactly two positional arguments: an input scenario JSON path and an output trace JSONL path. It resolves neither path beyond normal Python file handling, parses JSON once, validates the top-level contract, imports U1, and streams compact JSON objects separated by newlines.

## Behavior

1. Validate argument count and print usage to stderr on mismatch.
2. Parse and validate the scenario.
3. Open the destination for text output using UTF-8 and Unix newlines.
4. Serialize every U1 frame with compact separators and deterministic key insertion order.
5. Return zero only after clean close; return non-zero with a concise stderr error otherwise.

## Packaging

`submission/bin/run-scenario` is a small executable Python launcher. It adds the sibling `submission/src` directory to `sys.path` and calls the source entry point. No installation, dependencies, network, or original game files are required.

## Traceability

FR1, FR9, and FR10 map to the launcher/CLI module. NFR1-NFR3 and NFR6 map to deterministic serialization, standard-library-only imports, and end-to-end tests.
