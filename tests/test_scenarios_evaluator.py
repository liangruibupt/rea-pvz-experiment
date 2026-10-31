#!/usr/bin/env python3
import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GEN = load("pvz_scenarios", BASE / "harness" / "scenarios" / "generate_scenarios.py")
SCORE = load("pvz_score", BASE / "evaluator" / "score.py")


def frame(n=0):
    return {
        "f": n, "sun": 100, "ts": 1.0, "wave": 1, "wt": 3.0,
        "wbegin": 1, "wdead": 0, "end": 0, "zwin": 0,
        "hold": -1, "shovel": 0,
        "cards": [{"tag": 0, "ready": 1, "pct": 0.0, "en": 1}],
        "p": [{"id": 99, "t": "peashooter", "r": 2, "c": 3, "hp": 300.0}],
        "z": [{"id": 77, "t": "cone", "x": 1200.0, "y": 406.0,
               "hp": 200.0, "hs": 370.0, "bs": 0.0, "eat": 0,
               "alive": 1, "show": 1, "spd": 30.0}],
        "b": [{"id": 4, "x": 700.0, "y": 406.0, "used": 0}],
        "s": [{"id": 2, "x": 300.0, "y": 500.0, "en": 1}],
        "cars": [{"tag": -1, "live": 0, "st": 1, "x": 455.0}],
    }


class ScenarioTests(unittest.TestCase):
    def test_fixed_partition_and_unique_seeds(self):
        rows = GEN.scenarios()
        counts = {x: sum(s.split == x for s in rows) for x in ("public", "calibration", "hidden")}
        self.assertEqual(counts, {"public": 3, "calibration": 5, "hidden": 8})
        self.assertEqual(len({s.id for s in rows}), 16)
        self.assertEqual(len({(s.time_seed, s.device_seed) for s in rows}), 16)
        for s in rows:
            self.assertGreater(s.end_frame, 0)
            for action in s.plants:
                self.assertIn(action.card, (0, 1, 2))
                self.assertIn(action.row, range(5))
                self.assertIn(action.col, range(9))
                self.assertLess(action.frame, s.end_frame)

    def test_write_only_suite(self):
        scratch = Path(os.environ.get("KIROCREW_SCRATCH", tempfile.gettempdir()))
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            root = Path(tmp) / "suite"
            for s in GEN.scenarios():
                GEN.write_spec(s, root)
            sample = root / "public" / "public-01-idle" / "scenario.json"
            payload = json.loads(sample.read_text())
            self.assertEqual(payload["level"], 4)
            self.assertEqual(payload["frame_ms"], 16)
            self.assertEqual(payload["actions"], [])


class ScoreTests(unittest.TestCase):
    def test_identity_is_one_and_ids_are_ignored(self):
        a = [frame(0), frame(10)]
        b = copy.deepcopy(a)
        b[0]["p"][0]["id"] = 12345
        b[0]["z"][0]["id"] = 54321
        result = SCORE.score_traces(a, b, sample_every=1, align=0)
        self.assertAlmostEqual(result["score"], 1.0)
        self.assertTrue(all(abs(v - 1.0) < 1e-12 for v in result["categories"].values()))

    def test_behavior_error_lowers_relevant_categories(self):
        expected = [frame(0)]
        actual = copy.deepcopy(expected)
        actual[0]["sun"] = 50
        actual[0]["z"][0]["x"] = 1000.0
        actual[0]["z"][0]["hs"] = 0.0
        result = SCORE.score_traces(expected, actual, sample_every=1, align=0)
        self.assertLess(result["score"], 1.0)
        self.assertLess(result["categories"]["global"], 1.0)
        self.assertLess(result["categories"]["zombies"], 1.0)
        self.assertEqual(result["categories"]["plants"], 1.0)

    def test_missing_frame_scores_zero(self):
        expected = [frame(0), frame(10)]
        actual = [frame(0)]
        result = SCORE.score_traces(expected, actual, sample_every=1, align=0)
        self.assertEqual(result["missing_frames"], 1)
        self.assertAlmostEqual(result["score"], 0.5)

    def test_trace_parser_rejects_duplicate_frames(self):
        scratch = Path(os.environ.get("KIROCREW_SCRATCH", tempfile.gettempdir()))
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_text(json.dumps(frame(0)) + "\n" + json.dumps(frame(0)) + "\n")
            with self.assertRaises(ValueError):
                SCORE.load_trace(path)


if __name__ == "__main__":
    unittest.main()
