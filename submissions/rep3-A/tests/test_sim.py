#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "bin" / "run-scenario"


class SimulatorTests(unittest.TestCase):
    def run_scenario(self, scenario):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "scenario.json"
            out1 = Path(td) / "one.jsonl"
            out2 = Path(td) / "two.jsonl"
            source.write_text(json.dumps(scenario))
            subprocess.run([str(RUNNER), str(source), str(out1)], check=True)
            subprocess.run([str(RUNNER), str(source), str(out2)], check=True)
            self.assertEqual(out1.read_bytes(), out2.read_bytes())
            return [json.loads(line) for line in out1.read_text().splitlines()]

    def test_initialization_and_first_wave(self):
        rows = self.run_scenario({
            "schema": 1, "level": 4, "frame_ms": 16,
            "time_seed": 1700000101, "device_seed": 101,
            "end_frame": 1140,
            "collect_sun": {"mode": "first_enabled", "every_frames": 0},
            "actions": [],
        })
        self.assertEqual(len(rows), 1141)
        self.assertEqual(rows[0]["sun"], 10000)
        self.assertEqual(rows[58]["cars"].__len__(), 5)
        self.assertEqual(rows[1139]["wave"], 1)
        self.assertEqual(rows[1139]["z"][0]["t"], "common")
        self.assertEqual(rows[1139]["z"][0]["y"], 682.0)

    def test_plant_cost_grid_and_cooldown(self):
        rows = self.run_scenario({
            "schema": 1, "level": 4, "frame_ms": 16,
            "time_seed": 1, "device_seed": 7, "end_frame": 550,
            "collect_sun": {"mode": "first_enabled", "every_frames": 0},
            "actions": [{"frame": 60, "kind": "plant", "card": "sunflower",
                         "card_index": 0, "row": 2, "col": 3}],
        })
        self.assertEqual(rows[64]["sun"], 9950)
        self.assertEqual(rows[75]["p"][0]["r"], 3)
        self.assertEqual(rows[75]["p"][0]["c"], 2)
        self.assertEqual(rows[75]["p"][0]["hp"], 300.0)
        self.assertEqual(rows[544]["cards"][0]["ready"], 1)


if __name__ == "__main__":
    unittest.main()
