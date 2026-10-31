# U3 Trace CLI Design

## Interface
`submission/bin/run-scenario SCENARIO OUT_TRACE` resolves its own source directory, imports the simulator, validates input, and writes one compact JSON object plus newline per frame.

## Serialization
Keys follow the documented schema. Floats are rounded to three decimal places before JSON encoding. IDs increase by first appearance and are deterministic but are not used for matching.

## Performance
The implementation streams frames directly to the destination file and keeps only current game state. Complexity is linear in frames times live entities; Level 4 entity counts remain small.

## Error handling
Wrong argument count, invalid JSON, invalid schema fields, or an unwritable destination produce a non-zero exit and no claimed successful trace.

## Traceability
FR5, FR6, NFR1, NFR2, NFR3, NFR4.
