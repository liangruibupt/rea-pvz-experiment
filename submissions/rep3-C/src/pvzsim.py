"""Deterministic, headless approximation of the observed Level 4 game."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

MASK64 = (1 << 64) - 1
MINSTD_MOD = 2147483647


class SplitMix64:
    def __init__(self, seed: int):
        self.state = seed & MASK64

    def draw(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        z ^= z >> 31
        return (z >> 32) & 0xFFFFFFFF


class MinStd:
    """libstdc++ default_random_engine (minstd_rand0) and integer distribution."""

    def __init__(self, seed: int):
        self.state = seed % MINSTD_MOD or 1

    def raw(self) -> int:
        self.state = (self.state * 16807) % MINSTD_MOD
        return self.state

    def integer(self, low: int, high: int) -> int:
        width = high - low + 1
        return low + ((self.raw() - 1) * width // (MINSTD_MOD - 1))


@dataclass
class Card:
    tag: int
    cost: int
    duration: int
    ready_at: int
    enabled_at: int
    cooldown_start: int | None = None

    def state(self, frame: int, sun: int, held: int) -> dict[str, Any]:
        ready = frame >= self.ready_at
        if held == self.tag and ready:
            pct = 100.0
        elif ready:
            pct = 0.0
        else:
            start = 1 if self.cooldown_start is None else self.cooldown_start
            elapsed = max(0, frame - start)
            pct = max(0.0, 100.0 - elapsed * 100.0 * 0.016 / (self.duration * 0.016))
        enabled = ready and frame >= self.enabled_at and sun >= self.cost
        return {"tag": self.tag, "ready": int(ready), "pct": round(pct, 3), "en": int(enabled)}

    def use(self, frame: int) -> None:
        self.cooldown_start = frame
        self.ready_at = frame + self.duration
        self.enabled_at = self.ready_at + (1 if self.tag == 0 else 0)


class Game:
    COSTS = (50, 100, 50)
    COOLDOWNS = (469, 469, 1875)
    PLANT_HP = {"sunflower": 300.0, "peashooter": 300.0, "wallnut": 3000.0}
    WAVE_BASE = (1, 3, 3, 3, 10, 4, 3, 3, 4, 10)
    TYPE_PROBS = ((100, 0, 0), (95, 5, 0), (90, 10, 0), (85, 10, 5),
                  (80, 15, 5), (75, 15, 10), (70, 20, 10), (60, 25, 15),
                  (50, 30, 20), (40, 30, 30))

    def __init__(self, scenario: dict[str, Any]):
        validate_scenario(scenario)
        self.scenario = scenario
        self.frame = -1
        self.sun = 10000
        self.hold = -1
        self.wave = 0
        self.wt = 0
        self.wbegin = 0
        self.wdead = 0
        self.end = 0
        self.zwin = 0
        self.end_at: int | None = None
        self.cards = [Card(0, 50, 469, 1, 8), Card(1, 100, 469, 470, 470), Card(2, 50, 1875, 1876, 1876)]
        self.plants: list[dict[str, Any]] = []
        self.zombies: list[dict[str, Any]] = []
        self.bullets: list[dict[str, Any]] = []
        self.suns: list[dict[str, Any]] = []
        self.mowers: list[dict[str, Any]] = []
        self.next_ids = {"p": 1, "z": 1, "b": 1, "s": 1}
        self.actions_select: dict[int, list[dict[str, Any]]] = {}
        self.actions_place: dict[int, list[dict[str, Any]]] = {}
        for action in scenario.get("actions", []):
            self.actions_select.setdefault(action["frame"] + 4, []).append(action)
            self.actions_place.setdefault(action["frame"] + 15, []).append(action)
        self.pending_action: dict[str, Any] | None = None
        self.collect_every = scenario.get("collect_sun", {}).get("every_frames", 0)
        self.collect_targets: dict[int, int] = {}
        self.credit_frames: dict[int, int] = {}
        sm = SplitMix64(int(scenario["device_seed"]))
        draws = [sm.draw() for _ in range(15)]
        self.x_rng = MinStd(draws[0])
        self.type_rng = MinStd(draws[14])
        self.misc_rng = MinStd(draws[2])
        self.lane_rng = MinStd(int(scenario["time_seed"]))
        self.lanes_used: set[int] = set()
        self.sun_rng = MinStd((int(scenario["time_seed"]) ^ 0x5F3759DF) & 0xFFFFFFFF)
        self.wave_start = 64
        self.wave_off: int | None = 1133
        self.wave_spawn: int | None = None
        self.wave_threshold = 18
        self.sky_sun_next = 314
        self.sky_sun_index = 0

    def step(self) -> dict[str, Any]:
        self.frame += 1
        f = self.frame
        self._init_mowers()
        self._inputs()
        self._cards_tick()
        self._wave_tick()
        self._sun_tick()
        self._plants_tick()
        self._bullets_tick()
        self._zombies_tick()
        self._mowers_tick()
        self._cleanup()
        return self.snapshot()

    def _init_mowers(self) -> None:
        if self.frame in (33, 39, 45, 51, 58):
            lane = len(self.mowers)
            self.mowers.append({"lane": lane, "tag": -1, "live": 0, "st": 1,
                                "x": 455.0, "spent": False, "born": self.frame})

    def _inputs(self) -> None:
        f = self.frame
        for action in self.actions_select.get(f, []):
            idx = int(action["card_index"])
            states = [c.state(f, self.sun, self.hold) for c in self.cards]
            if self.hold == -1 and states[idx]["en"]:
                self.sun -= self.cards[idx].cost
                self.hold = idx
                self.pending_action = action
        for action in self.actions_place.get(f, []):
            idx = int(action["card_index"])
            if self.hold != idx or self.pending_action is not action:
                continue
            col, row = int(action["col"]), int(action["row"])
            occupied = any(p["col"] == col and p["row"] == row and p["hp"] > 0 for p in self.plants)
            if occupied:
                self.sun += self.cards[idx].cost
            else:
                kind = ("sunflower", "peashooter", "wallnut")[idx]
                plant = {"id": self.next_ids["p"], "t": kind, "col": col, "row": row,
                         "hp": self.PLANT_HP[kind], "born": f, "remove_at": None,
                         "next_sun": None, "next_shot": None}
                self.next_ids["p"] += 1
                if kind == "sunflower":
                    plant["next_sun"] = f + (313 if plant["id"] % 2 == 0 else 376)
                self.plants.append(plant)
                self.cards[idx].use(f)
            self.hold = -1
            self.pending_action = None

    def _cards_tick(self) -> None:
        return

    def _wave_size(self, wave_number: int) -> int:
        base = self.WAVE_BASE[(wave_number - 1) % len(self.WAVE_BASE)]
        s = int(self.scenario["device_seed"])
        if wave_number == 1:
            return 1
        if wave_number == 2:
            return base + ((3 * s * s + 4 * s + 12) % 13) % 3
        if wave_number == 3:
            return base + ((4 * s + 3) % 11) % 3
        if wave_number == 4:
            return base + (s % 4) % 3
        if wave_number % 5 == 0:
            return base + 3 + ((s * 7 + wave_number) % 3)
        return base + self.misc_rng.integer(0, 2)

    def _next_threshold(self) -> int:
        s = int(self.scenario["device_seed"])
        if self.wave == 1:
            return 32 + ((10 * s + 7) % 13) % 3
        if self.wave == 2:
            return 32
        if self.wave in (3, 8):
            alive = sum(1 for z in self.zombies if z["alive"])
            return 45 if alive > 4 else 27
        return 32 + self.misc_rng.integer(-2, 2)

    def _wave_tick(self) -> None:
        f = self.frame
        if f == self.wave_start:
            self.wbegin = 1
            self.wt = 1
        if self.wbegin:
            self.wt = 1 + max(0, int((f - self.wave_start) * 0.016))
        if self.wave_off is not None and f >= self.wave_off:
            self.wbegin = 0
            self.wdead = 1
            self.wave_spawn = f + 6
            self.wave_off = None
        if self.wave_spawn is not None and f >= self.wave_spawn:
            self.wave += 1
            self.wt = 0
            self.wdead = 0
            self._spawn_wave(self.wave)
            self.wave_spawn = None
            alive = sum(1 for z in self.zombies if z["alive"])
            if self.wave in (4, 9) and alive <= self._wave_size(self.wave) + 4:
                self.wave_spawn = f + 6
            elif self.wave < 10:
                delay = 50 if self.wave == 1 else 51
                self.wave_start = f + delay
                self.wave_threshold = self._next_threshold()
                scheduler_lag = 6 if self.wave == 1 else 31
                self.wave_off = int(round(self.wave_start + (self.wave_threshold - 1) * 62.5 + scheduler_lag))

    def _spawn_wave(self, number: int) -> None:
        count = self._wave_size(number)
        for _ in range(count):
            if len(self.lanes_used) == 5:
                self.lanes_used.clear()
            lane = self.lane_rng.integer(0, 4)
            while lane in self.lanes_used:
                lane = self.lane_rng.integer(0, 4)
            self.lanes_used.add(lane)
            q = self.type_rng.integer(0, 99)
            probs = self.TYPE_PROBS[min(number - 1, len(self.TYPE_PROBS) - 1)]
            common_cut = 90 if number in (2, 3) else probs[0]
            if q < common_cut:
                kind, shield = "common", 0.0
            elif q < common_cut + probs[1]:
                kind, shield = "cone", 600.0
            else:
                kind, shield = "bucket", 1200.0
            x0 = float(self.x_rng.integer(1780, 2280))
            self.zombies.append({"id": self.next_ids["z"], "t": kind, "lane": lane,
                                 "x": x0, "y": float(130 + 138 * lane), "hp": 200.0,
                                 "hs": shield, "bs": 0.0, "eat": 0, "alive": 1,
                                 "show": 0, "spd": 30.0, "born": self.frame,
                                 "bite_at": None, "stop_at": None, "remove_at": None,
                                 "death_kind": None})
            self.next_ids["z"] += 1

    def _sky_x(self) -> float:
        # The original uses a separate time-derived random stream. Keep the same observed range.
        return float(self.sun_rng.integer(550, 1530))

    def _create_sun(self, x: float, y: float, source: str, owner: int | None = None) -> None:
        self.suns.append({"id": self.next_ids["s"], "x": x, "y": y, "en": 1,
                          "born": self.frame, "source": source, "owner": owner,
                          "target_y": float(349 + 32 * (self.sky_sun_index % 4)) if source == "sky" else y,
                          "collect_at": None, "credit_at": None, "remove_at": None,
                          "collect_x": x, "collect_y": y})
        self.next_ids["s"] += 1

    def _sun_tick(self) -> None:
        f = self.frame
        if f == self.sky_sun_next:
            self._create_sun(self._sky_x(), 1150.001, "sky")
            self.sky_sun_index += 1
            self.sky_sun_next += 1562 if self.sky_sun_index % 2 else 1563
        # The bot chooses from the previous end-of-frame list on every collection cadence.
        if self.collect_every and f > 0 and f % self.collect_every == 0:
            for sun in self.suns:
                if sun["en"] and 0.0 < sun["x"] < 1920.0 and 0.0 < sun["y"] < 1080.0:
                    self.collect_targets[f + 3] = sun["id"]
                    break
        sid = self.collect_targets.pop(f, None)
        if sid is not None:
            for sun in self.suns:
                if sun["id"] == sid and sun["en"]:
                    sun["en"] = 0
                    sun["collect_at"] = f
                    sun["collect_x"], sun["collect_y"] = sun["x"], sun["y"]
                    sun["credit_at"] = f + 44
                    sun["remove_at"] = f + 388
                    break
        for sun in self.suns:
            age = f - sun["born"]
            if sun["credit_at"] == f:
                self.sun += 50
            if not sun["en"] and sun["collect_at"] is not None:
                t = min(1.0, (f - sun["collect_at"]) / 36.0)
                # Exponential-looking ease-out used by cocos actions.
                e = 1.0 - (1.0 - t) ** 4
                sun["x"] = sun["collect_x"] + (290.0 - sun["collect_x"]) * e
                sun["y"] = sun["collect_y"] + (1010.0 - sun["collect_y"]) * e
            elif sun["source"] == "sky":
                if age <= 40:
                    sun["y"] = 1150.001 + 105.0 * (4.0 * (age / 40.0) * (1.0 - age / 40.0))
                elif sun["y"] > sun["target_y"]:
                    sun["y"] = max(sun["target_y"], sun["y"] - 2.56)
                elif sun["remove_at"] is None:
                    sun["remove_at"] = f + 1000
            else:
                if age <= 20:
                    sun["y"] = sun["target_y"] + 140.0 * (2.0 * (age / 40.0) - (age / 40.0) ** 2)
                elif age <= 40:
                    q = (40 - age) / 20.0
                    sun["y"] = sun["target_y"] + 105.0 * max(0.0, q)

    def _plants_tick(self) -> None:
        f = self.frame
        for p in self.plants:
            if p["hp"] <= 0:
                if p["remove_at"] is None:
                    p["remove_at"] = f + 1
                continue
            if p["t"] == "sunflower" and p["next_sun"] == f:
                self._create_sun(float(630 + 122 * p["col"]), float(123 + 138 * p["row"]), "plant", p["id"])
                base = 1468 + ((1 - int(self.scenario["device_seed"]) % 3) % 3) * 63
                interval = base + (p["id"] - 1) * 63
                p["next_sun"] = f + interval
            elif p["t"] == "peashooter":
                origin = 700.0 + 122.0 * p["col"]
                target = any(z["alive"] and z["show"] and z["lane"] == p["row"] and z["x"] > origin - 40 for z in self.zombies)
                if not target:
                    p["next_shot"] = None
                elif p["next_shot"] is None:
                    p["next_shot"] = f + (87 if p["col"] >= 3 else 93)
                elif f >= p["next_shot"]:
                    self.bullets.append({"id": self.next_ids["b"], "lane": p["row"],
                                         "x": origin, "y": float(208 + 138 * p["row"]),
                                         "used": 0, "born": f, "remove_at": f + 189})
                    self.next_ids["b"] += 1
                    if p["col"] >= 3:
                        period = 90
                    elif p["row"] < 2:
                        period = 78
                    elif p["row"] == 2:
                        period = 70
                    else:
                        period = 63
                    p["next_shot"] = f + period

    def _bullets_tick(self) -> None:
        f = self.frame
        for b in self.bullets:
            if f > b["born"]:
                b["x"] += 10.6666667
            if b["used"]:
                continue
            candidates = [z for z in self.zombies if z["alive"] and z["lane"] == b["lane"] and z["show"] and b["x"] >= z["x"] - 22.0]
            if candidates:
                z = min(candidates, key=lambda q: q["x"])
                b["used"] = 1
                if z["hs"] > 0:
                    z["hs"] = max(0.0, z["hs"] - 20.0)
                elif z["bs"] > 0:
                    z["bs"] = max(0.0, z["bs"] - 20.0)
                else:
                    z["hp"] = max(0.0, z["hp"] - 20.0)
                    if z["hp"] == 0 and z["alive"]:
                        self._kill_zombie(z, "pea")

    def _kill_zombie(self, z: dict[str, Any], kind: str) -> None:
        z["alive"] = 0
        z["eat"] = 0
        z["death_kind"] = kind
        z["stop_at"] = self.frame + (35 if kind == "mower" else 42)
        z["remove_at"] = self.frame + (315 if kind == "mower" else 470)
        if kind == "mower":
            z["hp"] = z["hs"] = z["bs"] = 0.0

    def _zombies_tick(self) -> None:
        f = self.frame
        for z in self.zombies:
            if not z["alive"]:
                if z["stop_at"] is not None and f >= z["stop_at"]:
                    z["spd"] = 0.0
                continue
            if z["spd"]:
                z["x"] -= z["spd"] * 0.016
            if not z["show"] and z["x"] < 1710.0:
                z["show"] = 1
            if z["eat"]:
                plant = next((p for p in self.plants if p["id"] == z.get("eating_id") and p["hp"] > 0), None)
                if plant is None:
                    z["eat"] = 0
                    z["spd"] = 30.0
                    z["bite_at"] = None
                elif z["bite_at"] is not None and f >= z["bite_at"]:
                    plant["hp"] = max(0.0, plant["hp"] - 100.0)
                    z["bite_at"] = f + (82 if z["t"] == "cone" else 99)
                    if plant["hp"] <= 0:
                        plant["remove_at"] = f + 1
                continue
            candidates = [p for p in self.plants if p["hp"] > 0 and p["row"] == z["lane"]]
            if candidates:
                plant = max(candidates, key=lambda p: p["col"])
                px = 631.0 + 122.0 * plant["col"]
                if z["x"] <= px + 79.0 and z["x"] > px - 90.0:
                    z["eat"] = 1
                    z["spd"] = 0.0
                    z["eating_id"] = plant["id"]
                    z["bite_at"] = f + (41 if z["t"] == "cone" else 50)
                    continue
            mower = next((m for m in self.mowers if m["lane"] == z["lane"] and not m["spent"]), None)
            if z["x"] < 535.0:
                if mower is not None:
                    mower["live"] = 1
                    mower["st"] = 2
                    mower["spent"] = True
                    self._kill_zombie(z, "mower")
                elif z["x"] <= 430.0 and not self.end:
                    self.zwin = 1
                    self.end = 1
                    self.end_at = f

    def _mowers_tick(self) -> None:
        for m in self.mowers:
            if not m["live"]:
                continue
            if self.frame > m.get("triggered", self.frame):
                m["x"] += 12.16
            else:
                m["triggered"] = self.frame
            for z in self.zombies:
                if z["alive"] and z["lane"] == m["lane"] and z["x"] <= m["x"] + 82.0:
                    self._kill_zombie(z, "mower")
            if m["x"] > 2100.0:
                m["remove"] = True

    def _cleanup(self) -> None:
        f = self.frame
        self.plants = [p for p in self.plants if p["remove_at"] is None or f < p["remove_at"]]
        self.bullets = [b for b in self.bullets if f < b["remove_at"]]
        self.suns = [s for s in self.suns if s["remove_at"] is None or f < s["remove_at"]]
        self.zombies = [z for z in self.zombies if z["remove_at"] is None or f < z["remove_at"]]
        self.mowers = [m for m in self.mowers if not m.get("remove")]

    def snapshot(self) -> dict[str, Any]:
        f = self.frame
        cards = [c.state(f, self.sun, self.hold) for c in self.cards]
        return {
            "f": f, "sun": self.sun, "ts": 1.0, "wave": self.wave, "wt": float(self.wt),
            "wbegin": self.wbegin, "wdead": self.wdead, "end": self.end, "zwin": self.zwin,
            "cards": cards, "hold": self.hold, "shovel": 0,
            "z": [{"id": z["id"], "t": z["t"], "x": round(z["x"], 3), "y": round(z["y"], 3),
                   "hp": round(z["hp"], 3), "hs": round(z["hs"], 3), "bs": round(z["bs"], 3),
                   "eat": z["eat"], "alive": z["alive"], "show": z["show"], "spd": round(z["spd"], 3)}
                  for z in self.zombies],
            "p": [{"id": p["id"], "t": p["t"], "r": p["col"], "c": p["row"], "hp": round(p["hp"], 3)}
                  for p in self.plants],
            "b": [{"id": b["id"], "x": round(b["x"], 3), "y": round(b["y"], 3), "used": b["used"]}
                  for b in self.bullets],
            "s": [{"id": s["id"], "x": round(s["x"], 3), "y": round(s["y"], 3), "en": s["en"]}
                  for s in self.suns],
            "cars": [{"tag": m["tag"], "live": m["live"], "st": m["st"], "x": round(m["x"], 3)}
                     for m in self.mowers],
        }


def validate_scenario(s: dict[str, Any]) -> None:
    if not isinstance(s, dict):
        raise ValueError("scenario must be a JSON object")
    if s.get("schema") != 1 or s.get("level") != 4 or s.get("frame_ms") != 16:
        raise ValueError("only schema 1, level 4, frame_ms 16 is supported")
    if not isinstance(s.get("end_frame"), int) or s["end_frame"] < 0:
        raise ValueError("end_frame must be a non-negative integer")
    for key in ("time_seed", "device_seed"):
        if not isinstance(s.get(key), int):
            raise ValueError(f"{key} must be an integer")
    for a in s.get("actions", []):
        if a.get("kind") != "plant" or a.get("card_index") not in (0, 1, 2):
            raise ValueError("unsupported action")
        if not (0 <= a.get("row", -1) < 5 and 0 <= a.get("col", -1) < 9):
            raise ValueError("plant coordinate outside lawn")


def run_scenario(scenario: dict[str, Any]) -> Iterator[dict[str, Any]]:
    game = Game(scenario)
    end_frame = int(scenario["end_frame"])
    while game.frame < end_frame:
        row = game.step()
        yield row
        if game.end_at is not None and game.frame >= game.end_at + 60:
            break
