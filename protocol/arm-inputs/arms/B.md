# Arm B: Arm A plus REA / Ghidra

You have everything Arm A has (the program in `oracle/dist/`, the trace oracle
`bin/oracle-query` with the same 30-query budget). In addition you may statically analyse
`oracle/dist/pvz` and `oracle/dist/lib/*` with REA and Ghidra; see `rea/REA.md`. The
ban on debuggers and tracers (gdb, strace, ltrace) still applies.
