#!/usr/bin/env python3
"""Deterministic, standard-library-only simulator for the traced Level 4 state."""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

DT = 0.016
MASK64 = (1 << 64) - 1
COST = {"sunflower": 50, "peashooter": 100, "wallnut": 50}
HP = {"sunflower": 300.0, "peashooter": 300.0, "wallnut": 3000.0}
CARD_NAMES = ("sunflower", "peashooter", "wallnut")
CARD_COOLDOWN = (468.75, 468.75, 1875.0)
ROW_Y = (130.0, 268.0, 406.0, 544.0, 682.0)


def r3(v: float) -> float:
    return round(v + 1e-9, 3)


class SplitMix:
    def __init__(self, seed: int):
        self.state = seed & MASK64

    def draw(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        z ^= z >> 31
        return (z >> 32) & 0xFFFFFFFF

    def below(self, n: int) -> int:
        return self.draw() % n


@dataclass
class Card:
    tag: int
    remaining: float
    ready: int = 0
    enabled: int = 0
    ready_since: int = -1
    has_recharged: bool = False


class Simulator:
    def __init__(self, scenario: dict):
        self.sc = scenario
        time_seed = int(scenario.get("time_seed", 0)) & MASK64
        self.rng = SplitMix(time_seed)
        self.spawn_rng = SplitMix(int(scenario.get("device_seed", 0)))
        self.sun_rng = SplitMix(time_seed ^ 0x53554E)
        self.frame = -1
        self.sun = 10000
        self.wave = 0
        self.wt = 0.0
        self.wbegin = 0
        self.wdead = 0
        self.end = 0
        self.zwin = 0
        self.end_frame: int | None = None
        self.abort_before_trace = False
        self.hold = -1
        self.shovel = 0
        self.cards = [Card(0, 0.0), Card(1, CARD_COOLDOWN[1]), Card(2, CARD_COOLDOWN[2])]
        self.plants: list[dict] = []
        self.zombies: list[dict] = []
        self.bullets: list[dict] = []
        self.suns: list[dict] = []
        self.cars: list[dict] = []
        self.next_pid = self.next_zid = self.next_bid = self.next_sid = 1
        self.actions_select: dict[int, list[dict]] = {}
        self.actions_place: dict[int, list[dict]] = {}
        for action in scenario.get("actions", []):
            if action.get("kind") != "plant":
                continue
            f = int(action["frame"])
            self.actions_select.setdefault(f + 4, []).append(action)
            self.actions_place.setdefault(f + 15, []).append(action)
        self.collect_every = int(scenario.get("collect_sun", {}).get("every_frames", 0))
        self.pending_collect: dict[int, int] = {}
        self.wave_release_frames = self._make_wave_schedule()
        self.wave_threshold_frames = {f - 6 for f in self.wave_release_frames}

    def _make_wave_schedule(self) -> list[int]:
        # The first release is fixed. Later release delays center on 32.5 seconds.
        out = [1139]
        local = SplitMix(int(self.sc.get("device_seed", 0)) ^ 0x57415645)
        while len(out) < 5:
            next_wave = len(out) + 1
            if next_wave % 5 == 0:
                delay = 6
            elif next_wave == 2:
                delay = 2090 + local.below(63) - 31
            elif next_wave == 3:
                delay = 1930 + local.below(301) - 150
            else:
                delay = 1682 + local.below(41) - 20
            out.append(out[-1] + delay)
        return out

    def _start_cooldown(self, index: int) -> None:
        c = self.cards[index]
        c.remaining = CARD_COOLDOWN[index]
        c.ready = 0
        c.enabled = 0
        c.ready_since = -1
        c.has_recharged = True

    def _process_actions(self, f: int) -> None:
        for action in self.actions_select.get(f, []):
            i = int(action.get("card_index", -1))
            if 0 <= i < 3 and self.cards[i].enabled and self.hold < 0:
                self.hold = i
                self.sun -= COST[CARD_NAMES[i]]
        for action in self.actions_place.get(f, []):
            i = int(action.get("card_index", -1))
            if self.hold != i:
                continue
            row, col = int(action.get("row", -1)), int(action.get("col", -1))
            occupied = any(p["alive"] and p["row"] == row and p["col"] == col for p in self.plants)
            if 0 <= row < 5 and 0 <= col < 9 and not occupied:
                name = CARD_NAMES[i]
                plant = {
                    "id": self.next_pid, "t": name, "row": row, "col": col,
                    "hp": HP[name], "alive": True, "born": f, "dead": None,
                    "next_sun": None, "next_shot": None,
                }
                self.next_pid += 1
                if name == "sunflower":
                    plant["sun_period"] = 1469 + self.rng.below(126)
                    plant["next_sun"] = f + 313 + self.rng.below(64)
                elif name == "peashooter":
                    plant["shot_period"] = 69 + self.rng.below(22)
                self.plants.append(plant)
                self._start_cooldown(i)
            else:
                self.sun += COST[CARD_NAMES[i]]
            self.hold = -1

    def _update_cards(self, f: int) -> None:
        if f == 1:
            self.cards[0].ready = 1
            self.cards[0].remaining = 0.0
        for i, c in enumerate(self.cards):
            if not c.ready and f >= 2:
                c.remaining -= 1.0
                if c.remaining <= 0.001:
                    c.remaining = 0.0
                    c.ready = 1
                    c.ready_since = f
            affordable = self.sun >= COST[CARD_NAMES[i]]
            enable_lag = c.has_recharged and c.ready_since == f
            c.enabled = int(c.ready and affordable and self.hold < 0 and not enable_lag)
        # The card tray finishes entering at frame 8.
        if f < 8:
            for c in self.cards:
                c.enabled = 0

    def _spawn_wave(self, f: int) -> None:
        self.wave += 1
        self.wt = 0.0
        immediate_flag_follows = (self.wave + 1) % 5 == 0
        self.wdead = int(immediate_flag_follows)
        self.wbegin = 0
        if self.wave == 1:
            count = 1
        elif self.wave % 5 == 0:
            count = 15 + self.spawn_rng.below(4)
        else:
            count = 3 + self.spawn_rng.below(3)
        lanes: list[int] = []
        for n in range(count):
            if self.wave == 1:
                lane = 4
            else:
                lane = self.spawn_rng.below(5)
                if count >= 5 and n < 5:
                    # Bias the first five toward lawn coverage without enforcing uniqueness.
                    lane = (lane + n) % 5
            lanes.append(lane)
            if self.wave == 1:
                typ, shield = "common", 0.0
            else:
                roll = self.spawn_rng.below(100)
                if self.wave >= 4 and roll < 9:
                    typ, shield = "bucket", 1300.0
                elif roll < (28 if self.wave % 5 == 0 else 9):
                    typ, shield = "cone", 600.0
                else:
                    typ, shield = "common", 0.0
            x0 = 1800 + self.spawn_rng.below(500)
            self.zombies.append({
                "id": self.next_zid, "t": typ, "lane": lane, "x": float(x0),
                "hp": 200.0, "hs": shield, "bs": 0.0, "eat": 0,
                "alive": True, "show": 0, "spd": 30.0, "born": f,
                "dead": None, "mowed": False, "next_bite": None,
            })
            self.next_zid += 1

    def _update_wave(self, f: int) -> None:
        if f in self.wave_threshold_frames:
            self.wbegin = 0
            self.wdead = 1
        if f in self.wave_release_frames:
            self._spawn_wave(f)
            return
        # Original timer callback runs at alternating 62/63 frame gaps.
        if f >= 64 and ((f - 2) * 8) % 500 < 8:
            if self.wbegin:
                self.wt += 1.0
            elif not self.wdead:
                self.wbegin = 1
                self.wt += 1.0

    def _spawn_sun(self, f: int, x: float, y: float, kind: str) -> None:
        self.suns.append({
            "id": self.next_sid, "x0": x, "y0": y, "x": x, "y": y,
            "born": f, "kind": kind, "en": 1, "collected": None,
            "remove": None,
            "target_y": float(180 + self.sun_rng.below(530)),
            "drift": float(self.sun_rng.below(61) - 30),
        })
        self.next_sid += 1

    def _update_suns(self, f: int) -> None:
        if f >= 314 and (f - 314) % 1562 in (0,):
            x = float(550 + self.sun_rng.below(1001))
            self._spawn_sun(f, x, 1150.0, "sky")
        for p in self.plants:
            if p["alive"] and p["t"] == "sunflower" and p["next_sun"] == f:
                self._spawn_sun(f, 630.0 + 122.0 * p["col"], 123.0 + 138.0 * p["row"], "plant")
                p["next_sun"] += p["sun_period"]
        # A collection choice uses the preceding trace line and releases three frames later.
        if self.collect_every and f > 0 and f % self.collect_every == 0:
            for s in self.suns:
                if s["en"] and 0.0 < s["x"] < 1920.0 and 0.0 < s["y"] < 1080.0:
                    self.pending_collect[f + 3] = s["id"]
                    break
        sid = self.pending_collect.pop(f, None)
        if sid is not None:
            for s in self.suns:
                if s["id"] == sid and s["en"]:
                    s["en"] = 0
                    s["collected"] = f
                    s["credit"] = f + 44
                    s["remove"] = int(math.ceil((f + 375) / 125.0) * 125 + 1)
                    break
        for s in self.suns:
            age = f - s["born"]
            if s["collected"] is not None:
                ca = f - s["collected"]
                if ca <= 32:
                    q = 1.0 - 0.8 ** ca
                    s["x"] = s["x"] + (290.0 - s["x"]) * (0.2 if ca else 0.0)
                    s["y"] = s["y"] + (1010.0 - s["y"]) * (0.2 if ca else 0.0)
                else:
                    s["x"], s["y"] = 290.0, 1010.0
                if f == s.get("credit"):
                    self.sun += 50
            elif s["kind"] == "sky":
                if age <= 38:
                    # Launch arc: roughly +120 px before the long fall.
                    s["x"] = s["x0"] + s["drift"] * min(age, 38) / 38.0
                    s["y"] = s["y0"] + 122.0 * math.sin(math.pi * age / 38.0)
                else:
                    s["x"] = s["x0"] + s["drift"]
                    s["y"] = max(s["target_y"], s["y"] - 2.563)
                if age > 1311:
                    s["remove"] = f + 1
            else:
                if age <= 38:
                    s["x"] = s["x0"] + s["drift"] * age / 38.0
                    s["y"] = s["y0"] + 155.0 * math.sin(math.pi * age / 76.0)
                elif age <= 76:
                    s["x"] = s["x0"] + s["drift"]
                    s["y"] = s["y0"] + 155.0 * math.sin(math.pi * age / 76.0)
                if age > 1311:
                    s["remove"] = f + 1
        self.suns = [s for s in self.suns if s["remove"] is None or f < s["remove"]]

    def _kill_zombie(self, z: dict, f: int, mowed: bool) -> None:
        if not z["alive"]:
            return
        z["alive"] = False
        z["hp"] = 0.0
        z["eat"] = 0
        z["dead"] = f
        z["mowed"] = mowed

    def _update_zombies(self, f: int) -> None:
        for z in self.zombies:
            if not z["alive"]:
                continue
            lane = z["lane"]
            mower = next((c for c in self.cars if c["lane"] == lane), None)
            if mower and mower["live"] and abs(z["x"] - mower["x"]) < 145.0:
                self._kill_zombie(z, f, True)
                continue
            target = None
            for p in self.plants:
                if p["alive"] and p["row"] == lane and z["x"] >= 500.0:
                    contact = 630.0 + 122.0 * p["col"] + 80.0
                    if z["x"] <= contact + 0.25:
                        if target is None or p["col"] > target["col"]:
                            target = p
            if target is not None:
                if not z["eat"]:
                    z["eat"] = 1
                    z["next_bite"] = f + 45 + self.rng.below(11)
                if f == z["next_bite"]:
                    target["hp"] = max(0.0, target["hp"] - 100.0)
                    z["next_bite"] += 90
                    if target["hp"] <= 0.0:
                        target["alive"] = False
                        target["dead"] = f
                        z["eat"] = 0
            else:
                z["eat"] = 0
                z["x"] -= z["spd"] * DT
            z["show"] = int(z["x"] < 1710.0)
            if z["x"] <= 535.0 and mower and not mower["live"]:
                mower["live"] = 1
                mower["st"] = 2
                mower["started"] = f
                self._kill_zombie(z, f, True)
                # The starting mower overlaps nearby zombies in its row.
                for other in self.zombies:
                    if other["alive"] and other["lane"] == lane and other["x"] < 600.0:
                        self._kill_zombie(other, f, True)
            elif z["x"] <= 0.0 and mower is None:
                # The black-box build aborts before its trace writer records this frame.
                self.abort_before_trace = True
        self.zombies = [z for z in self.zombies if z["dead"] is None or f - z["dead"] <= (314 if z["mowed"] else 469)]

    def _update_cars(self, f: int) -> None:
        for born in (33, 39, 45, 51, 58):
            if f == born:
                self.cars.append({"tag": -1, "lane": len(self.cars), "live": 0, "st": 1, "x": 455.0, "started": None, "spent": False})
        kept = []
        for car in self.cars:
            if car["live"] and f > car["started"]:
                car["x"] += 12.16
            if car["live"] and f - car["started"] >= 137:
                car["spent"] = True
                continue
            kept.append(car)
        self.cars = kept

    def _update_plants_and_fire(self, f: int) -> None:
        for p in self.plants:
            if not p["alive"] or p["t"] != "peashooter":
                continue
            targets = [z for z in self.zombies if z["alive"] and z["lane"] == p["row"] and z["show"] and z["x"] > 630 + 122 * p["col"]]
            if targets:
                if p["next_shot"] is None:
                    p["next_shot"] = f + 86 + self.rng.below(9)
                elif f >= p["next_shot"]:
                    self.bullets.append({
                        "id": self.next_bid, "lane": p["row"],
                        "x": 700.0 + 122.0 * p["col"], "born": f, "used": 0,
                    })
                    self.next_bid += 1
                    p["next_shot"] += p["shot_period"]
            else:
                p["next_shot"] = None
        self.plants = [p for p in self.plants if p["dead"] is None or f - p["dead"] <= 250]

    def _update_bullets(self, f: int) -> None:
        for b in self.bullets:
            if f > b["born"]:
                b["x"] += 10.6666667
            if not b["used"]:
                candidates = [z for z in self.zombies if z["alive"] and z["lane"] == b["lane"] and b["x"] >= z["x"] - 22.0]
                if candidates:
                    z = min(candidates, key=lambda q: q["x"])
                    b["used"] = 1
                    if z["hs"] > 0:
                        z["hs"] = max(0.0, z["hs"] - 20.0)
                    elif z["bs"] > 0:
                        z["bs"] = max(0.0, z["bs"] - 20.0)
                    else:
                        z["hp"] = max(0.0, z["hp"] - 20.0)
                        if z["hp"] <= 0.0:
                            self._kill_zombie(z, f, False)
        self.bullets = [b for b in self.bullets if f - b["born"] <= 188]

    def step(self, f: int) -> dict:
        self.frame = f
        self._update_cards(f)
        self._process_actions(f)
        self._update_wave(f)
        self._update_cars(f)
        self._update_zombies(f)
        self._update_plants_and_fire(f)
        self._update_bullets(f)
        self._update_suns(f)
        # Selection changes the held cursor; successful placement already updates cooldown state.
        return self.trace_row(f)

    def trace_row(self, f: int) -> dict:
        cards = []
        for i, c in enumerate(self.cards):
            pct = 0.0 if c.ready else max(0.0, min(100.0, c.remaining / CARD_COOLDOWN[i] * 100.0))
            if self.hold == i:
                pct = 100.0
            cards.append({"tag": i, "ready": c.ready, "pct": r3(pct), "en": c.enabled})
        plants = [{"id": p["id"], "t": p["t"], "r": p["col"], "c": p["row"], "hp": r3(p["hp"])} for p in self.plants]
        zombies = [{
            "id": z["id"], "t": z["t"], "x": r3(z["x"]), "y": ROW_Y[z["lane"]],
            "hp": r3(z["hp"]), "hs": r3(z["hs"]), "bs": r3(z["bs"]),
            "eat": z["eat"], "alive": int(z["alive"]), "show": z["show"], "spd": z["spd"],
        } for z in self.zombies]
        bullets = [{"id": b["id"], "x": r3(b["x"]), "y": 208.0 + 138.0 * b["lane"], "used": b["used"]} for b in self.bullets]
        suns = [{"id": s["id"], "x": r3(s["x"]), "y": r3(s["y"]), "en": s["en"]} for s in self.suns]
        cars = [{"tag": c["tag"], "live": c["live"], "st": c["st"], "x": r3(c["x"])} for c in self.cars]
        return {
            "f": f, "sun": self.sun, "ts": 1.0, "wave": self.wave, "wt": self.wt,
            "wbegin": self.wbegin, "wdead": self.wdead, "end": self.end, "zwin": self.zwin,
            "hold": self.hold, "shovel": self.shovel, "cards": cards,
            "p": plants, "z": zombies, "b": bullets, "s": suns, "cars": cars,
        }


def run(scenario_path: str, output_path: str) -> None:
    with open(scenario_path, "r", encoding="utf-8") as fh:
        sc = json.load(fh)
    if sc.get("schema") != 1 or sc.get("level") != 4 or sc.get("frame_ms") != 16:
        raise ValueError("only schema 1, Level 4, 16 ms scenarios are supported")
    sim = Simulator(sc)
    limit = int(sc["end_frame"])
    with open(output_path, "w", encoding="utf-8") as out:
        for f in range(limit + 1):
            row = sim.step(f)
            if sim.abort_before_trace:
                break
            out.write(json.dumps(row, separators=(",", ":"), ensure_ascii=True) + "\n")
            if sim.end_frame is not None and f >= sim.end_frame + 60:
                break


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: run-scenario <scenario.json> <out-trace.jsonl>", file=sys.stderr)
        return 2
    run(argv[1], argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
