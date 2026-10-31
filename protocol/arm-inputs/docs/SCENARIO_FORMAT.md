# Scenario format

A scenario is one JSON object:

```json
{
  "schema": 1, "level": 4, "frame_ms": 16,
  "id": "public-03-single-lane",
  "time_seed": 1700000103,
  "device_seed": 103,
  "end_frame": 6500,
  "collect_sun": {"mode": "first_enabled", "every_frames": 35},
  "actions": [
    {"frame": 60, "kind": "plant", "card": "sunflower", "card_index": 0, "row": 1, "col": 1}
  ]
}
```

Extra keys (`id`, `split`, `purpose`) are informational.

## Time and entropy

- The game runs on a fixed virtual clock: every frame advances game time by exactly
  16 ms, whatever the wall clock does.
- Frame `0` is the first frame after Level 4 has started (menus, map and plant selection
  are already done). Trace line `f` is the state at the end of game frame `f`.
- "Level start" is the moment the level's game layer is created, just before frame 0.
- C `time()` returns `time_seed + floor(virtual seconds elapsed since level start)`.
- `std::random_device` draws come from a splitmix64 stream whose 64-bit state is set to
  `device_seed` at level start. Each draw advances the stream once and returns the high
  32 bits of the output:

  ```text
  state += 0x9E3779B97F4A7C15
  z = state
  z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9
  z = (z ^ (z >> 27)) * 0x94D049BB133111EB
  z = z ^ (z >> 31)
  draw = z >> 32            (all arithmetic modulo 2^64)
  ```
- These are the only external entropy sources. How the program turns them into game
  randomness (for example through the C library's `srand`/`rand` or C++ engines) is
  part of what you have to work out.

## Player actions

The player is a scripted bot that only uses the mouse. Coordinates below are *design*
coordinates: 1920x1080, origin bottom-left. The window is 1280x720, origin top-left, so
`wx = round(x * 1280 / 1920)` and `wy = round((1080 - y) * 720 / 1080)`.

`plant` action at frame `F` with card index `i`, row `r`, column `c` (both zero-based):

| Frame | Mouse event | Position (design) |
|---|---|---|
| F | move | card button `(105, 1008 - 103 * i)` |
| F+2 | press | same |
| F+3 | release | same |
| F+4 | move | lawn cell centre `(570 + 122 * c + 61, 110 + 140 * r + 70)` |
| F+14 | press | same |
| F+15 | release | same |

The game itself decides what those clicks do. Actions are not checked beforehand: a click
on a card that is cooling down or unaffordable, or on an occupied cell, does whatever the
original program does with it. Some scenarios do this on purpose.

`collect_sun.every_frames = N` (0 = never): on every frame `G > 0` with `G % N == 0`, the
bot looks at the suns listed in the previous trace line's `s` array, in that order, and
picks the first one with `en = 1` whose window position lies strictly inside the window
(`0 < wx < 1280` and `0 < wy < 720`). It moves to it at `G`, presses at `G+2` and releases
at `G+3`. If none qualifies it does nothing.

## End of run

The run stops at `end_frame`, or 60 frames after the game decides the result, whichever
comes first. The original program may also stop on its own; the trace then simply ends at
the last frame it wrote. Your trace should end where the original's would.
