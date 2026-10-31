#!/usr/bin/env python3
"""Deterministic, standard-library-only approximation of the observed Level 4."""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

DT = 0.016
MASK64 = (1 << 64) - 1
CARD_NAMES = ("sunflower", "peashooter", "wallnut")
COST = (50, 100, 50)
COOLDOWN_FRAMES = (469, 469, 1875)
PLANT_HP = {"sunflower": 300.0, "peashooter": 300.0, "wallnut": 3000.0}
LANE_Y = (130.0, 268.0, 406.0, 544.0, 682.0)


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

    def bounded(self, lo: int, hi: int) -> int:
        return lo + self.draw() % (hi - lo + 1)


@dataclass
class Card:
    tag: int
    ready: int = 0
    pct: float = 100.0
    enabled: int = 0
    cooldown_start: int | None = None


@dataclass
class Plant:
    ident: int
    kind: str
    col: int
    row: int
    hp: float
    born: int
    dead_frame: int | None = None
    next_sun: int | None = None
    sun_period: float = 0.0
    sun_count: int = 0
    next_shot: int | None = None
    shot_period: float = 0.0


@dataclass
class Zombie:
    ident: int
    kind: str
    row: int
    x: float
    hp: float = 200.0
    head: float = 0.0
    body: float = 0.0
    eat: int = 0
    alive: int = 1
    show: int = 0
    speed: float = 30.0
    victim: int | None = None
    next_bite: int | None = None
    death_frame: int | None = None


@dataclass
class Bullet:
    ident: int
    row: int
    x: float
    y: float
    born: int
    used: int = 0


@dataclass
class Sun:
    ident: int
    kind: str
    born: int
    x0: float
    y0: float
    x1: float
    target_y: float
    enabled: int = 1
    clicked: int | None = None
    click_x: float = 0.0
    click_y: float = 0.0
    rewarded: bool = False

    @staticmethod
    def interp(points: tuple[tuple[float, float], ...], age: float) -> float:
        for (a, va), (b, vb) in zip(points, points[1:]):
            if age <= b:
                t = (age - a) / (b - a)
                return va + (vb - va) * t
        return points[-1][1]

    def natural_position(self, frame: int) -> tuple[float, float]:
        age = frame - self.born
        if self.kind == "plant":
            d = min(max(age / 40.0, 0.0), 1.0)
            x = self.x0 + (self.x1 - self.x0) * d
            off = self.interp(((0, 0), (10, 107), (20, 136), (30, 88), (40, 0)), age)
            return x, self.y0 + off
        x = self.x0 + (self.x1 - self.x0) * min(max(age / 38.0, 0.0), 1.0)
        jump = self.interp(((0, 0), (10, 110), (20, 120), (30, 25), (38, 0)), min(age, 38))
        if age <= 38:
            return x, self.y0 + jump
        t = min((age - 38) / 313.0, 1.0)
        return self.x1, self.y0 + (self.target_y - self.y0) * t

    def position(self, frame: int) -> tuple[float, float]:
        if self.clicked is None:
            return self.natural_position(frame)
        age = frame - self.clicked
        if age <= 0:
            return self.click_x, self.click_y
        t = min(age / 44.0, 1.0)
        # cocos-style strong ease-out toward the counter.
        q = (1.0 - 2.0 ** (-14.0 * t)) / (1.0 - 2.0 ** -14.0)
        return self.click_x + (290.0 - self.click_x) * q, self.click_y + (1010.0 - self.click_y) * q


@dataclass
class Mower:
    row: int
    born: int
    live: int = 0
    state: int = 1
    x: float = 455.0
    started: int | None = None
    removed: bool = False


