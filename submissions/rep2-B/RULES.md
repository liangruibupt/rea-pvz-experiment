# Level 4 rules and evidence

This document distinguishes directly measured rules from simulator approximations. Frame numbers refer to the supplied or queried oracle traces. The fixed simulation step is 0.016 seconds.

## Board, coordinates, and actions

- The lawn has five rows and nine columns. Plant trace fields reverse the input names: trace `r` is the input column and trace `c` is the input row. Evidence: public-03's action `(row=1,col=1)` creates `p={r:1,c:1}` at frame 75.
- Cell centers are `x=630+122*col`, `y=130+138*row`. Zombie lanes use the same y formula. Evidence: all traces use zombie y values 130, 268, 406, 544, and 682; projectile origins are 70 units right and 78 units above their plant center.
- A valid scripted action selects its card at `F+4` and places at `F+15`. Selection deducts the cost and sets `hold`; placement clears `hold` and starts cooldown. Evidence: public-03 action at frame 60 changes bank/hold at 64 and creates the sunflower at 75.
- An occupied-cell attempt is refunded at `F+15` and does not start cooldown. Evidence: cal-03 frames 2614-2625 deduct then restore 50, with five plants before and after.
- A click on an unavailable card has no effect. Evidence: cal-02's action at 5750 occurs during the wallnut cooldown and produces no selection or new plant.

## Economy and cards

- Initial bank: 10,000 sun. Costs: sunflower 50, peashooter 100, wallnut 50. Evidence: public-03 bank changes at frames 64, 524, 1044, and 1944.
- Collected suns add 50. Evidence: public-03 frames 397, 502, 1972, and 2007.
- Sunflower and peashooter cooldown: 469 frames (7.5 seconds nominal), overlay decrement `100/469` per frame. Wallnut cooldown: 1,875 frames (30 seconds), overlay decrement `100/1875`. Evidence: public-03 sunflower placement 75 to ready 544; peashooter 535 to 1004; wallnut 1955 to 3830. The button becomes enabled one to four scheduler frames after `ready`; the simulator uses three.
- Startup readiness is special: sunflower is ready at frame 1 and enabled at 8; peashooter is ready/enabled at 470; wallnut at 1876. Evidence: public-01 frames 0-1876.

## Plants

- Sunflower and peashooter HP: 300. Wallnut HP: 3,000. Evidence: every creation event in public-02/public-03 and cal-02.
- A common zombie bite removes 100 HP. Once a zombie reaches about 80 units right of the plant center it stops and eats. Evidence: cal-03 zombie at x 709.6 eating the column-0 sunflower; cal-02 zombies at x 1319.6 eating column-5 wallnuts.
- The stable single-zombie bite cadence is about 83 frames. Multiple zombies have independent animation phases, so interleaved plant HP changes can be much faster. Evidence: cal-02 row-4 wallnut changes at 6733, 6817, 6900, 6983, and later near 83/84-frame spacing.
- A plant remains in the trace during its death animation after reaching zero HP. The simulator retains it for 251 frames. Evidence: cal-03 row-4 sunflower reaches 0 at 4203 and disappears at 4454.
- Sunflower first production occurs 250, 313, or 376 frames after placement. Repeats cluster from 1,406 to 1,656 frames; the simulator uses 1,469. Evidence: cal-03 first productions at offsets 250/313/376 and public-03 productions at 451, 1919, 3388, 4857.
- Peashooters fire only when a shown, live zombie is ahead in their lane. Individual observed firing periods are roughly 62-90 frames. The simulator assigns a deterministic per-plant period in that range. Evidence: public-03 bullets from column 2 at 3694, 3764, 3833 and from column 3 at 3688, 3778, 3867.

## Zombies and waves

