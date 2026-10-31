#!/usr/bin/env python3
"""Freeze, audit and blind the 12 PvZ submissions (R from runs-20261028, A/B/C from runs-20261028-abc)."""
from __future__ import annotations

import ast
import hashlib
import json
import random
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation-20261028"
SRC = {"R": ROOT / "runs-20261028", "A": ROOT / "runs-20261028-abc",
       "B": ROOT / "runs-20261028-abc", "C": ROOT / "runs-20261028-abc"}
STDLIB = set(sys.stdlib_module_names)
SUSPECT = ["oracle/dist", "/pvz", "oracle-query", "oracle-svc", "runs-20261028", "harness/suite",
           "public/", "trace.jsonl", "subprocess", "ctypes", "os.system", "Resources/"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tree(p: Path) -> dict[str, str]:
    return {str(f.relative_to(p)): sha(f) for f in sorted(p.rglob("*")) if f.is_file()}


def tree_hash(files: dict[str, str]) -> str:
    return hashlib.sha256("".join(f"{k}\0{v}\n" for k, v in sorted(files.items())).encode()).hexdigest()


def readonly(p: Path) -> None:
    for f in [p, *p.rglob("*")]:
        f.chmod(f.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def audit(sub: Path) -> dict:
    out = {"entry": (sub / "bin" / "run-scenario").is_file(), "rules": (sub / "RULES.md").is_file(),
           "non_stdlib_imports": [], "suspect_strings": [], "largest_file_bytes": 0, "py_lines": 0}
    local = {f.stem for f in sub.rglob("*.py")}
    for f in sub.rglob("*"):
        if not f.is_file():
            continue
        out["largest_file_bytes"] = max(out["largest_file_bytes"], f.stat().st_size)
        if "aidlc-docs" in f.parts or f.suffix == ".md":
            continue
        text = f.read_text(errors="replace")
        for s in SUSPECT:
            if s in text:
                out["suspect_strings"].append(f"{f.relative_to(sub)}: {s}")
        if f.suffix == ".py" or text.startswith("#!/usr/bin/env python"):
            out["py_lines"] += text.count("\n")
            try:
                tree_ = ast.parse(text)
            except SyntaxError as e:
                out["non_stdlib_imports"].append(f"{f.relative_to(sub)}: SYNTAX {e}")
                continue
            for n in ast.walk(tree_):
                names = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                        [n.module] if isinstance(n, ast.ImportFrom) and n.module and n.level == 0 else []
                for m in names:
                    top = m.split(".")[0]
                    if top not in STDLIB and top not in local:
                        out["non_stdlib_imports"].append(f"{f.relative_to(sub)}: {m}")
    return out


def main() -> int:
    if EVAL.exists():
        raise SystemExit(f"{EVAL} exists; refusing to overwrite a freeze")
    rng = random.SystemRandom()
    mapping, manifest = {}, {}
    for rep in (1, 2, 3):
        labels = ["W", "X", "Y", "Z"]
        rng.shuffle(labels)
        for arm, label in zip("RABC", labels):
            run = f"rep{rep}-{arm}"
            orig = SRC[arm] / run / "submission"
            files = tree(orig)
            blind = EVAL / "blind" / f"rep{rep}-{label}"
            shutil.copytree(orig, blind / "submission", symlinks=False)
            bfiles = tree(blind / "submission")
            assert bfiles == files, run
            readonly(orig)
            readonly(blind)
            mapping[run] = f"rep{rep}-{label}"
            manifest[f"rep{rep}-{label}"] = {"files": len(files), "tree_sha256": tree_hash(files),
                                             "audit": audit(blind / "submission")}
    (EVAL / "operator-only").mkdir(parents=True)
    (EVAL / "operator-only" / "blind-mapping.json").write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n")
    (EVAL / "operator-only").chmod(0o700)
    (EVAL / "freeze-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    for k, v in sorted(manifest.items()):
        a = v["audit"]
        print(k, v["files"], v["tree_sha256"][:12], "entry" if a["entry"] else "NO-ENTRY",
              "lines", a["py_lines"], "max", a["largest_file_bytes"],
              "nonstd", a["non_stdlib_imports"], "suspect", a["suspect_strings"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
