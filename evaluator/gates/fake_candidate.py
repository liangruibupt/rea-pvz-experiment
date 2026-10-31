#!/usr/bin/env python3
"""Operator-only fake candidates for evaluator end-to-end gates.

usage: fake_candidate.py MODE SCENARIO_JSON OUT_TRACE
  identity  copy the oracle trace exactly            -> expect score 1.0
  negative  perturb sun/zombies/plants every frame   -> expect a low score
  random    identity plus a random field per run     -> expect nondeterminism DQ
  static    frame 0 repeated (a game that never moves) -> the pre-registered null baseline
"""
import json
import os
import sys
from pathlib import Path


def main() -> int:
    mode, scenario, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    oracle = scenario.parent / "oracle" / "trace.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with oracle.open() as src, out.open("w") as dst:
        for line in src:
            frame = json.loads(line)
            if mode == "negative":
                frame["sun"] = 0
                frame["wave"] = 0
                frame["z"] = []
                frame["p"] = []
                frame["b"] = []
            elif mode == "random" and frame["f"] == 0:
                frame["nonce"] = os.urandom(8).hex()
            elif mode == "static":
                if frame["f"] == 0:
                    first = frame
                frame = dict(first, f=frame["f"])
            elif mode not in ("identity", "random"):
                raise SystemExit(f"unknown mode {mode}")
            dst.write(json.dumps(frame, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
