# Level 4 rules and evidence

## Clock, board, and trace

- One frame is exactly 0.016 seconds and traces start at frame 0. Evidence: `docs/SCENARIO_FORMAT.md`.
- The lawn has five lanes and nine columns. Zombie lane centres are y = 130 + 138*lane. Plant records intentionally use `r=column`, `c=row`. Evidence: `docs/TRACE_SCHEMA.md`; public-03 frame 3201 has zombie y values 130, 268, 406, and 544, and planted cells appear with the documented swapped fields.
- Plant design centres used for attacks/suns are x = 630 + 122*column. Produced-sun y is 123 + 138*row. Evidence: public-03 frames 451 and 1919 (`x=752,y=261`) for the sunflower at column 1, row 1.

## Economy and cards

- Initial sun is 10,000. Costs are sunflower 50, peashooter 100, wallnut 50. Evidence: public-03 frames 64, 524, 1044, and 1944.
- Initial card state: sunflower becomes ready at frame 1 and enabled at frame 8; peashooter completes at frame 470; wallnut completes at frame 1876. Evidence: all public traces.
- Sunflower and peashooter recharge in 469 frames (about 7.5 s); wallnut recharges in 1,875 frames (30 s). Overlay percentage decreases linearly from 100 to 0. Evidence: public-03 placements at frames 75/535/1055/1955 and readiness at 544/1004/1524/3830.
- A valid scripted card press is reflected four frames after the scenario action frame: cost is paid, `hold` becomes the card index, and the displayed overlay is 100. The plant appears and `hold` clears at action frame + 15. Evidence: public-03 action 60 and frames 64/75; action 520 and frames 524/535.
- Sunflower and peashooter have 300 HP; wallnut has 3,000 HP. Evidence: public-02 frame 75 and public-03 frames 535 and 1955.
- A zombie bite removes 100 plant HP per completed bite animation. Evidence: public-02 frames 3014, 3113, and 3212.

## Waves and zombies

- Wave timing starts at frame 64. The first warning begins at timer 18 (frame 1133), and wave 1 is released at frame 1139. Later waves are about 32-33 seconds apart, with a six-frame warning state. Evidence: public-02 wave 2 at frame 3195; public-03 wave 2 at 3201 and wave 3 at 5226.
- Wave 1 contains one common zombie in the top lane. Later waves contain increasing randomized groups. This submission uses the scenario's specified splitmix64 `random_device` stream directly for group details. Evidence: public-01/02/03 frame 1139; `docs/SCENARIO_FORMAT.md` for entropy.
- Common/cone/bucket zombies have 200 body HP and respectively 0/600/1300 head-shield HP. Common and cone values are measured at public-03 frames 1139 and 3201; bucket shield is an assumption extrapolated from standard progression and is recorded as a known gap.
- Walking speed is 30 design units/s, or 0.48 per frame. A zombie becomes shown below x=1710. Evidence: public-03 frames 1139-1140 and 1556-1557.
- Peas deal 20 damage, first against head shield and then body HP. Evidence: public-03 zombie HP transitions beginning at frame 3741.
- Dead zombies retain a visible death state briefly, stop moving after roughly 35 frames, and are removed later. Evidence: public-03 zombie 1 at frames 4005 and 4040 and removal at 4320.

## Peashooters and bullets

- A peashooter only fires while a shown, living zombie is ahead in its lane. Its first shot follows an animation delay; shot periods vary by plant in the observed program. The simulator deterministically assigns periods in the observed 69-90 frame range. Evidence: public-03 bullet sequences 3694/3764/3833 and 3688/3778/3867.
- Bullet spawn is x = 700 + 122*column, y = 208 + 138*row. Bullets move right by 10.6667 units/frame (666.67 units/s). Evidence: public-03 frames 3688-3690.
- A hit occurs at about 23 units before zombie x; the bullet then has `used=1` but continues until off-screen. Evidence: public-03 frame 3741 and later used-bullet positions.

## Suns

- Sky suns begin at frame 314 and recur every about 1,562-1,563 frames (25 s). They use a ballistic entrance and settle on the lawn. Evidence: public traces at frames 314, 1876, 3439, and 5001.
- Sunflowers first produce after roughly 5-6 seconds and repeat after randomized intervals near 23-31 seconds. Evidence: public-02 plant frame 75 and sun frames 451/1919/3388; plant frame 635 and sun frames 948/2542.
- Every collected sun is worth 50. The scripted collector disables a chosen sun on release and payment arrives 44 frames later. Evidence: public-02 sun 1 disabled at frame 363 and balance increased at 407; sun 2 disabled at 483 and balance increased at 527.
- Sun trajectories are deterministic ballistic approximations; exact random launch velocities and cleanup scheduling remain a known gap.

## Lawn mowers and end state

- Mowers are introduced one at a time at frames 33, 39, 45, 51, and 58, initially `tag=-1, live=0, st=1, x=455`. Evidence: all public traces.
- A mower triggers when a live zombie reaches about x=535, changes to `live=1, st=2`, moves right by about 12.16 units/frame, kills contacted zombies, and leaves after 137 frames. Evidence: public-03 frames 4005-4142 and public-02 frames 4085-4222.
- If a zombie passes the left edge after its lane's mower is gone, zombies win; the trace continues for 60 frames after the result. The exact original loss boundary and final-wave win count are assumptions because no public trace ends in a result. Evidence for the 60-frame rule: `docs/SCENARIO_FORMAT.md`.
