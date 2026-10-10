"""
build_zip.py — clean release zip in one command (replaces the manual zip steps).

  1. removes runtime-local files (logs, .idx caches, __pycache__, .pytest_cache)
  2. runs project_map_check --release (must be OK: nothing secret/runtime inside)
  3. writes the zip: eva-full-project/ + capture_tool/ (from ../tools/chitchat_capture)
  4. re-opens the zip: testzip + forbidden-path scan

Usage (from the project root):  python tools/build_zip.py [--out EVA_Bot_FINAL.zip]
Exit 0 only if every step passes.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CAPTURE = os.path.abspath(os.path.join(PROJECT, "..", "tools", "chitchat_capture"))
FORBIDDEN = re.compile(
    r"(^|/)(account_sessions|browser_profile|capture_out|__pycache__|logs|\.git)(/|$)"
    r"|\.pyc$|\.idx$|(^|/)configs/|storage_state|session\.json$|session_cookies|\.log$|\.zip$|\.exe$|(^|/)\.env$")


def clean_runtime() -> int:
    removed = 0
    for d, ds, fs in os.walk(PROJECT):
        for name in list(ds):
            if name in ("__pycache__", ".pytest_cache"):
                shutil.rmtree(os.path.join(d, name), ignore_errors=True)
                ds.remove(name)
                removed += 1
        for f in fs:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, PROJECT).replace(os.sep, "/")
            if f.endswith(".pyc") or re.match(r"data/\.[^/]*\.idx$", rel) or rel.startswith("data/logs/"):
                os.remove(p)
                removed += 1
    logs = os.path.join(PROJECT, "data", "logs")
    if os.path.isdir(logs) and not os.listdir(logs):
        os.rmdir(logs)
    cap_out = os.path.join(CAPTURE, "capture_out")
    if os.path.isdir(cap_out):
        shutil.rmtree(cap_out, ignore_errors=True)
    return removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="EVA_Bot_FINAL.zip")
    args = ap.parse_args()
    out = os.path.abspath(args.out)

    print(f"[1] cleaned runtime files: {clean_runtime()}", flush=True)
    sys.stdout.flush()
    rc = subprocess.run([sys.executable, os.path.join("tools", "project_map_check.py"), "--release"],
                        cwd=PROJECT).returncode
    print(f"[2] release map check: {'PASS' if rc == 0 else 'FAIL'}")
    if rc != 0:
        return 1

    if not os.path.isdir(CAPTURE):
        print(f"[3] capture tool not found at {CAPTURE} — aborting (zip would be incomplete)")
        return 1
    n = 0
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for src, dst in ((PROJECT, "eva-full-project"), (CAPTURE, "capture_tool")):
            for d, ds, fs in os.walk(src):
                ds[:] = [x for x in ds if x not in ("__pycache__", ".git")]
                for f in fs:
                    p = os.path.join(d, f)
                    z.write(p, os.path.join(dst, os.path.relpath(p, src)))
                    n += 1
    print(f"[3] wrote {out} ({n} files, {os.path.getsize(out)//1024} KB)")

    with zipfile.ZipFile(out) as z:
        bad_crc = z.testzip()
        bad = [x for x in z.namelist() if FORBIDDEN.search(x)]
    print(f"[4] testzip: {'OK' if bad_crc is None else bad_crc}; forbidden paths: {bad or 'none'}")
    ok = bad_crc is None and not bad
    print("BUILD:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
