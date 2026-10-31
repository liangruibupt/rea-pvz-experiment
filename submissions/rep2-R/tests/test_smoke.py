#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "submission" / "bin" / "run-scenario"
SCENARIO = ROOT / "public" / "public-01-idle" / "scenario.json"


class SimulatorSmokeTest(unittest.TestCase):
    def run_once(self, directory: Path, name: str) -> Path:
        out = directory / name
        subprocess.run([sys.executable, str(RUNNER), str(SCENARIO), str(out)], check=True, cwd=ROOT)
        return out

    def test_shape_and_determinism(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self.run_once(root, "a.jsonl")
            b = self.run_once(root, "b.jsonl")
            self.assertEqual(hashlib.sha256(a.read_bytes()).digest(), hashlib.sha256(b.read_bytes()).digest())
            rows = [json.loads(line) for line in a.read_text().splitlines()]
            self.assertEqual(len(rows), 3001)
            self.assertEqual([rows[0]["f"], rows[-1]["f"]], [0, 3000])
            self.assertEqual(len(rows[58]["cars"]), 5)
            self.assertEqual(rows[1139]["wave"], 1)
            self.assertEqual(rows[1139]["z"][0]["hp"], 200.0)


if __name__ == "__main__":
    unittest.main()
