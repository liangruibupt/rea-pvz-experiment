#!/usr/bin/env python3
"""Generate deterministic PVZ Level-4 oracle scenarios and optional traces.

The public semantic JSON is the implementation contract.  The operator-only replay
is produced by running the high-level oracle bot once, recording the resulting raw
input events, and replaying those events against the same stripped ELF.  A verified
scenario is accepted only when bot and replay traces are byte-identical.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

# In the original experiment tree this directory was operator/; here it is harness/.
OPERATOR = Path(__file__).resolve().parents[1]
ROOT = OPERATOR.parent
RUNNER = OPERATOR / "oracle" / "run-oracle.sh"
BOOT = OPERATOR / "scenarios" / "boot-level4.txt"
DEFAULT_OUT = OPERATOR / "scenario-suite"

CARD_NAMES = {0: "sunflower", 1: "peashooter", 2: "wallnut"}


@dataclass(frozen=True)
class Plant:
    frame: int
    card: int
    row: int
    col: int


@dataclass(frozen=True)
class Scenario:
    id: str
    split: str
    time_seed: int
    device_seed: int
    bot_seed: int
    end_frame: int
    collect_sun_every: int
    plants: tuple[Plant, ...]
    purpose: str


def p(frame: int, card: int, row: int, col: int) -> Plant:
    return Plant(frame, card, row, col)


def scenarios() -> list[Scenario]:
    # Frames are 16 ms. Some actions intentionally occur during cooldown or target an
    # occupied cell; a faithful implementation must reject them like the oracle.
    return [
        Scenario("public-01-idle", "public", 1700000101, 101, 1, 3000, 0, (),
                 "No plants; observes card readiness, first wave, movement and mower state."),
        Scenario("public-02-sun-economy", "public", 1700000102, 102, 2, 4500, 40,
                 (p(60, 0, 2, 1), p(620, 0, 0, 2), p(1180, 0, 4, 2)),
                 "Sunflower production and dynamic sun collection across rows."),
        Scenario("public-03-single-lane", "public", 1700000103, 103, 3, 6500, 35,
                 (p(60, 0, 1, 1), p(520, 1, 2, 2), p(1040, 1, 2, 3), p(1940, 2, 2, 6)),
                 "Single-lane shooting, repeat placement, wallnut blocking and combat."),

        Scenario("cal-01-five-lane-peas", "calibration", 1700000201, 201, 11, 7600, 35,
                 (p(60, 0, 2, 1), p(500, 1, 0, 2), p(1020, 1, 1, 2), p(1540, 1, 2, 2),
                  p(2060, 1, 3, 2), p(2580, 1, 4, 2), p(3900, 2, 2, 6)),
                 "Projectile and zombie behavior in all five rows."),
        Scenario("cal-02-wall-attrition", "calibration", 1700000202, 202, 12, 9000, 0,
                 (p(1900, 2, 0, 5), p(3800, 2, 2, 5), p(5700, 2, 4, 5), p(5750, 2, 1, 5)),
                 "Wallnut cooldown, failed during-cooldown action, eating and HP loss."),
        Scenario("cal-03-economy-grid", "calibration", 1700000203, 203, 13, 8200, 30,
                 (p(60, 0, 0, 0), p(570, 0, 1, 0), p(1080, 0, 2, 0), p(1590, 0, 3, 0),
                  p(2100, 0, 4, 0), p(2610, 0, 4, 0), p(2800, 1, 2, 2)),
                 "Five-producer economy plus occupied-cell rejection."),
        Scenario("cal-04-late-defense", "calibration", 1700000204, 204, 14, 10000, 40,
                 (p(2300, 1, 0, 2), p(2820, 1, 4, 2), p(3340, 1, 2, 2),
                  p(3900, 2, 2, 5), p(4450, 0, 1, 1)),
                 "Delayed response after zombies have advanced; mower pressure."),
        Scenario("cal-05-mixed", "calibration", 1700000205, 205, 15, 12500, 30,
                 (p(60, 0, 2, 0), p(520, 1, 0, 2), p(1040, 1, 4, 2), p(1560, 1, 2, 2),
                  p(2080, 1, 1, 3), p(2600, 1, 3, 3), p(3900, 2, 2, 6),
                  p(5800, 2, 0, 6), p(7700, 2, 4, 6)),
                 "Long mixed defense exercising waves, shields, bullets, suns and walls."),

        Scenario("hidden-01-idle-loss", "hidden", 1700000301, 301, 21, 11000, 0, (),
                 "Unopposed progression and loss/mower lifecycle."),
        Scenario("hidden-02-center-fort", "hidden", 1700000302, 302, 22, 9000, 28,
                 (p(60, 0, 2, 0), p(520, 1, 2, 2), p(1040, 1, 1, 2),
                  p(1560, 1, 3, 2), p(1950, 2, 2, 6)),
                 "Center-heavy mixed defense under a held-out entropy stream."),
        Scenario("hidden-03-edge-fort", "hidden", 1700000303, 303, 23, 9500, 37,
                 (p(60, 0, 0, 0), p(570, 0, 4, 0), p(1080, 1, 0, 2), p(1600, 1, 4, 2),
                  p(2120, 1, 2, 3), p(3900, 2, 0, 6), p(5800, 2, 4, 6)),
                 "Edge-lane coverage and held-out spawn ordering."),
        Scenario("hidden-04-cooldown-pressure", "hidden", 1700000304, 304, 24, 8500, 0,
                 (p(60, 1, 0, 1), p(100, 1, 1, 1), p(520, 1, 1, 1), p(540, 1, 2, 1),
                  p(1040, 1, 2, 1), p(1900, 2, 3, 5), p(2000, 2, 4, 5),
                  p(3800, 2, 4, 5)),
                 "Intentional cooldown violations and recovery at readiness boundaries."),
        Scenario("hidden-05-sun-saturation", "hidden", 1700000305, 305, 25, 10000, 20,
                 (p(60, 0, 0, 0), p(570, 0, 1, 0), p(1080, 0, 2, 0), p(1590, 0, 3, 0),
                  p(2100, 0, 4, 0), p(2700, 1, 0, 2), p(3220, 1, 4, 2)),
                 "Dense dynamic sun collection and economy state."),
        Scenario("hidden-06-shield-waves", "hidden", 1700000306, 306, 26, 13000, 32,
                 (p(60, 0, 2, 0), p(520, 1, 0, 2), p(1040, 1, 1, 2), p(1560, 1, 2, 2),
                  p(2080, 1, 3, 2), p(2600, 1, 4, 2), p(3900, 2, 1, 6),
                  p(5800, 2, 3, 6)),
                 "Longer wave sample emphasizing cone/bucket shield depletion."),
        Scenario("hidden-07-asymmetric", "hidden", 1700000307, 307, 27, 12000, 43,
                 (p(60, 0, 4, 1), p(520, 1, 4, 2), p(1040, 1, 3, 3),
                  p(1560, 1, 1, 4), p(2080, 1, 0, 5), p(3900, 2, 3, 7)),
                 "Asymmetric columns reveal row, range and collision assumptions."),
        Scenario("hidden-08-long-mixed", "hidden", 1700000308, 308, 28, 18000, 30,
                 (p(60, 0, 2, 0), p(570, 0, 0, 0), p(1080, 0, 4, 0),
                  p(520, 1, 0, 2), p(1040, 1, 4, 2), p(1560, 1, 2, 2),
                  p(2080, 1, 1, 3), p(2600, 1, 3, 3), p(3900, 2, 2, 6),
                  p(5800, 2, 0, 6), p(7700, 2, 4, 6), p(9600, 2, 1, 7),
                  p(11500, 2, 3, 7)),
                 "Longest held-out mixed trace for late waves and cumulative drift."),
    ]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def boot_lines() -> list[str]:
    return [line.rstrip() for line in BOOT.read_text().splitlines() if line.strip()]


def semantic_payload(s: Scenario) -> dict:
    return {
        "schema": 1,
        "id": s.id,
        "split": s.split,
        "level": 4,
        "frame_ms": 16,
        "time_seed": s.time_seed,
        "device_seed": s.device_seed,
        "end_frame": s.end_frame,
        "collect_sun": {"mode": "first_enabled", "every_frames": s.collect_sun_every},
        "actions": [
            {"frame": x.frame, "kind": "plant", "card": CARD_NAMES[x.card],
             "card_index": x.card, "row": x.row, "col": x.col}
            for x in s.plants
        ],
        "purpose": s.purpose,
    }


def header(s: Scenario, include_bot_seed: bool = False) -> list[str]:
    lines = [f"time_seed {s.time_seed}", f"device_seed {s.device_seed}"]
    if include_bot_seed:
        lines.append(f"bot_seed {s.bot_seed}")
    lines += ["boot_max 3000", f"end_frame {s.end_frame}", "post_result_frames 60"]
    lines += boot_lines()
    return lines


def write_spec(s: Scenario, out_root: Path) -> Path:
    d = out_root / s.split / s.id
    d.mkdir(parents=True, exist_ok=True)
    spec = d / "scenario.json"
    spec.write_text(json.dumps(semantic_payload(s), indent=2, sort_keys=True) + "\n")
    bot = d / "bot.txt"
    lines = header(s, True)
    lines += [f"bot_plant {x.frame} {x.card} {x.row} {x.col}" for x in s.plants]
    if s.collect_sun_every:
        lines.append(f"bot_collect_sun {s.collect_sun_every}")
    bot.write_text("\n".join(lines) + "\n")
    return d


def run_checked(s: Scenario, out_root: Path, verify: bool) -> dict:
    d = write_spec(s, out_root)
    scratch_base = Path(os.environ.get("KIROCREW_SCRATCH", tempfile.gettempdir()))
    tmp = Path(tempfile.mkdtemp(prefix=f"pvz-{s.id}-", dir=scratch_base))
    try:
        bot_out = tmp / "bot"
        subprocess.run([str(RUNNER), str(d / "bot.txt"), str(bot_out)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        events = (bot_out / "events.txt").read_text().splitlines()
        replay = d / "replay.txt"
        replay.write_text("\n".join(header(s) + events) + "\n")
        oracle = d / "oracle"
        if oracle.exists():
            shutil.rmtree(oracle)
        if verify:
            subprocess.run([str(RUNNER), str(replay), str(oracle)], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            bot_hash = sha256(bot_out / "trace.jsonl")
            replay_hash = sha256(oracle / "trace.jsonl")
            if bot_hash != replay_hash:
                raise RuntimeError(f"{s.id}: bot/replay trace mismatch {bot_hash} != {replay_hash}")
        else:
            shutil.copytree(bot_out, oracle)
            bot_hash = replay_hash = sha256(oracle / "trace.jsonl")
        meta = {
            "id": s.id,
            "split": s.split,
            "scenario_sha256": sha256(d / "scenario.json"),
            "replay_sha256": sha256(replay),
            "trace_sha256": replay_hash,
            "frames": sum(1 for _ in (oracle / "trace.jsonl").open()),
            "raw_input_events": len(events),
            "verified_replay": verify,
        }
        (d / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        return meta
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def completed_meta(s: Scenario, out_root: Path, verify: bool) -> dict | None:
    """Return stored meta only when every recorded hash still matches disk."""
    d = out_root / s.split / s.id
    meta_path = d / "meta.json"
    trace = d / "oracle" / "trace.jsonl"
    if not (meta_path.is_file() and trace.is_file() and (d / "replay.txt").is_file()):
        return None
    meta = json.loads(meta_path.read_text())
    if verify and not meta.get("verified_replay"):
        return None
    if (meta.get("scenario_sha256") != sha256(d / "scenario.json")
            or meta.get("replay_sha256") != sha256(d / "replay.txt")
            or meta.get("trace_sha256") != sha256(trace)
            or meta.get("frames") != sum(1 for _ in trace.open())):
        return None
    return meta


def protect_hidden(out_root: Path) -> None:
    hidden = out_root / "hidden"
    if not hidden.exists():
        return
    hidden.chmod(0o700)
    for path in hidden.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--materialize", action="store_true", help="run the stripped oracle")
    ap.add_argument("--verify", action="store_true", help="replay captured raw inputs and require byte identity")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--resume", action="store_true",
                    help="reuse scenarios whose meta.json hashes still match; rerun the rest")
    ap.add_argument("--split", choices=["public", "calibration", "hidden"])
    args = ap.parse_args()
    chosen = [s for s in scenarios() if not args.split or s.split == args.split]
    args.out.mkdir(parents=True, exist_ok=True)
    for s in chosen:
        write_spec(s, args.out)

    results: list[dict] = []
    if args.materialize:
        pending = []
        for s in chosen:
            meta = completed_meta(s, args.out, args.verify) if args.resume else None
            if meta is None:
                pending.append(s)
            else:
                results.append(meta)
                print(f"{s.id}: reused {meta['trace_sha256'][:12]}", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            futures = {pool.submit(run_checked, s, args.out, args.verify): s for s in pending}
            for future in concurrent.futures.as_completed(futures):
                meta = future.result()
                results.append(meta)
                print(f"{meta['id']}: {meta['frames']} frames {meta['trace_sha256'][:12]}", flush=True)
    else:
        results = [{"id": s.id, "split": s.split} for s in chosen]

    results.sort(key=lambda x: x["id"])
    manifest = {
        "schema": 1,
        "reference_commit": "cbc4c83dee9407dc3d82ca869ebf13b450bab382",
        "stripped_elf_sha256": "04c83db7035365985e2d9f5c00adfb401cc97ede12e3c2172532345d415cc424",
        "frame_ms": 16,
        "splits": {name: [x for x in results if x["split"] == name]
                   for name in ("public", "calibration", "hidden")},
        "materialized": args.materialize,
        "verified_replay": bool(args.materialize and args.verify),
    }
    (args.out / "suite.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    protect_hidden(args.out)
    print(json.dumps({k: len(v) for k, v in manifest["splits"].items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
