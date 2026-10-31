#!/usr/bin/env python3
"""Operator-side trace oracle service for the PvZ REA experiment (arms A/B/C).

Arms drop a semantic scenario JSON into <run>/oracle-svc/requests/<name>.json; this daemon
validates it, expands it to the operator bot script, runs the stripped ELF + shim under a
private Xvfb, and returns trace.jsonl / inputs.txt / rc / status.json under
<run>/oracle-svc/responses/<name>/.

Everything secret (shim .so, symbol table) is read ONCE at startup into memfds, so the
operator/ and sealed/ trees can be chmod 000 for the whole run. Shim stdout (which prints
mangled class names) is never returned.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPERATOR = HERE.parent
sys.path.insert(0, str(OPERATOR / "scenarios"))
import generate_scenarios as gen  # noqa: E402  (read at startup, before the lock)

CARDS = {"sunflower": 0, "peashooter": 1, "wallnut": 2}
MAX_END_FRAME = 12000
MAX_ACTIONS = 40


def memfd_from(path: Path, name: str) -> int:
    fd = os.memfd_create(name, 0)  # no CLOEXEC: inherited by the oracle child via pass_fds
    os.write(fd, path.read_bytes())
    os.lseek(fd, 0, os.SEEK_SET)
    return fd


def load_tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Service:
    def __init__(self, runs_root: Path, dist: Path, budget: int, jobs: int):
        self.runs_root = runs_root
        self.dist = dist
        self.budget = budget
        self.sem = threading.Semaphore(jobs)
        # one slot per run: a run's queries execute one at a time and never wait
        # behind another run's queries (as long as active runs <= jobs)
        self.run_locks: dict[str, threading.Lock] = {}
        self.lock = threading.Lock()
        self.svc_dir = runs_root / "_svc"
        self.work_dir = self.svc_dir / "work"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.svc_dir / "requests.jsonl"
        self.shim_fd = memfd_from(OPERATOR / "oracle" / "libpvzoracle.so", "o1")
        self.syms_fd = memfd_from(OPERATOR / "oracle" / "pvz.syms", "o2")
        self.home = load_tree(OPERATOR / "runtime" / "home-template")
        self.boot = gen.boot_lines()
        hidden = [s for s in gen.scenarios() if s.split == "hidden"]
        self.hidden_time = {s.time_seed for s in hidden}
        self.hidden_dev = {s.device_seed for s in hidden}
        self.in_flight: set[Path] = set()
        self.used = self._used_counts()

    # ---- bookkeeping -------------------------------------------------------------
    def _used_counts(self) -> dict[str, int]:
        used: dict[str, int] = {}
        if self.log_path.exists():
            for line in self.log_path.read_text().splitlines():
                r = json.loads(line)
                if r.get("accepted"):
                    used[r["run"]] = used.get(r["run"], 0) + 1
        return used

    def log(self, rec: dict) -> None:
        with self.lock, self.log_path.open("a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")

    # ---- validation ----------------------------------------------------------------
    def validate(self, spec: dict) -> str | None:
        def is_int(v):
            return isinstance(v, int) and not isinstance(v, bool)
        if not isinstance(spec, dict):
            return "scenario must be a JSON object"
        if spec.get("schema") != 1 or spec.get("level") != 4 or spec.get("frame_ms") != 16:
            return "schema must be 1, level 4, frame_ms 16"
        for k in ("time_seed", "device_seed"):
            if not is_int(spec.get(k)) or not 0 <= spec[k] < 2**31:
                return f"{k} must be an integer in [0, 2^31)"
        if spec["time_seed"] in self.hidden_time or spec["device_seed"] in self.hidden_dev:
            return "seed reserved by the evaluator; choose another seed"
        if not is_int(spec.get("end_frame")) or not 1 <= spec["end_frame"] <= MAX_END_FRAME:
            return f"end_frame must be an integer in [1, {MAX_END_FRAME}]"
        cs = spec.get("collect_sun", {"mode": "first_enabled", "every_frames": 0})
        if not isinstance(cs, dict) or cs.get("mode") != "first_enabled" or not is_int(cs.get("every_frames")):
            return "collect_sun must be {mode: first_enabled, every_frames: int}"
        if cs["every_frames"] != 0 and not 10 <= cs["every_frames"] <= 1000:
            return "collect_sun.every_frames must be 0 or in [10, 1000]"
        acts = spec.get("actions", [])
        if not isinstance(acts, list) or len(acts) > MAX_ACTIONS:
            return f"actions must be a list of at most {MAX_ACTIONS}"
        for a in acts:
            if not isinstance(a, dict) or a.get("kind") != "plant":
                return "every action must be an object with kind 'plant'"
            if a.get("card") not in CARDS or a.get("card_index", CARDS.get(a.get("card"))) != CARDS[a["card"]]:
                return "card must be sunflower|peashooter|wallnut (card_index 0|1|2)"
            for k, hi in (("frame", spec["end_frame"]), ("row", 4), ("col", 8)):
                if not is_int(a.get(k)) or not 0 <= a[k] <= hi:
                    return f"action.{k} out of range"
        return None

    def bot_script(self, spec: dict) -> str:
        cs = spec.get("collect_sun", {"every_frames": 0})
        lines = [f"time_seed {spec['time_seed']}", f"device_seed {spec['device_seed']}", "bot_seed 1",
                 "boot_max 3000", f"end_frame {spec['end_frame']}", "post_result_frames 60"]
        lines += self.boot
        lines += [f"bot_plant {a['frame']} {CARDS[a['card']]} {a['row']} {a['col']}"
                  for a in spec.get("actions", [])]
        if cs["every_frames"]:
            lines.append(f"bot_collect_sun {cs['every_frames']}")
        return "\n".join(lines) + "\n"

    # ---- execution -----------------------------------------------------------------
    def run_oracle(self, bot: str, out: Path) -> int:
        work = Path(tempfile.mkdtemp(prefix="req.", dir=self.work_dir))
        xvfb = None
        try:
            for rel, data in self.home.items():
                p = work / "home" / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            (work / "bot.txt").write_text(bot)
            r, w = os.pipe()
            xvfb = subprocess.Popen(["Xvfb", "-displayfd", str(w), "-screen", "0", "1600x900x24",
                                     "-nolisten", "tcp"], pass_fds=(w,),
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.close(w)
            disp = b""
            deadline = time.time() + 15
            while not disp.endswith(b"\n") and time.time() < deadline:
                chunk = os.read(r, 16)
                if not chunk:
                    break
                disp += chunk
            os.close(r)
            disp_n = "".join(ch for ch in disp.decode() if ch.isdigit())
            if not disp_n:
                raise RuntimeError("Xvfb did not report a display")
            env = {"PATH": "/usr/bin:/bin", "HOME": str(work / "home"),
                   "XDG_CONFIG_HOME": str(work / "home" / ".config"), "DISPLAY": f":{disp_n}",
                   "LIBGL_ALWAYS_SOFTWARE": "1",
                   "LD_PRELOAD": f"/proc/self/fd/{self.shim_fd}",
                   "PVZ_SYMS": f"/proc/self/fd/{self.syms_fd}",
                   "PVZ_SCENARIO": str(work / "bot.txt"), "PVZ_TRACE": str(out / "trace.jsonl"),
                   "PVZ_EVENTS_OUT": str(out / "inputs.txt")}
            with open(work / "stdout.log", "wb") as so:
                proc = subprocess.run(["timeout", "1800", "./pvz"], cwd=self.dist, env=env,
                                      pass_fds=(self.shim_fd, self.syms_fd), stdout=so,
                                      stderr=subprocess.STDOUT)
            return proc.returncode
        finally:
            if xvfb:
                xvfb.terminate()
                try:
                    xvfb.wait(10)
                except subprocess.TimeoutExpired:
                    xvfb.kill()
            shutil.rmtree(work, ignore_errors=True)

    def handle(self, run: str, req: Path) -> None:
        name = req.stem
        resp = req.parent.parent / "responses" / name
        queued = time.time()
        rec = {"run": run, "name": name, "queued_ts": queued}
        try:
            raw = req.read_bytes()
            rec["sha256"] = sha256_bytes(raw)
            err = None
            try:
                spec = json.loads(raw)
            except json.JSONDecodeError as e:
                spec, err = None, f"invalid JSON: {e}"
            err = err or self.validate(spec)
            with self.lock:
                used = self.used.get(run, 0)
                if err is None and used >= self.budget:
                    err = f"query budget exhausted ({self.budget})"
                if err is None:
                    self.used[run] = used + 1
            resp.mkdir(parents=True, exist_ok=True)
            if err:
                rec.update(accepted=False, error=err)
                status = {"status": "rejected", "error": err,
                          "remaining": self.budget - self.used.get(run, 0)}
            else:
                rec["accepted"] = True
                with self.lock:
                    run_lock = self.run_locks.setdefault(run, threading.Lock())
                with run_lock, self.sem:
                    rec["start_ts"] = time.time()
                    rc = self.run_oracle(self.bot_script(spec), resp)
                rec.update(end_ts=time.time(), rc=rc)
                frames = sum(1 for _ in (resp / "trace.jsonl").open()) if (resp / "trace.jsonl").exists() else 0
                rec["frames"] = frames
                (resp / "rc").write_text(f"{rc}\n")
                status = {"status": "done", "rc": rc, "frames": frames,
                          "remaining": self.budget - self.used.get(run, 0)}
            (resp / "status.json.tmp").write_text(json.dumps(status, indent=2) + "\n")
            os.replace(resp / "status.json.tmp", resp / "status.json")
        except Exception as e:  # never kill the daemon on one bad request
            rec.update(accepted=rec.get("accepted", False), error=f"service error: {e}")
            try:
                resp.mkdir(parents=True, exist_ok=True)
                (resp / "status.json").write_text(json.dumps({"status": "error", "error": str(e)}) + "\n")
            except OSError:
                pass
        finally:
            self.log(rec)
            try:
                req.rename(req.with_suffix(".done"))
            except OSError:
                pass
            with self.lock:
                self.in_flight.discard(req)

    def loop(self, stop: threading.Event) -> None:
        while not stop.is_set():
            for reqdir in sorted(self.runs_root.glob("*/oracle-svc/requests")):
                run = reqdir.parent.parent.name
                try:
                    reqs = sorted(reqdir.glob("*.json"), key=lambda p: p.stat().st_mtime)
                except OSError:
                    continue
                for req in reqs:
                    with self.lock:
                        if req in self.in_flight:
                            continue
                        self.in_flight.add(req)
                    threading.Thread(target=self.handle, args=(run, req), daemon=True).start()
            stop.wait(2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", type=Path, required=True)
    ap.add_argument("--dist", type=Path, required=True, help="service copy of the arm-visible dist")
    ap.add_argument("--budget", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    svc = Service(args.runs_root.resolve(), args.dist.resolve(), args.budget, args.jobs)
    (svc.svc_dir / "service.pid").write_text(f"{os.getpid()}\n")
    (svc.svc_dir / "ready").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    svc.loop(stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
