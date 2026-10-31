# Level 4 rules and evidence

This submission is a clean-room simulator based only on `TASK.md`, `ARM.md`, the two format documents, and the three public traces. It does not contain or call the original program or use trace lookup tables.

## Clock, board, and startup

- One frame is exactly 0.016 seconds and frame 0 is emitted after the first game update. Evidence: `docs/SCENARIO_FORMAT.md`.
- The board has five rows and nine columns. Plant records store input column in `r` and input row in `c`. Evidence: `docs/TRACE_SCHEMA.md` and every successful placement in the public traces.
- Plant centers used by collision/economy logic are `x = 630 + 122*column`; zombie lane centers are `y = 130 + 138*row`. Pea bullets use `x = 700 + 122*column`, `y = 208 + 138*row`. Evidence: public-03 plants at columns 2/3 produce bullets at x=944/1066 and y=484; zombie lane y values are 130, 268, 406, 544, 682.
- The initial sun bank is 10,000. Evidence: frame 0 in all public traces.
- Card 0 becomes ready at frame 1 and enabled at frame 8. The mower rows appear progressively at frames 33, 39, 45, 51, and 58. The initial wave timer starts at frame 64. Evidence: public-01 frames 0-64.
- A mower begins at x=455, state 1, and is removed after crossing roughly x=2100. While running it has state 2 and advances about 12.067 design units per frame. Evidence: public-03 frames 4005-4142.

## Cards and plants

- Costs are sunflower 50, peashooter 100, and wallnut 50. Evidence: public-02 frame 64 and public-03 frames 524 and 1944.
- Cooldowns are sunflower 7.5 s, peashooter 7.5 s, wallnut 30 s. The covered percentage falls linearly from 100 to 0. Evidence: public-02 sunflower placement 75 to ready 544, public-03 peashooter placement 535 to ready 1004, and wallnut placement 1955 to ready 3830.
- A successful card click charges immediately and sets `hold` four frames after the scheduled action. Placement occurs at action frame +15, clears `hold`, and starts cooldown. Evidence: public-02 action 60 changes hold/sun at frame 64 and places at frame 75.
- An occupied-cell attempt is treated as a cancelled placement and refunded. This is an assumption because the public traces contain no rejected placement; calibration scenario 03 motivates handling it explicitly.
- Sunflower and peashooter HP are 300; wallnut HP is 3000. Evidence: creation frames 75, 535, and 1955 in public-03.
- A plant at zero HP remains in the trace for about 250 frames. Evidence: public-02 sunflower reaches 0 at frame 3212 and disappears at 3463; public-03 reaches 0 at 5987 and disappears at 6238.

## Suns and economy

- A collected sun is worth 50. Evidence: public-02 frames 363-407 and public-03 frames 458-502.
- Sky suns first appear at frame 314, then every 1562/1563 frames (25 seconds). Evidence: frames 314, 1876, 3439, and 5001 across public traces.
- Uncollected sky suns arc briefly, fall at about 2.5 design units per frame, stop at a seed-dependent height, and expire after about 1312 frames. Evidence: public-01 sun 1, frames 314-1626.
- A newly placed sunflower first produces after about 5-6 seconds. Later production is seed-dependent at approximately 23.5, 24.5, or 25.5 seconds. Evidence: public-02 production at 451/1982/3513 and 948/2542/4135; public-03 at 451/1919/3388/4857.
- Produced suns originate at `x=630+122*column`, `y=123+138*row`, then follow a short ballistic arc. Evidence: public-02 frames 451, 948, 1571, 1982, and 2542.
- The scripted collector examines the prior frame at each configured interval. Its click disables a sun three frames later; the bank increases 44 frames after that. Evidence: public-02 sky sun selected on the frame-360 cycle, disabled at 363, awarded at 407.
- Collected suns ease toward (290,1010) and are retained for several seconds. Exact visual animation and cleanup timing vary in the public traces; the implementation uses the measured central values.

## Zombies, waves, and combat

- Wave 1 releases at frame 1139 after an 18-second opening timer. Later releases are roughly 32-33 seconds apart, with a six-frame warning state. Evidence: public-03 releases at 1139, 3201, and 5226; public-02 at 1139 and 3195.
- The observed first wave contains one common zombie in the top row. Later observed waves contain three or five zombies, seed dependent. The implementation uses one on wave 1 and three for even device seeds or five for odd device seeds. Evidence: public-02 wave 2 has three; public-03 waves 2 and 3 have five.
- Public wave composition supports these early templates: even-seed wave 2 uses common zombies in rows 1,0,2; odd-seed wave 2 uses one cone then commons in rows 1,2,0,3,3; odd-seed wave 3 uses commons in rows 2,4,0,1,2. Later waves cycle rows and introduce stronger types. Evidence: wave-spawn frames 3195 in public-02 and 3201/5226 in public-03. Spawn x and wave-4+ type choices use the specified splitmix64 stream; later composition is approximate.
- Common zombies have body HP 200 and no shield; cones have body HP 200 and head shield 600. Buckets are assigned body HP 200 and head shield 1300 as a stated assumption. Evidence for common and cone: public-03 spawn frames 1139 and 3201. No public bucket is present.
- All observed zombies move left at speed 30, exactly 0.48 units per frame. They become displayed around x=1710. Evidence: public-01 frames 1139-2176.
- Contact begins around plant center +80. Common first bite delay is about 50 frames and repeat period about 99; cone delay is about 41 and repeat period about 82. Every bite removes 100 HP. Evidence: public-02 frames 2964/3014/3113/3212 and public-03 frames 5782/5823/5905/5987.
- Peas travel right about 10.667 units per frame and deal 20 damage, exhausting head shield before body HP. Evidence: public-03 frames 3688-4084. A used pea continues visually until it has travelled about 2000 units from its origin.
- Public shooters at even column 2 use a roughly 70-frame cadence; the column-3 shooter uses roughly 89 frames. Evidence: public-03 bullet birth series 3694/3764/3833 and 3688/3778/3867.
- A zombie reaching about x=535 triggers its row mower. The mower kills zombies in its row, including shields. If a later zombie passes the left boundary without a mower, zombies win. Evidence for trigger/kill: public-03 frames 4005 and 5949-5955. The un-mowered loss threshold is an assumption because no public trace contains a loss.
- Dead zombies stop after about 35 frames and remain for about 470 frames. Evidence: public-03 common zombie 3 dies at 4084, stops at 4125, disappears at 4554.
- The level is assumed to contain ten waves and to win after the final wave is dead. No public trace reaches a win; this is recorded as an assumption for long hidden runs.

## Randomness and known uncertainty

- `std::random_device` is implemented exactly as the specified splitmix64 high-32-bit stream. Range conversion uses deterministic multiply-high mapping.
- A portable glibc-compatible `rand()` sequence is seeded from `time_seed` for sun animation and production variation. The documentation exposes both entropy sources, but the three traces do not uniquely identify which subsystem consumes each draw.
- Wave release jitter uses a deterministic seed/wave rule fitted to the observed 32-33 second range. Spawn composition, later-wave progression, sky-sun coordinates, death animation timing, collection cleanup, and win/loss overlay timing remain approximate where the public evidence is insufficient.
