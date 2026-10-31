import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "submission" / "src"))

from pvzsim import Game, SplitMix64, validate_scenario


BASE = {
    "schema": 1,
    "level": 4,
    "frame_ms": 16,
    "time_seed": 1700000103,
    "device_seed": 103,
    "end_frame": 100,
    "collect_sun": {"mode": "first_enabled", "every_frames": 0},
    "actions": [],
}


class SimulatorTests(unittest.TestCase):
    def test_splitmix_high_words(self):
        rng = SplitMix64(103)
        self.assertEqual([rng.draw() for _ in range(3)], [434590093, 2835980760, 887559442])

    def test_startup_cards_and_mowers(self):
        game = Game(BASE)
        rows = [game.step() for _ in range(65)]
        self.assertEqual(rows[0]["cards"][0]["ready"], 0)
        self.assertEqual(rows[1]["cards"][0]["ready"], 1)
        self.assertEqual(rows[2]["cards"][1]["pct"], 99.787)
        self.assertEqual(len(rows[33]["cars"]), 1)
        self.assertEqual(len(rows[58]["cars"]), 5)
        self.assertEqual(rows[64]["wbegin"], 1)

    def test_plant_action_cost_and_placement(self):
        scenario = dict(BASE)
        scenario["actions"] = [{"frame": 60, "kind": "plant", "card": "sunflower", "card_index": 0, "row": 2, "col": 1}]
        game = Game(scenario)
        rows = [game.step() for _ in range(76)]
        self.assertEqual(rows[64]["sun"], 9950)
        self.assertEqual(rows[64]["hold"], 0)
        self.assertEqual(rows[75]["hold"], -1)
        self.assertEqual(rows[75]["p"][0]["hp"], 300.0)

    def test_validation(self):
        validate_scenario(BASE)
        bad = dict(BASE, level=3)
        with self.assertRaises(ValueError):
            validate_scenario(bad)

    def test_seeded_first_zombie_matches_public_sequence(self):
        scenario = dict(BASE, end_frame=1140)
        game = Game(scenario)
        rows = [game.step() for _ in range(1140)]
        zombie = rows[1139]["z"][0]
        self.assertEqual((zombie["x"], zombie["y"], zombie["t"]), (1910.52, 682.0, "common"))
        self.assertEqual(rows[1139]["wave"], 1)

    def test_repeat_is_byte_stable(self):
        def digest():
            game = Game(BASE)
            data = "".join(json.dumps(game.step(), separators=(",", ":")) + "\n" for _ in range(101))
            return hashlib.sha256(data.encode()).hexdigest()
        self.assertEqual(digest(), digest())


if __name__ == "__main__":
    unittest.main()
