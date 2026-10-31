# U2 Simulation Core Design

## State model
The simulation owns global wave/economy fields plus ordered collections of cards, plants, zombies, bullets, suns, and mowers. Internal entities carry creation frame and private timers; trace projection exposes only schema fields.

## Clock and ordering
Each iteration advances one 16 ms frame. Scheduled events use integer frame numbers. The update order is: initialize staged objects, handle card-selection events, handle plant-release events, update wave clock/spawns, update suns and collection events, update plants/projectiles, update zombies/collisions/combat, update mowers, then project trace state.

## Determinism
A local SplitMix64 stream seeded by `device_seed` supplies deterministic approximations where the original random transformation was not completely recovered. No wall clock, process-global random state, or iteration over unordered sets may affect output.

## Core rules
- Plants occupy one grid cell; failed occupied placement refunds the card cost and does not start cooldown.
- Cooldowns are frame-based and affordability gates card enablement.
- Zombies move left, become visible at the lawn edge, stop to eat the first live plant in their lane, and attack in 100-HP steps.
- Peashooters fire only when a live zombie is ahead in the lane; bullets deal 20 damage to head shield before body health.
- Falling and produced suns have deterministic motion, clickability, collection flight, credit, and cleanup timers.
- A mower activates at the left trigger, kills intersecting zombies, moves right, and is removed after leaving the lawn.

## Traceability
FR2, FR3, FR4, NFR1, NFR2, NFR5.
