#!/usr/bin/env python3
"""Mechanically compare a candidate PVZ trace with sealed oracle traces.

Candidate command contract:
    COMMAND... <scenario.json> <output-trace.jsonl>
The evaluator runs every scenario twice and disqualifies nondeterministic output.
Alternatively, --candidate-root may contain <scenario-id>/trace.jsonl or
<scenario-id>.jsonl files produced earlier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from statistics import mean

CATEGORY_WEIGHTS = {
    "global": 0.20,
    "cards": 0.10,
    "plants": 0.15,
    "zombies": 0.25,
    "bullets": 0.10,
    "suns": 0.10,
    "cars": 0.10,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_trace(path: Path) -> list[dict]:
    rows: list[dict] = []
    last = -1
    with path.open() as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            frame = row.get("f")
            if not isinstance(frame, int) or frame <= last:
                raise ValueError(f"{path}:{lineno}: frame must be a strictly increasing integer")
            last = frame
            rows.append(row)
    if not rows:
        raise ValueError(f"{path}: empty trace")
    return rows


def exact(a, b) -> float:
    return 1.0 if a == b else 0.0


def close(a, b, tolerance: float) -> float:
    try:
        delta = abs(float(a) - float(b))
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(delta):
        return 0.0
    return max(0.0, 1.0 - delta / tolerance) if tolerance > 0 else exact(a, b)


def average(values) -> float:
    vals = list(values)
    return mean(vals) if vals else 1.0


def lane(y) -> int:
    try:
        return int(round((float(y) - 130.0) / 138.0))
    except (TypeError, ValueError):
        return -99


def keyed_score(expected: list[dict], actual: list[dict], key, fields) -> float:
    e = {key(x): x for x in expected}
    a = {key(x): x for x in actual}
    keys = set(e) | set(a)
    if not keys:
        return 1.0
    scores = []
    for k in keys:
        if k not in e or k not in a:
            scores.append(0.0)
            continue
        scores.append(average(fn(e[k].get(name), a[k].get(name)) for name, fn in fields))
    return average(scores)


def grouped_sorted_score(expected: list[dict], actual: list[dict], group, order, fields) -> float:
    eg, ag = defaultdict(list), defaultdict(list)
    for item in expected:
        eg[group(item)].append(item)
    for item in actual:
        ag[group(item)].append(item)
    groups = set(eg) | set(ag)
    if not groups:
        return 1.0
    out = []
    for g in groups:
        es, ac = sorted(eg[g], key=order), sorted(ag[g], key=order)
        size = max(len(es), len(ac))
        if size == 0:
            out.append(1.0)
            continue
        pair_scores = []
        for i in range(size):
            if i >= len(es) or i >= len(ac):
                pair_scores.append(0.0)
            else:
                pair_scores.append(average(fn(es[i].get(name), ac[i].get(name)) for name, fn in fields))
        out.append(average(pair_scores))
    return average(out)


def score_frame(e: dict, a: dict) -> dict[str, float]:
    global_fields = [
        ("sun", exact), ("ts", lambda x, y: close(x, y, 0.01)),
        ("wave", exact), ("wt", lambda x, y: close(x, y, 0.25)),
        ("wbegin", exact), ("wdead", exact), ("end", exact), ("zwin", exact),
        ("hold", exact), ("shovel", exact),
    ]
    global_score = average(fn(e.get(name), a.get(name)) for name, fn in global_fields)

    cards = keyed_score(e.get("cards", []), a.get("cards", []), lambda x: x.get("tag"), [
        ("ready", exact), ("pct", lambda x, y: close(x, y, 2.0)), ("en", exact),
    ])
    plants = keyed_score(e.get("p", []), a.get("p", []),
                         lambda x: (x.get("t"), x.get("r"), x.get("c")), [
        ("hp", lambda x, y: close(x, y, 1.0)),
    ])
    zombies = grouped_sorted_score(e.get("z", []), a.get("z", []),
        lambda x: (x.get("t"), lane(x.get("y"))), lambda x: float(x.get("x", 0)), [
            ("x", lambda x, y: close(x, y, 8.0)),
            ("y", lambda x, y: close(x, y, 3.0)),
            ("hp", lambda x, y: close(x, y, 1.0)),
            ("hs", lambda x, y: close(x, y, 1.0)),
            ("bs", lambda x, y: close(x, y, 1.0)),
            ("eat", exact), ("alive", exact), ("show", exact),
            ("spd", lambda x, y: close(x, y, 0.1)),
        ])
    bullets = grouped_sorted_score(e.get("b", []), a.get("b", []),
        lambda x: lane(x.get("y")), lambda x: float(x.get("x", 0)), [
            ("x", lambda x, y: close(x, y, 10.0)),
            ("y", lambda x, y: close(x, y, 3.0)), ("used", exact),
        ])
    suns = grouped_sorted_score(e.get("s", []), a.get("s", []),
        lambda x: x.get("en"), lambda x: (float(x.get("y", 0)), float(x.get("x", 0))), [
            ("x", lambda x, y: close(x, y, 10.0)),
            ("y", lambda x, y: close(x, y, 10.0)), ("en", exact),
        ])
    cars = grouped_sorted_score(e.get("cars", []), a.get("cars", []),
        lambda x: x.get("tag"), lambda x: float(x.get("x", 0)), [
            ("live", exact), ("st", exact), ("x", lambda x, y: close(x, y, 5.0)),
        ])
    return {"global": global_score, "cards": cards, "plants": plants,
            "zombies": zombies, "bullets": bullets, "suns": suns, "cars": cars}


def score_traces(expected: list[dict], actual: list[dict], sample_every: int, align: int) -> dict:
    actual_by_frame = {x["f"]: x for x in actual}
    sampled = expected[::sample_every]
    if sampled[-1]["f"] != expected[-1]["f"]:
        sampled.append(expected[-1])
    totals: dict[str, list[float]] = {k: [] for k in CATEGORY_WEIGHTS}
    missing = 0
    alignments: dict[int, int] = defaultdict(int)
    for row in sampled:
        frame = row["f"]
        candidate = None
        chosen_delta = 0
        for delta in [0] + [d for n in range(1, align + 1) for d in (-n, n)]:
            if frame + delta in actual_by_frame:
                candidate = actual_by_frame[frame + delta]
                chosen_delta = delta
                break
        if candidate is None:
            missing += 1
            for category in totals:
                totals[category].append(0.0)
            continue
        alignments[chosen_delta] += 1
        scores = score_frame(row, candidate)
        for category, score in scores.items():
            totals[category].append(score)
    categories = {k: average(v) for k, v in totals.items()}
    total = sum(categories[k] * CATEGORY_WEIGHTS[k] for k in CATEGORY_WEIGHTS)
    return {
        "score": total,
        "categories": categories,
        "sampled_frames": len(sampled),
        "missing_frames": missing,
        "alignment_counts": {str(k): v for k, v in sorted(alignments.items())},
        "oracle_frames": len(expected),
        "candidate_frames": len(actual),
    }


def find_candidate(root: Path, scenario_id: str) -> Path:
    options = [root / scenario_id / "trace.jsonl", root / f"{scenario_id}.jsonl"]
    for path in options:
        if path.is_file():
            return path
    raise FileNotFoundError(f"candidate trace missing for {scenario_id}: {options}")


def run_candidate(command: list[str], cwd: Path, scenario: Path, timeout: int) -> tuple[Path, str]:
    scratch = Path(os.environ.get("KIROCREW_SCRATCH", tempfile.gettempdir()))
    run_dir = Path(tempfile.mkdtemp(prefix=f"pvz-eval-{scenario.stem}-", dir=scratch))
    hashes = []
    traces = []
    for n in (1, 2):
        trace = run_dir / f"trace-{n}.jsonl"
        proc = subprocess.run(command + [str(scenario), str(trace)], cwd=cwd,
                              timeout=timeout, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
        (run_dir / f"candidate-{n}.log").write_text(proc.stdout)
        if proc.returncode != 0:
            raise RuntimeError(f"candidate exited {proc.returncode}; log={run_dir / f'candidate-{n}.log'}")
        load_trace(trace)
        hashes.append(sha256(trace))
        traces.append(trace)
    if hashes[0] != hashes[1]:
        raise RuntimeError(f"candidate nondeterministic: {hashes[0]} != {hashes[1]}")
    return traces[0], hashes[0]


def scenario_records(suite_root: Path, splits: set[str]) -> list[tuple[str, str, Path, Path]]:
    suite = json.loads((suite_root / "suite.json").read_text())
    rows = []
    for split in ("public", "calibration", "hidden"):
        if split not in splits:
            continue
        for item in suite["splits"].get(split, []):
            sid = item["id"]
            base = suite_root / split / sid
            rows.append((sid, split, base / "scenario.json", base / "oracle" / "trace.jsonl"))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite-root", type=Path, required=True)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--candidate-root", type=Path)
    source.add_argument("--candidate-command", nargs="+")
    ap.add_argument("--candidate-cwd", type=Path, default=Path.cwd())
    ap.add_argument("--split", action="append", choices=["public", "calibration", "hidden"])
    ap.add_argument("--sample-every", type=int, default=10)
    ap.add_argument("--align-frames", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    splits = set(args.split or ["public", "calibration", "hidden"])
    results = []
    for sid, split, scenario, oracle_path in scenario_records(args.suite_root, splits):
        row = {"id": sid, "split": split, "status": "pending"}
        try:
            if not oracle_path.is_file():
                raise FileNotFoundError(f"oracle trace missing: {oracle_path}")
            if args.candidate_command:
                candidate_path, candidate_hash = run_candidate(
                    args.candidate_command, args.candidate_cwd, scenario, args.timeout)
                row["deterministic"] = True
                row["candidate_sha256"] = candidate_hash
            else:
                candidate_path = find_candidate(args.candidate_root, sid)
                row["candidate_sha256"] = sha256(candidate_path)
            row.update(score_traces(load_trace(oracle_path), load_trace(candidate_path),
                                    args.sample_every, args.align_frames))
            row["oracle_sha256"] = sha256(oracle_path)
            row["status"] = "scored"
        except Exception as exc:
            row.update({"status": "disqualified", "score": 0.0, "error": str(exc)})
        results.append(row)
        print(f"{sid}: {row['status']} {row.get('score', 0):.4f}", flush=True)

    scored = [r for r in results if r["status"] == "scored"]
    by_split = {}
    for split in sorted(splits):
        subset = [r for r in results if r["split"] == split]
        by_split[split] = {
            "score": average(r["score"] for r in subset),
            "scored": sum(r["status"] == "scored" for r in subset),
            "total": len(subset),
        }
    summary = {
        "schema": 1,
        "score": average(r["score"] for r in results),
        "scored": len(scored),
        "total": len(results),
        "sample_every": args.sample_every,
        "align_frames": args.align_frames,
        "category_weights": CATEGORY_WEIGHTS,
        "splits": by_split,
        "scenarios": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"score": summary["score"], "scored": len(scored), "total": len(results)}))
    return 0 if len(scored) == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