- Common body HP: 200. Cone head shield: 600. Bucket head shield: 1,200. Body shield is zero for observed Level 4 types. Evidence: public-03 wave 2 frame 3201 and cal-04 final-wave frame 8020.
- Walking speed: 30 units/second, exactly 0.48 design units per frame. Zombies become shown at x about 1710. Evidence: public-03 zombie 1 moves 1910.52, 1910.04, 1909.56 from frames 1139-1141 and changes `show` at frame 1557 near x 1710.
- Spawn x is an inclusive uniform integer in 1780..2280, followed by the current frame's 0.48 movement. The engine is libstdc++ `default_random_engine` (`minstd_rand0`) seeded with the first high-32-bit SplitMix64 `random_device` draw. Evidence: device seed 103 yields configured x sequence 1911, 2071, 1902, 2024, 1907, 1854, matching public-03 waves 1 and 2 exactly.
- Damage is applied to head shield, then body shield, then body HP in steps of 20. Evidence: common HP transitions in public-03 and bucket shield transitions in cal-04 frames 8732 onward.
- Dead zombies retain `show=1` during their animation. Their reported speed falls to zero about 42 frames after death; removal is much later. Evidence: cal-01 zombie 1 reaches HP 0 at 3254 and speed 0 at 3305.
- Wave 1 spawns one common zombie in the top lane at frame 1139. The no-action second wave is frame 3226 with three commons in lanes 2, 3, 0. Evidence: all consecutive-seed `waves-d100` through `waves-d107` experiments.
- Player activity perturbs the original's shared random/scheduler state. Observed active-scenario second waves occur at frames 3139-3264 and contain three to five zombies. The simulator approximates this with frame 3201, three zombies without defenders and five with defenders.
- Wave 3 is near frame 5200. A later wave is forced after about 45 seconds if earlier zombies survive; if all are dead it can begin sooner. The penultimate warning wave can be followed six frames later by the large wave. Evidence: cal-01 waves 3/4/5 at 5051/6733/6739; idle-long-d1 waves at 5314/8076/8351.
- The simulator uses deterministic lane/type templates plus a seeded engine for later cone/bucket choices. Exact lane/type generation was not fully recovered.

## Bullets

- Bullet speed: 666.667 units/second, about 10.667 per frame. The first scheduler frame advances only about 0.001. Evidence: public-03 bullet 1 at frames 3688-3691 is x 1066.000, 1066.001, 1076.667, 1087.334.
- A hit is registered when the bullet is about 22 units left of a zombie. It sets `used=1` and deals 20. Used bullets continue visually before deletion. Evidence: public-03 frame 3741, bullet x 1620.667 versus zombie x 1642.331.

## Suns

- Sky suns spawn at frames `floor(314+n*1562.5)`: 314, 1876, 3439, 5001, 6564, 8126. This is a 25-second cadence. Evidence: public and calibration traces.
- At level construction, the game calls `srand(time(NULL))`. Evidence: Ghidra procedure `FUN_001f2e34` at 0x1f2e34, decompilation in `rea-out/sun-srand.json`; the call is at 0x1f2e8c.
- With no early plant, the first sky x is `500 + rand()%1100` from C-rand draw 52 (zero-based index 51), and horizontal drift is the next draw modulo 120 minus 60. A sunflower constructed before it consumes eight C-rand calls. Evidence: entropy probe traces and glibc stream matching all four no-action time seeds; public/calibration first-sun x values then match at draw 60 when one sunflower exists.
- An uncollected sky sun lands 314 frames after spawn and expires 1,312 frames after spawn. Evidence: public-01 first sun settles at frame 628 and disappears at 1626.
- Sun collection disables the object, animates it toward the bank, and credits 50 after a distance-dependent delay. The simulator approximates that animation and delay. Evidence: public-03 first sky sun is disabled near frame 386 and credits at 397; produced sun 2 credits at 502.

## Mowers

- Five mowers appear during startup at frames 33, 39, 45, 51, 58. Idle state is `live=0, st=1, x=455`. Evidence: every trace.
- A mower triggers when an alive zombie reaches x about 535 in its lane. Trigger state is `live=1, st=2`. After a two-frame delay it moves 12.16 units per frame (760 units/second), kills zombies in its lane regardless of shields, and disappears just after x 2100. Evidence: public-03 top mower triggers at 4005, moves from 455 to 467.161 at 4007, and disappears at 4142.

## Win/loss and trace termination

- Supplied public traces end at `end_frame` when no result occurs. The documented contract requires stopping 60 frames after a result overlay.
- Long idle oracle experiments ended with original-process `rc=-6` before any `end=1` or `zwin=1` was traced. The exact no-mower loss threshold and overlay timing therefore remain unresolved. The simulator keeps `end=0,zwin=0` and writes through `end_frame`; this is the largest known gap for hidden loss scenarios.
