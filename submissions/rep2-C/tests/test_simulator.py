from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from scenario import load_scenario
from simulator import Simulation


class SimulatorTests(unittest.TestCase):
    def scenario(self, *, end=2000, actions=(), collect=0):
        return {
            "schema": 1,
            "level": 4,
            "frame_ms": 16,
            "time_seed": 1700000999,
            "device_seed": 999,
            "end_frame": end,
            "collect_sun": {"mode": "first_enabled", "every_frames": collect},
            "actions": list(actions),
        }

    def load(self, data):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scenario.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_scenario(path)

    def test_rejects_wrong_level(self):
        data = self.scenario()
        data["level"] = 3
        with self.assertRaises(ValueError):
            self.load(data)

    def test_startup_and_first_wave(self):
        rows = list(Simulation(self.load(self.scenario(end=1140))).run())
        self.assertEqual(rows[0]["cards"][0]["ready"], 0)
        self.assertEqual(rows[1]["cards"][0]["ready"], 1)
        self.assertEqual(rows[8]["cards"][0]["en"], 1)
        self.assertEqual(len(rows[58]["cars"]), 5)
        self.assertEqual(rows[1139]["wave"], 1)
        self.assertEqual(len(rows[1139]["z"]), 1)

    def test_occupied_cell_refunds(self):
        action = lambda frame: {
            "frame": frame,
            "kind": "plant",
            "card": "sunflower",
            "card_index": 0,
            "row": 2,
            "col": 1,
        }
        rows = list(Simulation(self.load(self.scenario(end=700, actions=[action(60), action(620)]))).run())
        self.assertEqual(len(rows[635]["p"]), 1)
        self.assertEqual(rows[635]["sun"], 9950)
        self.assertEqual(rows[635]["cards"][0]["ready"], 1)

    def test_deterministic_rows(self):
        scenario = self.load(self.scenario(end=800, collect=35))
        def digest():
            encoded = "".join(json.dumps(row, sort_keys=True) + "\n" for row in Simulation(scenario).run())
            return hashlib.sha256(encoded.encode()).hexdigest()
        self.assertEqual(digest(), digest())


if __name__ == "__main__":
    unittest.main()
