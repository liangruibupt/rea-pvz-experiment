# Level 4 Rules and Evidence

This document distinguishes measured behavior from approximations. Frame references use the supplied or queried original traces, never simulator output.

## Clock, startup, and trace lifecycle

- One update is 16 ms and trace frame `f` is end-of-frame state. Evidence: `docs/SCENARIO_FORMAT.md` and constant zombie displacement of 0.480 per frame in `public/public-01-idle/trace.jsonl` frames 1139-1140.
- The player starts with 10,000 sun and speed multiplier 1.000. Evidence: every public trace frame 0.
- Sunflower becomes ready at frame 1 and enabled at frame 8. Peashooter becomes ready/enabled at frame 470. Wallnut becomes ready/enabled at frame 1876. Evidence: public idle frames 0-8, 469-470, and 1875-1876.
- Mowers are inserted at frames 33, 39, 45, 51, and 58, initially `{tag:-1, live:0, st:1, x:455}`. Evidence: transition scan of public idle.
- The wave timer starts at frame 64. Evidence: public idle frames 63-64.
- Output includes frame 0 and stops at the scenario end frame, or 60 frames after a simulated result. The 60-frame rule comes from `docs/SCENARIO_FORMAT.md`.

## Cards, economy, and placement

- Costs are sunflower 50, peashooter 100, wallnut 50. Evidence: public economy frame 64 (sunflower selection), public single-lane frames 524 and 1944.
- Sunflower and peashooter recharge over 469 frames (about 7.5 seconds). Wallnut recharges over 1875 frames (30 seconds). The overlay decreases linearly by 0.213333 percentage points per frame for short cooldowns and 0.053333 for wallnut. Evidence: public idle frames 1-2 and 469-470; public single-lane frames 535/1004 and 1955/3830.
- An accepted card click occurs on action frame + 4, deducts cost, sets `hold`, and displays 100% overlay while held. Lawn release occurs on action frame + 15. Evidence: public economy action 60, trace frames 64 and 75.
- Successful placement clears `hold`, creates the plant, and starts cooldown. A click while unavailable does nothing. An occupied-cell release clears `hold`, refunds the selected card's cost, and leaves the card ready. Evidence: queried calibration economy-grid frames 2614-2625 and wall-attrition frames 5750-5765.
- `en` requires both readiness and affordability. The implementation models the small UI polling delay after cooldown conservatively. Evidence: public economy frames 544-545 and 1104-1108.

## Plants

- Health: sunflower 300, peashooter 300, wallnut 3000. Evidence: public traces at each first placement; wallnut at public single-lane frame 1955.
- Plant trace coordinates preserve the program's reversed names: `r` is lawn column and `c` is lawn row. Evidence: `docs/TRACE_SCHEMA.md` and public economy frame 75.
- A common zombie bite removes 100 plant HP. Its first bite is about 50 frames after eating starts and later bites are about 99 frames apart. Evidence: public economy frames 2964, 3014, 3113, 3212.
- Cone eating uses a faster animation, with a first event around 41 frames and later events around 82 frames. Evidence: public single-lane frames 5782, 5823, 5905, 5987.
- A zombie begins eating when its x coordinate reaches approximately plant-center x + 79, then speed becomes zero. Evidence: public economy frame 2964, where the column-2 sunflower center is x=875 and zombie x=953.556.

## Peashooters and bullets

- Bullet origin is x=`700 + 122*column`; y=`208 + 138*row`. Evidence: queried five-lane trace bullet births and public single-lane origins 944 (column 2) and 1066 (column 3).
- Bullets move right by 10.666667 design units per frame (666.667 units/second). Evidence: public single-lane frames 3688-3700.
- Each pea removes 20 points, applying to head shield before body health. Evidence: public single-lane zombie 3 HP transitions beginning frame 3741 and queried cone traces.
- Bullets remain in the trace for about 189 frames from creation; `used` becomes 1 on collision but the visual continues moving. Evidence: public single-lane bullet 1, born 3688, used 3741, last present 3876.
- Emission phase varies by planted animation. Measured recurring periods used by the simulator are 63-90 frames depending on row/column, with first eligible emission after about 87-93 frames. Evidence: public single-lane births for each origin and queried five-lane bullet birth series. This is an approximation of animation callback phase rather than a recovered source constant.

## Zombies and randomness

