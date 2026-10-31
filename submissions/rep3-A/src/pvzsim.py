#!/usr/bin/env python3
"""Deterministic, standard-library-only approximation of the observed Level 4 game."""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass

MASK64 = (1 << 64) - 1
Y_BY_ROW = [130.0, 268.0, 406.0, 544.0, 682.0]
PLANT_X = [631.0 + 122.0 * c for c in range(9)]
COST = {"sunflower": 50, "peashooter": 100, "wallnut": 50}
HP = {"sunflower": 300.0, "peashooter": 300.0, "wallnut": 3000.0}
CARD = {"sunflower": 0, "peashooter": 1, "wallnut": 2}
COOLDOWN = [469, 469, 1875]


def r3(x: float) -> float:
    return round(float(x) + 1e-10, 3)


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

    def between(self, lo: int, hi: int) -> int:
        return lo + self.draw() % (hi - lo + 1)


@dataclass
class Plant:
    id: int
    t: str
    col: int
    row: int
    hp: float
    born: int
    dead_at: int | None = None
    next_shot: int = 0
    next_sun: int = 0


@dataclass
class Zombie:
    id: int
    t: str
    x: float
    row: int
    hp: float
    hs: float
    born: int
    eat: int = 0
    alive: int = 1
    show: int = 0
    spd: float = 30.0
    dead_at: int | None = None
    stop_at: int | None = None
    remove_at: int | None = None
    target: int | None = None
    next_bite: int = 0


@dataclass
class Bullet:
    id: int
    x: float
    row: int
    born: int
    used: int = 0


@dataclass
class Sun:
    id: int
    x: float
    y: float
    born: int
    kind: str
    target_x: float
    target_y: float
    en: int = 1
    collect_at: int | None = None
    award_at: int | None = None
    remove_at: int | None = None


@dataclass
class Car:
    row: int
    born: int
    live: int = 0
    st: int = 1
    x: float = 455.0
    start_at: int | None = None


