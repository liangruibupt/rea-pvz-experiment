"""Clean-room, deterministic approximation of the observed Level 4 rules."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterator

from scenario import Scenario

MASK64 = (1 << 64) - 1
CARD_COST = (50, 100, 50)
CARD_COOLDOWN = (469, 469, 1875)
PLANT_HP = {"sunflower": 300.0, "peashooter": 300.0, "wallnut": 3000.0}
LANE_Y = (130.0, 268.0, 406.0, 544.0, 682.0)
PLANT_X = tuple(631.0 + 122.0 * col for col in range(9))


def mix64(value: int) -> int:
    value = (value + 0x9E3779B97F4A7C15) & MASK64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
    return (value ^ (value >> 31)) & MASK64


def r3(value: float) -> float:
    return round(float(value) + 1e-10, 3)


@dataclass
class Card:
    tag: int
    ready: int = 0
    pct: float = 100.0
    enabled: int = 0
    cooldown_start: int | None = None
    held: bool = False


@dataclass
class Plant:
    id: int
    kind: str
    col: int
    row: int
    hp: float
    born: int
    dead_frame: int | None = None
    fire_charge: int = 0
    fired_once: bool = False
    next_sun: int | None = None
    sun_period: int = 1531


@dataclass
class Zombie:
    id: int
    kind: str
    wave: int
    x: float
    row: int
    hp: float = 200.0
    hs: float = 0.0
    bs: float = 0.0
    eat: int = 0
    alive: int = 1
    show: int = 0
    spd: float = 30.0
    attack_charge: int = 0
    dead_frame: int | None = None


@dataclass
class Bullet:
    id: int
    x: float
    row: int
    born: int
    used: int = 0
    used_frame: int | None = None


@dataclass
class Sun:
    id: int
    kind: str
    born: int
    x0: float
    y0: float
    x_target: float
    y_target: float
    en: int = 1
    clicked: int | None = None
    credited: bool = False

    def position(self, frame: int) -> tuple[float, float]:
        age = max(0, frame - self.born)
        if self.clicked is not None and frame >= self.clicked:
            flight = min(1.0, (frame - self.clicked) / 44.0)
            sx, sy = self._natural(self.clicked)
            return (sx + (290.0 - sx) * flight, sy + (1010.0 - sy) * flight)
        return self._natural(frame)

    def _natural(self, frame: int) -> tuple[float, float]:
        age = max(0, frame - self.born)
        if self.kind == "falling":
            if age <= 39:
                t = age / 39.0
                x = self.x0 + (self.x_target - self.x0) * t
                y = self.y0 + 115.0 * (4.0 * t * (1.0 - t)) - 150.0 * t
                return x, y
            y = max(self.y_target, self.y0 - 150.0 - (age - 39) * 2.5632)
            return self.x_target, y
        if age <= 45:
            t = age / 45.0
            x = self.x0 + (self.x_target - self.x0) * t
            y = self.y0 + 145.0 * (4.0 * t * (1.0 - t))
            return x, y
        return self.x_target, self.y_target


@dataclass
class Car:
    lane: int
    live: int = 0
    st: int = 1
    x: float = 455.0


class Simulation:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.sun_bank = 10000
        self.cards = [Card(i) for i in range(3)]
        self.plants: list[Plant] = []
        self.zombies: list[Zombie] = []
        self.bullets: list[Bullet] = []
        self.suns: list[Sun] = []
        self.cars: list[Car] = []
        self.hold = -1
        self.shovel = 0
        self.wave = 0
        self.wt = 0.0
        self.wbegin = 0
        self.wdead = 0
        self.end = 0
        self.zwin = 0
        self.end_decided: int | None = None
        self.stop_after_frame: int | None = None
        self.wave_base_tick = 0
        self.wave_start_frame = -1
        self.wave_pending: int | None = 1139
        self.dead_pending: int | None = 1133
        self.final_pending: int | None = None
        self.next_ids = {"plant": 1, "zombie": 1, "bullet": 1, "sun": 1}
        self.select_events: dict[int, list] = {}
        self.place_events: dict[int, list] = {}
        for action in scenario.actions:
            self.select_events.setdefault(action.frame + 4, []).append(action)
            self.place_events.setdefault(action.frame + 15, []).append(action)
        self.collect_releases: dict[int, int] = {}
        self.credit_events: dict[int, list[int]] = {}
        self.previous_frame = -1

    @staticmethod
    def tick(frame: int) -> int:
        return max(0, math.floor((frame - 1) / 62.5))

    def _id(self, kind: str) -> int:
        value = self.next_ids[kind]
        self.next_ids[kind] += 1
        return value

    def _card_update(self, frame: int) -> None:
        for card in self.cards:
            if card.cooldown_start is None:
                if card.tag == 0 and frame >= 1:
                    card.ready, card.pct = 1, 0.0
                elif card.tag == 1:
                    elapsed = max(0, frame - 1)
                    card.pct = max(0.0, 100.0 - elapsed * 100.0 / 468.75)
                    if frame >= 470:
                        card.ready, card.pct = 1, 0.0
                else:
                    elapsed = max(0, frame - 1)
                    card.pct = max(0.0, 100.0 - elapsed * 100.0 / 1875.0)
                    if frame >= 1876:
                        card.ready, card.pct = 1, 0.0
            elif not card.ready:
                elapsed = frame - card.cooldown_start
                duration = CARD_COOLDOWN[card.tag]
                card.pct = max(0.0, 100.0 * (1.0 - elapsed / duration))
                if elapsed >= duration:
                    card.ready, card.pct = 1, 0.0
            if card.held:
                card.pct = 100.0
            initial_delay = card.tag == 0 and card.cooldown_start is None and frame < 8
            card.enabled = int(card.ready and not initial_delay and self.sun_bank >= CARD_COST[card.tag])
            if card.cooldown_start is not None and not card.ready:
                card.enabled = 0

    def _select(self, frame: int) -> None:
        for action in self.select_events.get(frame, ()):
            card = self.cards[action.card_index]
            if self.hold == -1 and card.ready and card.enabled:
                self.sun_bank -= CARD_COST[action.card_index]
                self.hold = action.card_index
                card.held = True
                card.pct = 100.0

    def _place(self, frame: int) -> None:
        for action in self.place_events.get(frame, ()):
            if self.hold != action.card_index:
                continue
            card = self.cards[action.card_index]
            occupied = any(p.col == action.col and p.row == action.row and p.dead_frame is None for p in self.plants)
            card.held = False
            self.hold = -1
            if occupied:
                self.sun_bank += CARD_COST[action.card_index]
                card.ready, card.pct, card.enabled = 1, 0.0, 1
                continue
            pid = self._id("plant")
            plant = Plant(pid, action.card, action.col, action.row, PLANT_HP[action.card], frame)
            if action.card == "sunflower":
                delay_s = 4 + mix64(self.scenario.device_seed + 196 + (pid - 1) * 18) % 3
                plant.next_sun = int(round(frame + delay_s * 62.5)) + (1 if delay_s == 6 else 0)
                period_s = 22.5 + mix64(self.scenario.device_seed + 348 + pid * 36) % 5
                plant.sun_period = int(round(period_s * 62.5))
            self.plants.append(plant)
            card.ready, card.pct, card.enabled = 0, 100.0, 0
            card.cooldown_start = frame

    def _falling_sun_due(self, frame: int) -> bool:
        if frame < 314:
            return False
        n = int(round((frame - 314) / 1562.5))
        return frame == int(314 + n * 1562.5)

    def _new_sun(self, frame: int, kind: str, x: float, y: float, salt: int) -> None:
        sid = self._id("sun")
        rnd = mix64(self.scenario.device_seed + salt * 0x9E37 + sid * 0x10001)
        if kind == "falling":
            tx = 520.0 + float(rnd % 1060)
            ty = 250.0 + float((rnd >> 16) % 330)
        else:
            tx = x + float(int((rnd >> 8) % 81) - 40)
            ty = y
        self.suns.append(Sun(sid, kind, frame, x, y, tx, ty))

    def _sun_update(self, frame: int) -> None:
        if self._falling_sun_due(frame):
            rnd = mix64(self.scenario.device_seed + frame)
            x = 520.0 + float(rnd % 1060)
            self._new_sun(frame, "falling", x, 1150.001, frame)
        for plant in self.plants:
            if plant.kind == "sunflower" and plant.dead_frame is None and plant.next_sun == frame:
                self._new_sun(frame, "produced", PLANT_X[plant.col] - 1.0, 123.001 + 138.0 * plant.row, plant.id)
                plant.next_sun += plant.sun_period
        if self.scenario.collect_every and frame > 0 and frame % self.scenario.collect_every == 0:
            for sun in self.suns:
                x, y = sun.position(frame - 1)
                if sun.en and 0.0 < x < 1920.0 and 0.0 < y < 1080.0:
                    self.collect_releases[frame + 3] = sun.id
                    break
        sid = self.collect_releases.get(frame)
        if sid is not None:
            for sun in self.suns:
                if sun.id == sid and sun.en:
                    sun.en = 0
                    sun.clicked = frame
                    self.credit_events.setdefault(frame + 44, []).append(sid)
                    break
        for sid in self.credit_events.get(frame, ()):
            for sun in self.suns:
                if sun.id == sid and not sun.credited:
                    sun.credited = True
                    self.sun_bank += 50
        kept: list[Sun] = []
        for sun in self.suns:
            age = frame - sun.born
            if sun.clicked is not None:
                if frame - sun.clicked <= 397:
                    kept.append(sun)
            elif age <= 1311:
                kept.append(sun)
        self.suns = kept

    def _wave_interval(self, wave: int) -> int:
        if wave == 1:
            return 32 + int(mix64(self.scenario.device_seed + 49) % 3)
        if wave == 2:
            return 32 + int(mix64(self.scenario.device_seed + 14) % 2)
        return 45

    def _spawn_count(self, wave: int) -> int:
        if wave == 1:
            return 1
        if wave in (2, 3):
            return 3 + int(mix64(self.scenario.device_seed + wave * 323 + 72) % 3)
        if wave == 4:
            return 3 + int(mix64(self.scenario.device_seed + 404) % 2)
        return 11 + int(mix64(self.scenario.device_seed + 505) % 5)

    def _spawn_wave(self, frame: int, wave: int) -> None:
        self.wave = wave
        self.wt = 0.0
        self.wdead = 0
        self.wave_base_tick = self.tick(frame)
        self.wave_start_frame = frame
        count = self._spawn_count(wave)
        cone_budget = 0
        bucket_budget = 0
        if wave == 2 and mix64(self.scenario.device_seed + 32) % 3 == 0:
            cone_budget = 1
        elif wave == 3 and mix64(self.scenario.device_seed + 4) % 3 == 0:
            cone_budget = 1
        elif wave >= 4:
            cone_budget = max(1, count // 4)
            if mix64(self.scenario.device_seed + wave * 193) % 3 == 0:
                bucket_budget = 1
        base_rows = [4] if wave == 1 else ([0, 1, 2, 3] if wave == 2 else [0, 1, 2, 3, 4])
        duplicate_row = int(mix64(self.scenario.device_seed + 1248) % 4)
        for i in range(count):
            rnd = mix64(self.scenario.device_seed + wave * 0x100000 + i * 0x101)
            if wave == 1:
                rnd = mix64(self.scenario.device_seed + 769250)
            if i < len(base_rows):
                row = base_rows[i]
            elif wave == 2:
                row = duplicate_row
            else:
                row = int((rnd >> 17) % 5)
            x = 1780.0 + float(rnd % 501) + 1.0
            kind = "common"
            if bucket_budget and i == count // 2:
                kind, bucket_budget = "bucket", bucket_budget - 1
            elif cone_budget and ((wave == 2 and i == 1) or (wave != 2 and i >= count - cone_budget)):
                kind, cone_budget = "cone", cone_budget - 1
            hs = 1200.0 if kind == "bucket" else 600.0 if kind == "cone" else 0.0
            self.zombies.append(Zombie(self._id("zombie"), kind, wave, x, row, hs=hs))
        if wave == 4:
            self.wdead = 1
            self.final_pending = frame + 6
        elif wave < 4:
            self.dead_pending = None
            self.wave_pending = None

    def _wave_update(self, frame: int) -> None:
        tick = self.tick(frame)
        if frame == 64:
            self.wbegin = 1
        boundary_now = False
        if frame == self.dead_pending:
            self.wbegin, self.wdead = 0, 1
            boundary_now = True
        if frame == self.wave_pending:
            self._spawn_wave(frame, self.wave + 1)
            boundary_now = True
        if frame == self.final_pending:
            self.final_pending = None
            self._spawn_wave(frame, 5)
            boundary_now = True
        if self.wave and tick > self.wave_base_tick:
            self.wt = float(tick - self.wave_base_tick)
            if not boundary_now:
                self.wbegin = 1
        elif self.wave == 0:
            self.wt = float(tick)
        if 0 < self.wave < 4 and self.dead_pending is None:
            interval = self._wave_interval(self.wave)
            if self.wt >= interval:
                self.dead_pending = frame + 6
                self.wave_pending = frame + 12
            else:
                latest = [z for z in self.zombies if z.wave == self.wave]
                if self.wt >= 1 and latest and not any(z.alive for z in latest):
                    self.dead_pending = frame + 4
                    self.wave_pending = frame + 10

    def _shooting_update(self, frame: int) -> None:
        for plant in self.plants:
            if plant.kind != "peashooter" or plant.dead_frame is not None:
                continue
            px = PLANT_X[plant.col]
            targets = [z for z in self.zombies if z.alive and z.row == plant.row and z.show and z.x > px - 20.0]
            if not targets:
                plant.fire_charge = 0
                plant.fired_once = False
                continue
            plant.fire_charge += 1
            threshold = 90 if not plant.fired_once else 69
            if plant.fire_charge >= threshold:
                self.bullets.append(Bullet(self._id("bullet"), px + 69.0, plant.row, frame))
                plant.fire_charge = 0
                plant.fired_once = True
        kept: list[Bullet] = []
        for bullet in self.bullets:
            if bullet.used:
                if bullet.used_frame == frame:
                    kept.append(bullet)
                continue
            if bullet.born == frame:
                kept.append(bullet)
                continue
            bullet.x += 9.6
            targets = sorted((z for z in self.zombies if z.alive and z.show and z.row == bullet.row and z.x >= bullet.x - 90.0), key=lambda z: z.x)
            if targets:
                z = targets[0]
                if bullet.x >= z.x - 70.0:
                    if z.hs > 0:
                        z.hs = max(0.0, z.hs - 20.0)
                    else:
                        z.hp = max(0.0, z.hp - 20.0)
                        if z.hp <= 0:
                            z.alive = 0
                            z.dead_frame = frame
                    bullet.used = 1
                    bullet.used_frame = frame
            if bullet.x < 2200.0:
                kept.append(bullet)
        self.bullets = kept

    def _zombie_update(self, frame: int) -> None:
        for z in self.zombies:
            if not z.alive:
                if z.dead_frame is not None and frame - z.dead_frame >= 42:
                    z.spd = 0.0
                continue
            if not z.eat:
                z.x -= z.spd * 0.016
                if z.x <= 1710.0:
                    z.show = 1
                candidates = sorted((p for p in self.plants if p.row == z.row and p.dead_frame is None and z.x <= PLANT_X[p.col] + 79.0 and z.x >= PLANT_X[p.col] - 80.0), key=lambda p: p.col, reverse=True)
                if candidates:
                    z.eat = 1
                    z.spd = 0.0
                    z.attack_charge = 0
            if z.eat:
                targets = sorted((p for p in self.plants if p.row == z.row and p.dead_frame is None and abs(z.x - (PLANT_X[p.col] + 79.0)) < 90.0), key=lambda p: p.col, reverse=True)
                if not targets:
                    z.eat, z.spd, z.attack_charge = 0, 30.0, 0
                else:
                    plant = targets[0]
                    z.attack_charge += 1
                    if z.attack_charge == 42 or (z.attack_charge > 42 and (z.attack_charge - 42) % 83 == 0):
                        plant.hp -= 100.0
                        if plant.hp <= 0 and plant.dead_frame is None:
                            plant.dead_frame = frame
                            z.eat, z.spd, z.attack_charge = 0, 30.0, 0
        self.zombies = [z for z in self.zombies if z.dead_frame is None or frame - z.dead_frame <= 280]
        self.plants = [p for p in self.plants if p.dead_frame is None or frame - p.dead_frame <= 250]

    def _cars_update(self, frame: int) -> None:
        car_birth = {33: 0, 39: 1, 45: 2, 51: 3, 58: 4}
        if frame in car_birth:
            self.cars.append(Car(car_birth[frame]))
        by_lane = {c.lane: c for c in self.cars}
        for z in self.zombies:
            if z.alive and z.x <= 535.0:
                car = by_lane.get(z.row)
                if car is not None and car.st == 1:
                    car.live, car.st = 1, 2
                elif car is None and z.x <= 0.48:
                    self.stop_after_frame = frame
        for car in self.cars:
            if car.live:
                car.x += 11.52
                for z in self.zombies:
                    if z.alive and z.row == car.lane and z.x <= car.x + 90.0:
                        z.hp, z.alive, z.dead_frame = 0.0, 0, frame
        self.cars = [c for c in self.cars if c.x <= 2020.0]

    def _project(self, frame: int) -> dict:
        return {
            "f": frame,
            "sun": self.sun_bank,
            "ts": 1.0,
            "wave": self.wave,
            "wt": r3(self.wt),
            "wbegin": self.wbegin,
            "wdead": self.wdead,
            "end": self.end,
            "zwin": self.zwin,
            "hold": self.hold,
            "shovel": self.shovel,
            "cards": [{"tag": c.tag, "ready": c.ready, "pct": r3(c.pct), "en": c.enabled} for c in self.cards],
            "p": [{"id": p.id, "t": p.kind, "r": p.col, "c": p.row, "hp": r3(p.hp)} for p in self.plants],
            "z": [{"id": z.id, "t": z.kind, "x": r3(z.x), "y": LANE_Y[z.row], "hp": r3(z.hp), "hs": r3(z.hs), "bs": r3(z.bs), "eat": z.eat, "alive": z.alive, "show": z.show, "spd": r3(z.spd)} for z in self.zombies],
            "b": [{"id": b.id, "x": r3(b.x), "y": 208.0 + 138.0 * b.row, "used": b.used} for b in self.bullets],
            "s": [{"id": s.id, "x": r3(s.position(frame)[0]), "y": r3(s.position(frame)[1]), "en": s.en} for s in self.suns],
            "cars": [{"tag": -1, "live": c.live, "st": c.st, "x": r3(c.x)} for c in self.cars],
        }

    def run(self) -> Iterator[dict]:
        for frame in range(self.scenario.end_frame + 1):
            self._card_update(frame)
            self._select(frame)
            self._place(frame)
            self._wave_update(frame)
            self._sun_update(frame)
            self._shooting_update(frame)
            self._zombie_update(frame)
            self._cars_update(frame)
            self._card_update(frame)
            yield self._project(frame)
            if self.stop_after_frame is not None and frame >= self.stop_after_frame:
                return
            if self.end_decided is not None and frame >= self.end_decided + 60:
                return
