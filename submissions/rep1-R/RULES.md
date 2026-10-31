# Level 4 simulator rules

This is a clean-room simulator based only on the supplied scenarios, schemas, and public traces. Values marked **approximation** are extrapolations where the public traces did not identify the original random or scheduling rule uniquely.

## Clock and level setup

- One frame is exactly 0.016 seconds. Evidence: `docs/SCENARIO_FORMAT.md` and zombie movement of 0.480 design units per frame at speed 30, for example public-01 frames 1139-1140.
- Trace frame 0 is emitted before the level-opening animation has completed. The five mowers appear on frames 33, 39, 45, 51, and 58. Wave timing starts on frame 64. Evidence: public-01.
- Initial sun is 10000. All three public traces show this on frame 0.
- Initial card states are covered and disabled. Sunflower becomes internally ready on frame 1 and enabled on frame 8. Peashooter becomes ready on frame 470. Wallnut becomes ready on frame 1876. Evidence: public-01 state transitions.

## Cards and planting

- Card order is sunflower, peashooter, wallnut. Costs are 50, 100, and 50 sun respectively. Evidence: public-03 changes at frames 64, 524, 1044, and 1944.
- Sunflower and peashooter recharge in 469 frames (about 7.5 seconds). Wallnut recharges in 1875 frames (30 seconds). Cooldown percentages fall linearly. Evidence: public-01 frames 2-470 and 2-1876; public-03 frame 3000 after the wallnut placement on frame 1955.
- A successful scripted card click is visible four frames after the action's nominal frame. It immediately deducts the cost and sets `hold`. Placement occurs on action frame + 15, clears `hold`, creates the plant, and starts cooldown. Evidence: every public planting action.
- Occupied or off-grid placement is rejected and refunds the selection cost. **Approximation:** no supplied traced scenario exposes the occupied-cell result.
- Sunflower and peashooter have 300 HP; wallnut has 3000 HP. Evidence: public-02/public-03 plant creation frames.
- Dead plants remain trace-visible for 250 additional frames. Evidence: public-02 plant 3, HP reaches zero on frame 3212 and the object disappears after frame 3462.

## Suns and economy

- Collected suns add 50. Evidence: public-02 frame 407 and subsequent collections.
- Sky suns first appear on frame 314, then every 1562.5 frames (25 seconds), alternating the rounded 1562/1563-frame interval. Evidence: public traces at frames 314, 1876, 3439, and 5001.
- Sky suns start at y=1150, make a short arcing motion, then fall over about five seconds to a random resting height. Their x coordinate, small lateral arc displacement, and resting height use the documented splitmix64 device stream. **Approximation:** the public samples do not uniquely identify the original bounded-distribution adapter.
- A sunflower's produced sun starts at x=`630 + 122*column`, y=`123 + 138*row`, makes a 40-frame arc, and rests at the same y. Evidence: public-02 and public-03 produced-sun creation positions and trajectories.
- The first production is about five seconds after planting on the bottom row and six seconds elsewhere. Subsequent observed periods vary by plant from about 23.5 to over 30 seconds; the simulator selects a stable period from row and seed, including alternating one-frame rounding on the bottom row. **Approximation:** the public samples do not uniquely reveal the original per-plant random-period adapter.
- The collector examines the preceding trace state every configured N frames. A qualifying sun becomes disabled three frames later, eases to (290,1010), and pays out 44 frames after selection. Evidence: public-02, where selection at frame 360 disables sky sun 1 on frame 363 and pays on frame 407.

## Waves and zombies

- The first wave is announced after 18 seconds: `wdead` on frame 1133 and spawn on frame 1139. The first wave has one common zombie in the top lane. Evidence: all public traces.
- Later wave intervals are approximately 32-33 seconds. `wdead` is set six frames before each spawn. The timer origin is 12 frames before spawn. **Approximation:** public-02 and public-03 differ by six frames for wave 2, so a small seed-based phase is used.
- Wave 2 has three zombies for even device seeds and five for odd device seeds. The five-zombie form begins with a cone zombie. Wave 3 has five common zombies. Later waves increase toward ten and introduce cone and bucket zombies. **Approximation:** wave 2 is evidenced by public-02 (three common) and public-03 (five including one cone); later composition is extrapolated.
- Common body HP is 200, cone head shield is 600, and the approximated bucket head shield is 1300. Peas deal 20 to head shield first, then body shield, then body. Evidence: public-03 common and cone initial states; 20-point common damage steps on frames 3741 onward.
- Zombies move left at 30 units/second and become shown at x about 1710. Evidence: public-03 zombie 3 becomes shown on frame 3601 at x=1709.528.
- A zombie stops around 139 units to the right of a plant center, bites for 100 damage, and repeats every 99 frames. Evidence: public-02 zombie 1 stops at x=953.556 by the column-2 sunflower and damages it on frames 3014, 3113, and 3212.
- Dead zombies coast briefly, stop about 40 frames after death, and remain visible for about 315 frames. Evidence: public-03 zombie 3.
- Peas travel at 2000/3 units/second (10.667 per frame), persist for 188 frames, and remain visible after being used. Evidence: public-03 bullet lifetimes and positions.
- Peashooter cadence is about 69.5 frames in column 2 and 89.5 in column 3 in the supplied trace. **Approximation:** this likely reflects a hidden randomized animation period.

## Mowers and end state

- Mowers begin at x=455 with state 1 and `live=0`. A zombie reaching x about 535 starts that lane's mower and is killed. Evidence: public-03 zombie 1/mower transition at frame 4005.
- A running mower enters state 2, moves right by 12.16 units per frame after a one-frame setup delay, kills zombies it intersects, and is removed around x=2096. Evidence: public-03 frames 4005-4145.
- A zombie crossing the mower threshold after that row's mower has been consumed causes zombie victory and the end overlay; output continues for 60 frames. **Approximation:** the supplied public traces do not reach a loss.
- `ts` is always 1.0 and `shovel` is always 0 for this scenario format. Evidence: all public traces.
