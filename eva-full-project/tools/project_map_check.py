"""
project_map_check.py — keeps project.map.json honest.

Checks (exit 1 if any FAIL):
  1. every project file is covered by a class pattern (first match wins)
  2. no never_ship file exists inside the project folder
  3. every pattern matches at least one file (no stale entries)
  4. every test named in a class exists

runtime_local files (logs/.idx/__pycache__ made by running the tests) are ignored
in normal mode. Use --release before building the zip: then they must be absent too.

Run from the project root:
  python tools/project_map_check.py            # normal (gate uses this)
  python tools/project_map_check.py --release  # zip gate: nothing runtime-local may exist
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAP_PATH = os.path.join(ROOT, "project.map.json")
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache"}


def glob_to_regex(pattern: str) -> re.Pattern:
    """Minimal glob: '**/' = any dirs, '**' = anything, '*' = one segment, '?' = one char."""
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def project_files(spec: dict, release: bool) -> list[str]:
    runtime = [] if release else [glob_to_regex(p) for p in spec.get("runtime_local", [])]
    files = []
    for d, ds, fs in os.walk(ROOT):
        ds[:] = [x for x in ds if x not in SKIP_DIRS]
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, "/")
            if any(rx.match(rel) for rx in runtime):
                continue
            files.append(rel)
    return sorted(files)


def main() -> int:
    with open(MAP_PATH, encoding="utf-8") as fh:
        spec = json.load(fh)
    release = "--release" in sys.argv[1:]
    files = project_files(spec, release)
    print(f"mode: {'release (zip gate)' if release else 'normal'}")
    fails = 0

    def report(ok: bool, name: str, detail: str = "") -> None:
        nonlocal fails
        if not ok:
            fails += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -> {detail}" if detail and not ok else ""))

    # compile patterns once, remember which class each pattern belongs to
    entries = []
    for cname, cls in spec["classes"].items():
        for pat in cls.get("patterns", []) + cls.get("approval_patterns", []):
            entries.append((cname, pat, glob_to_regex(pat)))

    print("[1] unclassified files")
    unclassified = []
    owner_of = {}
    for f in files:
        hit = next((e for e in entries if e[2].match(f)), None)
        if hit is None:
            unclassified.append(f)
        else:
            owner_of[f] = hit[0]
    report(not unclassified, "every file has a class", ", ".join(unclassified[:10]))

    print("[2] never_ship files present")
    shipped = []
    for f in files:
        for pat in spec.get("never_ship", []):
            if glob_to_regex(pat).match(f):
                shipped.append(f)
                break
    report(not shipped, "no secret/runtime file in project", ", ".join(shipped[:10]))

    print("[3] stale patterns (match nothing)")
    stale = [f"{c}:{p}" for c, p, rx in entries if not any(rx.match(f) for f in files)]
    report(not stale, "every pattern matches a file", ", ".join(stale[:10]))

    print("[4] tests named in classes exist")
    missing = set()
    for cls in spec["classes"].values():
        for t in cls.get("tests", []):
            if t not in files and not any(glob_to_regex(t).match(f) for f in files):
                missing.add(t)
    report(not missing, "all listed tests exist", ", ".join(sorted(missing)))

    print("\nSummary by class:")
    counts = {}
    for owner in owner_of.values():
        counts[owner] = counts.get(owner, 0) + 1
    for cname in spec["classes"]:
        risk = spec["classes"][cname]["risk"]
        print(f"  {cname:<16} risk={risk:<6} files={counts.get(cname, 0)}")
    print(f"\nRESULT: {'OK' if fails == 0 else f'{fails} FAIL'} ({len(files)} files checked)")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
