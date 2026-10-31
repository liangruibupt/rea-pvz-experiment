#!/usr/bin/env python3
"""Neutralize arm-revealing evidence in frozen RULES.md files and relabel them.

Rule CONTENT is kept. Removed or neutralized: "Evidence:" clauses, file paths,
tool names (REA/Ghidra/decompiler), function names/addresses, oracle wording and
AI-DLC references, so a scorer cannot infer the arm from how a rule was found.
Output: blinded/D01.md ... plus operator-only/doc-mapping.json (not for scorers).
"""
import hashlib, json, random, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BLIND = ROOT.parent / "blind"
OUT = ROOT / "blinded"
OPS = ROOT.parent / "operator-only"

EVIDENCE = re.compile(r"(?:Evidence|REA confirmation|Confirmation|Source)\s*:\s*.*?(?=(?:\.\s+(?=[A-Z][a-z]))|$)")
SUBS = [
    (re.compile(r"`[^`]*[/\\][^`]*`"), "[ref]"),
    (re.compile(r"\b(?:oracle-results|rea-out|aidlc-docs|harness-out|public|calibration)/\S+"), "[ref]"),
    (re.compile(r"\bFUN_[0-9a-fA-F]+\b"), "[fn]"),
    (re.compile(r"\b0x[0-9a-fA-F]{3,}\b"), "[addr]"),
    (re.compile(r"\b(?:REA|Ghidra|IDA)\b"), "analysis"),
    (re.compile(r"\b(?:de)?compil(?:ed|er|ation)s?\b|\bdecompil\w*|\bdisassembl\w*", re.I), "analysis"),
    (re.compile(r"\boracle(?:-query)?\b", re.I), "reference"),
    (re.compile(r"\bquer(?:y|ies)\b", re.I), "probe"),
    (re.compile(r"\bAI-?DLC\b", re.I), "process"),
    (re.compile(r"\b(?:public|calibration|cal)-[\w-]+\b"), "[scenario]"),
]

POST = [
    (re.compile(r"\banalysis (found|finds|confirms|confirmed|shows|showed)\b( that)?", re.I), "Recovered:"),
    (re.compile(r"\b(?:queried|supplied or queried|controlled) reference (?:traces?|experiments?|runs?)\b", re.I), "measurements"),
    (re.compile(r"\breference (?:experiments?|runs?|probes?)\b|\bprobes?\b|\bqueried\b", re.I), "measurement"),
    (re.compile(r"\b(?:black-box )?reference\b", re.I), "measurement"),
    (re.compile(r"\banalysis\b", re.I), "measurement"),
    (re.compile(r"\.\.+"), "."),
]
DROP_LINE = re.compile(r"\[fn\]|\[addr\]|_INIT_\d|semantic symbols|shipped AArch64 binary", re.I)
POST.insert(0, (re.compile(r"\boriginal[- ]process\b|\boriginal executable\b|\bthe binary\b|\bexecutable\b", re.I), "program"))
POST.insert(0, (re.compile(r"`?\brc=-?\d+`?|\breturn code -?\d+\b"), "an abort"))
DROP_SECTION = re.compile(r"^#+.*(evidence|analysis|provenance|method|process|tool)", re.I)

def redact(text: str) -> str:
    out = []
    skipping = False
    for line in text.splitlines():
        if line.startswith("#"):
            skipping = bool(DROP_SECTION.match(line))
            if skipping:
                continue
        if skipping:
            continue
        line = EVIDENCE.sub("", line)
        for pat, rep in SUBS + POST:
            line = pat.sub(rep, line)
        if DROP_LINE.search(line):
            continue
        line = re.sub(r"\s+\.", ".", re.sub(r"[ \t]{2,}", " ", line)).rstrip()
        if line.strip() in {"-", "*", ""} and out and out[-1] == "":
            continue
        out.append(line)
    return "\n".join(out).strip() + "\n"

def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 20261028
    docs = sorted(p for p in BLIND.glob("rep*/submission/RULES.md"))
    labels = [p.parts[-3] for p in docs]
    order = labels[:]
    random.Random(seed).shuffle(order)
    OUT.mkdir(exist_ok=True)
    mapping = {}
    for i, lab in enumerate(order, 1):
        src = BLIND / lab / "submission" / "RULES.md"
        doc_id = f"D{i:02d}"
        red = redact(src.read_text(encoding="utf-8"))
        (OUT / f"{doc_id}.md").write_text(red, encoding="utf-8")
        mapping[doc_id] = {"blind_label": lab,
                           "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
                           "redacted_sha256": hashlib.sha256(red.encode()).hexdigest()}
    (OPS / "doc-mapping.json").write_text(json.dumps(mapping, indent=2) + "\n")
    missing = sorted({p.name for p in BLIND.iterdir()} - set(labels))
    print(f"wrote {len(order)} docs; no RULES.md (disqualified): {missing}")

if __name__ == "__main__":
    main()
