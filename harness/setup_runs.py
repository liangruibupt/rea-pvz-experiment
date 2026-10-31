#!/usr/bin/env python3
"""Create the R/A/B/C x N run directories for the PvZ REA experiment from frozen inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OP = ROOT / "operator"
INPUTS = OP / "arm-inputs"
SUITE = OP / "scenario-suite"
AIDLC = Path("/home/ubuntu/workspace/rea-mdb-replication-20261025-2333/runs/rep1-C/aidlc")
ELF_SHA = "04c83db7035365985e2d9f5c00adfb401cc97ede12e3c2172532345d415cc424"
FROZEN_DIRS = ["docs", "public", "calibration", "harness", "oracle", "bin", "rea", "aidlc"]
FROZEN_FILES = ["TASK.md", "ARM.md"]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def tree_hashes(run: Path) -> dict[str, str]:
    out = {}
    for name in FROZEN_FILES + FROZEN_DIRS:
        p = run / name
        if p.is_file():
            out[name] = sha(p)
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file():
                    out[str(f.relative_to(run))] = sha(f)
    return out


def make_readonly(p: Path) -> None:
    if p.is_file():
        p.chmod(p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        return
    for f in p.rglob("*"):
        if not f.is_symlink():
            f.chmod(f.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    p.chmod(p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def build(run: Path, arm: str) -> None:
    run.mkdir(parents=True)
    shutil.copy2(INPUTS / "TASK.md", run / "TASK.md")
    shutil.copy2(INPUTS / "arms" / f"{arm}.md", run / "ARM.md")
    shutil.copytree(INPUTS / "docs", run / "docs")
    suite = json.loads((SUITE / "suite.json").read_text())
    pub_meta = suite["splits"]["public"]
    for m in pub_meta:
        d = run / "public" / m["id"]
        d.mkdir(parents=True)
        shutil.copy2(SUITE / "public" / m["id"] / "scenario.json", d / "scenario.json")
        shutil.copy2(SUITE / "public" / m["id"] / "oracle" / "trace.jsonl", d / "trace.jsonl")
        h = run / "harness" / "suite" / "public" / m["id"]
        (h / "oracle").mkdir(parents=True)
        shutil.copy2(SUITE / "public" / m["id"] / "scenario.json", h / "scenario.json")
        shutil.copy2(SUITE / "public" / m["id"] / "oracle" / "trace.jsonl", h / "oracle" / "trace.jsonl")
    (run / "harness" / "suite" / "suite.json").write_text(json.dumps(
        {"schema": 1, "frame_ms": 16, "splits": {"public": pub_meta}}, indent=2, sort_keys=True) + "\n")
    shutil.copy2(OP / "evaluator" / "score.py", run / "harness" / "score.py")
    for m in suite["splits"]["calibration"]:
        d = run / "calibration" / m["id"]
        d.mkdir(parents=True)
        shutil.copy2(SUITE / "calibration" / m["id"] / "scenario.json", d / "scenario.json")
    for d in ("submission", "harness-out"):
        (run / d).mkdir()
    if arm in "ABC":
        shutil.copytree(OP / "runtime" / "dist", run / "oracle" / "dist", symlinks=True)
        shutil.copytree(OP / "runtime" / "home-template", run / "oracle" / "home-template")
        (run / "bin").mkdir()
        shutil.copy2(OP / "oracle-svc" / "oracle-query", run / "bin" / "oracle-query")
        (run / "bin" / "oracle-query").chmod(0o755)
        for d in ("requests", "responses"):
            (run / "oracle-svc" / d).mkdir(parents=True)
        (run / "oracle-results").mkdir()
        assert sha(run / "oracle" / "dist" / "pvz") == ELF_SHA
    if arm in "BC":
        (run / "rea").mkdir()
        shutil.copy2(INPUTS / "rea" / "REA.md", run / "rea" / "REA.md")
        (run / "rea-out").mkdir()
    if arm == "C":
        shutil.copytree(AIDLC, run / "aidlc")
    hashes = tree_hashes(run)
    (run / "freeze.json").write_text(json.dumps({"arm": arm, "files": hashes}, indent=1, sort_keys=True) + "\n")
    for name in FROZEN_FILES + FROZEN_DIRS + ["freeze.json"]:
        if (run / name).exists():
            make_readonly(run / name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--arms", default="RABC")
    args = ap.parse_args()
    root = args.runs_root.resolve()
    manifest = {"elf_sha256": ELF_SHA, "runs": {}}
    for rep in range(1, args.reps + 1):
        for arm in args.arms:
            run = root / f"rep{rep}-{arm}"
            build(run, arm)
            fr = json.loads((run / "freeze.json").read_text())["files"]
            manifest["runs"][run.name] = {"arm": arm, "files": len(fr),
                                          "freeze_sha256": sha(run / "freeze.json")}
            print(run.name, len(fr))
    # common inputs must be byte-identical across arms
    common = None
    for name, info in manifest["runs"].items():
        fr = json.loads((root / name / "freeze.json").read_text())["files"]
        shared = {k: v for k, v in fr.items() if k.split("/")[0] in ("TASK.md", "docs", "public", "calibration", "harness")}
        if common is None:
            common = shared
        elif shared != common:
            raise SystemExit(f"common inputs differ in {name}")
    manifest["common_files"] = len(common)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("common files identical across", len(manifest["runs"]), "runs:", len(common))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
