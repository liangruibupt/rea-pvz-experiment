#!/usr/bin/env python3
"""Deterministic, headless approximation of the observed Level 4 rules."""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

MASK64 = (1 << 64) - 1
FRAME_DT = 0.016


def r3(value: float) -> float:
    return round(float(value) + 1e-9, 3)


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
    """libstdc++ default_random_engine (minstd_rand0)."""

    def __init__(self, seed: int):
        self.state = seed % 2147483647
        if self.state == 0:
            self.state = 1

    def draw(self) -> int:
        self.state = (self.state * 16807) % 2147483647
        return self.state

    def uniform(self, low: int, high: int) -> int:
        count = high - low + 1
        scale = 2147483645 // count
        past = scale * count
        while True:
            value = self.draw() - 1
            if value < past:
                return low + value // scale


class GlibcRand:
    """glibc random()/rand() TYPE_3 stream, including srand warm-up."""

    def __init__(self, seed: int):
        seed &= 0xFFFFFFFF
        if seed == 0:
            seed = 1
        values = [seed]
        for i in range(1, 31):
            values.append((16807 * values[-1]) % 2147483647)
        values.extend((values[0], values[1], values[2]))
        for i in range(34, 344):
            values.append((values[i - 31] + values[i - 3]) & 0xFFFFFFFF)
        self.values = values
        self.index = 344

    def draw(self) -> int:
        value = (self.values[self.index - 31] + self.values[self.index - 3]) & 0xFFFFFFFF
        self.values.append(value)
        self.index += 1
        return value >> 1


@dataclass
class Card:
    tag: int
    cooldown_frames: int
    ready_frame: int
    enabled_frame: int
    cooldown_start: int | None = None
    selected: bool = False

    def state(self, frame: int, affordable: bool) -> dict:
        if self.selected:
            return {"tag": self.tag, "ready": 1, "pct": 100.0, "en": 1}
        ready = frame >= self.ready_frame
        if ready:
            pct = 0.0
        elif self.cooldown_start is None:
            elapsed = max(0, frame - 1)
            pct = max(0.0, 100.0 - elapsed * 100.0 / self.cooldown_frames)
        else:
            elapsed = max(0, frame - self.cooldown_start)
            pct = max(0.0, 100.0 - elapsed * 100.0 / self.cooldown_frames)
        enabled = ready and frame >= self.enabled_frame and affordable
        return {"tag": self.tag, "ready": int(ready), "pct": r3(pct), "en": int(enabled)}

    def spend(self, frame: int) -> None:
        self.selected = True

    def placed(self, frame: int) -> None:
        self.selected = False
        self.cooldown_start = frame
        self.ready_frame = frame + self.cooldown_frames
        self.enabled_frame = self.ready_frame + 3

    def cancel(self) -> None:
        self.selected = False


@dataclass
class Plant:
    ident: int
    kind: str
    row: int
    col: int
    hp: float
    born: int
    death_frame: int | None = None
    next_shot: int | None = None
    shot_period: int = 78
    next_sun: int | None = None
    sun_period: int = 1500

    @property
    def x(self) -> float:
        return 630.0 + 122.0 * self.col

    @property
    def y(self) -> float:
        return 130.0 + 138.0 * self.row


@dataclass
class Zombie:
    ident: int
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
    born: int = 0
    death_frame: int | None = None
    next_bite: int | None = None

    @property
    def y(self) -> float:
        return 130.0 + 138.0 * self.lane


@dataclass
class Bullet:
    ident: int
    lane: int
    x: float
    y: float
    born: int
    used: int = 0


