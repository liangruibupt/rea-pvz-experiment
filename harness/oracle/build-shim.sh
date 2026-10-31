#!/usr/bin/env bash
# Build the oracle shim and the operator-only symbol table from the unstripped twin of the ELF.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)
O=$(cd "$H/.." && pwd)
ELF=${1:-$O/build/bin/pvz/pvz}

FLAGS=$(sed -E 's#^/usr/bin/c\+\+ ##' "$H/cxxflags.txt")
# shellcheck disable=SC2086
c++ $FLAGS -fPIC -O1 -fvisibility=hidden -Wno-unused-function \
    -c "$H/shim.cpp" -o "$H/shim.o"
cc -O1 -fPIC -fvisibility=hidden -c "$H/xinput.c" -o "$H/xinput.o"
c++ -shared "$H/shim.o" "$H/xinput.o" -o "$H/libpvzoracle.so" -ldl -lX11 -lXtst

# name hexoffset size  (only sized symbols; vtables, statics, globals, functions)
nm --defined-only -S "$ELF" | awk 'NF==4 {print $4, $1, strtonum("0x"$2)}' > "$H/pvz.syms"
for s in _ZN7Runtime9_instanceE controlLayerInformation buttonLayerInformation _Z12ZombiesGroupB5cxx11 \
         PlantsGroup _Z11BulletGroupB5cxx11 _Z9SunsGroupB5cxx11 _Z9CarsGroupB5cxx11 _ZN7Zombies12_zombieIsWinE \
         _ZN7cocos2dL16s_SharedDirectorE _ZN14GSControlLayerC2Ev; do
    grep -q "^$s " "$H/pvz.syms" || { echo "missing symbol: $s" >&2; exit 1; }
done
echo "shim: $H/libpvzoracle.so  syms: $(wc -l < "$H/pvz.syms")"
