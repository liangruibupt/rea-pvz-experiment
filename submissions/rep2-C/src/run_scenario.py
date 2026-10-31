#!/usr/bin/env python3
"""Run one deterministic Level 4 scenario and stream its JSONL trace."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from scenario import load_scenario
from simulator import Simulation


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: run-scenario <scenario.json> <out-trace.jsonl>", file=sys.stderr)
        return 2
    try:
        scenario = load_scenario(argv[1])
        out = Path(argv[2])
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="\n") as stream:
            for row in Simulation(scenario).run():
                stream.write(json.dumps(row, separators=(",", ":"), ensure_ascii=True))
                stream.write("\n")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"run-scenario: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