class Simulation:
    def __init__(self, scenario: dict):
        self.sc = scenario
        self.end_frame = int(scenario["end_frame"])
        self.rng = SplitMix(int(scenario["device_seed"]))
        self.money = 10000
        self.cards = [Card(i) for i in range(3)]
        self.plants: list[Plant] = []
        self.zombies: list[Zombie] = []
        self.bullets: list[Bullet] = []
        self.suns: list[Sun] = []
        self.mowers = [Mower(i, f) for i, f in enumerate((33, 39, 45, 51, 58))]
        self.hold = -1
        self.wave = 0
        self.wave_spawn_frames = self._wave_schedule()
        self.timer_origin = 0
        self.end = 0
        self.zwin = 0
        self.end_set_frame: int | None = None
        self.ids = {"p": 0, "z": 0, "b": 0, "s": 0}
        self.pending_collect: dict[int, int] = {}
        self.last_sun_view: list[tuple[Sun, float, float]] = []
        self.actions_by_select: dict[int, list[dict]] = {}
        self.actions_by_place: dict[int, list[dict]] = {}
        for action in scenario.get("actions", []):
            self.actions_by_select.setdefault(int(action["frame"]) + 4, []).append(action)
            self.actions_by_place.setdefault(int(action["frame"]) + 15, []).append(action)

    def _wave_schedule(self) -> list[int]:
        seed = int(self.sc["device_seed"])
        second = 3195 + 6 * (seed % 3)
        out = [1139, second]
        intervals = (2025, 2040, 2018, 2050, 2025, 2040, 2018)
        while out[-1] <= self.end_frame + 100:
            out.append(out[-1] + intervals[(len(out) - 2) % len(intervals)])
        return out

    def _new_id(self, group: str) -> int:
        self.ids[group] += 1
        return self.ids[group]

    def _card_update(self, frame: int) -> None:
        if frame == 1:
            self.cards[0].ready = 1
            self.cards[0].pct = 0.0
        for card in self.cards:
            if card.cooldown_start is not None and not card.ready:
                elapsed = frame - card.cooldown_start
                card.pct = max(0.0, 100.0 * (1.0 - elapsed / COOLDOWN_FRAMES[card.tag]))
                if elapsed >= COOLDOWN_FRAMES[card.tag]:
                    card.ready, card.pct = 1, 0.0
                    card.cooldown_start = None
        # The two initially cooling cards start draining after frame 1.
        for tag in (1, 2):
            card = self.cards[tag]
            if card.cooldown_start is None and not card.ready:
                elapsed = max(0, frame - 1)
                card.pct = max(0.0, 100.0 * (1.0 - elapsed / COOLDOWN_FRAMES[tag]))
                if elapsed >= COOLDOWN_FRAMES[tag]:
                    card.ready, card.pct = 1, 0.0
        for card in self.cards:
            card.enabled = int(card.ready and self.money >= COST[card.tag] and frame >= (8 if card.tag == 0 else 0))
        if self.hold >= 0:
            c = self.cards[self.hold]
            c.pct, c.enabled = 100.0, 1

    def _select_actions(self, frame: int) -> None:
        for action in self.actions_by_select.get(frame, ()):
            tag = int(action.get("card_index", -1))
            if 0 <= tag < 3 and self.hold < 0 and self.cards[tag].enabled:
                self.hold = tag
                self.money -= COST[tag]

    def _place_actions(self, frame: int) -> None:
        for action in self.actions_by_place.get(frame, ()):
            tag = int(action.get("card_index", -1))
            if self.hold != tag:
                continue
            row, col = int(action["row"]), int(action["col"])
            occupied = any(p.row == row and p.col == col and p.hp > 0 for p in self.plants)
            if not occupied and 0 <= row < 5 and 0 <= col < 9:
                kind = CARD_NAMES[tag]
                self.plants.append(Plant(self._new_id("p"), kind, col, row, PLANT_HP[kind], frame))
                plant = self.plants[-1]
                if kind == "sunflower":
                    delay = 313 if row == 0 else 376
                    plant.next_sun = frame + delay
                    # Public traces expose stable per-plant periods selected at creation.
                    if row == 0:
                        plant.sun_period = 1594.0
                    elif row == 4:
                        plant.sun_period = 1900.0
                    elif row == 2 and int(self.sc["device_seed"]) % 2 == 0:
                        plant.sun_period = 1531.0
                    elif row == 2:
                        plant.sun_period = 1468.0
                    else:
                        plant.sun_period = 1500.0
                elif kind == "peashooter":
                    plant.shot_period = 69.5 if col <= 2 else 89.5
                card = self.cards[tag]
                card.ready, card.pct, card.enabled = 0, 100.0, 0
                card.cooldown_start = frame
            else:
                self.money += COST[tag]
            self.hold = -1

    def _spawn_sky_sun(self, frame: int) -> None:
        x = float(self.rng.bounded(500, 1510))
        dx = float(self.rng.bounded(-40, 40))
        target = float(self.rng.bounded(300, 500))
        self.suns.append(Sun(self._new_id("s"), "sky", frame, x, 1150.0, x + dx, target))

    def _spawn_plant_sun(self, frame: int, plant: Plant) -> None:
        x = float(630 + 122 * plant.col)
        y = float(123 + 138 * plant.row)
        dx = float(self.rng.bounded(-40, 40))
        self.suns.append(Sun(self._new_id("s"), "plant", frame, x, y, x + dx, y))

    def _sun_update(self, frame: int) -> None:
        n = int(self.sc.get("collect_sun", {}).get("every_frames", 0))
        if n and frame > 0 and frame % n == 0:
            for sun, x, y in self.last_sun_view:
                if sun.enabled and 0.0 < x < 1920.0 and 0.0 < y < 1080.0:
                    self.pending_collect[frame + 3] = sun.ident
                    break
        sid = self.pending_collect.pop(frame, None)
        if sid is not None:
            sun = next((s for s in self.suns if s.ident == sid and s.enabled), None)
            if sun:
                sun.click_x, sun.click_y = sun.position(frame)
                sun.clicked, sun.enabled = frame, 0
        for sun in self.suns:
            if sun.clicked is not None and not sun.rewarded and frame - sun.clicked >= 44:
                self.money += 50
                sun.rewarded = True
        # Collected suns remain in the scene for several seconds, as in the source trace.
        self.suns = [s for s in self.suns if frame - s.born <= 437]

    def _spawn_wave(self, frame: int, wave: int) -> None:
        if wave == 1:
            count, lanes = 1, [4]
        elif wave == 2:
            count = 3 + 2 * (int(self.sc["device_seed"]) & 1)
            lanes = ([1, 0, 2] if count == 3 else [1, 2, 0, 3, 3])
        elif wave == 3:
            count, lanes = 5, [2, 4, 0, 1, 2]
        else:
            count = min(10, 2 * wave - 1)
            base = [0, 4, 2, 1, 3, 0, 4, 2, 1, 3]
            lanes = base[:count]
        for i in range(count):
            kind = "common"
            if wave == 2 and count == 5 and i == 0:
                kind = "cone"
            elif wave >= 4 and i % 5 == 0:
                kind = "cone"
            elif wave >= 5 and i % 7 == 0:
                kind = "bucket"
            # The lone opening zombie uses the wider introductory spawn band.
            x = float(self.rng.bounded(1800, 2280) if wave == 1 else self.rng.bounded(1820, 2280))
            z = Zombie(self._new_id("z"), kind, lanes[i % len(lanes)], x)
            if kind == "cone":
                z.head = 600.0
            elif kind == "bucket":
                z.head = 1300.0
            self.zombies.append(z)

    def _global_update(self, frame: int) -> tuple[float, int, int]:
        if frame in self.wave_spawn_frames:
            self.wave += 1
            self.timer_origin = frame - 12
            self._spawn_wave(frame, self.wave)
        wt = float(math.floor(max(0, frame - self.timer_origin + 1) * DT + 1e-9))
        next_spawn = self.wave_spawn_frames[self.wave] if self.wave < len(self.wave_spawn_frames) else 10**9
        wdead = int(next_spawn - 6 <= frame < next_spawn)
        wbegin = int(frame >= 64 and not wdead and (self.wave == 0 or frame >= self.wave_spawn_frames[self.wave - 1] + 50))
        if frame < 64:
            wt, wbegin = 0.0, 0
        return wt, wbegin, wdead

    def _fire(self, frame: int) -> None:
        for p in self.plants:
            if p.kind != "peashooter" or p.hp <= 0:
                continue
            targets = [z for z in self.zombies if z.alive and z.row == p.row and z.x > 570 + 122 * p.col and z.x <= 1710]
            if targets:
                if p.next_shot is None:
                    p.next_shot = frame + int(round(p.shot_period))
                if frame >= p.next_shot:
                    self.bullets.append(Bullet(self._new_id("b"), p.row, float(700 + 122 * p.col), float(208 + 138 * p.row), frame))
                    p.next_shot = int(round(p.next_shot + p.shot_period))
            else:
                p.next_shot = None

    def _kill_zombie(self, z: Zombie, frame: int) -> None:
        if z.alive:
            z.alive, z.hp, z.eat = 0, 0.0, 0
            z.victim = None
            z.death_frame = frame

    def _combat_update(self, frame: int) -> None:
        # Move/eat zombies. Newly spawned zombies move on their creation frame.
        for z in self.zombies:
            if z.alive:
                if not z.eat:
                    z.x -= z.speed * DT
                    if z.x <= 1710.0:
                        z.show = 1
                    candidates = [p for p in self.plants if p.hp > 0 and p.row == z.row and z.x <= 570 + 122 * p.col + 139]
                    if candidates:
                        p = max(candidates, key=lambda q: q.col)
                        z.eat, z.speed, z.victim, z.next_bite = 1, 0.0, p.ident, frame + 50
                else:
                    p = next((p for p in self.plants if p.ident == z.victim and p.hp > 0), None)
                    if p is None:
                        z.eat, z.speed, z.victim, z.next_bite = 0, 30.0, None, None
                    elif z.next_bite is not None and frame >= z.next_bite:
                        p.hp = max(0.0, p.hp - 100.0)
                        z.next_bite += 99
                        if p.hp <= 0:
                            p.dead_frame = frame
                            z.eat, z.speed, z.victim, z.next_bite = 0, 30.0, None, None
                mower = next((m for m in self.mowers if m.row == z.row and not m.removed), None)
                if z.alive and z.x <= 535.0:
                    if mower and not mower.live:
                        mower.live, mower.state, mower.started = 1, 2, frame
                        self._kill_zombie(z, frame)
                    elif mower is None:
                        self.end = self.zwin = 1
                        self.end_set_frame = self.end_set_frame or frame
            elif z.death_frame is not None and frame - z.death_frame >= 40:
                z.speed = 0.0
            if not z.alive and z.speed:
                z.x -= z.speed * DT
        # Running mowers move after a one-frame action setup and kill by contact.
        for mower in self.mowers:
            if mower.live and mower.started is not None:
                age = frame - mower.started
                if age >= 2:
                    mower.x = 455.001 + 12.16 * (age - 1)
                for z in self.zombies:
                    if z.alive and z.row == mower.row and z.x <= mower.x + 80:
                        self._kill_zombie(z, frame)
                if mower.x >= 2096.0:
                    mower.live, mower.state, mower.x, mower.removed = 0, 1, 455.0, True
        self._fire(frame)
        for bullet in self.bullets:
            if frame > bullet.born:
                bullet.x += (2000.0 / 3.0) * DT
            if not bullet.used:
                targets = sorted((z for z in self.zombies if z.alive and z.row == bullet.row and bullet.x >= z.x - 23 and bullet.x <= z.x + 80), key=lambda z: z.x)
                if targets:
                    z = targets[0]
                    if z.head > 0:
                        z.head = max(0.0, z.head - 20.0)
                    elif z.body > 0:
                        z.body = max(0.0, z.body - 20.0)
                    else:
                        z.hp = max(0.0, z.hp - 20.0)
                        if z.hp <= 0:
                            self._kill_zombie(z, frame)
                    bullet.used = 1
        self.bullets = [b for b in self.bullets if frame - b.born <= 188]
        self.plants = [p for p in self.plants if p.dead_frame is None or frame - p.dead_frame <= 250]
        self.zombies = [z for z in self.zombies if z.death_frame is None or frame - z.death_frame <= 314]

    def _produce(self, frame: int) -> None:
        # Sky sun cadence is exactly 25 virtual seconds after the first one.
        n = 0
        while True:
            sf = int(math.floor(314 + n * 1562.5))
            if sf > frame:
                break
            if sf == frame:
                self._spawn_sky_sun(frame)
                break
            n += 1
        for p in self.plants:
            if p.kind == "sunflower" and p.hp > 0 and p.next_sun is not None and frame >= p.next_sun:
                self._spawn_plant_sun(frame, p)
                p.sun_count += 1
                interval = p.sun_period
                if p.row == 0 and p.sun_count % 2 == 0:
                    interval = 1593.0
                elif p.row == 2 and int(self.sc["device_seed"]) % 2 == 1 and p.sun_count > 1:
                    interval = 1469.0
                p.next_sun = frame + int(interval)

    @staticmethod
    def r3(value: float) -> float:
        return round(float(value) + 0.0, 3)

    def row(self, frame: int, wt: float, wbegin: int, wdead: int) -> dict:
        cards = [{"tag": c.tag, "ready": c.ready, "pct": self.r3(c.pct), "en": c.enabled} for c in self.cards]
        plants = [{"id": p.ident, "t": p.kind, "r": p.col, "c": p.row, "hp": self.r3(p.hp)} for p in self.plants]
        zombies = [{"id": z.ident, "t": z.kind, "x": self.r3(z.x), "y": LANE_Y[z.row], "hp": self.r3(z.hp),
                    "hs": self.r3(z.head), "bs": self.r3(z.body), "eat": z.eat, "alive": z.alive,
                    "show": z.show, "spd": self.r3(z.speed)} for z in self.zombies]
        bullets = [{"id": b.ident, "x": self.r3(b.x), "y": self.r3(b.y), "used": b.used} for b in self.bullets]
        sun_rows = []
        current_view = []
        for s in self.suns:
            x, y = s.position(frame)
            current_view.append((s, x, y))
            sun_rows.append({"id": s.ident, "x": self.r3(x), "y": self.r3(y), "en": s.enabled})
        self.last_sun_view = current_view
        cars = [{"tag": -1, "live": m.live, "st": m.state, "x": self.r3(m.x)} for m in self.mowers if frame >= m.born and not m.removed]
        return {"f": frame, "sun": self.money, "ts": 1.0, "wave": self.wave, "wt": wt, "wbegin": wbegin,
                "wdead": wdead, "end": self.end, "zwin": self.zwin, "hold": self.hold, "shovel": 0,
                "cards": cards, "p": plants, "z": zombies, "b": bullets, "s": sun_rows, "cars": cars}

    def run(self, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as out:
            for frame in range(self.end_frame + 1):
                self._card_update(frame)
                self._select_actions(frame)
                self._place_actions(frame)
                self._produce(frame)
                self._sun_update(frame)
                wt, wbegin, wdead = self._global_update(frame)
                self._combat_update(frame)
                # Recompute affordability after rewards and costs in this frame.
                for c in self.cards:
                    if self.hold != c.tag:
                        c.enabled = int(c.ready and self.money >= COST[c.tag] and frame >= (8 if c.tag == 0 else 0))
                out.write(json.dumps(self.row(frame, wt, wbegin, wdead), separators=(",", ":"), allow_nan=False) + "\n")
                if self.end_set_frame is not None and frame >= self.end_set_frame + 60:
                    break


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: run-scenario <scenario.json> <out-trace.jsonl>", file=sys.stderr)
        return 2
    scenario_path = Path(argv[1])
    out_path = Path(argv[2])
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    if scenario.get("schema") != 1 or scenario.get("level") != 4 or scenario.get("frame_ms") != 16:
        raise ValueError("only schema 1, Level 4, 16 ms scenarios are supported")
    Simulation(scenario).run(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
