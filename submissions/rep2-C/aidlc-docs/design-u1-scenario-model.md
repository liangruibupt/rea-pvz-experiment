# U1 Scenario Model Design

## Inputs and outputs
Input is one JSON object from an explicit caller-provided path. Output is a normalized immutable scenario representation used by the simulator.

## Rules
- Require `schema=1`, `level=4`, `frame_ms=16`, a non-negative integer `end_frame`, integer seeds, a supported collection object, and a list of plant actions.
- Normalize actions into frame-indexed events while preserving source order for equal frames.
- Reject malformed card indices, card names, rows, and columns with a concise stderr diagnostic and non-zero exit.
- Ignore informational keys named by the scenario contract.

## Failure behavior
No partial trace is considered successful. Validation happens before opening the output file.

## Traceability
FR1, FR6, NFR1, NFR3.
