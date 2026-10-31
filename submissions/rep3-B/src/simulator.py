#!/usr/bin/env python3
"""Deterministic, headless approximation of the observed Level 4 game."""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

DT = 0.016
CARD_NAMES = ("sunflower", "peashooter", "wallnut")
COST = (50, 100, 50)
COOLDOWN = (469, 469, 1875)
LANE_Y = (130.0, 268.0, 406.0, 544.0, 682.0)
PLANT_HP = {"sunflower": 300.0, "peashooter": 300.0, "wallnut": 3000.0}


class RNG:
    """The scenario-specified random_device stream, used directly and reproducibly."""
    def __init__(self, seed: int):
        self.state = seed & ((1 << 64) - 1)

    def u32(self) -> int:
        mask = (1 << 64) - 1
        self.state = (self.state + 0x9E3779B97F4A7C15) & mask
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & mask
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & mask
        z ^= z >> 31
        return z >> 32

    def range(self, lo: int, hi: int) -> int:
        return lo + self.u32() % (hi - lo + 1)


@dataclass
class Plant:
    id: int
    kind: str
    row: int
    col: int
    hp: float
    made: int
    next_sun: int | None = None
    bite_at: int | None = None
    shot_at: int | None = None
    shot_period: int = 78
    dead_at: int | None = None
    remove_at: int | None = None


@dataclass
class Zombie:
    id: int
    kind: str
    lane: int
    x: float
    hp: float = 200.0
    hs: float = 0.0
    bs: float = 0.0
    eat: int = 0
    alive: int = 1
    show: int = 0
    spd: float = 30.0
    dead_at: int | None = None
    remove_at: int | None = None


@dataclass
class Bullet:
    id: int
    lane: int
    x: float
    born: int
    used: int = 0


@dataclass
class Sun:
    id: int
    x: float
    y: float
    born: int
    kind: str
    vx: float
    vy: float
    floor_y: float
    en: int = 1
    collect_at: int | None = None
    paid_at: int | None = None
    remove_at: int | None = None


@dataclass
class Mower:
    lane: int
    x: float = 455.0
    live: int = 0
    st: int = 1
    born: int = 0


