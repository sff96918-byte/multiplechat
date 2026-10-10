"""critical_guard.py — warns when HIGH-risk (CRITICAL_CORE) files change without a test change (v26).

Reads `project.map.json` class CRITICAL_CORE. Looks at files changed versus a git
base (default HEAD = uncommitted edits + new untracked files). If any CRITICAL_CORE
file changed and no `test_*.py` file changed in the same diff, it reports FAIL.

    python tools/critical_guard.py              # vs HEAD (uncommitted work)
    python tools/critical_guard.py --base main  # vs a branch
    python tools/critical_guard.py --allow      # report only, exit 0

Limits (stated plainly):
- It cannot verify that a test was written BEFORE the change (TDD order).
- It is NOT part of verify_gate.py: the gate also runs in the extracted zip,
  which has no git history. Run this by hand before committing a CRITICAL edit.
- Without a git repository it prints SKIP and exits 0.
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from project_map_check import glob_to_regex  # noqa: E402


def git(args):
    p = subprocess.run(["git"] + args, cwd=ROOT, capture_output=True, text=True)
    return p.returncode, p.stdout


def changed_files(base):
    rc, _ = git(["rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        return None
    files = set()
    rc, out = git(["diff", "--name-only", "--relative", base, "--", "."])
    if rc != 0:
        raise SystemExit(f"git diff failed against base '{base}'")
    files.update(line.strip() for line in out.splitlines() if line.strip())
    rc, out = git(["ls-files", "--others", "--exclude-standard", "--", "."])
    files.update(line.strip() for line in out.splitlines() if line.strip())
    return sorted(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--allow", action="store_true",
                    help="report only, always exit 0")
    args = ap.parse_args()

    with open(os.path.join(ROOT, "project.map.json"), encoding="utf-8") as f:
        spec = json.load(f)
    patterns = [glob_to_regex(p) for p in
                spec["classes"]["CRITICAL_CORE"]["patterns"]]

    files = changed_files(args.base)
    if files is None:
        print("SKIP  not a git repository; critical_guard needs git history")
        return 0

    critical = [f for f in files if any(p.match(f) for p in patterns)]
    tests = [f for f in files if os.path.basename(f).startswith("test_")
             and f.endswith(".py")]

    print(f"base={args.base}  changed={len(files)}  "
          f"CRITICAL_CORE changed={len(critical)}  test files changed={len(tests)}")
    for f in critical:
        print(f"  CRITICAL  {f}")
    if not critical:
        print("OK    no HIGH-risk file changed")
        return 0
    if tests:
        print("OK    CRITICAL change(s) come with test change(s); "
              "check TDD order yourself")
        return 0
    print("FAIL  CRITICAL_CORE changed with NO test_*.py change. "
          "Add a failing test first (AGENTS.md / project.map.json rule).")
    return 0 if args.allow else 1


if __name__ == "__main__":
    sys.exit(main())
