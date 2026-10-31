"""Scenario parsing for the clean-room Level 4 simulator."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CARD_NAMES = ("sunflower", "peashooter", "wallnut")


@dataclass(frozen=True)
class Action:
    frame: int
    card: str
    card_index: int
    row: int
    col: int


@dataclass(frozen=True)
class Scenario:
    time_seed: int
    device_seed: int
    end_frame: int
    collect_every: int
    actions: tuple[Action, ...]


def _integer(value: Any, name: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def load_scenario(path: str | Path) -> Scenario:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("scenario must be a JSON object")
    if raw.get("schema") != 1 or raw.get("level") != 4 or raw.get("frame_ms") != 16:
        raise ValueError("only schema 1, level 4, frame_ms 16 is supported")
    time_seed = _integer(raw.get("time_seed"), "time_seed")
    device_seed = _integer(raw.get("device_seed"), "device_seed")
    end_frame = _integer(raw.get("end_frame"), "end_frame", 1)
    collect = raw.get("collect_sun")
    if not isinstance(collect, dict) or collect.get("mode") != "first_enabled":
        raise ValueError("collect_sun.mode must be first_enabled")
    collect_every = _integer(collect.get("every_frames"), "collect_sun.every_frames", 0)
    actions_raw = raw.get("actions")
    if not isinstance(actions_raw, list):
        raise ValueError("actions must be a list")
    actions: list[Action] = []
    for n, item in enumerate(actions_raw):
        if not isinstance(item, dict) or item.get("kind") != "plant":
            raise ValueError(f"actions[{n}] must be a plant action")
        index = _integer(item.get("card_index"), f"actions[{n}].card_index", 0)
        card = item.get("card")
        row = _integer(item.get("row"), f"actions[{n}].row", 0)
        col = _integer(item.get("col"), f"actions[{n}].col", 0)
        frame = _integer(item.get("frame"), f"actions[{n}].frame", 0)
        if index >= len(CARD_NAMES) or card != CARD_NAMES[index]:
            raise ValueError(f"actions[{n}] card and card_index disagree")
        if row >= 5 or col >= 9:
            raise ValueError(f"actions[{n}] lawn coordinate is out of range")
        actions.append(Action(frame, card, index, row, col))
    return Scenario(time_seed, device_seed, end_frame, collect_every, tuple(actions))
