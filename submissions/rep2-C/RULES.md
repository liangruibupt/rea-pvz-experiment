# Level 4 Rules and Evidence

This is a clean-room simulator. It contains rules and measured constants, not original code, resources, or trace lookup tables.

## Clock, trace, and board

- A frame is 16 ms and frame 0 is emitted. Output is contiguous through `end_frame`, except that an unprotected zombie crossing the left boundary ends the trace before an invalid next frame. Evidence: `docs/SCENARIO_FORMAT.md`; no-action oracle `oracle-results/cal-loss-206/trace.jsonl` ends at frame 9956 with the leading zombie at x=0.307 and no overlay.
- The lawn has five lanes at y = 130, 268, 406, 544, 682 and nine plant columns with logical centers x = 631 + 122*column. Evidence: public zombie positions and projectile origins; `public/public-03-single-lane/trace.jsonl` frames 1139 and 3688.
- Plant trace fields intentionally expose program storage order: `r` is column and `c` is row. Evidence: `docs/TRACE_SCHEMA.md` and frame 75 of each planted public trace.

## Economy, cards, and planting

- Starting sun is 10,000. Costs are sunflower 50, peashooter 100, wallnut 50. Evidence: `public/public-03-single-lane/trace.jsonl` frames 64, 524, and 1944.
- Startup readiness: sunflower frame 1, peashooter frame 470, wallnut frame 1876. The sunflower becomes enabled at frame 8. Evidence: `public/public-01-idle/trace.jsonl` frames 0, 1, 8, 470, and 1876.
- Sunflower and peashooter cooldowns are 7.5 seconds (468.75 frames); wallnut cooldown is 30 seconds (1875 frames). Cooldown overlay decreases linearly from 100 to 0. Evidence: idle frames 2, 469, 470, 1875, 1876; successful sunflower placement at frame 75 becomes ready at frame 544.
- A card selection takes effect at action frame F+4: cost is deducted, `hold` becomes the card index, and the overlay reads 100 while held. Placement takes effect at F+15. Evidence: public actions beginning at frame 60 produce transitions at frames 64 and 75.
- Successful placement starts cooldown. Occupied-cell placement refunds the cost and leaves the card ready. Evidence: `oracle-results/cal-03/trace.jsonl` frames 2614-2625.
- Plant HP: sunflower 300, peashooter 300, wallnut 3000. Evidence: public frame 75, frame 535, and frame 1955; `oracle-results/cal-02/trace.jsonl` frame 1915.

## Wave clock and spawning

- The integer wave timer advances on a 62.5-frame cadence, corresponding to one second at 16 ms. Its observed global tick frames begin 64, 127, 189, 252. Evidence: `public/public-01-idle/trace.jsonl`.
- The pre-wave interval is 18 seconds. `wdead` is set at frame 1133 and wave 1 is created at frame 1139. Evidence: every public and calibration trace.
- Measured later maximum intervals are 32-34 seconds after wave 1, 32-33 seconds after wave 2, and 45 seconds after wave 3. A cleared wave may advance earlier. Wave 4 is followed six frames later by the large fifth wave. Evidence: wave transitions in `oracle-results/cal-01/trace.jsonl`, `oracle-results/cal-02/trace.jsonl`, `oracle-results/cal-03/trace.jsonl`, and `oracle-results/cal-04/trace.jsonl`.
- Spawn counts measured for Level 4 are one zombie in wave 1, 3-5 in waves 2 and 3, 3-4 in wave 4, and 11-15 in the final wave. The simulator uses a deterministic seed mixer within these ranges; the exact original engine-seeding transform remains unrecovered.
- Wave 1 is in the top lane. Wave 2 populates lanes 0-3 before adding a possible duplicate. Evidence: all seven public/calibration seeds; for example public-03 frame 3201 and calibration cal-02 frame 3139.
- Common zombies have body HP 200; cones add head-shield HP 600; buckets add head-shield HP 1200; body-shield HP is 0 for these types. Evidence: public-03 frame 3201, cal-02 frame 5158, cal-04 frame 8020. REA confirmation: constructors at `FUN_0021f050`, `FUN_0021fcc4`, and `FUN_0021de74` in `rea-out/zombie-subtype2-decompile.json`, `rea-out/zombie-subtype3-decompile.json`, and `rea-out/zombie-subtype-decompile.json` contain float constants 200, 600, and 1200.
- REA found the original wave uniform-integer helper to be a Park-Miller `minstd_rand` engine using multiplier 16807 and modulus 2147483647. Evidence: `FUN_0020c590` in `rea-out/wave-randint-decompile.json`. The wave assembler requests 1-3 zombies per configured entry and rejects spawn positions within distance 100 of an existing spawn. Evidence: `FUN_0020cd84` and `FUN_0020cbf4` in `rea-out/wave-assemble-decompile.json` and `rea-out/zombie-position-decompile.json`.
- Each zombie constructor seeds a Park-Miller state from `std::random_device`; the supplied random-device stream is SplitMix64. Evidence: `FUN_00223d04` in `rea-out/zombie-init-decompile.json` and `docs/SCENARIO_FORMAT.md`. The precise object-construction draw index was not recovered, so spawn positions use a deterministic calibrated mixer rather than a seed-specific table.