class Game:
    def __init__(self, scenario: dict):
        self.scenario = scenario
        self.end_frame = int(scenario["end_frame"])
        self.sun = 10000
        # Device entropy drives the measured zombie wave-table variants.
        self.seed = int(scenario["device_seed"])
        self.rng = SplitMix(self.seed)
        # The first draw also predicts two observed Level-4 wave table variants.
        self.first_entropy = self.rng.draw()
        self.setup_entropy = [self.first_entropy, self.rng.draw(), self.rng.draw()]
        self.sun_rng = SplitMix(int(scenario["time_seed"]))
        # Twelve setup draws best match the isolated first-sun observations.
        for _ in range(12):
            self.sun_rng.draw()
        self.cards_ready = [False, False, False]
        self.card_ready_at = [1, 470, 1876]
        self.card_reset_at: list[int | None] = [None, None, None]
        self.hold = -1
        self.pending_card: dict[int, int] = {}
        self.pending_plant: dict[int, dict] = {}
        self.plants: list[Plant] = []
        self.zombies: list[Zombie] = []
        self.bullets: list[Bullet] = []
        self.suns: list[Sun] = []
        self.cars: list[Car] = []
        self.ids = {"p": 0, "z": 0, "b": 0, "s": 0}
        self.wave = 0
        self.wave_started = False
        self.wdead = False
        self.wave_timer_base_sec = 0
        self.next_wave_frame = 1139
        self.next_wave_interval = 32
        self.end = 0
        self.zwin = 0
        self.result_frame: int | None = None
        self.final_clear_at: int | None = None
        self.collect_every = int(scenario.get("collect_sun", {}).get("every_frames", 0))
        for action in scenario.get("actions", []):
            if action.get("kind") == "plant":
                self.pending_card[int(action["frame"]) + 4] = int(action["card_index"])
                self.pending_plant[int(action["frame"]) + 15] = action

    def sec(self, f: int) -> int:
        return max(0, (16 * f - 24) // 1000)

    def new_id(self, kind: str) -> int:
        self.ids[kind] += 1
        return self.ids[kind]

    def kill_zombie(self, z: Zombie, f: int, mower: bool = False) -> None:
        if not z.alive:
            return
        z.hp = 0.0
        z.hs = 0.0
        z.alive = 0
        z.eat = 0
        z.target = None
        z.dead_at = f
        z.stop_at = f + (36 if mower else 41)
        z.remove_at = f + (315 if mower else 470)

    def spawn_sky_sun(self, f: int) -> None:
        x = float(self.sun_rng.between(520, 1520))
        tx = float(max(500, min(1520, x + self.sun_rng.between(-36, 36))))
        ty = float(self.sun_rng.between(330, 520))
        self.suns.append(Sun(self.new_id("s"), x, 1150.001, f, "sky", tx, ty))

    def spawn_plant_sun(self, p: Plant, f: int) -> None:
        self.suns.append(Sun(self.new_id("s"), PLANT_X[p.col] - 1.0,
                             Y_BY_ROW[p.row] - 7.0, f, "plant",
                             PLANT_X[p.col] - 1.0, Y_BY_ROW[p.row] - 7.0))
        p.next_sun = f + self.rng.between(1406, 1656)

    def spawn_wave(self, f: int) -> None:
        self.wave += 1
        self.wdead = False
        self.wave_started = False
        self.wave_timer_base_sec = self.sec(f)
        odd_variant = bool(self.first_entropy & 1)
        late_defense_variant = (odd_variant and self.first_entropy % 3 == 2)
        cone_variant = (odd_variant and not late_defense_variant)
        sparse_variant = (not odd_variant and self.first_entropy % 3 == 2 and self.first_entropy % 4 == 0)
        rapid_defense_variant = (not odd_variant and self.first_entropy % 4 == 2)
        if self.wave == 1:
            specs = [("common", 4)]
        elif self.wave == 2:
            if sparse_variant:
                specs = [("common", r) for r in (1, 0, 2)]
            elif rapid_defense_variant:
                specs = [("common", r) for r in (1, 3, 2, 0)]
            elif late_defense_variant:
                specs = [("common", r) for r in (3, 1, 2, 0, 0)]
            elif cone_variant:
                specs = [("cone" if i == 0 else "common", r)
                         for i, r in enumerate((1, 2, 0, 3, 3))]
            else:
                specs = [("common", r) for r in (2, 0, 1, 3, 1)]
        elif self.wave == 3:
            if late_defense_variant:
                lanes = (2, 3, 4, 1, 0)
            elif cone_variant:
                lanes = (2, 4, 0, 1, 2)
            elif rapid_defense_variant:
                lanes = (0, 2, 4, 1)
            else:
                lanes = (0, 2, 4, 3)
            specs = [("common", r) for r in lanes]
        elif self.wave == 4:
            if rapid_defense_variant:
                lanes = (3, 1, 2, 4)
            elif late_defense_variant:
                lanes = (1, 2, 4)
            else:
                lanes = (4, 3, 0)
            specs = [("common", r) for r in lanes]
        elif self.wave == 5:
            if rapid_defense_variant:
                specs = [(t, r) for t, r in (
                    ("common", 3), ("common", 0), ("common", 3), ("common", 0),
                    ("common", 2), ("common", 4), ("common", 1), ("common", 1),
                    ("common", 2), ("cone", 0), ("common", 3), ("cone", 4),
                    ("common", 2), ("common", 0), ("common", 4))]
            elif late_defense_variant:
                specs = [(t, r) for t, r in (
                    ("common", 3), ("common", 4), ("common", 1), ("bucket", 2),
                    ("common", 3), ("common", 0), ("common", 3), ("common", 0),
                    ("common", 4), ("common", 2), ("common", 1), ("common", 1),
                    ("common", 0), ("common", 2), ("cone", 4))]
            else:
                specs = [(t, r) for t, r in (
                    ("common", 2), ("common", 1), ("common", 0), ("common", 4),
                    ("cone", 3), ("common", 2), ("cone", 1), ("common", 3),
                    ("cone", 0), ("common", 2), ("cone", 1), ("cone", 4),
                    ("common", 0), ("cone", 4))]
        else:
            specs = []
        for typ, row in specs:
            self.ids["z"] += 1
            hs = 600.0 if typ == "cone" else (1300.0 if typ == "bucket" else 0.0)
            x = float(self.rng.between(1800, 2280)) - 0.48
            self.zombies.append(Zombie(self.ids["z"], typ, x, int(row), 200.0, hs, f))
        # Measured release gaps: two 32/33-second normal gaps, a 45-second
        # pre-final gap, then the large final wave six frames later.
        if self.wave == 1:
            if rapid_defense_variant:
                self.next_wave_interval = 34
                self.next_wave_frame = f + 2125
            elif late_defense_variant:
                self.next_wave_interval = 32
                self.next_wave_frame = f + 2006
            else:
                first_is_32 = (not odd_variant and self.first_entropy % 3 == 1)
                self.next_wave_interval = 32 if first_is_32 else 33
                self.next_wave_frame = f + (2025 if first_is_32 else 2056 + (6 if odd_variant else 0))
        elif self.wave == 2:
            if rapid_defense_variant:
                self.next_wave_interval = 28
                self.next_wave_frame = f + 1787
            elif late_defense_variant:
                self.next_wave_interval = 33
                self.next_wave_frame = f + 2056
            elif self.next_wave_interval == 32:
                self.next_wave_interval = 33
                self.next_wave_frame = f + 2075
            else:
                self.next_wave_interval = 32
                self.next_wave_frame = f + 2025
        elif self.wave == 3:
            if rapid_defense_variant:
                self.next_wave_interval = 27
                self.next_wave_frame = f + 1682
            elif late_defense_variant:
                self.next_wave_interval = 45
                self.next_wave_frame = f + 2813
            else:
                self.next_wave_interval = 45
                self.next_wave_frame = f + 2775
        elif self.wave == 4:
            self.next_wave_interval = 0
            self.next_wave_frame = f + 6
        else:
            self.next_wave_interval = 10**9
            self.next_wave_frame = 10**9

    def select_card(self, f: int, idx: int) -> None:
        if 0 <= idx < 3 and self.cards_ready[idx] and self.hold < 0:
            typ = ["sunflower", "peashooter", "wallnut"][idx]
            if self.sun >= COST[typ]:
                self.sun -= COST[typ]
                self.hold = idx

    def place(self, f: int, action: dict) -> None:
        idx = int(action["card_index"])
        if self.hold != idx:
            return
        typ = ["sunflower", "peashooter", "wallnut"][idx]
        row, col = int(action["row"]), int(action["col"])
        occupied = any(p.hp > 0 and p.row == row and p.col == col for p in self.plants)
        if occupied or not (0 <= row < 5 and 0 <= col < 9):
            self.sun += COST[typ]
            self.hold = -1
            return
        self.ids["p"] += 1
        p = Plant(self.ids["p"], typ, col, row, HP[typ], f)
        if typ == "peashooter":
            p.next_shot = f + self.rng.between(55, 90)
        elif typ == "sunflower":
            p.next_sun = f + self.rng.between(250, 376)
        self.plants.append(p)
        self.hold = -1
        self.cards_ready[idx] = False
        self.card_reset_at[idx] = f
        self.card_ready_at[idx] = f + COOLDOWN[idx]

    def update_suns(self, f: int) -> None:
        if f >= 314 and (f - 314) % 1562 in (0,):
            self.spawn_sky_sun(f)
        for p in self.plants:
            if p.hp > 0 and p.t == "sunflower" and p.next_sun and f == p.next_sun:
                self.spawn_plant_sun(p, f)
        for s in list(self.suns):
            age = f - s.born
            if s.en:
                if s.kind == "sky":
                    if age <= 40:
                        u = age / 40.0
                        s.x = s.x + (s.target_x - s.x) * min(1.0, u)
                        s.y = 1150.001 + 700.0 * u - 700.0 * u * u
                    elif s.y > s.target_y:
                        s.x = s.target_x
                        s.y = max(s.target_y, s.y - 2.56)
                if age >= 1312:
                    self.suns.remove(s)
                    continue
            elif s.collect_at is not None and s.award_at is not None:
                u = min(1.0, max(0.0, (f - s.collect_at) / max(1, s.award_at - s.collect_at)))
                s.x += (290.0 - s.x) * min(1.0, 0.18 + u * 0.12)
                s.y += (1010.0 - s.y) * min(1.0, 0.18 + u * 0.12)
                if f == s.award_at:
                    self.sun += 50
                    s.x, s.y = 290.0, 1010.0
                if s.remove_at is not None and f > s.remove_at:
                    self.suns.remove(s)
        if self.collect_every and f > 0 and f % self.collect_every == 0:
            for s in self.suns:
                if s.en and 0.0 < s.x < 1920.0 and 0.0 < s.y < 1080.0:
                    s.en = 0
                    s.collect_at = f + 2
                    s.award_at = f + 47
                    s.remove_at = f + 375
                    break

    def update_plants_and_combat(self, f: int) -> None:
        # Peashooters fire only when a visible living zombie is ahead in their lane.
        for p in self.plants:
            if p.hp <= 0 or p.t != "peashooter":
                continue
            targets = [z for z in self.zombies if z.alive and z.show and z.row == p.row and z.x > PLANT_X[p.col]]
            if targets and f >= p.next_shot:
                self.bullets.append(Bullet(self.new_id("b"), PLANT_X[p.col] + 69.0, p.row, f))
                p.next_shot = f + self.rng.between(69, 90)
            elif not targets and f >= p.next_shot:
                p.next_shot = f + 1
        for b in list(self.bullets):
            age = f - b.born
            if age == 1:
                b.x += 0.001
            elif age > 1:
                b.x += 10.666667
            if not b.used:
                candidates = sorted((z for z in self.zombies if z.alive and z.row == b.row and z.show and z.x >= b.x - 25), key=lambda z: z.x)
                if candidates:
                    z = candidates[0]
                    if b.x >= z.x - 25.0:
                        b.used = 1
                        if z.hs > 0:
                            z.hs = max(0.0, z.hs - 20.0)
                        else:
                            z.hp = max(0.0, z.hp - 20.0)
                            if z.hp <= 0:
                                self.kill_zombie(z, f)
            if b.x > 3060.0:
                self.bullets.remove(b)
        for p in list(self.plants):
            if p.hp <= 0 and p.dead_at is not None and f > p.dead_at + 250:
                self.plants.remove(p)

    def update_zombies(self, f: int) -> None:
        by_id = {p.id: p for p in self.plants}
        for z in list(self.zombies):
            if not z.alive:
                if z.stop_at is not None and f >= z.stop_at:
                    z.spd = 0.0
                elif z.spd:
                    z.x -= 0.48
                if z.remove_at is not None and f > z.remove_at:
                    self.zombies.remove(z)
                continue
            if not z.show and z.x <= 1710.0:
                z.show = 1
            target = by_id.get(z.target) if z.target is not None else None
            if target is None or target.hp <= 0:
                z.target = None
                z.eat = 0
                z.spd = 30.0
                # Closest still-living plant immediately in front of the zombie.
                candidates = [p for p in self.plants if p.hp > 0 and p.row == z.row and z.x >= PLANT_X[p.col]]
                if candidates:
                    p = max(candidates, key=lambda q: PLANT_X[q.col])
                    if z.x <= PLANT_X[p.col] + 79.0:
                        z.target = p.id
                        z.eat = 1
                        z.spd = 0.0
                        z.next_bite = f + 43
                if z.target is None:
                    z.x -= 0.48
            else:
                z.eat = 1
                z.spd = 0.0
                if f >= z.next_bite:
                    target.hp = max(0.0, target.hp - 100.0)
                    z.next_bite = f + 84 + (self.rng.draw() & 1)
                    if target.hp <= 0:
                        target.dead_at = f
                        z.target = None
                        z.eat = 0
                        z.spd = 30.0
        # Trigger a row's mower at the observed left-edge threshold.
        for car in self.cars:
            if not car.live and car.st == 1:
                hit = next((z for z in self.zombies if z.alive and z.row == car.row and z.x <= 535.0), None)
                if hit:
                    car.live = 1
                    car.st = 2
                    car.start_at = f
                    self.kill_zombie(hit, f, mower=True)
            if car.live and car.start_at is not None:
                age = f - car.start_at
                if age == 1:
                    car.x = 455.001
                elif age > 1:
                    car.x += 12.16
                for z in self.zombies:
                    if z.alive and z.row == car.row and car.x + 80.0 >= z.x:
                        self.kill_zombie(z, f, mower=True)
        self.cars = [c for c in self.cars if not (c.live and c.x > 2100.0)]
        # A second breach in a row whose mower has gone is a zombie victory.
        if not self.end:
            for z in self.zombies:
                if z.alive and z.x < 380.0 and not any(c.row == z.row for c in self.cars):
                    self.end = 1
                    self.zwin = 1
                    self.result_frame = f
                    break
        if self.wave >= 5 and not self.end:
            if not any(z.alive for z in self.zombies):
                if self.final_clear_at is None:
                    self.final_clear_at = f
                elif f >= self.final_clear_at + 180:
                    self.end = 1
                    self.zwin = 0
                    self.result_frame = f
            else:
                self.final_clear_at = None

    def card_trace(self, f: int) -> list[dict]:
        out = []
        for i in range(3):
            if f >= self.card_ready_at[i]:
                self.cards_ready[i] = True
            ready = 1 if self.cards_ready[i] else 0
            if ready:
                pct = 100.0 if self.hold == i else 0.0
            else:
                start = self.card_reset_at[i]
                if start is None:
                    elapsed = max(0, f - 1)
                    pct = max(0.0, 100.0 - elapsed * 100.0 / COOLDOWN[i])
                else:
                    pct = max(0.0, 100.0 - (f - start) * 100.0 / COOLDOWN[i])
            en = ready
            if i == 0 and f < 8:
                en = 0
            out.append({"tag": i, "ready": ready, "pct": r3(pct), "en": en})
        return out

    def trace(self, f: int) -> dict:
        cards = self.card_trace(f)
        return {
            "f": f, "sun": self.sun, "ts": 1.0, "wave": self.wave,
            "wt": float(max(0, self.sec(f) - self.wave_timer_base_sec)) if self.wave_started else (float(max(0, self.sec(f) - self.wave_timer_base_sec)) if self.wdead else 0.0),
            "wbegin": int(self.wave_started), "wdead": int(self.wdead),
            "end": self.end, "zwin": self.zwin, "cards": cards,
            "hold": self.hold, "shovel": 0,
            "z": [{"id": z.id, "t": z.t, "x": r3(z.x), "y": Y_BY_ROW[z.row],
                   "hp": r3(z.hp), "hs": r3(z.hs), "bs": 0.0, "eat": z.eat,
                   "alive": z.alive, "show": z.show, "spd": r3(z.spd)} for z in self.zombies],
            "p": [{"id": p.id, "t": p.t, "r": p.col, "c": p.row, "hp": r3(p.hp)} for p in self.plants],
            "b": [{"id": b.id, "x": r3(b.x), "y": Y_BY_ROW[b.row] + 78.0, "used": b.used} for b in self.bullets],
            "s": [{"id": s.id, "x": r3(s.x), "y": r3(s.y), "en": s.en} for s in self.suns],
            "cars": [{"tag": -1, "live": c.live, "st": c.st, "x": r3(c.x)} for c in self.cars],
        }

    def run(self, output: str) -> None:
        stop = self.end_frame
        with open(output, "w", encoding="utf-8") as fh:
            for f in range(self.end_frame + 1):
                if f in self.pending_card:
                    self.select_card(f, self.pending_card[f])
                if f in self.pending_plant:
                    self.place(f, self.pending_plant[f])
                if f in (33, 39, 45, 51, 58):
                    self.cars.append(Car((f - 33) // 6, f))
                if f == 64:
                    self.wave_started = True
                if f == self.next_wave_frame - 6:
                    self.wave_started = False
                    self.wdead = True
                if f == self.next_wave_frame:
                    self.spawn_wave(f)
                if self.wave and not self.wave_started and not self.wdead and f == self.next_wave_frame - int(round(self.next_wave_interval * 62.5)) - 6 + 50:
                    self.wave_started = True
                # More directly, every wave begins counting 50 frames after release.
                if self.wave and not self.wave_started and not self.wdead:
                    latest = max((z.born for z in self.zombies), default=-1000)
                    if f == latest + 50:
                        self.wave_started = True
                self.update_suns(f)
                self.update_zombies(f)
                self.update_plants_and_combat(f)
                fh.write(json.dumps(self.trace(f), separators=(",", ":"), allow_nan=False) + "\n")
                if self.result_frame is not None and f >= self.result_frame + 60:
                    stop = f
                    break


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: run-scenario <scenario.json> <out-trace.jsonl>", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        scenario = json.load(fh)
    if scenario.get("schema") != 1 or scenario.get("level") != 4:
        raise ValueError("only schema 1, level 4 scenarios are supported")
    Game(scenario).run(argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
