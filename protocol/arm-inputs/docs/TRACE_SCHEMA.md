# Trace format

One JSON object per line, one line per game frame, `f` = 0, 1, 2, ... strictly increasing.
Numbers printed with three decimals are floats; others are integers. Key order does not
matter to the scorer. Positions are design coordinates (1920x1080, origin bottom-left).
Object `id`s are assigned by the trace writer in order of first appearance and are **not
scored**; objects are matched by type, lane and position.

## Global

| Key | Meaning |
|---|---|
| `f` | game frame number |
| `sun` | sun the player currently has |
| `ts` | game speed multiplier (1.0 in every scenario) |
| `wave` | number of zombie waves released so far |
| `wt` | wave timer, seconds |
| `wbegin` | 1 once the wave system has started |
| `wdead` | 1 when the zombies of the latest wave are all dead |
| `end` | 1 once the end-of-level overlay is shown |
| `zwin` | 1 once zombies have won |
| `hold` | card index held on the cursor, -1 if none |
| `shovel` | 1 while the shovel is held |

## `cards` (always three, in card order)

| Key | Meaning |
|---|---|
| `tag` | card index: 0 sunflower, 1 peashooter, 2 wallnut |
| `ready` | 1 once the card's cooldown bar has finished |
| `pct` | cooldown overlay percentage (100 = fully covered) |
| `en` | 1 when the card button is enabled |

## `p`: plants

| Key | Meaning |
|---|---|
| `t` | `sunflower`, `peashooter` or `wallnut` |
| `r` | **column** index (0-8), as the program stores it |
| `c` | **row** index (0-4, 0 = bottom row), as the program stores it |
| `hp` | current health |

## `z`: zombies

| Key | Meaning |
|---|---|
| `t` | `common`, `cone` or `bucket` (other names may exist in the program) |
| `x`, `y` | position |
| `hp` | body health |
| `hs` | head-shield health (cone/bucket) |
| `bs` | body-shield health |
| `eat` | 1 while eating a plant |
| `alive` | 1 while alive |
| `show` | 1 while the zombie is displayed |
| `spd` | current speed |

## `b`: bullets

| Key | Meaning |
|---|---|
| `x`, `y` | position |
| `used` | 1 once the bullet has hit something |

## `s`: suns (falling and produced)

| Key | Meaning |
|---|---|
| `x`, `y` | position |
| `en` | 1 while the sun can be clicked |

## `cars`: lawn mowers (always five)

| Key | Meaning |
|---|---|
| `tag` | program tag |
| `live` | 1 while running |
| `st` | state code |
| `x` | x position |

Lists keep the order in which the program iterates its own containers; the scorer does not
depend on list order, but the sun-collecting bot does (see `SCENARIO_FORMAT.md`).
