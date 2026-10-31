# Level 4 rules and evidence

This simulator is a clean-room state-machine implementation based only on the supplied traces and black-box oracle runs. It does not load or call the original game.

## Clock and initialization

- One frame is exactly 0.016 seconds. Evidence: `docs/SCENARIO_FORMAT.md` and the 0.480-position decrement per frame for a speed-30 zombie in `public-01-idle`, frames 1139-1141.
- The player starts with 10,000 sun and game speed 1.0. Evidence: frame 0 in every public trace and all oracle experiments.
- Lawn mowers are created in row order at frames 33, 39, 45, 51, and 58. Each starts at x=455, `live=0`, `st=1`, and tag -1. Evidence: `public-01-idle`, frames 32-63.

## Cards and planting

| Card | Cost | HP | Cooldown |
|---|---:|---:|---:|
| sunflower | 50 | 300 | 7.5 seconds / 469 trace frames |
| peashooter | 100 | 300 | 7.5 seconds / 469 trace frames |
| wallnut | 50 | 3000 | 30 seconds / 1875 trace frames |

Evidence: selection changes in `public-03-single-lane` at frames 64, 524, 1044, and 1944; plant creation at frames 75, 535, 1055, and 1955; cooldown-ready transitions at frames 544/1004/1524/3830; initial plant HP values in the same trace.

- Sun is charged when the card is picked up, at action frame F+4. A valid plant appears and the cooldown begins at F+15. Evidence: all public planting actions.
- Plant trace fields intentionally follow the program's reversed names: `r` is column and `c` is row. Evidence: supplied trace schema and all public placements.
- Occupied and out-of-grid cells reject placement. This is treated as a failed placement without starting cooldown. This is an explicit assumption; the supplied public examples contain only successful placements.

## Wave state

- The initial wave timer starts at frame 64. The warning state changes at frame 1133 and wave 1 is released at frame 1139. Evidence: all public traces and seed probes.
- Measured later release centers are approximately frames 3195, 5220, and 8014. The first two inter-wave waits are about 32 seconds and the next is about 45 seconds. Evidence: `public-02-sun-economy`, `public-03-single-lane`, the `cal-02-wall-attrition` oracle experiment, and the 12,000-frame idle-loss experiment.
- Wave 1 is one common zombie in the top lane. Later observed waves contain 3-5 zombies. The simulator uses a deterministic seed-derived 3-5 count and measured lane-coverage patterns. Evidence: the same four traces/experiments. Exact later-wave random draw order remains inferred.
- Observed equipment is 600 cone HP and 1200 bucket HP over 200 body HP. Evidence: `public-03-single-lane` wave 2; wall-attrition wave 3; idle-loss wave 4.

## Zombies and eating

- Lane centers are y = 130 + 138*row. Evidence: every zombie in the supplied traces.
- Walking speed is 30 design units/s, or 0.480/frame. A zombie becomes displayed near x=1710. Evidence: `public-01-idle` frames 1139 onward and all appearance transitions.
- A zombie begins eating when its center reaches approximately 79 units right of a plant center. Plant centers are x = 631 + 122*column. Evidence: wallnuts in the wall-attrition experiment begin being eaten near x=1319.6 for column 5.
- Bites remove 100 plant HP. Attack periods vary by zombie; the implementation uses a deterministic 1.0-1.6 second approximation. Evidence: plant HP steps in `public-02-sun-economy`, `public-03-single-lane`, and wall-attrition.
- A zero-HP plant remains in the trace for about 251 frames before removal. Evidence: `public-02-sun-economy` frames 3212-3463 and wall-attrition frames 6087-6338.

## Peashooters and bullets

- Peas deal 20 damage. Damage is taken from head shield before body HP. Evidence: every common-zombie HP step in `public-03-single-lane` is 20; equipment values are separate trace fields.
- Bullet spawn is 69 units right of the plant center and at y = 208 + 138*row. Bullet speed is approximately 666.667 units/s, or 10.667/frame. Evidence: `public-03-single-lane`, bullet 1 frames 3688-3700.
- Observed firing periods were about 70 frames for the column-2 shooter and 90 frames for the column-3 shooter. The implementation preserves those measured periods and starts firing only when a displayed, living zombie is ahead in the same lane. Evidence: bullet creation sequences beginning at frames 3688 and 3694 in `public-03-single-lane`.
- Used bullets continue their visual flight and are removed after leaving the right side. Evidence: bullet 1 remains after its frame-3741 hit and is removed at frame 3877.

## Sun

- Sky sun first appears at frame 314, then every 24.992 seconds (alternating 1562/1563-frame gaps). Evidence: sky-sun creation at frames 314, 1876, 3439, and 5001 in public traces.
- A produced sun appears at x = plant center - 1 and y = 123 + 138*row. Evidence: `public-02-sun-economy` produced suns at (752,399), (874,123), and (874,675).
- First sunflower production occurs after about 5-6 seconds. Later measured periods are 23.5, 24.5, or 25.5 seconds. Evidence: creation frames 451/1919/3388/4857 in `public-03-single-lane` and 451/1982/3513 plus 948/2542/4135 in `public-02-sun-economy`.
- A collected sun becomes disabled on mouse release, flies toward (290,1010), and credits 50 sun 44 frames later. Evidence: `public-03-single-lane` frames 353/397 and 458/502; `public-02-sun-economy` frames 363/407.
- Exact sky-sun x, target y, and launch velocity randomization are approximated from the time seed. The supplied seed probes establish that sky sun depends on `time_seed`, while zombie placement depends on `device_seed`.

## Mowers and end state

- A mower triggers when a zombie reaches approximately x=535, changes to `live=1`, `st=2`, waits one frame, then moves right at 760 units/s (12.16/frame). It disappears 137 frames after triggering. Evidence: `public-03-single-lane`, frames 4005-4142.
- A mower kills zombies in its lane immediately, zeroing body and head-shield HP. Evidence: wall-attrition and idle-loss experiments.
- With no mower left in a lane, a zombie reaching the house is treated as a zombie win. The long idle oracle process aborted before emitting an end overlay, so exact loss-overlay timing is a known gap.
- The exact final-wave count and victory-overlay timing were not reached by the supplied examples or accepted experiments and remain a known gap.
