#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "submission" / "src"))
from simulator import Simulator


class SimulatorTests(unittest.TestCase):
    def scenario(self, **updates):
        data = {"schema": 1, "level": 4, "frame_ms": 16, "time_seed": 1,
                "device_seed": 2, "end_frame": 600,
                "collect_sun": {"mode": "first_enabled", "every_frames": 0},
                "actions": []}
        data.update(updates)
        return data

    def test_known_initial_timing(self):
        sim = Simulator(self.scenario())
        rows = [sim.step(f) for f in range(471)]
        self.assertEqual(rows[0]["sun"], 10000)
        self.assertEqual(len(rows[32]["cars"]), 0)
        self.assertEqual(len(rows[58]["cars"]), 5)
        self.assertEqual(rows[64]["wbegin"], 1)
        self.assertEqual(rows[470]["cards"][1]["ready"], 1)

    def test_plant_action_frames(self):
        action = {"frame": 60, "kind": "plant", "card": "sunflower",
                  "card_index": 0, "row": 2, "col": 1}
        sim = Simulator(self.scenario(actions=[action]))
        rows = [sim.step(f) for f in range(76)]
        self.assertEqual(rows[64]["sun"], 9950)
        self.assertEqual(rows[64]["hold"], 0)
        self.assertEqual(rows[75]["hold"], -1)
        self.assertEqual(rows[75]["p"][0]["hp"], 300.0)

    def test_byte_determinism(self):
        scenario = self.scenario(end_frame=100)
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / "a", Path(td) / "b"
            Simulator(scenario).run(a)
            Simulator(scenario).run(b)
            self.assertEqual(a.read_bytes(), b.read_bytes())


if __name__ == "__main__":
    unittest.main()
