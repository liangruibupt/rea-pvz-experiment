# Level 4 rules and evidence

This document distinguishes directly measured behavior from the deterministic approximations used where the available traces did not identify the original random-number transformation.

## Clock and trace

- A frame is 16 ms and frame 0 is emitted. The simulator emits every integer frame through `end_frame`, unless a result occurred 60 frames earlier. Evidence: `docs/SCENARIO_FORMAT.md`; all three public traces contain frame 0 and the declared final frame.
- The integer game-second transition is modeled as `floor((16*f-24)/1000)`, clamped to zero. Evidence: `public-01-idle/trace.jsonl` changes `wt` at frames 64, 127, 189, 252, 314, and so on.
- `ts` is always 1.0 and the shovel is never held. Evidence: schema and every supplied trace.

## Cards and planting

- Costs are sunflower 50, peashooter 100, and wallnut 50 sun. Evidence: public-02 frames 64/75 and 624/635; public-03 frames 524/535 and 1944/1955.
- Initial sun is 10000. Evidence: frame 0 of every public and queried calibration trace.
- Sunflower is ready at frame 1 and enabled at frame 8. Peashooter is ready/enabled at frame 470. Wallnut is ready/enabled at frame 1876. Evidence: public-01 transitions.
- Sunflower and peashooter cooldowns last 469 frames; wallnut cooldown lasts 1875 frames. Their overlay falls linearly from 100 to 0. Evidence: public-03 sunflower placement frame 75 to ready frame 544, peashooter 535 to 1004, wallnut 1955 to 3830; public-01 overlay samples.
- A successful card selection occurs at action frame `F+4`; it deducts the cost and sets `hold`. A successful plant appears at `F+15`, clears `hold`, and starts cooldown. Evidence: every public planting action.
- An occupied-cell placement clears `hold`, refunds its selection cost, creates no plant, and does not start cooldown. Evidence: cal-03 action at 2610, selection/deduction at 2614, refund and clear at 2625, with no new plant.
- Plant HP is 300 for sunflower and peashooter, 3000 for wallnut. Evidence: public-02/public-03 creation frames and cal-02 wall trace.
- Trace plant fields intentionally follow the program's reversed naming: `r` is the requested column and `c` is the requested row. Evidence: schema and public placement traces.

## Suns and economy

- A sky sun first appears at frame 314 and thereafter about every 1562 frames (25 seconds). It starts at y=1150.001, animates upward, falls to a random lawn point, and expires after about 1312 frames when uncollected. Its random positions depend on `time_seed`, not `device_seed`: changing only device seed 101 to 999 preserved x=1510 and x=881, while changing only the time seed changed them to x=1234 and x=1416. Evidence: public-01; accepted `probe-device` and `probe-time` oracle experiments.
- A sunflower emits its first sun roughly 250--376 frames after placement, then at a randomized interval observed between 1406 and 1656 frames. Produced suns start at plant x minus 1 and lane y minus 7. Evidence: cal-03 producer birth sequences and public-02/public-03.
- A collected sun awards 50. The simulator marks the first eligible sun disabled at the scenario collection cadence, animates it toward (290,1010), and awards after 47 frames. Evidence: public-03 first sky-sun collection and public-02 economy transitions. The exact original flight duration varies with starting position, so 47 is an approximation.

## Waves and zombies

- The wave system starts at frame 64. First-wave handoff begins at frame 1133 and wave 1 is released at 1139. Wave 1 contains one common zombie in row 4. Evidence: all public and calibration traces.
- Level 4 has five waves. Wave 4 is followed six frames later by the large final wave 5. Evidence: queried cal-01, cal-03, and cal-04 traces.
- Normal release gaps are about 27--45 seconds and depend on the random stream/game state. Several measured Level-4 table variants are selected deterministically from the documented device entropy. Evidence: public-02/public-03 and queried cal-01/cal-03/cal-04 release frames. This variant selection is an approximation because no supplied material exposed the original entropy-to-table transformation.
- Common zombies have 200 body HP. Cone zombies have 200 body HP plus 600 head-shield HP. Bucket zombies have 200 body HP plus 1300 head-shield HP. Evidence: public-03 cone at frame 3201; cal-04 final-wave bucket; common births in every trace.
- Zombies move left at 30 design units/second, or 0.48 per frame, and become `show=1` at x about 1710. Evidence: public-01 frames 1139--3000 and public-03 show transitions.
- Zombie spawn x lies in approximately 1800--2280. The simulator uses the documented splitmix64 stream and an inclusive integer mapping. Evidence: all wave birth positions. The exact original mapping remains an approximation.
- A zombie begins eating when it reaches about 79 units to the right of a plant center. It stops moving while eating and deals 100 HP every 84--85 frames. Evidence: cal-03 zombie 1 begins eating at x=709.616 against column 0; plant HP falls at frames 4034, 4118, and 4203.
- Grid plant centers are x=`631+122*column`; zombie lane y values are `[130,268,406,544,682]`. Evidence: scenario click geometry plus all trace positions.

## Peashooters and bullets

- A pea deals 20 damage, removing shield HP before body HP. Evidence: public-03 zombie 3 HP transitions 200,180,...,0 and cone traces.
- Bullets start at plant-center x plus 69 and lane y plus 78. Evidence: public-03 bullets at x=944/1066 and y=484.
- A bullet advances by 0.001 on its first update and then by 10.666667 per frame. It remains visible after impact with `used=1` and is removed beyond x=3060. Evidence: public-03 frames 3688--3695 and 3874--3883.
- Observed per-plant firing periods are stable and range from 62.5 to 89.3 frames (animation rates 10 through 7). The simulator uses a deterministic interval in that range. Evidence: cal-01 lane periods and public-03's two interleaved shooters. Exact animation-rate selection is an approximation.

## Lawn mowers and end states

- Five mowers appear progressively at frames 33, 39, 45, 51, and 58. Their resting trace is `tag=-1, live=0, st=1, x=455`. Evidence: every public trace.
- A mower triggers when a live zombie reaches x about 535. It becomes `live=1, st=2`, advances by 0.001 on its first update and then 12.16 per frame, kills zombies in its row, and disappears beyond x about 2100. Evidence: public-03 trigger frames 4005, 5949, and 6303 and subsequent mower trajectories.
- A living zombie crossing x=380 in a row whose mower has gone is treated as a zombie win. The result trace lasts 60 more frames. Evidence basis: task/schema end contract and observed mower breach geometry. The exact original loss threshold was not isolated by an accepted long-idle query, so this is a known approximation.
- Dead zombies keep moving briefly during their death animation, then report speed 0 and remain in the trace for a cleanup interval. The simulator uses 36--41 moving frames and 315--470 total frames depending on mower versus projectile death. Evidence: public-03 zombie 1 and zombie 3 death/stop/removal transitions.
