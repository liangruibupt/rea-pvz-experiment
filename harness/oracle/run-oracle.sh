#!/usr/bin/env bash
# Run one scenario on the oracle: the stripped pvz ELF + LD_PRELOAD shim, private Xvfb, fresh HOME.
# usage: run-oracle.sh <scenario> <out_dir> [--shots N]   (--shots: real-time screenshots every N s, exploration only)
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)
O=$(cd "$H/.." && pwd)
SCEN=$(realpath "$1"); OUT=$(realpath -m "$2"); SHOTS=${4:-0}
[ "${3:-}" = "--shots" ] || SHOTS=0
mkdir -p "$OUT"
WORK=$(mktemp -d "${KIROCREW_SCRATCH:-/tmp}/pvzrun.XXXXXX")
cp -a "$O/runtime/home-template/." "$WORK/"
# private X display (server picks a free number and reports it)
DF="$WORK/.display"
Xvfb -displayfd 9 -screen 0 1600x900x24 -nolisten tcp 9>"$DF" >/dev/null 2>&1 &
XPID=$!
trap 'kill $XPID 2>/dev/null || true; rm -rf "$WORK"' EXIT
for i in $(seq 100); do [ -s "$DF" ] && break; sleep 0.1; done
DISP=$(tr -dc '0-9' < "$DF")
cd "$O/runtime/dist"
env -i PATH=/usr/bin:/bin HOME="$WORK" XDG_CONFIG_HOME="$WORK/.config" DISPLAY=:$DISP \
    LIBGL_ALWAYS_SOFTWARE=1 LD_PRELOAD="$H/libpvzoracle.so${EXTRA_PRELOAD:+:$EXTRA_PRELOAD}" PVZ_SYMS="$H/pvz.syms" \
    PVZ_SCENARIO="$SCEN" PVZ_TRACE="$OUT/trace.jsonl" PVZ_EVENTS_OUT="$OUT/events.txt" \
    timeout 1800 ./pvz > "$OUT/stdout.log" 2>&1 &
PID=$!
if [ "$SHOTS" != 0 ]; then
    n=0
    while kill -0 $PID 2>/dev/null; do
        sleep "$SHOTS"; n=$((n+1))
        ffmpeg -loglevel error -y -f x11grab -video_size 1600x900 -i :$DISP -frames:v 1 "$OUT/shot-$(printf %03d $n).png" || true
    done
fi
set +e; wait $PID; RC=$?; set -e
echo "$RC" > "$OUT/rc"
echo "rc=$RC frames=$(wc -l < "$OUT/trace.jsonl" 2>/dev/null || echo 0)"
