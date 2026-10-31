#!/usr/bin/env python3
"""Deterministic, headless approximation of the observed Level 4 state machine."""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

MASK64 = (1 << 64) - 1
CARD_NAMES = ("sunflower", "peashooter", "wallnut")
COSTS = (50, 100, 50)
COOLDOWN_FRAMES = (469, 469, 1875)
COOLDOWN_RATES = (100.0 * 0.016 / 7.5, 100.0 * 0.016 / 7.5, 100.0 * 0.016 / 30.0)
PLANT_HP = (300.0, 300.0, 3000.0)
LANE_Y = tuple(130.0 + 138.0 * row for row in range(5))


class SplitMix:
    def __init__(self, seed: int):
        self.state = seed & MASK64

    def next_u32(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        z ^= z >> 31
        return (z >> 32) & 0xFFFFFFFF


@dataclass
class Card:
    tag: int
    ready: bool = False
    cooldown_start: int | None = None


@dataclass
class Plant:
    id: int
    kind: str
    row: int
    col: int
    hp: float
    born: int
    next_sun: int | None = None
    sun_count: int = 0
    zero_frame: int | None = None
    next_fire: int | None = None


@dataclass
class Zombie:
    id: int
    kind: str
    row: int
    x: float
    hp: float = 200.0
    hs: float = 0.0
    bs: float = 0.0
    eat: bool = False
    alive: bool = True
    show: bool = False
    spd: float = 30.0
    target: int | None = None
    next_attack: int | None = None
    death_frame: int | None = None
    death_cause: str = ""


@dataclass
class Bullet:
    id: int
    row: int
    x0: float
    y: float
    born: int
    used: bool = False

    def x_at(self, frame: int) -> float:
        age = frame - self.born
        if age <= 0:
            return self.x0
        if age == 1:
            return self.x0 + 0.001
        return self.x0 + 0.001 + (age - 1) * (2000.0 / 3.0) * 0.016


@dataclass
class Sun:
    id: int
    kind: str
    x0: float
    y0: float
    born: int
    target_y: float
    vx: float = 0.0
    enabled: bool = True
    disabled_frame: int | None = None
    reward_frame: int | None = None
    expire_frame: int | None = None

    def position(self, frame: int) -> tuple[float, float]:
        if not self.enabled:
            age = frame - (self.disabled_frame or frame)
            if age <= 0:
                return self.x0, self.y0
            # The collection animation exponentially approaches the counter.
            k = 0.80 ** age
            return 290.0 + (self.x0 - 290.0) * k, 1010.0 + (self.y0 - 1010.0) * k
        age = frame - self.born
        if self.kind == "produced":
            return self.x0, self.y0
        if age == 0:
            return self.x0, 1150.001
        # Measured launch arc, followed by the falling phase.
        if age <= 38:
            y = 1150.001 + 11.73 * age - 0.3815 * age * age
            x = self.x0 + self.vx * age
        else:
            x = self.x0 + self.vx * 38.0
            y38 = 1150.001 + 11.73 * 38.0 - 0.3815 * 38.0 * 38.0
            y = max(self.target_y, y38 - 2.56 * (age - 38))
        return x, y


@dataclass
class Mower:
    row: int
    born: int
    active_frame: int | None = None

    def x_at(self, frame: int) -> float:
        if self.active_frame is None:
            return 455.0
        age = frame - self.active_frame
        if age <= 0:
            return 455.0
        if age == 1:
            return 455.001
        return 455.001 + 12.16 * (age - 1)


class Simulator:
    def __init__(self, scenario: dict):
        self.scenario = scenario
        self.end_frame = int(scenario["end_frame"])
        self.sun_points = 10000
        self.cards = [Card(i) for i in range(3)]
        self.hold = -1
        self.plants: list[Plant] = []
        self.zombies: list[Zombie] = []
        self.bullets: list[Bullet] = []
        self.suns: list[Sun] = []
        self.mowers: list[Mower] = []
        self.next_plant_id = 1
        self.next_zombie_id = 1
        self.next_bullet_id = 1
        self.next_sun_id = 1
        self.wave = 0
        self.wbegin = 0
        self.wdead = 0
        self.end = 0
        self.zwin = 0
        self.last_wave_begin: int | None = None
        self.rng = SplitMix(int(scenario.get("device_seed", 0)))
        self.profile_draw = self.rng.next_u32()
        self.sun_rng = SplitMix(int(scenario.get("time_seed", 0)))
        self.actions_select: dict[int, list[dict]] = {}
        self.actions_place: dict[int, list[dict]] = {}
        for action in scenario.get("actions", []):
            if action.get("kind") != "plant":
                continue
            f = int(action["frame"])
            self.actions_select.setdefault(f + 4, []).append(action)
            self.actions_place.setdefault(f + 15, []).append(action)
        self.pending_collect: dict[int, list[int]] = {}
        self.reward_events: dict[int, int] = {}
        self.collect_every = int(scenario.get("collect_sun", {}).get("every_frames", 0))
        odd_shift = 6 if int(scenario.get("device_seed", 0)) & 1 else 0
        self.wave_spawns = [1139, 3195 + odd_shift, 5220 + odd_shift,
                            8014 + odd_shift, 10808 + odd_shift,
                            13602 + odd_shift, 16396 + odd_shift]

    @staticmethod
    def plant_x(col: int) -> float:
        return 631.0 + 122.0 * col

    def card_state(self, card: Card, frame: int) -> tuple[int, float, int]:
        if card.cooldown_start is None:
            if card.tag == 0:
                ready = frame >= 1
                pct = 0.0 if ready else 100.0
            else:
                elapsed = max(0, frame - 1)
                pct = max(0.0, 100.0 - elapsed * COOLDOWN_RATES[card.tag])
                ready = frame >= (470 if card.tag == 1 else 1876)
                if ready:
                    pct = 0.0
        else:
            elapsed = frame - card.cooldown_start
            ready = elapsed >= COOLDOWN_FRAMES[card.tag]
            pct = 0.0 if ready else max(0.0, 100.0 - elapsed * COOLDOWN_RATES[card.tag])
        card.ready = ready
        if self.hold == card.tag and ready:
            pct = 100.0
        enabled = int(ready and self.sun_points >= COSTS[card.tag] and frame >= 8)
        return int(ready), pct, enabled

    def create_plant(self, card_index: int, row: int, col: int, frame: int) -> None:
        if not (0 <= card_index < 3 and 0 <= row < 5 and 0 <= col < 9):
            return
        if any(p.row == row and p.col == col for p in self.plants):
            return
        kind = CARD_NAMES[card_index]
        p = Plant(self.next_plant_id, kind, row, col, PLANT_HP[card_index], frame)
        self.next_plant_id += 1
        if kind == "sunflower":
            first_delay = 313 if row in (0, 3) else 376
            p.next_sun = frame + first_delay
        self.plants.append(p)
        self.cards[card_index].cooldown_start = frame
        self.cards[card_index].ready = False

    def process_actions(self, frame: int) -> None:
        for action in self.actions_select.get(frame, []):
            idx = int(action.get("card_index", -1))
            if self.hold != -1 or not 0 <= idx < 3:
                continue
            ready, _, enabled = self.card_state(self.cards[idx], frame)
            if ready and enabled:
                self.hold = idx
                self.sun_points -= COSTS[idx]
        for action in self.actions_place.get(frame, []):
            idx = int(action.get("card_index", -1))
            if self.hold != idx:
                continue
            self.create_plant(idx, int(action.get("row", -1)), int(action.get("col", -1)), frame)
            self.hold = -1

    def sky_spawn_frame(self, n: int) -> int:
        return 314 + (3125 * n) // 2

    def add_sun(self, kind: str, x: float, y: float, frame: int, target_y: float = 350.0, vx: float = 0.0) -> None:
        life = 1312 if kind == "sky" else 425
        self.suns.append(Sun(self.next_sun_id, kind, x, y, frame, target_y, vx,
                             expire_frame=frame + life))
        self.next_sun_id += 1

    def process_sun_generation(self, frame: int) -> None:
        sky_index = next((n for n in range(16) if self.sky_spawn_frame(n) == frame), None)
        if sky_index is not None:
            d1, d2, d3 = self.sun_rng.next_u32(), self.sun_rng.next_u32(), self.sun_rng.next_u32()
            x = 650.0 + float((d1 >> 2) % 1194)
            target = 349.0 + 64.0 * (sky_index % 3)
            vx = ((d3 % 41) - 20) / 50.0
            self.add_sun("sky", x, 1150.001, frame, target, vx)
        for p in self.plants:
            if p.kind != "sunflower" or p.hp <= 0 or p.next_sun != frame:
                continue
            self.add_sun("produced", self.plant_x(p.col) - 1.0,
                         123.001 + 138.0 * p.row, frame,
                         123.001 + 138.0 * p.row)
            category = (p.row + 2) % 3
            if category == 0:
                interval = 1468 if p.sun_count == 0 else 1469
            elif category == 1:
                interval = 1531
            else:
                interval = 1594 if p.sun_count == 0 else 1593
            p.sun_count += 1
            p.next_sun = frame + interval

    def schedule_collection(self, frame: int) -> None:
        if not self.collect_every or frame <= 0 or frame % self.collect_every:
            return
        for sun in self.suns:
            if not sun.enabled:
                continue
            x, y = sun.position(frame)
            if 0.0 < x < 1920.0 and 0.0 < y < 1080.0:
                self.pending_collect.setdefault(frame + 3, []).append(sun.id)
                break

    def process_collections(self, frame: int) -> None:
        for sid in self.pending_collect.get(frame, []):
            sun = next((s for s in self.suns if s.id == sid), None)
            if sun is None or not sun.enabled:
                continue
            x, y = sun.position(frame)
            sun.x0, sun.y0 = x, y
            sun.enabled = False
            sun.disabled_frame = frame
            sun.reward_frame = frame + 44
            sun.expire_frame = min(sun.expire_frame or frame + 500,
                                   sun.born + (437 if sun.kind == "sky" else 425))
            self.reward_events[frame + 44] = self.reward_events.get(frame + 44, 0) + 50

    def wave_count(self) -> int:
        return 3 + (((self.profile_draw >> 2) ^ (self.profile_draw >> 26)) % 3)

    def wave_lanes(self, wave: int, count: int) -> list[int]:
        seed = int(self.scenario.get("device_seed", 0))
        if wave == 1:
            return [4]
        if wave == 2:
            lanes = [0, 1, 2, 3][:count]
            if count == 5:
                lanes.append(3 if seed & 1 else 2)
            return lanes
        if wave == 3:
            if count == 5:
                q = 2 if seed & 1 else 3
                return [0, 1, 4, q, q]
            return [0, 1, 2, 3][:count]
        if wave == 4 and count == 5:
            q = 4 if (self.profile_draw & 8) else 1
            missing = 1 if q == 4 else 3
            return [r for r in range(5) if r != missing] + [q]
        return [(wave + i * 2) % 5 for i in range(count)]

    def zombie_kind(self, wave: int, row: int, ordinal: int) -> str:
        seed = int(self.scenario.get("device_seed", 0))
        if wave == 2 and (self.profile_draw & 8) and row == seed % 2:
            return "cone"
        if wave == 3 and seed % 2 == 0 and row == (seed + 1) % 5 and ordinal == 0:
            return "cone"
        if wave == 4 and (self.profile_draw & 8):
            if row == 4 and ordinal == 0:
                return "bucket"
            if row == 3 and ordinal == 0:
                return "cone"
        if wave >= 5:
            if ordinal == 0:
                return "bucket"
            if ordinal == 1:
                return "cone"
        return "common"

    def spawn_wave(self, frame: int) -> None:
        self.wave += 1
        self.wdead = 0
        self.wbegin = 0
        self.last_wave_begin = frame + (50 if self.wave != 3 else 32)
        count = 1 if self.wave == 1 else self.wave_count()
        lanes = self.wave_lanes(self.wave, count)
        type_seen: dict[tuple[str, int], int] = {}
        for ordinal, row in enumerate(lanes):
            key_ord = type_seen.get(("slot", row), 0)
            kind = self.zombie_kind(self.wave, row, key_ord)
            type_seen[("slot", row)] = key_ord + 1
            position_draw = self.rng.next_u32()
            if self.wave == 1:
                x = 1730.0 + float((self.profile_draw >> 2) % 586)
            else:
                x = 1750.0 + float(position_draw % 551)
            hs = 600.0 if kind == "cone" else 1200.0 if kind == "bucket" else 0.0
            self.zombies.append(Zombie(self.next_zombie_id, kind, row, x, hs=hs))
            self.next_zombie_id += 1

    def process_waves(self, frame: int) -> None:
        if frame == 64:
            self.wbegin = 1
            self.last_wave_begin = 64
        elif self.last_wave_begin is not None and frame == self.last_wave_begin:
            self.wbegin = 1
        for spawn in self.wave_spawns:
            if frame == spawn - 6:
                self.wbegin = 0
                self.wdead = 1
            if frame == spawn:
                self.spawn_wave(frame)

    def wave_timer(self, frame: int) -> float:
        if self.wave == 0:
            return float(max(0, math.floor((frame - 1) * 0.016))) if frame >= 64 else 0.0
        spawn = self.wave_spawns[self.wave - 1] if self.wave <= len(self.wave_spawns) else frame
        if frame == spawn:
            return 0.0
        if self.last_wave_begin is None or frame < self.last_wave_begin:
            return 0.0
        return float(1 + math.floor((frame - self.last_wave_begin) * 0.016 + 1e-9))

    def damage_zombie(self, z: Zombie, amount: float, frame: int, cause: str) -> None:
        if not z.alive:
            return
        remaining = amount
        if z.hs > 0:
            used = min(z.hs, remaining)
            z.hs -= used
            remaining -= used
        if remaining > 0:
            z.hp -= remaining
        if z.hp <= 0:
            z.hp = 0.0
            z.alive = False
            z.eat = False
            z.target = None
            z.death_frame = frame
            z.death_cause = cause

    def update_zombies(self, frame: int) -> None:
        plant_by_id = {p.id: p for p in self.plants}
        for z in self.zombies:
            if not z.alive:
                if z.death_frame is not None and frame - z.death_frame >= 35:
                    z.spd = 0.0
                continue
            if z.eat:
                target = plant_by_id.get(z.target or -1)
                if target is None or target.hp <= 0:
                    z.eat = False
                    z.target = None
                    z.next_attack = None
                    z.spd = 30.0
                elif z.next_attack is not None and frame >= z.next_attack:
                    target.hp -= 100.0
                    z.next_attack += 65 + (z.id * 17) % 35
                    if target.hp <= 0 and target.zero_frame is None:
                        target.zero_frame = frame
                        for other in self.zombies:
                            if other.target == target.id:
                                other.eat = False
                                other.target = None
                                other.next_attack = None
                                if other.alive:
                                    other.spd = 30.0
            if not z.eat and z.alive:
                z.x -= 30.0 * 0.016
                candidates = [p for p in self.plants if p.row == z.row and p.hp > 0
                              and z.x >= self.plant_x(p.col) - 40.0]
                if candidates:
                    target = max(candidates, key=lambda p: p.col)
                    if z.x <= self.plant_x(target.col) + 79.0:
                        z.eat = True
                        z.target = target.id
                        z.spd = 0.0
                        z.next_attack = frame + 42 + (z.id * 7) % 18
            if z.x <= 1710.0:
                z.show = True
            mower = next((m for m in self.mowers if m.row == z.row and m.active_frame is None), None)
            if z.alive and z.x <= 535.0 and mower is not None:
                mower.active_frame = frame
                z.hs = 0.0
                self.damage_zombie(z, z.hp, frame, "mower")
            elif z.alive and z.x < 360.0 and mower is None:
                self.zwin = 1
                self.end = 1

    def update_mowers(self, frame: int) -> None:
        for mower in self.mowers:
            if mower.active_frame is None:
                continue
            mx = mower.x_at(frame)
            for z in self.zombies:
                if z.alive and z.row == mower.row and mx - 80.0 <= z.x <= mx + 125.0:
                    z.hs = 0.0
                    self.damage_zombie(z, z.hp, frame, "mower")
        self.mowers = [m for m in self.mowers
                       if m.active_frame is None or frame - m.active_frame < 137]

    def update_shooters(self, frame: int) -> None:
        for p in self.plants:
            if p.kind != "peashooter" or p.hp <= 0:
                continue
            targets = [z for z in self.zombies if z.alive and z.show and z.row == p.row
                       and z.x > self.plant_x(p.col)]
            if not targets:
                p.next_fire = None
                continue
            period = 70 if p.col % 2 == 0 else 90
            if p.next_fire is None:
                p.next_fire = frame + (93 if p.col % 2 == 0 else 87)
            if frame >= p.next_fire:
                self.bullets.append(Bullet(self.next_bullet_id, p.row,
                                           self.plant_x(p.col) + 69.0,
                                           208.0 + 138.0 * p.row, frame))
                self.next_bullet_id += 1
                p.next_fire += period

    def update_bullets(self, frame: int) -> None:
        for b in self.bullets:
            if b.used:
                continue
            bx = b.x_at(frame)
            targets = sorted((z for z in self.zombies if z.alive and z.row == b.row
                              and bx <= z.x + 80.0), key=lambda z: z.x)
            if targets and bx >= targets[0].x - 35.0:
                b.used = True
                self.damage_zombie(targets[0], 20.0, frame, "pea")
        self.bullets = [b for b in self.bullets if b.x_at(frame) <= 3000.0]

    def cleanup(self, frame: int) -> None:
        self.plants = [p for p in self.plants
                       if p.zero_frame is None or frame - p.zero_frame < 251]
        kept = []
        for z in self.zombies:
            if z.death_frame is None:
                kept.append(z)
                continue
            lifetime = 315 if z.death_cause == "mower" else 470
            if frame - z.death_frame < lifetime:
                kept.append(z)
        self.zombies = kept
        self.suns = [s for s in self.suns if s.expire_frame is None or frame < s.expire_frame]

    def frame_row(self, frame: int) -> dict:
        cards = []
        for card in self.cards:
            ready, pct, enabled = self.card_state(card, frame)
            cards.append({"tag": card.tag, "ready": ready, "pct": round(pct, 3), "en": enabled})
        plants = [{"id": p.id, "t": p.kind, "r": p.col, "c": p.row, "hp": round(p.hp, 3)}
                  for p in self.plants]
        zombies = [{"id": z.id, "t": z.kind, "x": round(z.x, 3), "y": LANE_Y[z.row],
                    "hp": round(z.hp, 3), "hs": round(z.hs, 3), "bs": round(z.bs, 3),
                    "eat": int(z.eat), "alive": int(z.alive), "show": int(z.show),
                    "spd": round(z.spd, 3)} for z in self.zombies]
        bullets = [{"id": b.id, "x": round(b.x_at(frame), 3), "y": b.y,
                    "used": int(b.used)} for b in self.bullets]
        suns = []
        for s in self.suns:
            x, y = s.position(frame)
            suns.append({"id": s.id, "x": round(x, 3), "y": round(y, 3), "en": int(s.enabled)})
        cars = [{"tag": -1, "live": int(m.active_frame is not None),
                 "st": 2 if m.active_frame is not None else 1,
                 "x": round(m.x_at(frame), 3)} for m in self.mowers]
        return {"f": frame, "sun": self.sun_points, "ts": 1.0, "wave": self.wave,
                "wt": self.wave_timer(frame), "wbegin": self.wbegin, "wdead": self.wdead,
                "end": self.end, "zwin": self.zwin, "cards": cards, "hold": self.hold,
                "shovel": 0, "z": zombies, "p": plants, "b": bullets, "s": suns,
                "cars": cars}

    def step(self, frame: int) -> dict:
        if frame in (33, 39, 45, 51, 58):
            self.mowers.append(Mower(len(self.mowers), frame))
        self.process_waves(frame)
        self.process_sun_generation(frame)
        self.process_actions(frame)
        if frame in self.reward_events:
            self.sun_points += self.reward_events[frame]
        self.update_zombies(frame)
        self.update_mowers(frame)
        self.update_shooters(frame)
        self.update_bullets(frame)
        self.schedule_collection(frame)
        self.process_collections(frame)
        self.cleanup(frame)
        return self.frame_row(frame)

    def run(self, output: Path) -> None:
        with output.open("w", encoding="utf-8") as out:
            for frame in range(self.end_frame + 1):
                out.write(json.dumps(self.step(frame), separators=(",", ":"), allow_nan=False))
                out.write("\n")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: run-scenario <scenario.json> <out-trace.jsonl>", file=sys.stderr)
        return 2
    scenario_path = Path(argv[1])
    output_path = Path(argv[2])
    with scenario_path.open(encoding="utf-8") as f:
        scenario = json.load(f)
    if scenario.get("schema") != 1 or scenario.get("level") != 4 or scenario.get("frame_ms") != 16:
        raise ValueError("only schema 1, Level 4, frame_ms 16 scenarios are supported")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Simulator(scenario).run(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
