"""Command-line entry point for the Level 4 simulator."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pvzsim import run_scenario


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: run-scenario <scenario.json> <out-trace.jsonl>", file=sys.stderr)
        return 2
    source, destination = map(Path, args)
    try:
        scenario = json.loads(source.read_text(encoding="utf-8"))
        with destination.open("w", encoding="utf-8", newline="\n") as out:
            for frame in run_scenario(scenario):
                out.write(json.dumps(frame, separators=(",", ":"), ensure_ascii=False))
                out.write("\n")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"run-scenario: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