- Common body HP is 200. Cone shield HP is 600. Bucket shield HP is 1200. Evidence: public/query first appearances, including public single-lane frame 3201 and late-defense frame 8020.
- Walking speed is 30 units/second, serialized as `spd:30`, which produces 0.480 units per frame. Eating and completed death animations use speed 0. Evidence: public idle frames 1139-1140 and public economy frame 2964.
- Zombies become shown when x falls below 1710. Evidence: public idle frames 2175-2176.
- Initial x is an integer in [1780,2280], followed by the current frame's 0.480 movement. The exact generator is libstdc++ `default_random_engine` (`minstd_rand0`) seeded by the first specified splitmix64 device draw, with one uniform draw per zombie. Evidence: seed-isolation oracle probes plus all queried calibration initial positions; for device seed 103 the generated sequence 1911, 2071, 1902, 2024, 1907, 1854 exactly matches public single-lane.
- Lane selection uses another `default_random_engine` seeded directly with `time_seed`, uniform 0-4. Already-used lanes are rerolled until all five have appeared; the used set then clears, including across wave boundaries. Evidence: public single-lane lane sequence 4 / 1,2,0,3,3 and queried five-lane sequences.
- Type selection uses an independent deterministic stream and Level 4 probabilities. The probability table is measured from `oracle/dist/Resources/resources/Text/GAMEWORLD_1DATAS.json`: successive configured rows begin 100/0/0, 95/5/0, 90/10/0 and progress toward more cones/buckets. The exact original stream seed was not fully recovered; the simulator uses a measured-fit independent minstd stream.
- A pea-killed zombie becomes `alive:0` immediately, stops after roughly 42 frames, and remains for roughly 470 frames. Mower kills stop sooner and remain about 315 frames. Evidence: public single-lane zombie 3 frames 4084/4125/4554 and zombie 1 frames 4005/4040/4320.

## Waves

- Level 4 has 10 configured frequencies; base populations are `[1,3,3,3,10,4,3,3,4,10]`, with a large-wave marker at wave 5. Evidence: `oracle/dist/Resources/resources/Text/GAMEWORLD_1DATAS.json` (`Level_4`). Actual traces add a small seeded variation: waves 2-4 add 0-2 zombies and wave 5 adds roughly 3-5.
- First-wave threshold is 18 timer seconds. Wave state changes to dead/paused, then the wave releases about six frames later. Evidence: all public and queried traces frames 1133/1139.
- Later ordinary thresholds cluster at 28-34 seconds. A congested pre-large-wave interval can extend to 45 seconds. Evidence: queried calibration transitions: five-lane 34/28/27, wall-attrition 32/32/45, economy-grid 32/33/45, late-defense 32/33/45.
- `wt` is an integer-valued floating field and resets to 0 on release. `wbegin` marks timer activity; `wdead` is briefly 1 during the pre-release pause. Evidence: public idle frames 1132-1139.
- The exact adaptive timer and wave-size random streams remain approximated. The simulator preserves measured ranges and early public schedules.

## Suns

- Sky suns first appear at frame 314 and then every 1562-1563 frames (25 seconds). Evidence: public idle births 314 and 1876; public economy births 314, 1876, 3439.
- A sky sun begins at y=1150, follows a short rise/fall animation, then falls about 2.56 units per frame to a seeded resting y. Evidence: public idle frames 314-514.
- A sunflower-produced sun starts at x=`630 + 122*column`, y=`123 + 138*row`. Evidence: public economy births at x752/y399 for column1/row2 and x874/y123 for column2/row0.
- First production occurs roughly 5-6 seconds after planting. Recurrence is roughly 23.5-25.5 seconds, seeded/per-plant. Evidence: public economy births 451, 948, 1571, 1982, 2542, 3513, 4135 and public single-lane births 451, 1919, 3388, 4857.
- Sun value is 50. Collection disables the sun on mouse release (collection frame + 3), credits 44 frames after release, animates toward (290,1010), and removes roughly 388 frames after release. Evidence: public economy first sky sun disabled frame 363, credited frame 407, removed after frame 750.
- The exact sky horizontal-position generator and jump arc are approximated. This is the largest measured public subsystem gap.

## Mowers and end state

- A mower triggers when an alive zombie crosses x≈535 in its row. On the trigger frame it becomes `{live:1, st:2}` and kills the zombie; it then moves right about 12.16 units per frame. Evidence: public economy frames 4084-4118.
- A running mower kills zombies it reaches and is removed after passing x≈2100, reducing the `cars` list length. Evidence: public single-lane frames 6439-6440.
- `UserLose` is 430 in Level 4 configuration. The simulator declares zombie victory when a zombie reaches x≤430 in a row whose mower is exhausted, then emits 60 additional frames. Evidence: `GAMEWORLD_1DATAS.json` and scenario stop contract. Exact overlay timing was not isolated from a clean oracle loss and remains a known gap.

## REA evidence

- `rea-out/level4-strings.json` identifies Level 4 classes/assets including `SunFlower`, `PeaShooter`, `WallNut`, `CommonZombies`, `ConeZombies`, and `BucketZombies` in the shipped AArch64 binary.
- `rea-out/decompile-sunflower-init.json` decompiles `FUN_001e3170` and confirms the sunflower animation binding `SunFlower_Normal` at address `0x1e3170`.
- `rea-out/decompile-sun-layer.json` decompiles `_INIT_4` and confirms the dedicated global `sunLayer` binding at address `0x1c99dc`.
- REA did not recover semantic symbols for gameplay methods, so timing and random behavior above rely primarily on frame traces and controlled oracle experiments rather than speculative decompiler naming.
