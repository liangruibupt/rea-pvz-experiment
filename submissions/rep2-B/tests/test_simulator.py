#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from simulator import GlibcRand, MinStd, Simulator, SplitMix64


def scenario(actions=None, device_seed=103, time_seed=1700000103, end_frame=100):
    return {
        "schema": 1,
        "level": 4,
        "frame_ms": 16,
        "time_seed": time_seed,
        "device_seed": device_seed,
        "end_frame": end_frame,
        "collect_sun": {"mode": "first_enabled", "every_frames": 0},
        "actions": actions or [],
    }


class SimulatorTests(unittest.TestCase):
    def test_splitmix_seeded_minstd_matches_first_zombie_x(self):
        entropy = SplitMix64(103)
        rng = MinStd(entropy.draw())
        self.assertEqual(rng.uniform(1780, 2280), 1911)

    def test_glibc_stream_matches_first_idle_sun(self):
        rng = GlibcRand(1700000101)
        for _ in range(51):
            rng.draw()
        x = 500 + rng.draw() % 1100
        dx = rng.draw() % 120 - 60
        self.assertEqual((x, dx), (1510, -17))

    def test_successful_plant_action_timing(self):
        action = {"frame": 60, "kind": "plant", "card": "sunflower",
                  "card_index": 0, "row": 2, "col": 1}
        sim = Simulator(scenario([action]))
        for frame in range(76):
            sim.step(frame)
            if frame == 64:
                self.assertEqual((sim.sun_bank, sim.hold), (9950, 0))
        self.assertEqual((len(sim.plants), sim.hold), (1, -1))
        self.assertEqual((sim.plants[0].row, sim.plants[0].col), (2, 1))

    def test_occupied_cell_refunds_and_does_not_cool(self):
        actions = [
            {"frame": 60, "kind": "plant", "card": "sunflower",
             "card_index": 0, "row": 2, "col": 1},
            {"frame": 600, "kind": "plant", "card": "sunflower",
             "card_index": 0, "row": 2, "col": 1},
        ]
        sim = Simulator(scenario(actions, end_frame=620))
        for frame in range(616):
            sim.step(frame)
        self.assertEqual(len(sim.plants), 1)
        self.assertEqual(sim.sun_bank, 9950)
        self.assertTrue(sim.cards[0].state(615, True)["ready"])


if __name__ == "__main__":
    unittest.main()