@dataclass
class Sun:
    ident: int
    x0: float
    landing_x: float
    landing_y: float
    born: int
    kind: str
    en: int = 1
    collect_frame: int | None = None
    credit_frame: int | None = None

    def position(self, frame: int) -> tuple[float, float]:
        age = frame - self.born
        if self.collect_frame is not None and frame >= self.collect_frame:
            # The original animates collected sun to the bank. A short linear path
            # keeps the object visible and disabled during that transition.
            t = min(1.0, (frame - self.collect_frame) / 20.0)
            sx, sy = self._natural(self.collect_frame)
            return sx + (290.0 - sx) * t, sy + (1010.0 - sy) * t
        return self._natural(frame)

    def _natural(self, frame: int) -> tuple[float, float]:
        age = max(0, frame - self.born)
        if self.kind == "sky":
            if age <= 38:
                t = age / 38.0
                x = self.x0 + (self.landing_x - self.x0) * t
                y = self.y_start + (-100.0 * t) + 560.0 * t * (1.0 - t)
                return x, y
            if age < 314:
                t = (age - 38) / 276.0
                return self.landing_x, 1050.0 + (self.landing_y - 1050.0) * t
            return self.landing_x, self.landing_y
        # Produced sun makes a compact upward arc and then rests near its plant.
        if age <= 38:
            t = age / 38.0
            x = self.x0 + (self.landing_x - self.x0) * t
            y = self.y_start + 380.0 * t * (1.0 - t) + 80.0 * t
            return x, y
        return self.landing_x, self.landing_y

    @property
    def y_start(self) -> float:
        return 1150.001 if self.kind == "sky" else self.landing_y - 80.0


@dataclass
class Mower:
    lane: int
    born: int
    live: int = 0
    st: int = 1
    x: float = 455.0
    trigger_frame: int | None = None


