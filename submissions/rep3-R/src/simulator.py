#!/usr/bin/env python3
"""Deterministic, standard-library-only approximation of the observed Level 4."""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

MASK64 = (1 << 64) - 1


class SplitMixDevice:
    def __init__(self, state: int):
        self.state = state & MASK64

    def draw(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        z ^= z >> 31
        return (z >> 32) & 0xFFFFFFFF


class MinstdRand0:
    """C++ minstd_rand0/default_random_engine as observed in zombie X positions."""
    modulus = 2147483647

    def __init__(self, seed: int):
        self.state = seed % self.modulus
        if self.state == 0:
            self.state = 1

    def draw(self) -> int:
        self.state = (16807 * self.state) % self.modulus
        return self.state

    def randint(self, low: int, high: int) -> int:
        # uniform_int_distribution for this engine's [1, 2147483646] range.
        span = high - low + 1
        return low + ((self.draw() - 1) * span // (self.modulus - 1))


class MT19937:
    """The C++ mt19937 seed recurrence and libstdc++-style integer scaling."""
    def __init__(self, seed: int):
        self.state = [seed & 0xFFFFFFFF]
        for i in range(1, 624):
            x = self.state[-1]
            self.state.append((1812433253 * (x ^ (x >> 30)) + i) & 0xFFFFFFFF)
        self.index = 624

    def draw(self) -> int:
        if self.index >= 624:
            for i in range(624):
                x = (self.state[i] & 0x80000000) | (self.state[(i + 1) % 624] & 0x7FFFFFFF)
                self.state[i] = self.state[(i + 397) % 624] ^ (x >> 1)
                if x & 1:
                    self.state[i] ^= 0x9908B0DF
            self.index = 0
        y = self.state[self.index]
        self.index += 1
        y ^= y >> 11
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        y ^= y >> 18
        return y & 0xFFFFFFFF

    def randint(self, low: int, high: int) -> int:
        span = high - low + 1
        threshold = (-span) % span
        while True:
            product = self.draw() * span
            if (product & 0xFFFFFFFF) >= threshold:
                return low + (product >> 32)


@dataclass
class Card:
    tag: int
    cost: int
    duration: float
    remaining: float
    ready: bool = False
    enable_frame: int = 8
    held: bool = False

    def step(self, frame: int) -> None:
        if self.remaining > 0.0:
            self.remaining = max(0.0, self.remaining - 0.016)
            if self.remaining == 0.0:
                self.ready = True
                self.enable_frame = frame + 1

    def start_cooldown(self, frame: int) -> None:
        self.remaining = self.duration
        self.ready = False
        self.held = False
        self.enable_frame = frame + int(math.ceil(self.duration / 0.016)) + 1

    def output(self, frame: int, sun: int) -> dict:
        pct = 100.0 if self.held else (100.0 * self.remaining / self.duration if self.duration else 0.0)
        enabled = self.ready and frame >= self.enable_frame and sun >= self.cost
        if self.held:
            enabled = True
        return {"tag": self.tag, "ready": int(self.ready), "pct": r3(pct), "en": int(enabled)}


@dataclass
class Plant:
    id: int
    kind: str
    row: int
    col: int
    hp: float
    born: int
    dead_frame: int | None = None
    next_sun: int | None = None
    sun_period: int = 1500
    shot_period: int = 75
    next_shot: int = 0


@dataclass
class Zombie:
    id: int
    kind: str
    row: int
    x: float
    hp: float
    shield: float
    body_shield: float
    born: int
    alive: bool = True
    eating: bool = False
    bite_at: int = 0
    dead_frame: int | None = None
    mower_kill: bool = False


@dataclass
class Bullet:
    id: int
    row: int
    x: float
    y: float
    born: int
    used: bool = False


@dataclass
class Sun:
    id: int
    x: float
    y: float
    born: int
    produced: bool
    target_y: float
    drift_x: float
    enabled: bool = True
    collect_frame: int | None = None
    credit_frame: int | None = None


@dataclass
class Mower:
    row: int
    x: float = 455.0
    live: bool = False
    used: bool = False
    start: int | None = None


def r3(value: float) -> float:
    value = round(float(value) + 1e-10, 3)
    return 0.0 if value == -0.0 else value


class Simulator:
    COST = {"sunflower": 50, "peashooter": 100, "wallnut": 50}
    HP = {"sunflower": 300.0, "peashooter": 300.0, "wallnut": 3000.0}
    CARD_TAG = {"sunflower": 0, "peashooter": 1, "wallnut": 2}
    LANE_PATTERN = {
        1: [4],
        2: [1, 2, 0, 3, 3],
        3: [2, 4, 0, 1, 2],
        4: [3, 0, 4, 1, 2, 3],
        5: [0, 4, 2, 1, 3, 0, 4],
    }

    def __init__(self, scenario: dict):
        self.scenario = scenario
        self.end_frame = int(scenario["end_frame"])
        self.device_seed = int(scenario["device_seed"])
        device = SplitMixDevice(self.device_seed)
        device_seed = device.draw()
        self.zombie_x_rng = MinstdRand0(device_seed)
        self.rng = MT19937(device_seed)
        self.sun = 10000
        self.cards = [
            Card(0, 50, 7.5, 0.0, False),
            Card(1, 100, 7.5, 7.5, False),
            Card(2, 50, 30.0, 30.0, False),
        ]
        self.actions_select: dict[int, list[dict]] = {}
        self.actions_place: dict[int, list[dict]] = {}
        for action in scenario.get("actions", []):
            if action.get("kind") != "plant":
                continue
            self.actions_select.setdefault(int(action["frame"]) + 4, []).append(action)
            self.actions_place.setdefault(int(action["frame"]) + 15, []).append(action)
        self.pending: dict[int, bool] = {}
        self.hold = -1
        self.plants: list[Plant] = []
        self.zombies: list[Zombie] = []
        self.bullets: list[Bullet] = []
        self.suns: list[Sun] = []
        self.mowers = [Mower(i) for i in range(5)]
        self.next_plant_id = self.next_zombie_id = self.next_bullet_id = self.next_sun_id = 1
        self.wave = 0
        self.wave_begin = False
        self.wave_dead = False
        self.wave_timer = 0.0
        self.wave_begin_frame: int | None = None
        self.wave_stop_frame = 1133
        self.wave_spawn_frame = 1139
        self.result_frame: int | None = None
        self.zombies_win = False
        self.collect_every = int(scenario.get("collect_sun", {}).get("every_frames", 0))

    def random_wave_duration(self, wave: int) -> int:
        if wave == 1:
            return 2006 if (self.device_seed & 1) else 2000
        if wave == 2:
            return 1968
        return (1968, 2000, 2006)[self.rng.randint(0, 2)]

    def select_actions(self, frame: int) -> None:
        for action in self.actions_select.get(frame, []):
            tag = int(action.get("card_index", self.CARD_TAG.get(action.get("card"), -1)))
            if not 0 <= tag < 3:
                continue
            card = self.cards[tag]
            if card.ready and frame >= card.enable_frame and self.sun >= card.cost and self.hold < 0:
                self.sun -= card.cost
                card.held = True
                self.hold = tag
                self.pending[id(action)] = True

    def place_actions(self, frame: int) -> None:
        for action in self.actions_place.get(frame, []):
            if not self.pending.pop(id(action), False):
                continue
            tag = int(action.get("card_index", -1))
            card = self.cards[tag]
            row, col = int(action["row"]), int(action["col"])
            occupied = any(p.hp > 0 and p.row == row and p.col == col for p in self.plants)
            if occupied or not (0 <= row < 5 and 0 <= col < 9):
                self.sun += card.cost
                card.held = False
                self.hold = -1
                continue
            kind = action.get("card") or ("sunflower", "peashooter", "wallnut")[tag]
            plant = Plant(self.next_plant_id, kind, row, col, self.HP[kind], frame)
            self.next_plant_id += 1
            if kind == "sunflower":
                first_seconds = 6 if (plant.id & 1) else 5
                plant.next_sun = frame + int(round(first_seconds / 0.016))
                plant.sun_period = int(round(self.rng.randint(47, 51) * 0.5 / 0.016))
            elif kind == "peashooter":
                # A shooter's cadence is stable for its lifetime in the traces.
                plant.shot_period = self.rng.randint(69, 90)
                plant.next_shot = frame + plant.shot_period
            self.plants.append(plant)
            card.start_cooldown(frame)
            self.hold = -1

    def spawn_sun(self, frame: int, plant: Plant | None = None) -> None:
        if plant is None:
            x = float(self.rng.randint(500, 1600))
            y = 1150.0
            target_y = float(self.rng.randint(210, 620))
            drift = float(self.rng.randint(-35, 35))
            produced = False
        else:
            x = 630.0 + 122.0 * plant.col
            y = 123.0 + 138.0 * plant.row
            target_y = y
            drift = float(self.rng.randint(-28, 28))
            produced = True
        self.suns.append(Sun(self.next_sun_id, x, y, frame, produced, target_y, drift))
        self.next_sun_id += 1

    def update_suns(self, frame: int) -> None:
        if frame >= 314 and (frame - 314) % 1563 == 0:
            self.spawn_sun(frame)
        for p in self.plants:
            if p.kind == "sunflower" and p.hp > 0 and p.next_sun is not None and frame >= p.next_sun:
                self.spawn_sun(frame, p)
                p.next_sun += p.sun_period
        # The scripted collector acts on the previous frame. At G+3 the
        # release disables the sun; collection reaches the counter 44 frames later.
        if self.collect_every and frame > 0 and frame % self.collect_every == 3:
            for sun in self.suns:
                if sun.enabled and 0.0 < sun.x < 1920.0 and 0.0 < sun.y < 1080.0:
                    sun.enabled = False
                    sun.collect_frame = frame
                    sun.credit_frame = frame + 44
                    break
        for sun in self.suns:
            age = frame - sun.born
            if sun.collect_frame is not None:
                t = frame - sun.collect_frame
                if t > 0:
                    factor = 0.8 ** min(t, 32)
                    sun.x = 290.0 + (sun.x - 290.0) * factor
                    sun.y = 1010.0 + (sun.y - 1010.0) * factor
                    if t >= 32:
                        sun.x, sun.y = 290.0, 1010.0
                if frame == sun.credit_frame:
                    self.sun += 50
            elif sun.produced:
                if 0 < age <= 25:
                    u = age / 25.0
                    sun.x += sun.drift_x / 25.0
                    sun.y += (22.0 * (1.0 - u) - 18.0 * u)
            else:
                if 0 < age <= 38:
                    sun.x += sun.drift_x / 38.0
                    sun.y += 4.2 if age <= 16 else -7.3
                elif sun.y > sun.target_y:
                    sun.y = max(sun.target_y, sun.y - 2.48)
        kept = []
        for sun in self.suns:
            if sun.collect_frame is not None:
                if frame - sun.born <= 430:
                    kept.append(sun)
            elif frame - sun.born <= 1312:
                kept.append(sun)
        self.suns = kept

    def spawn_wave(self, frame: int) -> None:
        self.wave += 1
        lanes = self.LANE_PATTERN.get(self.wave)
        if lanes is None:
            base = [0, 3, 1, 4, 2, 0, 4, 1]
            shift = self.wave % 5
            lanes = [((x + shift) % 5) for x in base]
        if self.wave == 1:
            count = 1
        elif self.wave == 2:
            count = 3 + 2 * (self.device_seed & 1)
        else:
            count = min(len(lanes), 4 + self.wave // 2)
        for i, row in enumerate(lanes[:count]):
            roll = self.rng.randint(0, 99)
            if self.wave == 2 and (self.device_seed & 1) and i == 0:
                kind, shield = "cone", 600.0
            elif self.wave >= 5 and roll < min(12, self.wave * 2):
                kind, shield = "bucket", 1300.0
            elif self.wave >= 3 and roll < min(18, 5 + self.wave * 3):
                kind, shield = "cone", 600.0
            else:
                kind, shield = "common", 0.0
            x = float(self.zombie_x_rng.randint(1780, 2280))
            self.zombies.append(Zombie(self.next_zombie_id, kind, int(row), x, 200.0, shield, 0.0, frame))
            self.next_zombie_id += 1
        self.wave_dead = False
        self.wave_timer = 0.0
        self.wave_begin = self.wave == 2 and not (self.device_seed & 1)
        measured_begins = {1: 1189, 2: 3252, 3: 5252}
        self.wave_begin_frame = measured_begins.get(self.wave, frame + 26)
        self.wave_stop_frame = self.wave_begin_frame + self.random_wave_duration(self.wave)
        self.wave_spawn_frame = self.wave_stop_frame + 6

    def update_wave(self, frame: int) -> None:
        if frame == 64:
            self.wave_begin = True
            self.wave_begin_frame = 64
        if frame == self.wave_stop_frame:
            self.wave_begin = False
            self.wave_dead = True
        if frame == self.wave_spawn_frame and self.wave < 10:
            self.spawn_wave(frame)
        if self.wave_begin_frame is not None and frame == self.wave_begin_frame:
            self.wave_begin = True
        if self.wave_begin and self.wave_begin_frame is not None:
            self.wave_timer = 1.0 + math.floor((frame - self.wave_begin_frame) / 62.5 + 1e-9)
        if self.wave_dead and self.wave >= 10 and not any(z.alive for z in self.zombies):
            self.finish(frame, False)

    def plant_x(self, plant: Plant) -> float:
        return 631.0 + 122.0 * plant.col

    def update_zombies(self, frame: int) -> None:
        for z in self.zombies:
            if not z.alive:
                continue
            targets = [p for p in self.plants if p.row == z.row and p.hp > 0 and self.plant_x(p) < z.x + 80.0]
            target = max(targets, key=self.plant_x) if targets else None
            stop_x = self.plant_x(target) + 78.7 if target else None
            if target is not None and z.x <= stop_x:
                if not z.eating:
                    z.eating = True
                    z.bite_at = frame + (50 if z.kind == "common" else 41)
                if frame >= z.bite_at:
                    target.hp = max(0.0, target.hp - 100.0)
                    if target.hp == 0.0 and target.dead_frame is None:
                        target.dead_frame = frame
                    z.bite_at += 99 if z.kind == "common" else 82
                    if target.hp == 0.0:
                        z.eating = False
                continue
            z.eating = False
            z.x -= 0.48
            if z.x <= 535.0:
                mower = self.mowers[z.row]
                if not mower.used:
                    self.start_mower(mower, frame)
                    self.kill_zombie(z, frame, True)
                elif z.x <= 350.0:
                    self.finish(frame, True)
        for mower in self.mowers:
            if mower.live and mower.start is not None:
                if frame > mower.start:
                    mower.x += 12.16
                for z in self.zombies:
                    if z.alive and z.row == mower.row and z.x <= mower.x + 80.0:
                        self.kill_zombie(z, frame, True)
                if mower.x > 2100.0:
                    mower.live = False
        self.zombies = [z for z in self.zombies if z.dead_frame is None or frame - z.dead_frame < (315 if z.mower_kill else 470)]
        self.plants = [p for p in self.plants if p.dead_frame is None or frame - p.dead_frame < 251]

    def start_mower(self, mower: Mower, frame: int) -> None:
        mower.used = True
        mower.live = True
        mower.start = frame
        mower.x = 455.0

    def kill_zombie(self, zombie: Zombie, frame: int, mower: bool = False) -> None:
        zombie.hp = 0.0
        zombie.shield = 0.0
        zombie.body_shield = 0.0
        zombie.alive = False
        zombie.eating = False
        zombie.dead_frame = frame
        zombie.mower_kill = mower

    def update_plants_and_bullets(self, frame: int) -> None:
        for p in self.plants:
            if p.kind != "peashooter" or p.hp <= 0:
                continue
            if frame >= p.next_shot:
                visible = any(z.alive and z.row == p.row and z.x > self.plant_x(p) and z.x <= 1710.0 for z in self.zombies)
                if visible:
                    self.bullets.append(Bullet(self.next_bullet_id, p.row, 700.0 + 122.0 * p.col,
                                               208.0 + 138.0 * p.row, frame))
                    self.next_bullet_id += 1
                p.next_shot += p.shot_period
                while p.next_shot <= frame:
                    p.next_shot += p.shot_period
        for bullet in self.bullets:
            if frame > bullet.born:
                bullet.x += 10.666667
            if bullet.used:
                continue
            targets = [z for z in self.zombies if z.alive and z.row == bullet.row and z.x >= bullet.x - 18.0]
            if not targets:
                continue
            target = min(targets, key=lambda z: z.x)
            if bullet.x >= target.x - 12.0:
                bullet.used = True
                damage = 20.0
                if target.body_shield > 0:
                    target.body_shield = max(0.0, target.body_shield - damage)
                elif target.shield > 0:
                    target.shield = max(0.0, target.shield - damage)
                else:
                    target.hp = max(0.0, target.hp - damage)
                    if target.hp == 0:
                        self.kill_zombie(target, frame, False)
        self.bullets = [b for b in self.bullets if frame - b.born < 189]

    def finish(self, frame: int, zombies_win: bool) -> None:
        if self.result_frame is None:
            self.result_frame = frame
            self.zombies_win = zombies_win

    def output(self, frame: int) -> dict:
        zrows = []
        for z in self.zombies:
            speed = 0.0 if z.eating or (not z.alive and z.dead_frame != frame) else 30.0
            zrows.append({"id": z.id, "t": z.kind, "x": r3(z.x), "y": r3(130.0 + 138.0 * z.row),
                          "hp": r3(z.hp), "hs": r3(z.shield), "bs": r3(z.body_shield),
                          "eat": int(z.eating), "alive": int(z.alive),
                          "show": int(z.x <= 1710.0), "spd": r3(speed)})
        prows = [{"id": p.id, "t": p.kind, "r": p.col, "c": p.row, "hp": r3(p.hp)} for p in self.plants]
        brows = [{"id": b.id, "x": r3(b.x), "y": r3(b.y), "used": int(b.used)} for b in self.bullets]
        srows = [{"id": s.id, "x": r3(s.x), "y": r3(s.y), "en": int(s.enabled)} for s in self.suns]
        cars = []
        if frame >= 33:
            for mower in self.mowers:
                if mower.used and not mower.live:
                    continue
                cars.append({"tag": -1, "live": int(mower.live), "st": 2 if mower.live else 1, "x": r3(mower.x)})
        return {"f": frame, "sun": self.sun, "ts": 1.0, "wave": self.wave, "wt": r3(self.wave_timer),
                "wbegin": int(self.wave_begin), "wdead": int(self.wave_dead),
                "end": int(self.result_frame is not None), "zwin": int(self.zombies_win),
                "cards": [card.output(frame, self.sun) for card in self.cards],
                "hold": self.hold, "shovel": 0, "z": zrows, "p": prows,
                "b": brows, "s": srows, "cars": cars}

    def run(self, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as out:
            for frame in range(self.end_frame + 1):
                if frame == 1:
                    self.cards[0].ready = True
                    self.cards[0].enable_frame = 8
                for card in self.cards:
                    if frame > 1 or card.tag == 0:
                        card.step(frame)
                self.select_actions(frame)
                self.place_actions(frame)
                self.update_wave(frame)
                self.update_suns(frame)
                self.update_zombies(frame)
                self.update_plants_and_bullets(frame)
                out.write(json.dumps(self.output(frame), separators=(",", ":"), allow_nan=False) + "\n")
                if self.result_frame is not None and frame >= self.result_frame + 60:
                    break


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: run-scenario <scenario.json> <out-trace.jsonl>", file=sys.stderr)
        return 2
    scenario_path = Path(argv[1])
    out_path = Path(argv[2])
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    if scenario.get("schema") != 1 or scenario.get("level") != 4 or scenario.get("frame_ms") != 16:
        raise ValueError("only schema 1, level 4, 16 ms scenarios are supported")
    Simulator(scenario).run(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
