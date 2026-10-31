# REA / Ghidra (arms B and C)

The toolchain lives outside this workspace and is read-only to you. Set, per command:

```bash
T=/home/ubuntu/workspace/rea-toolchains/rea-tc
export JAVA_HOME=$T/jdk-21.0.13+9 PATH=$T/jdk-21.0.13+9/bin:/usr/bin:/bin \
       GHIDRA_INSTALL_DIR=$T/ghidra_12.1.4_PUBLIC \
       XDG_CONFIG_HOME=$PWD/.rea-xdg/config XDG_CACHE_HOME=$PWD/.rea-xdg/cache
REA=/home/ubuntu/workspace/rea-real-software-benchmarks/tools/node_modules/.bin/rea
```

The target is a stripped AArch64 PIE with about 14,000 procedures (game code plus the
statically linked cocos2d-x engine). Analyse it once into a snapshot and reuse it:

```bash
$REA doctor   --target oracle/dist/pvz --provider ghidra --format json --full-output > rea-out/doctor.json
$REA analyze  oracle/dist/pvz --provider ghidra --snapshot rea-out/pvz.rea.json --format json --full-output > rea-out/analyze.json
$REA search   oracle/dist/pvz '<regex>' --kind procedures --mode regex --provider ghidra --snapshot rea-out/pvz.rea.json --format json --full-output > rea-out/<name>.json
$REA search   oracle/dist/pvz '<regex>' --kind strings    --mode regex --provider ghidra --snapshot rea-out/pvz.rea.json --format json --full-output > rea-out/<name>.json
$REA decompile oracle/dist/pvz <FUN_name|0xaddress> --provider ghidra --snapshot rea-out/pvz.rea.json --format json --full-output > rea-out/<name>.json
$REA xrefs    oracle/dist/pvz <FUN_name|0xaddress> --provider ghidra --snapshot rea-out/pvz.rea.json --format json --full-output > rea-out/<name>.json
```

Rules: one REA operation per shell command; write output to files under `rea-out/` and
read them with your file-reading tool; do not loop over many outputs inside one shell
command. Cite REA evidence (procedure/address and file) in `RULES.md`.