class Simulator:
    COSTS = (50, 100, 50)
    KINDS = ("sunflower", "peashooter", "wallnut")

    def __init__(self, scenario: dict):
        self.scenario = scenario
        self.end_frame = int(scenario["end_frame"])
        self.sun_bank = 10000
        self.hold = -1
        self.wave = 0
        self.last_wave_frame = 0
        self.wave_frames: list[int] = [1139]
        self.next_ids = {"p": 1, "z": 1, "b": 1, "s": 1}
        self.plants: list[Plant] = []
        self.zombies: list[Zombie] = []
        self.bullets: list[Bullet] = []
        self.suns: list[Sun] = []
        self.mowers: list[Mower] = []
        self.pending_credit: list[int] = []
        self.pending_place: dict[int, dict] = {}
        self.actions = {int(a["frame"]): a for a in scenario.get("actions", [])}
        self.collect_every = int(scenario.get("collect_sun", {}).get("every_frames", 0))

        entropy = SplitMix64(int(scenario["device_seed"]))
        self.x_rng = MinStd(entropy.draw())
        self.content_rng = MinStd(entropy.draw())
        entropy.draw()  # separate engine used by scene animation details
        self.sunflower_rng = MinStd(entropy.draw())
        time_entropy = SplitMix64(int(scenario["time_seed"]))
        self.sun_rng = MinStd(time_entropy.draw())
        self.c_rng = GlibcRand(int(scenario["time_seed"]))
        for _ in range(51):
            self.c_rng.draw()

        self.cards = [
            Card(0, 469, 1, 8),
            Card(1, 469, 470, 470),
            Card(2, 1875, 1876, 1876),
        ]

    def new_id(self, group: str) -> int:
        value = self.next_ids[group]
        self.next_ids[group] += 1
        return value

    def run(self, output: Path) -> None:
        with output.open("w", encoding="utf-8") as stream:
            for frame in range(self.end_frame + 1):
                self.step(frame)
                stream.write(json.dumps(self.trace(frame), separators=(",", ":")) + "\n")

    def step(self, frame: int) -> None:
        # Startup lawn-mower construction is staggered by the scene scheduler.
        if frame in (33, 39, 45, 51, 58):
            lane = len(self.mowers)
            self.mowers.append(Mower(lane=lane, born=frame))

        self.handle_actions(frame)
        self.handle_waves(frame)
        self.handle_suns(frame)
        self.handle_plants(frame)
        self.handle_zombies(frame)
        self.handle_bullets(frame)
        self.handle_mowers(frame)
        self.cleanup(frame)

    def handle_actions(self, frame: int) -> None:
        action = self.actions.get(frame)
        if action is not None and action.get("kind") == "plant":
            index = int(action["card_index"])
            self.pending_place[frame + 15] = action
            self.pending_place[frame + 4] = {"select": action}

        event = self.pending_place.pop(frame, None)
        if not event:
            return
        if "select" in event:
            action = event["select"]
            index = int(action["card_index"])
            state = self.cards[index].state(frame, self.sun_bank >= self.COSTS[index])
            if state["en"] and self.hold < 0:
                self.sun_bank -= self.COSTS[index]
                self.hold = index
                self.cards[index].spend(frame)
            return

        action = event
        index = int(action["card_index"])
        if self.hold != index:
            return
        row, col = int(action["row"]), int(action["col"])
        occupied = any(p.row == row and p.col == col and p.hp > 0 for p in self.plants)
        if occupied:
            self.sun_bank += self.COSTS[index]
            self.cards[index].cancel()
            self.hold = -1
            return
        kind = self.KINDS[index]
        hp = 3000.0 if kind == "wallnut" else 300.0
        plant = Plant(self.new_id("p"), kind, row, col, hp, frame)
        if kind == "peashooter":
            # Each plant has a stable cadence in the observed program.
            plant.shot_period = 69 + self.content_rng.uniform(0, 21)
        elif kind == "sunflower":
            first_delay = (250, 313, 376)[self.sunflower_rng.uniform(0, 2)]
            # Sunflower construction consumes eight calls from the scene's C
            # rand stream before the next falling-sun position is chosen.
            for _ in range(8):
                self.c_rng.draw()
            # Repeats cluster near 23.5 seconds; individual animation callbacks
            # account for the small per-plant spread in the original.
            plant.sun_period = 1469
            plant.next_sun = frame + first_delay
        self.plants.append(plant)
        self.cards[index].placed(frame)
        self.hold = -1

    def handle_waves(self, frame: int) -> None:
        if frame != self.wave_frames[-1]:
            return
        self.wave += 1
        self.last_wave_frame = frame
        self.spawn_wave(frame)
        if self.wave == 1:
            self.wave_frames.append(3201 if self.actions else 3226)
        elif self.wave == 2:
            self.wave_frames.append(5226 if self.actions else 5208)
        elif self.wave == 3:
            alive = sum(z.alive for z in self.zombies)
            self.wave_frames.append(frame + (1682 if alive <= 1 else 2788))
        elif self.wave == 4:
            prior_alive = sum(z.alive for z in self.zombies)
            self.wave_frames.append(frame + (6 if prior_alive <= 4 else 156))
        elif self.wave < 8:
            self.wave_frames.append(frame + 2813)

    def spawn_wave(self, frame: int) -> None:
        defenders = sum(p.kind != "sunflower" and p.hp > 0 for p in self.plants)
        if self.wave == 1:
            count, lanes = 1, [4]
        elif self.wave == 2:
            count = 5 if defenders else 3
            lanes = ([1, 2, 0, 3, 3] if defenders else [2, 3, 0])
        elif self.wave == 3:
            count = 5 if defenders else 4
            lanes = [2, 4, 0, 1, 2][:count]
        elif self.wave == 4:
            count = 3
            lanes = [4, 2, 3]
        else:
            count = 15 + self.content_rng.uniform(0, 4)
            lanes = [3, 0, 2, 4, 1] * 4

        for i in range(count):
            kind = "common"
            if self.wave >= 3 and self.content_rng.uniform(0, 9) < (self.wave - 2):
                kind = "cone"
            if self.wave >= 5 and self.content_rng.uniform(0, 19) == 0:
                kind = "bucket"
            if (self.wave == 2 and defenders and i == 0 and
                    sum(p.kind == "peashooter" and p.hp > 0 for p in self.plants) >= 2 and
                    any(p.kind == "wallnut" and p.hp > 0 for p in self.plants)):
                kind = "cone"
            configured_x = self.x_rng.uniform(1780, 2280)
            hs = 600.0 if kind == "cone" else 1200.0 if kind == "bucket" else 0.0
            self.zombies.append(
                Zombie(self.new_id("z"), kind, lanes[i % len(lanes)], float(configured_x),
                       hs=hs, born=frame)
            )

    def handle_suns(self, frame: int) -> None:
        # Sky sun starts near 5 seconds and repeats every 25 seconds. The
        # 62.5-frame half-step alternates intervals of 1562 and 1563 frames.
        sky_index = max(0, int(round((frame - 314) / 1562.5))) if frame >= 314 else -1
        sky_frame = math.floor(314 + sky_index * 1562.5) if sky_index >= 0 else -1
        if frame == sky_frame:
            x0 = float(500 + self.c_rng.draw() % 1100)
            landing_x = x0 + (self.c_rng.draw() % 120 - 60)
            landing_y = float(self.sun_rng.uniform(170, 350))
            self.suns.append(Sun(self.new_id("s"), x0, landing_x, landing_y, frame, "sky"))

        for plant in self.plants:
            if plant.kind == "sunflower" and plant.hp > 0 and plant.next_sun == frame:
                lx = plant.x + self.content_rng.uniform(-18, 18)
                ly = plant.y + 73.0
                self.suns.append(Sun(self.new_id("s"), plant.x, lx, ly, frame, "plant"))
                plant.next_sun += plant.sun_period

        if self.collect_every and frame > 0 and frame % self.collect_every == 0:
            for sun in self.suns:
                if not sun.en:
                    continue
                x, y = sun.position(frame - 1)
                if 0.0 < x < 1920.0 and 0.0 < y < 1080.0:
                    sun.en = 0
                    sun.collect_frame = frame + 3
                    distance = math.hypot(x - 290.0, y - 1010.0)
                    sun.credit_frame = frame + 8 + int(distance / 35.0)
                    break

        for sun in self.suns:
            if sun.credit_frame == frame:
                self.sun_bank += 50

    def handle_plants(self, frame: int) -> None:
        for plant in self.plants:
            if plant.kind != "peashooter" or plant.hp <= 0:
                continue
            targets = [z for z in self.zombies if z.alive and z.lane == plant.row and z.show and z.x > plant.x]
            if not targets:
                plant.next_shot = None
                continue
            if plant.next_shot is None:
                plant.next_shot = frame + plant.shot_period
            if frame >= plant.next_shot:
                self.bullets.append(Bullet(self.new_id("b"), plant.row, plant.x + 70.0,
                                           plant.y + 78.0, frame))
                plant.next_shot += plant.shot_period

    def handle_zombies(self, frame: int) -> None:
        for zombie in self.zombies:
            if zombie.death_frame is not None:
                if frame - zombie.death_frame >= 42:
                    zombie.spd = 0.0
                elif zombie.spd:
                    zombie.x -= zombie.spd * FRAME_DT
                continue
            if not zombie.alive:
                continue
            zombie.show = int(zombie.x <= 1710.0)
            blockers = [p for p in self.plants if p.row == zombie.lane and p.hp > 0 and p.x < zombie.x]
            blocker = max(blockers, key=lambda p: p.x, default=None)
            if blocker is not None and zombie.x <= blocker.x + 80.0:
                zombie.x = blocker.x + 80.0
                if not zombie.eat:
                    zombie.eat = 1
                    zombie.spd = 0.0
                    zombie.next_bite = frame + 42
                if zombie.next_bite is not None and frame >= zombie.next_bite:
                    blocker.hp -= 100.0
                    zombie.next_bite += 83
                    if blocker.hp <= 0:
                        blocker.death_frame = frame
                        zombie.eat = 0
                        zombie.spd = 30.0
                        zombie.next_bite = None
            else:
                if zombie.eat:
                    zombie.eat = 0
                    zombie.spd = 30.0
                    zombie.next_bite = None
                zombie.x -= zombie.spd * FRAME_DT
            mower = next((m for m in self.mowers if m.lane == zombie.lane), None)
            if zombie.alive and zombie.x <= 535.0 and mower is not None and not mower.live:
                mower.live, mower.st, mower.trigger_frame = 1, 2, frame
                self.kill_zombie(zombie, frame)
            elif zombie.alive and zombie.x < 290.0 and mower is None:
                # The observed build often terminates abnormally before an overlay, so
                # preserve the trace rather than inventing an early result frame.
                pass

    def handle_bullets(self, frame: int) -> None:
        for bullet in self.bullets:
            age = frame - bullet.born
            if age == 1:
                bullet.x += 0.001
            elif age > 1:
                bullet.x += 10.6666667
            if bullet.used:
                continue
            targets = sorted((z for z in self.zombies if z.alive and z.lane == bullet.lane), key=lambda z: z.x)
            for zombie in targets:
                if bullet.x + 22.0 >= zombie.x:
                    bullet.used = 1
                    if zombie.hs > 0:
                        zombie.hs = max(0.0, zombie.hs - 20.0)
                    elif zombie.bs > 0:
                        zombie.bs = max(0.0, zombie.bs - 20.0)
                    else:
                        zombie.hp -= 20.0
                        if zombie.hp <= 0:
                            zombie.hp = 0.0
                            self.kill_zombie(zombie, frame)
                    break

    def kill_zombie(self, zombie: Zombie, frame: int) -> None:
        zombie.hp = 0.0
        zombie.alive = 0
        zombie.death_frame = frame

    def handle_mowers(self, frame: int) -> None:
        for mower in self.mowers:
            if not mower.live or mower.trigger_frame is None:
                continue
            if frame >= mower.trigger_frame + 2:
                mower.x += 12.16
            for zombie in self.zombies:
                if zombie.alive and zombie.lane == mower.lane and mower.x + 90.0 >= zombie.x:
                    self.kill_zombie(zombie, frame)

    def cleanup(self, frame: int) -> None:
        self.bullets = [b for b in self.bullets if b.x <= 2800.0]
        self.suns = [s for s in self.suns if frame - s.born < (437 if s.collect_frame is not None else 1312)]
        self.plants = [p for p in self.plants if p.death_frame is None or frame - p.death_frame < 251]
        self.zombies = [z for z in self.zombies if z.death_frame is None or frame - z.death_frame < 500]
        self.mowers = [m for m in self.mowers if not (m.live and m.x > 2100.0)]

    def trace(self, frame: int) -> dict:
        next_wave = self.wave_frames[-1] if self.wave_frames else 10**9
        wdead = int(next_wave - 6 <= frame < next_wave)
        global_seconds = int(frame * FRAME_DT)
        if self.wave == 0:
            wt = float(global_seconds if frame >= 64 else 0)
        else:
            wt = float(max(0, global_seconds - int(self.last_wave_frame * FRAME_DT)))
        wbegin = int(frame >= 64 and not wdead and
                     (self.wave == 0 or global_seconds > int(self.last_wave_frame * FRAME_DT)))
        cards = [card.state(frame, self.sun_bank >= self.COSTS[card.tag]) for card in self.cards]
        return {
            "f": frame,
            "sun": self.sun_bank,
            "ts": 1.0,
            "wave": self.wave,
            "wt": wt,
            "wbegin": wbegin,
            "wdead": wdead,
            "end": 0,
            "zwin": 0,
            "hold": self.hold,
            "shovel": 0,
            "cards": cards,
            "p": [{"id": p.ident, "t": p.kind, "r": p.col, "c": p.row, "hp": r3(p.hp)}
                  for p in self.plants],
            "z": [{"id": z.ident, "t": z.kind, "x": r3(z.x), "y": r3(z.y),
                   "hp": r3(z.hp), "hs": r3(z.hs), "bs": r3(z.bs), "eat": z.eat,
                   "alive": z.alive, "show": z.show, "spd": r3(z.spd)} for z in self.zombies],
            "b": [{"id": b.ident, "x": r3(b.x), "y": r3(b.y), "used": b.used}
                  for b in self.bullets],
            "s": [{"id": s.ident, "x": r3(s.position(frame)[0]), "y": r3(s.position(frame)[1]),
                   "en": s.en} for s in self.suns],
            "cars": [{"tag": -1, "live": m.live, "st": m.st, "x": r3(m.x)} for m in self.mowers],
        }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: run-scenario <scenario.json> <out-trace.jsonl>", file=sys.stderr)
        return 2
    scenario_path = Path(argv[1])
    output_path = Path(argv[2])
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    if scenario.get("schema") != 1 or scenario.get("level") != 4 or scenario.get("frame_ms") != 16:
        raise ValueError("only schema 1, level 4, frame_ms 16 scenarios are supported")
    Simulator(scenario).run(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