class Sim:
    def __init__(self, scenario: dict):
        self.sc = scenario
        self.end_frame = int(scenario["end_frame"])
        self.rng = RNG(int(scenario["device_seed"]))
        self.sun = 10000
        self.wave = 0
        self.wave_spawn = {1139: 1}
        self.next_wave_frame = 1139
        self.wave_reset = 1139
        self.wave_variant = self.rng.u32() & 1
        self.wave_threshold = 32 + self.wave_variant
        self.next_sky_frame = 314
        self.sky_index = 0
        self.plants: list[Plant] = []
        self.zombies: list[Zombie] = []
        self.bullets: list[Bullet] = []
        self.suns: list[Sun] = []
        self.mowers: list[Mower] = []
        self.next_pid = self.next_zid = self.next_bid = self.next_sid = 1
        self.hold = -1
        self.held_action: dict | None = None
        self.cool_start: list[int | None] = [None, 1, 1]
        self.ready_since: list[int | None] = [1, None, None]
        self.action_select: dict[int, list[dict]] = {}
        self.action_place: dict[int, list[dict]] = {}
        for a in scenario.get("actions", []):
            self.action_select.setdefault(int(a["frame"]) + 4, []).append(a)
            self.action_place.setdefault(int(a["frame"]) + 15, []).append(a)
        self.collect_every = int(scenario.get("collect_sun", {}).get("every_frames", 0))
        self.pending_collect: dict[int, int] = {}
        self.result_frame: int | None = None

    def card_state(self, f: int, tag: int) -> dict:
        if tag == 0 and self.cool_start[tag] is None:
            ready = f >= 1
            pct = 0.0 if ready else 100.0
            en = ready and f >= 8
        else:
            start = self.cool_start[tag]
            age = 0 if start is None else f - start
            ready = start is None or age >= COOLDOWN[tag]
            pct = 0.0 if ready else max(0.0, 100.0 * (1.0 - age / COOLDOWN[tag]))
            if ready:
                if self.ready_since[tag] is None:
                    self.ready_since[tag] = f
                delay = 0 if start == 1 else 2 + ((start + tag) % 3)
                en = f >= self.ready_since[tag] + delay
            else:
                self.ready_since[tag] = None
                en = False
        if self.sun < COST[tag]:
            en = False
        return {"tag": tag, "ready": int(ready), "pct": round(pct, 1), "en": int(en)}

    def select_actions(self, f: int) -> None:
        for a in self.action_select.get(f, []):
            tag = int(a["card_index"])
            c = self.card_state(f, tag)
            if self.hold < 0 and c["ready"] and c["en"] and self.sun >= COST[tag]:
                self.hold = tag
                self.held_action = a
                self.sun -= COST[tag]

    def place_actions(self, f: int) -> None:
        for a in self.action_place.get(f, []):
            if self.held_action is not a:
                continue
            row, col = int(a["row"]), int(a["col"])
            occupied = any(p.row == row and p.col == col and p.hp > 0 for p in self.plants)
            tag = self.hold
            if not occupied and 0 <= row < 5 and 0 <= col < 9:
                kind = CARD_NAMES[tag]
                p = Plant(self.next_pid, kind, row, col, PLANT_HP[kind], f)
                self.next_pid += 1
                if kind == "sunflower":
                    p.next_sun = f + (313 if p.id % 2 == 0 else 376)
                if kind == "peashooter":
                    p.shot_period = 69 + (self.rng.u32() % 22)
                self.plants.append(p)
                self.cool_start[tag] = f
                self.ready_since[tag] = None
            else:
                self.sun += COST[tag]
            self.hold = -1
            self.held_action = None

    def add_sun(self, f: int, kind: str, x: float, y: float, floor_y: float) -> None:
        vx = (self.rng.range(-24, 24)) / 30.0
        vy = self.rng.range(720, 980) * DT
        s = Sun(self.next_sid, x, y, f, kind, vx, vy, floor_y)
        self.next_sid += 1
        self.suns.append(s)

    def update_suns(self, f: int) -> None:
        # Sky sun every 25 seconds, first at five seconds. Frame intervals alternate 1562/1563.
        if f == self.next_sky_frame:
            x = float(self.rng.range(520, 1520))
            floor_y = float(self.rng.range(300, 520))
            self.add_sun(f, "sky", x, 1150.001, floor_y)
            self.sky_index += 1
            self.next_sky_frame += 1562 if self.sky_index % 2 else 1563
        for p in self.plants:
            if p.kind == "sunflower" and p.hp > 0 and p.next_sun is not None and f >= p.next_sun:
                self.add_sun(f, "plant", 630.0 + 122.0 * p.col, 123.001 + 138.0 * p.row,
                             123.0 + 138.0 * p.row)
                p.next_sun = f + self.rng.range(1460, 1945)
        # Scripted collector chooses from the previous frame, then releases three frames later.
        if self.collect_every and f > 0 and f % self.collect_every == 0:
            for s in self.suns:
                wx, wy = round(s.x * 1280 / 1920), round((1080 - s.y) * 720 / 1080)
                if s.en and 0 < wx < 1280 and 0 < wy < 720:
                    self.pending_collect[f + 3] = s.id
                    break
        sid = self.pending_collect.pop(f, None)
        if sid is not None:
            s = next((q for q in self.suns if q.id == sid), None)
            if s is not None and s.en:
                s.en = 0
                s.collect_at = f
                s.paid_at = f + 44
        for s in self.suns:
            if s.paid_at == f:
                self.sun += 50
            age = f - s.born
            if s.collect_at is not None:
                n = f - s.collect_at
                if n >= 44:
                    s.x, s.y = 290.0, 1010.0
                elif n > 0:
                    q = n / 44.0
                    ease = 1.0 - (1.0 - q) ** 3
                    s.x += (290.0 - s.x) * min(1.0, 0.08 + ease * 0.20)
                    s.y += (1010.0 - s.y) * min(1.0, 0.08 + ease * 0.20)
            else:
                n = age
                if n > 0 and (s.y > s.floor_y or n < 20):
                    s.x += s.vx
                    s.y += s.vy - 0.3815 * n * 2.0
                    if s.y <= s.floor_y and n > 20:
                        s.y = s.floor_y
                        s.vx = 0.0
            if age >= 1312 or (s.collect_at is not None and age >= 430):
                s.remove_at = f
        self.suns = [s for s in self.suns if s.remove_at != f]

    def spawn_wave(self, f: int) -> None:
        self.wave += 1
        if self.wave == 1:
            count = 1
        elif self.wave == 2:
            count = 3 + 2 * self.wave_variant
        else:
            count = min(8, 2 + self.wave)
        lanes: list[int] = []
        if self.wave == 1:
            lanes = [4]
        else:
            for _ in range(count):
                lanes.append(self.rng.range(0, 4))
        for i, lane in enumerate(lanes):
            roll = self.rng.range(0, 99)
            if self.wave >= 4 and roll < 18:
                kind, hs = "bucket", 1300.0
            elif self.wave >= 2 and roll < 38:
                kind, hs = "cone", 600.0
            else:
                kind, hs = "common", 0.0
            x = float(self.rng.range(1800, 2280))
            self.zombies.append(Zombie(self.next_zid, kind, lane, x, hs=hs))
            self.next_zid += 1
        self.wave_reset = f
        if self.wave == 1:
            self.next_wave_frame = f + 2056 + 6 * self.wave_variant
        else:
            self.next_wave_frame = f + 2025

    def damage_zombie(self, z: Zombie, amount: float, f: int) -> None:
        if not z.alive:
            return
        if z.hs > 0:
            take = min(z.hs, amount)
            z.hs -= take
            amount -= take
        if amount > 0:
            z.hp = max(0.0, z.hp - amount)
        if z.hp <= 0 and z.alive:
            z.alive = 0
            z.eat = 0
            z.dead_at = f
            z.remove_at = f + 314

    def update_combat(self, f: int) -> None:
        # Plant firing. A shooter starts shortly after a visible target enters its lane.
        for p in self.plants:
            if p.kind != "peashooter" or p.hp <= 0:
                continue
            targets = [z for z in self.zombies if z.alive and z.lane == p.row and z.show]
            if targets:
                if p.shot_at is None:
                    p.shot_at = f + 87 + ((p.col + p.id) % 7)
                if f >= p.shot_at:
                    self.bullets.append(Bullet(self.next_bid, p.row, 700.0 + 122.0 * p.col, f))
                    self.next_bid += 1
                    p.shot_at += p.shot_period
            else:
                p.shot_at = None
        for b in self.bullets:
            if f > b.born:
                b.x += 10.666667
            if not b.used:
                candidates = [z for z in self.zombies if z.alive and z.lane == b.lane and z.show
                              and b.x >= z.x - 23.0]
                if candidates:
                    z = min(candidates, key=lambda q: q.x)
                    b.used = 1
                    self.damage_zombie(z, 20.0, f)
        self.bullets = [b for b in self.bullets if b.x <= 3000.0]

    def update_zombies(self, f: int) -> None:
        # Determine eating contacts before movement.
        for z in self.zombies:
            if z.dead_at is not None:
                if f >= z.dead_at + 35:
                    z.spd = 0.0
                continue
            contacts = [p for p in self.plants if p.hp > 0 and p.row == z.lane
                        and z.x <= (630.0 + 122.0 * p.col) + 80.0
                        and z.x >= (630.0 + 122.0 * p.col) - 45.0]
            if contacts:
                p = max(contacts, key=lambda q: q.col)
                z.eat, z.spd = 1, 0.0
                if p.bite_at is None:
                    p.bite_at = f + 82 + ((p.id + z.id) % 18)
                if f >= p.bite_at:
                    p.hp = max(0.0, p.hp - 100.0)
                    p.bite_at += 82 + ((p.id + z.id) % 18)
                    if p.hp <= 0:
                        if p.dead_at is None:
                            p.dead_at = f
                            p.remove_at = f + 251
                        z.eat, z.spd = 0, 30.0
            else:
                z.eat, z.spd = 0, 30.0
                z.x -= z.spd * DT
            z.show = int(z.x < 1710.0)
            if z.x < 535.0:
                mower = next((m for m in self.mowers if m.lane == z.lane), None)
                if mower is not None and not mower.live:
                    mower.live, mower.st, mower.born = 1, 2, f
                    self.damage_zombie(z, 99999.0, f)
                elif mower is None and z.x < 300.0 and self.result_frame is None:
                    self.result_frame = f
        # Moving mowers kill their lane and leave after about 2.2 seconds.
        for m in self.mowers:
            if m.live:
                if f > m.born:
                    m.x += 12.16
                for z in self.zombies:
                    if z.alive and z.lane == m.lane and z.x <= m.x + 80.0:
                        self.damage_zombie(z, 99999.0, f)
        self.mowers = [m for m in self.mowers if not (m.live and f >= m.born + 137)]
        self.plants = [p for p in self.plants if p.remove_at is None or f < p.remove_at]
        self.zombies = [z for z in self.zombies if z.remove_at is None or f < z.remove_at]

    def wave_state(self, f: int) -> tuple[float, int, int]:
        if f < 64:
            return 0.0, 0, 0
        if self.wave == 0:
            wt = float(min(18, max(0, math.floor((f - 1) * DT))))
            if 1133 <= f < 1139:
                return 18.0, 0, 1
            return wt, 1, 0
        elapsed = f - self.wave_reset
        if elapsed < 50:
            wt = 0.0
            begin = 0
        else:
            wt = float(1 + math.floor((elapsed - 50) * DT))
            begin = 1
        if self.next_wave_frame - 6 <= f < self.next_wave_frame:
            return wt, 0, 1
        return wt, begin, 0

    def frame(self, f: int) -> dict:
        # Initialization is visibly staggered by the original scene animation.
        mower_frames = (33, 39, 45, 51, 58)
        if f in mower_frames:
            self.mowers.append(Mower(len(self.mowers)))
        self.select_actions(f)
        self.place_actions(f)
        if f == self.next_wave_frame:
            self.spawn_wave(f)
        self.update_suns(f)
        self.update_zombies(f)
        self.update_combat(f)
        wt, wbegin, wdead = self.wave_state(f)
        end = int(self.result_frame is not None and f >= self.result_frame)
        cards = [self.card_state(f, i) for i in range(3)]
        if self.hold >= 0:
            cards[self.hold]["pct"] = 100.0
        return {
            "f": f, "sun": self.sun, "ts": 1.0, "wave": self.wave, "wt": wt,
            "wbegin": wbegin, "wdead": wdead, "end": end, "zwin": end,
            "cards": cards, "hold": self.hold, "shovel": 0,
            "z": [{"id": z.id, "t": z.kind, "x": round(z.x, 3), "y": LANE_Y[z.lane],
                   "hp": z.hp, "hs": z.hs, "bs": z.bs, "eat": z.eat,
                   "alive": z.alive, "show": z.show, "spd": z.spd} for z in self.zombies],
            "p": [{"id": p.id, "t": p.kind, "r": p.col, "c": p.row, "hp": p.hp}
                  for p in self.plants],
            "b": [{"id": b.id, "x": round(b.x, 3), "y": 208.0 + 138.0 * b.lane,
                   "used": b.used} for b in self.bullets],
            "s": [{"id": s.id, "x": round(s.x, 3), "y": round(s.y, 3), "en": s.en}
                  for s in self.suns],
            "cars": [{"tag": -1, "live": m.live, "st": m.st, "x": round(m.x, 3)}
                     for m in self.mowers],
        }

    def run(self, out: Path) -> None:
        stop = self.end_frame
        with out.open("w", encoding="utf-8") as fh:
            for f in range(self.end_frame + 1):
                row = self.frame(f)
                fh.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
                if self.result_frame is not None:
                    stop = min(stop, self.result_frame + 60)
                if f >= stop:
                    break


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: run-scenario <scenario.json> <out-trace.jsonl>", file=sys.stderr)
        return 2
    src, dst = Path(argv[1]), Path(argv[2])
    scenario = json.loads(src.read_text(encoding="utf-8"))
    if scenario.get("schema") != 1 or scenario.get("level") != 4 or scenario.get("frame_ms") != 16:
        raise ValueError("only schema 1, Level 4, 16 ms scenarios are supported")
    Sim(scenario).run(dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
