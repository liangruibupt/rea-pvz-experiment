#!/usr/bin/env python3
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from simulator import Simulator


BASE = {
    "schema": 1,
    "level": 4,
    "frame_ms": 16,
    "time_seed": 1700000999,
    "device_seed": 999,
    "end_frame": 2500,
    "collect_sun": {"mode": "first_enabled", "every_frames": 0},
    "actions": [],
}


class SimulatorTests(unittest.TestCase):
    def test_deterministic_rows(self):
        a = Simulator(copy.deepcopy(BASE))
        b = Simulator(copy.deepcopy(BASE))
        for frame in range(2000):
            self.assertEqual(a.step(frame), b.step(frame))

    def test_card_and_plant_timing(self):
        sc = copy.deepcopy(BASE)
        sc["actions"] = [{
            "frame": 60, "kind": "plant", "card": "sunflower",
            "card_index": 0, "row": 2, "col": 1,
        }]
        sim = Simulator(sc)
        rows = [sim.step(f) for f in range(76)]
        self.assertEqual(rows[64]["sun"], 9950)
        self.assertEqual(rows[64]["hold"], 0)
        self.assertEqual(rows[75]["hold"], -1)
        self.assertEqual(rows[75]["p"], [{"id": 1, "t": "sunflower", "r": 1, "c": 2, "hp": 300.0}])
        self.assertEqual(rows[75]["cards"][0]["pct"], 100.0)

    def test_initial_cards_and_wave(self):
        sim = Simulator(copy.deepcopy(BASE))
        rows = [sim.step(f) for f in range(1140)]
        self.assertEqual(rows[0]["cards"][0]["ready"], 0)
        self.assertEqual(rows[1]["cards"][0]["ready"], 1)
        self.assertEqual(rows[8]["cards"][0]["en"], 1)
        self.assertEqual(rows[470]["cards"][1]["ready"], 1)
        self.assertEqual(rows[1139]["wave"], 1)
        self.assertEqual(len(rows[1139]["z"]), 1)

    def test_mower_population(self):
        sim = Simulator(copy.deepcopy(BASE))
        rows = [sim.step(f) for f in range(59)]
        self.assertEqual(len(rows[32]["cars"]), 0)
        self.assertEqual(len(rows[33]["cars"]), 1)
        self.assertEqual(len(rows[58]["cars"]), 5)

    def test_occupied_drop_refunds_cost(self):
        sc = copy.deepcopy(BASE)
        sc["actions"] = [
            {"frame": 60, "kind": "plant", "card": "sunflower", "card_index": 0, "row": 0, "col": 0},
            {"frame": 600, "kind": "plant", "card": "sunflower", "card_index": 0, "row": 0, "col": 0},
        ]
        sim = Simulator(sc)
        rows = [sim.step(f) for f in range(616)]
        self.assertEqual(rows[604]["sun"], 9900)
        self.assertEqual(rows[615]["sun"], 9950)
        self.assertEqual(len(rows[615]["p"]), 1)
        self.assertEqual(rows[615]["cards"][0]["ready"], 1)


if __name__ == "__main__":
    unittest.main()
