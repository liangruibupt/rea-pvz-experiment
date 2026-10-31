# Level 4 rules implemented

All frame references below are from the supplied public traces unless identified as an oracle experiment. The simulator uses a fixed 16 ms step and emits state after each step.

## Board and input

- The lawn has five rows and nine columns. Trace plant coordinates are reversed relative to scenario wording: trace `r` is the scenario column and trace `c` is the scenario row. Evidence: the action `(row=2,col=1)` in `public-02-sun-economy` creates `p={r:1,c:2}` at frame 75.
- Cell centers are `x=630+122*column`; zombie lane centers are `y=130+138*row`; pea bullets use `y=208+138*row`. Evidence: plants and bullets in `public-03-single-lane`, especially bullet frames 3688 and 3694.
- A successful scripted plant action takes its card and cost at `F+4`, then creates the plant at `F+15`. Evidence: `public-03-single-lane` action at frame 60 changes `hold` and sun at frame 64, and creates the sunflower at frame 75.
- An occupied drop is rejected, clears `hold`, refunds the selected cost, and leaves the card ready. A click during cooldown does nothing. Evidence: focused `probe-actions` oracle experiment, especially frames 100-115 and 604-615.

## Economy, cards, and plants

- Initial sun is 10,000. Costs are sunflower 50, peashooter 100, wallnut 50. Evidence: sun changes at selection frames 64, 524, 1044, and 1944 in `public-03-single-lane`.
- Sunflower and peashooter recharge in 7.5 seconds (468.75 frames); wallnut recharges in 30 seconds (1,875 frames). Their cooldown overlay declines linearly from 100 to 0. Evidence: initial peashooter is ready at frame 470 and wallnut at frame 1876 in `public-01-idle`; after placement, the public traces show the same rates.
- Sunflower is logically ready at frame 1, while card buttons finish entering and become enabled at frame 8. Evidence: frames 0, 1, and 8 of `public-01-idle`.
- Sunflower and peashooter have 300 HP; wallnut has 3,000 HP. Evidence: plant first-appearance records in `public-02-sun-economy` and `public-03-single-lane`.
- A zombie bite removes 100 plant HP. A destroyed plant remains in the trace with zero HP for 250 frames, but no longer blocks or occupies its cell. Evidence: the top-row sunflower in `public-02-sun-economy` loses HP at frames 3014, 3113, and 3212, and remains through frame 3462.

## Suns

- Sky suns begin at frame 314 and recur about every 1,562.5 frames (25 seconds). Evidence: appearances at 314, 1876, 3439, and 5001.
- A sunflower first produces after roughly 5-6 seconds and then roughly every 23.5-25.5 seconds. The exact phase and period vary by the scenario entropy. Evidence: produced-sun appearances in `public-02-sun-economy` and `public-03-single-lane`.
- Every collected sun is worth 50. It becomes disabled on mouse release and credits the counter 44 frames later. Evidence: the first sky sun in `public-03-single-lane` disables at frame 353 and credits at frame 397; the first produced sun disables at 458 and credits at 502.
- A collected sun flies toward `(290,1010)`. Disabled sun objects are retained until a later 125-frame cleanup boundary. Uncollected suns live for about 21 seconds. Evidence: sun lifetimes in all public traces.
- Exact random launch vectors and landing positions are approximated with deterministic SplitMix-derived values. Event cadence, enabled state, value, and collection delay are modeled directly from evidence.

## Waves and zombies

- The wave timer begins at frame 64 and advances in one-second callbacks at alternating 62/63-frame gaps. The first wave is released at frame 1139 after a six-frame warning state. Evidence: global transitions in every public trace.
- Later regular waves are separated by approximately 27-34 seconds with entropy-derived jitter. Every fifth wave is a 15-18-zombie flag wave released six frames after the preceding regular wave. Evidence: the `cal-01-five-lane-peas` oracle experiment releases waves 4 and 5 at frames 6733 and 6739 and adds 15 zombies; the long-idle experiment releases them at 6895 and 6901 and adds 18.
- Wave 1 is one common zombie in the top row. Regular waves contain 3-5 zombies. Common zombies dominate early waves, cones have a 600-point head shield, and buckets have a 1,300-point head shield from wave 4 onward. Evidence: public wave spawns; cone at frame 3201 in `public-03-single-lane`; bucket at frame 6895 and flag-wave composition in the long-idle oracle experiment.
- Zombies have 200 body HP, speed 30 design units/second, and move 0.48 units per frame. They become shown near `x=1710`. Evidence: the first zombie in `public-01-idle`, frames 1139-3000.
- A zombie starts eating at about 80 units to the right of a plant center. It stops moving while eating and bites for 100 damage on an approximately 1.4-second cycle. Exact animation phase is entropy-dependent and approximated. Evidence: the top-row sunflower encounter in `public-02-sun-economy`.
- A normal zombie death remains in the trace for 469 frames; a mower death remains for 314 frames. Evidence: zombie 3 and zombie 1 lifetimes in `public-03-single-lane`.

## Peas and combat

- A peashooter attacks only a shown, living zombie in its row and to its right. Its first shot follows an attack-animation delay. Subsequent shot periods vary by plant, approximately 69-90 frames. Evidence: bullet creation sequences from frames 3688 onward in `public-03-single-lane`.
- A pea starts at `x=700+122*column` and advances 10.666667 units per frame (666.667 units/second). It remains in the trace for 188 frames after creation. Evidence: bullet 1 from frames 3688-3876 in `public-03-single-lane`.
- A pea deals 20 damage, consuming head shield, then body shield, then body HP. Evidence: zombie 3 HP steps at frames 3741-4084 in `public-03-single-lane`.
- A hit bullet sets `used=1` but continues its fixed trajectory until its lifetime expires. Evidence: bullet 1 after frame 3741 in `public-03-single-lane`.

## Mowers and end state

- Five mowers enter one at a time at frames 33, 39, 45, 51, and 58. Their initial state is `tag=-1, live=0, st=1, x=455`. Evidence: `public-01-idle`.
- A mower triggers when a living zombie reaches approximately `x=535`, changes to `live=1, st=2`, and kills overlapping zombies in that row. It moves right at 12.16 units/frame and leaves after 137 frames. Evidence: mower activation at frame 4005 in `public-03-single-lane`, positions through frame 4141, and removal at 4142.
- After all mowers are spent, an unmowed zombie continues left. In the long-idle oracle experiment the last trace frame is 10610 with the leading zombie at `x=0.367`; the program exits before emitting the next frame, where it would cross zero. `end` and `zwin` remain zero through the final line. The simulator therefore stops before writing the first frame with an unmowed living zombie at `x<=0`.

## Determinism and entropy

- The implementation is Python 3.12 standard library only. It uses integer SplitMix64 streams derived solely from `time_seed` and `device_seed`; iteration order is fixed and output floats are rounded to three decimals.
- The original program's precise conversion of entropy into wave delays, lanes, positions, attack phases, and sun arcs could not be uniquely identified from the available observations. The submission therefore models the measured distributions and timing ranges rather than embedding any trace data.