## Zombie movement, eating, and death

- Walking speed is 30 design units/second, so x decreases by 0.48 each frame. Zombies become shown at x approximately 1710. Evidence: public-03 zombie 1 from frames 1139 to 1557; `spd=30` throughout.
- A zombie stops at approximately plant-center x + 79, sets `eat=1`, and `spd=0`. Evidence: cal-03 frame 3991 at x=709.616 for column 0; public-03 frame 5782 at x=831.690 for column 1.
- Eating damage is 100 HP per bite. The first hit is about 42 frames after contact and later hits are about 83 frames apart. Evidence: public-03 plant HP changes at frames 5823, 5905, 5987; cal-03 frames 4034, 4118, 4203.
- Plants remain trace-visible for roughly 250 frames after reaching 0 HP, while collision ceases immediately. Evidence: public-03 sunflower reaches 0 at frame 5987 and disappears at frame 6238.
- Dead zombies retain a visible death animation, stop moving after roughly 42 frames, and are removed later. The simulator uses a 280-frame bounded cleanup approximation. Evidence: public-03 zombie 3 dies at frame 4084, stops at 4125, and is removed by frame 4320.

## Peashooters and bullets

- A peashooter only attacks a shown, live zombie ahead in its lane. The first shot follows target acquisition by about 87-93 frames; later shots are about 69 frames apart. Evidence: public-03 target show at frame 3601 and bullets at frames 3688/3694, then 3764/3778.
- Bullet origins are plant-center x + 69 and y = 208 + 138*row. Evidence: public-03 frame 3688 has x=1066, y=484 for column 3, row 2; frame 3694 has x=944 for column 2.
- Bullet speed is approximated as 600 design units/second (9.6/frame). A hit deals 20 HP, consuming head shield before body HP. Evidence: cal-01 zombie 1 loses 20 HP per projectile from frame 2716 onward; shield-first behavior appears in public-03 cone combat.

## Suns

- Falling suns start at frame 314 and repeat every 1562.5 frames (25 seconds): 314, 1876, 3439, 5001, 6564, 8126. Evidence: every long public/calibration trace.
- An uncollected falling sun remains about 1312 frames. Evidence: idle sun 1 appears at frame 314 and disappears at 1626.
- A collected sun is disabled on mouse release and credits 50 sun 44 frames later. Evidence: public-03 sun 1 disables at frame 353 and credits at 397; produced sun 2 disables at 458 and credits at 502.
- A sunflower first produces after a measured 4-6 seconds, then repeats at a plant-specific measured interval from 22.5-26.5 seconds. Evidence: cal-03 first products at frames 325, 835, 1345, 1918, 2491 and later sequences; public-03 products at 451, 1919, 3388, 4857.
- Sun animation target positions depend on original random state. The simulator preserves observed cadence, clickability, flight-to-bank timing, and lifetime, but approximates exact random x/y targets.
- REA confirms production chooses one of two throw animations with `rand() & 1` and creates a Sun object. Evidence: `FUN_001e4a50` in `rea-out/sun-produce-decompile.json`.

## Lawn mowers and end behavior

- Five mowers appear one at a time at frames 33, 39, 45, 51, 58. Initial fields are `tag=-1`, `live=0`, `st=1`, `x=455`. Evidence: every trace, especially idle frames 33-58.
- A mower activates near zombie x=535, changes to `live=1`, `st=2`, kills intersecting zombies, and moves right at approximately 11.52 units/frame until removed beyond the lawn. Evidence: public-03 mower transitions at frames 4005-4142; cal-loss-206 frames 4055-4192.
- Mower kills set body HP to 0 even when a head shield remains. Evidence: cal-02 cone killed around frame 6670.
- With no mower, the supplied program's no-action run ended before writing a frame with negative zombie x and did not expose an end overlay in its last valid frame. The simulator therefore ends its trace at that boundary without inventing `end` or `zwin`. Evidence: `oracle-results/cal-loss-206/trace.jsonl` frame 9956 and oracle return code -6.

## Known approximations

Exact original transformations for random spawn coordinates, wave subtype selection, random sun target positions, animation phase offsets, and some wave-callback delays were not fully recovered. The implementation uses deterministic, seed-driven rules constrained by measured ranges. It never embeds per-frame oracle data or dispatches the original executable.
