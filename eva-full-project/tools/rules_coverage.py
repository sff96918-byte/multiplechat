"""rules_coverage.py — line coverage of chat/rules.py from the existing tests (v26).

    python tools/rules_coverage.py            # prints % and missing lines
    python tools/rules_coverage.py --floor 55 # exit 1 if below the floor

Runs test_rules_characterization.py, test_live.py and test_flow.py under
`coverage`, then reports coverage for chat/rules.py only.

Limits (stated plainly):
- Needs the `coverage` package (pip install coverage). Without it: SKIP, exit 0.
- Measures LINE coverage only, not branch coverage, and says nothing about
  whether the reply wording is correct.
- Coverage is a measurement, not proof. The floor is a regression guard.
"""
import argparse
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = ["test_rules_characterization.py", "test_live.py", "test_flow.py"]
TARGET = "chat/rules.py"


def have_coverage():
    p = subprocess.run([sys.executable, "-c", "import coverage"],
                       capture_output=True)
    return p.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", type=float, default=0.0)
    args = ap.parse_args()

    if not have_coverage():
        print("SKIP  coverage not installed (pip install coverage)")
        return 0

    tmp = tempfile.mkdtemp(prefix="rules_cov_")
    datafiles = []
    for i, t in enumerate(TESTS):
        df = os.path.join(tmp, f".cov{i}")
        datafiles.append(df)
        subprocess.run(
            [sys.executable, "-m", "coverage", "run",
             f"--include={TARGET}", f"--data-file={df}", t],
            cwd=ROOT, capture_output=True, text=True)
    merged = os.path.join(tmp, ".covall")
    subprocess.run([sys.executable, "-m", "coverage", "combine",
                    f"--data-file={merged}"] + datafiles,
                   cwd=ROOT, capture_output=True, text=True)
    rep = subprocess.run(
        [sys.executable, "-m", "coverage", "report", "-m",
         f"--data-file={merged}", f"--include={TARGET}"],
        cwd=ROOT, capture_output=True, text=True)
    if rep.returncode != 0 or TARGET not in rep.stdout:
        print("FAIL  coverage report produced no data")
        print(rep.stdout, rep.stderr)
        return 1
    line = [l for l in rep.stdout.splitlines() if l.startswith(TARGET)][0]
    pct_tok = next(t for t in line.split() if t.endswith("%"))
    pct = float(pct_tok.rstrip("%"))
    print(line)
    print(f"RULES COVERAGE: {pct:.0f}%  (floor {args.floor:.0f}%)")
    if pct + 1e-9 < args.floor:
        print("FAIL  below floor")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
