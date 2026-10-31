# Arm A: Arm R plus the original program as a black box

Besides everything Arm R has:

1. **The program itself**, `oracle/dist/` (stripped AArch64 ELF `pvz`, its `lib/` and
   `Resources/`), plus a fresh save directory `oracle/home-template/`. You may run it
   yourself, for example under `Xvfb` with screenshots via `ffmpeg -f x11grab`. Copy
   `oracle/home-template/.` into a scratch `HOME` per run, use `XDG_CONFIG_HOME=$HOME/.config`,
   run from inside `oracle/dist/`, and set `LIBGL_ALWAYS_SOFTWARE=1`. Never modify
   `oracle/`.
2. **A trace oracle**: `bin/oracle-query <scenario.json> [out_dir]` plays your scenario on
   the original program and returns its trace in the format of `docs/TRACE_SCHEMA.md`,
   together with the exact mouse events the bot sent (`inputs.txt`) and the exit code (`rc`).
   - Budget: **30 accepted queries** for the whole task. Rejected queries are free.
   - Limits: `end_frame <= 12000`, at most 40 actions. A few seeds are reserved by the
     evaluator and are rejected.
   - The oracle has one slot reserved for you and runs your queries one at a time; no
     other user shares it. One query takes about 1 minute per 3,000 frames (a 9,000-frame
     run is about 3 minutes). Queries submitted together wait for each other, so plan
     them and keep working while they run (for example start them in the background
     with `&`).
   - Calibration scenarios can be queried like any other.

You may not use disassemblers, decompilers or debuggers on the program (no Ghidra, gdb,
objdump -d, radare2, strace/ltrace or similar). Observe it only through running it and
the trace oracle.
