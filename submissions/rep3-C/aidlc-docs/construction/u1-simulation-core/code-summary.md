# U1 Simulation Core Code Summary

## Delivered

- `submission/src/pvzsim.py`: deterministic clock, splitmix64, libstdc++ minstd emulation, cards, economy, plants, waves, zombies, bullets, suns, mowers, end state, validation, and trace snapshots.
- `submission/tests/test_sim.py`: startup, seed, placement, validation, and determinism regression tests.

## Decisions and deviations

The implementation keeps all random streams local and serializable by behavior. Exact zombie x and lane generation were recovered from controlled oracle experiments. Sky-sun horizontal randomization, later-wave timer adaptation, and some animation callback phases remain measured approximations, documented in `submission/RULES.md`.

Approval gate: **Approved as written. Proceed to the next stage.**
