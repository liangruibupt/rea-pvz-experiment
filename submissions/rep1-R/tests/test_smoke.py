#!/usr/bin/env python3
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "submission" / "bin" / "run-scenario"
SCENARIO = ROOT / "public" / "public-01-idle" / "scenario.json"


class SmokeTest(unittest.TestCase):
    def test_deterministic_and_complete(self):
        with tempfile.TemporaryDirectory() as td:
            paths = [Path(td) / "a.jsonl", Path(td) / "b.jsonl"]
            for path in paths:
                subprocess.run([str(RUNNER), str(SCENARIO), str(path)], check=True, cwd=ROOT)
            self.assertEqual(hashlib.sha256(paths[0].read_bytes()).digest(), hashlib.sha256(paths[1].read_bytes()).digest())
            rows = [json.loads(line) for line in paths[0].read_text().splitlines()]
            self.assertEqual([row["f"] for row in rows], list(range(3001)))
            self.assertEqual(rows[0]["sun"], 10000)
            self.assertEqual(rows[1139]["wave"], 1)


if __name__ == "__main__":
    unittest.main()
