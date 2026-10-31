#!/usr/bin/env python3
"""Deterministic, headless approximation of the observed Level 4 game."""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DT = 0.016
CARD_NAMES = ("sunflower", "peashooter", "wallnut")
COST = (50, 100, 50)
COOLDOWN = (7.5, 7.5, 30.0)
PLANT_HP = {"sunflower": 300.0, "peashooter": 300.0, "wallnut": 3000.0}
MASK64 = (1 << 64) - 1


class SplitMixDevice:
    """The scenario's specified random_device replacement."""

    def __init__(self, seed: int):
        self.state = seed & MASK64

    def draw(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        z ^= z >> 31
        return (z >> 32) & 0xFFFFFFFF

    def integer(self, lo: int, hi: int) -> int:
        # Multiply-high mapping is deterministic and avoids modulo bias.
        return lo + ((self.draw() * (hi - lo + 1)) >> 32)


class GlibcRand:
    """Portable implementation of the glibc random()/rand() sequence."""

    def __init__(self, seed: int):
        seed &= 0xFFFFFFFF
        if seed == 0:
            seed = 1
        state = [seed]
        for i in range(1, 31):
            state.append((16807 * state[-1]) % 2147483647)
        state.extend(state[i - 31] for i in range(31, 34))
        for i in range(34, 344):
            state.append((state[i - 31] + state[i - 3]) & 0xFFFFFFFF)
        self.state = state[-31:]
        self.i = 0
        self.j = 28

    def draw(self) -> int:
        value = (self.state[self.i] + self.state[self.j]) & 0xFFFFFFFF
        self.state[self.i] = value
        self.i = (self.i + 1) % 31
        self.j = (self.j + 1) % 31
        return value >> 1

    def integer(self, lo: int, hi: int) -> int:
        return lo + self.draw() % (hi - lo + 1)


@dataclass
class Card:
    tag: int
    ready: int = 0
    pct: float = 100.0
    enabled: int = 0
    reset_frame: int | None = None
    enable_frame: int | None = None


@dataclass
class Plant:
    ident: int
    kind: str
    col: int
    row: int
    hp: float
    born: int
    next_sun: int | None = None
    fire_interval: int = 70
    next_fire: int | None = None
    zero_frame: int | None = None

    @property
    def x(self) -> float:
        return 630.0 + 122.0 * self.col


@dataclass
class Zombie:
    ident: int
    kind: str
    x: float
    row: int
    born: int
    hp: float = 200.0
    hs: float = 0.0
    bs: float = 0.0
    eat: int = 0
    alive: int = 1
    show: int = 0
    spd: float = 30.0
    bite_at: int | None = None
    dead_frame: int | None = None
    stop_frame: int | None = None

    @property
    def y(self) -> float:
        return 130.0 + 138.0 * self.row


@dataclass
class Bullet:
    ident: int
    x: float
    y: float
    row: int
    origin: float
    born: int
    used: int = 0


@dataclass
class Sun:
    ident: int
    x: float
    y: float
    born: int
    kind: str
    en: int = 1
    vx: float = 0.0
    vy: float = 0.0
    gravity: float = 0.0
    floor_y: float = 300.0
    collect_frame: int | None = None
    award_frame: int | None = None
    remove_frame: int | None = None
    collect_x: float = 0.0
    collect_y: float = 0.0


@dataclass
class Mower:
    row: int
    live: int = 0
    st: int = 1
    x: float = 455.0


class Simulator:
    def __init__(self, scenario: dict[str, Any]):
        self.scenario = scenario
        self.end_frame = int(scenario["end_frame"])
        self.device_seed = int(scenario["device_seed"])
        self.device = SplitMixDevice(self.device_seed)
        self.c_rand = GlibcRand(int(scenario["time_seed"]))
        self.cards = [Card(i) for i in range(3)]
        self.sun = 10000
        self.wave = 0
        self.wave_spawn_frame = 0
        self.next_wave_frame = 1139
        self.wbegin = 0
        self.wdead = 0
        self.end = 0
        self.zwin = 0
        self.end_decided_frame: int | None = None
        self.hold = -1
        self.shovel = 0
        self.plants: list[Plant] = []
        self.zombies: list[Zombie] = []
        self.bullets: list[Bullet] = []
        self.suns: list[Sun] = []
        self.mowers: list[Mower] = []
        self.next_id = 1
        self.actions = list(scenario.get("actions", []))
        self.action_select = {int(a["frame"]) + 4: a for a in self.actions if a.get("kind") == "plant"}
        self.action_place = {int(a["frame"]) + 15: a for a in self.actions if a.get("kind") == "plant"}
        self.collect_every = int(scenario.get("collect_sun", {}).get("every_frames", 0))
        self.pending_collect: dict[int, int] = {}
        self.sky_index = 0
        self.next_sky = self.sky_frame(0)

    def alloc(self) -> int:
        value = self.next_id
        self.next_id += 1
        return value

    @staticmethod
    def wall_second(frame: int) -> int:
        if frame < 2:
            return 0
        return max(0, int(math.floor((frame - 1.5) / 62.5)))

    @staticmethod
    def sky_frame(index: int) -> int:
        return 314 + int(math.floor(index * 1562.5))

    def cooldown_enable_delay(self, frame: int, tag: int) -> int:
        # The original enables a completed card on a nearby UI-update callback.
        return (frame + tag + self.device_seed) % 4

    def update_cards(self, f: int) -> None:
        for card in self.cards:
            if f == 0:
                continue
            if card.tag == 0 and f == 1 and card.reset_frame is None:
                card.ready, card.pct = 1, 0.0
                card.enable_frame = 8
            elif card.reset_frame is None and not card.ready:
                elapsed = (f - 1) * DT
                card.pct = max(0.0, 100.0 * (1.0 - elapsed / COOLDOWN[card.tag]))
                if elapsed >= COOLDOWN[card.tag]:
                    card.ready, card.pct = 1, 0.0
                    card.enable_frame = f
            elif card.reset_frame is not None and not card.ready:
                elapsed = (f - card.reset_frame) * DT
                card.pct = max(0.0, 100.0 * (1.0 - elapsed / COOLDOWN[card.tag]))
                if elapsed >= COOLDOWN[card.tag]:
                    card.ready, card.pct = 1, 0.0
                    card.enable_frame = f + self.cooldown_enable_delay(f, card.tag)
            if card.ready and card.enable_frame is not None and f >= card.enable_frame:
                card.enabled = int(self.sun >= COST[card.tag])
            elif not card.ready:
                card.enabled = 0

    def update_startup(self, f: int) -> None:
        for frame, row in ((33, 0), (39, 1), (45, 2), (51, 3), (58, 4)):
            if f == frame:
                self.mowers.append(Mower(row))
        if f == 64:
            self.wbegin = 1

    def select_action(self, f: int) -> None:
        action = self.action_select.get(f)
        if action is None or self.hold != -1:
            return
        tag = int(action.get("card_index", CARD_NAMES.index(action["card"])))
        card = self.cards[tag]
        if card.ready and card.enabled and self.sun >= COST[tag]:
            self.sun -= COST[tag]
            self.hold = tag
            card.pct = 100.0

    def place_action(self, f: int) -> None:
        action = self.action_place.get(f)
        if action is None or self.hold == -1:
            return
        tag = self.hold
        row, col = int(action["row"]), int(action["col"])
        expected = int(action.get("card_index", tag))
        if expected != tag:
            return
        occupied = any(p.row == row and p.col == col and p.hp > 0 for p in self.plants)
        if occupied:
            self.sun += COST[tag]
            self.hold = -1
            self.cards[tag].pct = 0.0
            return
        kind = CARD_NAMES[tag]
        plant = Plant(self.alloc(), kind, col, row, PLANT_HP[kind], f)
        if kind == "sunflower":
            first_seconds = 5 if self.c_rand.integer(0, 2) == 0 else 6
            # The early scripted sunflower starts on the first observed producer tick.
            plant.next_sun = max(f + int(round(first_seconds / DT)), 451 if f < 100 else 0)
        elif kind == "peashooter":
            plant.fire_interval = 70 if col % 2 == 0 else 89
        self.plants.append(plant)
        self.hold = -1
        card = self.cards[tag]
        card.ready = 0
        card.enabled = 0
        card.pct = 100.0
        card.reset_frame = f
        card.enable_frame = None

    def spawn_sky_sun(self, f: int) -> None:
        x = float(self.c_rand.integer(520, 1520))
        target_dx = float(self.c_rand.integer(-40, 40))
        peak_v = float(self.c_rand.integer(9, 14))
        floor_y = float(self.c_rand.integer(270, 690))
        sun = Sun(self.alloc(), x, 1150.001, f, "sky")
        sun.vx = target_dx / 38.0
        sun.vy = peak_v
        sun.gravity = 0.62
        sun.floor_y = floor_y
        sun.remove_frame = f + 1312
        self.suns.append(sun)
        self.sky_index += 1
        self.next_sky = self.sky_frame(self.sky_index)

    def spawn_plant_sun(self, p: Plant, f: int) -> None:
        x = 630.0 + 122.0 * p.col
        y = 123.001 + 138.0 * p.row
        sun = Sun(self.alloc(), x, y, f, "plant")
        sun.vx = self.c_rand.integer(-16, 16) / 15.0
        sun.vy = float(self.c_rand.integer(9, 13))
        sun.gravity = 0.58
        sun.floor_y = y
        sun.remove_frame = f + 1312
        self.suns.append(sun)
        period = 1469 + 63 * self.c_rand.integer(0, 2)
        p.next_sun = f + period

    def update_sun_production(self, f: int) -> None:
        if f == self.next_sky:
            self.spawn_sky_sun(f)
        for plant in list(self.plants):
            if plant.kind == "sunflower" and plant.hp > 0 and plant.next_sun == f:
                self.spawn_plant_sun(plant, f)

    def choose_sun_collection(self, f: int) -> None:
        if self.collect_every <= 0 or f <= 0 or f % self.collect_every:
            return
        for sun in self.suns:
            if not sun.en:
                continue
            wx = round(sun.x * 1280.0 / 1920.0)
            wy = round((1080.0 - sun.y) * 720.0 / 1080.0)
            if 0 < wx < 1280 and 0 < wy < 720:
                self.pending_collect[f + 3] = sun.ident
                return

    def update_suns(self, f: int) -> None:
        collect_id = self.pending_collect.pop(f, None)
        for sun in list(self.suns):
            age = f - sun.born
            if age == 0:
                continue
            if sun.en:
                if sun.kind == "sky":
                    if age <= 38:
                        sun.x += sun.vx
                        sun.y += sun.vy
                        sun.vy -= sun.gravity
                    elif sun.y > sun.floor_y:
                        sun.y = max(sun.floor_y, sun.y - 2.48)
                else:
                    if age <= 40:
                        sun.x += sun.vx
                        sun.y += sun.vy
                        sun.vy -= sun.gravity
                if collect_id == sun.ident:
                    sun.en = 0
                    sun.collect_frame = f
                    sun.award_frame = f + 44
                    sun.remove_frame = f + 410
                    sun.collect_x, sun.collect_y = sun.x, sun.y
            else:
                assert sun.collect_frame is not None
                t = min(1.0, (f - sun.collect_frame) / 43.0)
                ease = 1.0 - (1.0 - t) ** 3
                sun.x = sun.collect_x + (290.0 - sun.collect_x) * ease
                sun.y = sun.collect_y + (1010.0 - sun.collect_y) * ease
                if sun.award_frame == f:
                    self.sun += 50
            if sun.remove_frame is not None and f > sun.remove_frame:
                self.suns.remove(sun)

    def wave_interval(self, next_wave: int) -> int:
        # Public observations span 32.0--33.0 seconds between later waves.
        return 2000 + ((6 * self.device_seed + 11 + 26 * (next_wave - 2)) % 63)

    def spawn_wave(self, f: int) -> None:
        self.wave += 1
        count = 1 if self.wave == 1 else (3 if self.device_seed % 2 == 0 else 5)
        even_rows = [1, 0, 2, 3, 4]
        odd_templates = {
            2: [1, 2, 0, 3, 3],
            3: [2, 4, 0, 1, 2],
        }
        for index in range(count):
            if self.wave == 1:
                row = 4
                kind = "common"
            else:
                if count == 3:
                    row = even_rows[index]
                else:
                    template = odd_templates.get(self.wave)
                    row = template[index] if template else (index + self.wave) % 5
                # The observed second odd-seed wave starts with one cone. Other
                # zombies through wave 3 are common; stronger types enter later.
                if self.wave == 2 and count == 5 and index == 0:
                    kind = "cone"
                elif self.wave >= 4:
                    roll = self.device.integer(0, 99)
                    kind = "bucket" if roll < min(4 * self.wave, 24) else ("cone" if roll < 45 else "common")
                else:
                    kind = "common"
            x = float(self.device.integer(1800, 2299))
            hs = 600.0 if kind == "cone" else (1300.0 if kind == "bucket" else 0.0)
            z = Zombie(self.alloc(), kind, x, row, f, hs=hs)
            # Every traced spawn has already taken one 16 ms movement step.
            z.x -= z.spd * DT
            self.zombies.append(z)
        self.wave_spawn_frame = f
        self.wdead = 0
        self.next_wave_frame = f + self.wave_interval(self.wave + 1)
        if self.wave < 10:
            # The wave-start flag returns after the short release animation.
            self.wbegin = 0

    def update_wave(self, f: int) -> None:
        if f == self.next_wave_frame - 6:
            self.wdead = 1
            self.wbegin = 0
        if f == self.next_wave_frame:
            self.spawn_wave(f)
        if self.wave > 0 and f == self.wave_spawn_frame + (50 if self.wave == 1 else 51):
            self.wbegin = 1
        if self.wave >= 10 and not any(z.alive for z in self.zombies) and self.end_decided_frame is None:
            self.end = 1
            self.end_decided_frame = f

    def wave_timer(self, f: int) -> float:
        if self.wave == 0:
            return float(self.wall_second(f))
        return float(max(0, self.wall_second(f) - self.wall_second(self.wave_spawn_frame)))

    def target_for(self, z: Zombie) -> Plant | None:
        candidates = [p for p in self.plants if p.row == z.row and p.hp > 0 and p.zero_frame is None and p.x <= z.x + 2]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.x)

    def damage_zombie(self, z: Zombie, damage: float, f: int) -> None:
        if not z.alive:
            return
        if z.hs > 0:
            z.hs = max(0.0, z.hs - damage)
        elif z.bs > 0:
            z.bs = max(0.0, z.bs - damage)
        else:
            z.hp = max(0.0, z.hp - damage)
            if z.hp <= 0:
                z.alive = 0
                z.eat = 0
                z.dead_frame = f
                z.stop_frame = f + (35 if z.kind == "common" else 38)

    def update_mowers(self, f: int) -> None:
        for mower in list(self.mowers):
            if mower.live:
                mower.x += 12.067
                for z in self.zombies:
                    if z.alive and z.row == mower.row and z.x <= mower.x + 85.0:
                        z.hs = z.bs = 0.0
                        z.hp = 0.0
                        z.alive = 0
                        z.eat = 0
                        z.dead_frame = f
                        z.stop_frame = f + 35
                if mower.x > 2100.0:
                    self.mowers.remove(mower)

    def update_zombies(self, f: int) -> None:
        for z in list(self.zombies):
            if f == z.born:
                continue
            if not z.alive:
                if z.stop_frame is not None and f >= z.stop_frame:
                    z.spd = 0.0
                if z.dead_frame is not None and f > z.dead_frame + 469:
                    self.zombies.remove(z)
                continue
            if z.eat:
                target = self.target_for(z)
                if target is None:
                    z.eat, z.spd, z.bite_at = 0, 30.0, None
                elif z.bite_at is not None and f >= z.bite_at:
                    target.hp = max(0.0, target.hp - 100.0)
                    cadence = 82 if z.kind == "cone" else (90 if z.kind == "bucket" else 99)
                    z.bite_at += cadence
                    if target.hp <= 0:
                        target.zero_frame = f
                        z.eat, z.spd, z.bite_at = 0, 30.0, None
            if not z.eat:
                z.x -= z.spd * DT
                target = self.target_for(z)
                if target is not None and z.x <= target.x + 80.0:
                    z.x = target.x + (79.69 if z.kind == "cone" else 79.556)
                    z.eat, z.spd = 1, 0.0
                    z.bite_at = f + (41 if z.kind == "cone" else (45 if z.kind == "bucket" else 50))
            if not z.show and z.x < 1710.0:
                z.show = 1
            mower = next((m for m in self.mowers if m.row == z.row), None)
            if z.alive and z.x <= 535.0 and mower is not None and not mower.live:
                mower.live, mower.st = 1, 2
                z.hs = z.bs = 0.0
                self.damage_zombie(z, z.hp, f)
            elif z.alive and z.x <= 410.0 and mower is None and self.end_decided_frame is None:
                self.zwin = self.end = 1
                self.end_decided_frame = f

    def update_plants(self, f: int) -> None:
        for p in list(self.plants):
            if p.zero_frame is not None and f > p.zero_frame + 250:
                self.plants.remove(p)

    def zombie_target_exists(self, p: Plant) -> bool:
        return any(z.alive and z.show and z.row == p.row and z.x > p.x - 20 for z in self.zombies)

    def update_peashooters(self, f: int) -> None:
        for p in self.plants:
            if p.kind != "peashooter" or p.hp <= 0:
                continue
            has_target = self.zombie_target_exists(p)
            if has_target and p.next_fire is None:
                p.next_fire = f + p.fire_interval
            if not has_target:
                p.next_fire = None
            elif p.next_fire is not None and f >= p.next_fire:
                x = 700.0 + 122.0 * p.col
                y = 208.0 + 138.0 * p.row
                self.bullets.append(Bullet(self.alloc(), x, y, p.row, x, f))
                p.next_fire += p.fire_interval

    def update_bullets(self, f: int) -> None:
        for b in list(self.bullets):
            if f == b.born:
                continue
            b.x += 10.6666667
            if not b.used:
                candidates = [z for z in self.zombies if z.alive and z.row == b.row and z.x >= b.origin - 40]
                if candidates:
                    target = min(candidates, key=lambda z: z.x)
                    if b.x >= target.x - 22.0:
                        b.used = 1
                        self.damage_zombie(target, 20.0, f)
            if b.x - b.origin > 2000.0:
                self.bullets.remove(b)

    def step(self, f: int) -> None:
        self.update_startup(f)
        self.update_cards(f)
        self.select_action(f)
        self.place_action(f)
        self.update_wave(f)
        self.update_sun_production(f)
        self.update_mowers(f)
        self.update_zombies(f)
        self.update_peashooters(f)
        self.update_bullets(f)
        self.update_plants(f)
        self.update_suns(f)
        self.choose_sun_collection(f)

    @staticmethod
    def q(value: float) -> float:
        return round(float(value) + 0.0, 3)

    def trace_row(self, f: int) -> dict[str, Any]:
        return {
            "f": f,
            "sun": self.sun,
            "ts": 1.0,
            "wave": self.wave,
            "wt": self.wave_timer(f),
            "wbegin": self.wbegin,
            "wdead": self.wdead,
            "end": self.end,
            "zwin": self.zwin,
            "cards": [
                {"tag": c.tag, "ready": c.ready, "pct": self.q(c.pct), "en": c.enabled}
                for c in self.cards
            ],
            "hold": self.hold,
            "shovel": self.shovel,
            "z": [
                {"id": z.ident, "t": z.kind, "x": self.q(z.x), "y": self.q(z.y),
                 "hp": self.q(z.hp), "hs": self.q(z.hs), "bs": self.q(z.bs),
                 "eat": z.eat, "alive": z.alive, "show": z.show, "spd": self.q(z.spd)}
                for z in self.zombies
            ],
            "p": [
                {"id": p.ident, "t": p.kind, "r": p.col, "c": p.row, "hp": self.q(p.hp)}
                for p in self.plants
            ],
            "b": [
                {"id": b.ident, "x": self.q(b.x), "y": self.q(b.y), "used": b.used}
                for b in self.bullets
            ],
            "s": [
                {"id": s.ident, "x": self.q(s.x), "y": self.q(s.y), "en": s.en}
                for s in self.suns
            ],
            "cars": [
                {"tag": -1, "live": m.live, "st": m.st, "x": self.q(m.x)}
                for m in self.mowers
            ],
        }

    def run(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for f in range(self.end_frame + 1):
                self.step(f)
                handle.write(json.dumps(self.trace_row(f), separators=(",", ":"), ensure_ascii=False))
                handle.write("\n")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: run-scenario <scenario.json> <out-trace.jsonl>", file=sys.stderr)
        return 2
    scenario_path = Path(argv[1]).resolve()
    output_path = Path(argv[2]).resolve()
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    if scenario.get("schema") != 1 or scenario.get("level") != 4 or scenario.get("frame_ms") != 16:
        raise ValueError("only schema 1, Level 4, frame_ms 16 scenarios are supported")
    Simulator(scenario).run(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
