"""
verify_gate.py — runs the AGENTS.md §5 verify gate in one command.

Usage (from the project root):  python tools/verify_gate.py
Prints one line per step and a summary. Exit 0 only if every step passes.

Steps are exactly the sandbox-runnable checks. Not covered (needs Windows/live):
GUI rendering, Playwright browser mode, live chitchat.gg chat, install.bat.
"""
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = sys.executable

COMPILE = ["entry/main.py", "entry/thread_manager.py", "entry/paths.py",
           "browser/browser_automation.py", "core/config_loader.py",
           "core/session_chat.py", "core/ws_transport/ws_chat_loop.py",
           "core/ws_transport/chitchat_api.py", "tools/verify_gate.py",
           "tools/project_map_check.py", "tools/gui_import_check.py"]

STEPS = [
    ("project map", [PY, "tools/project_map_check.py"]),
    ("py_compile", [PY, "-m", "py_compile"] + COMPILE),
    ("import chat + eva_flow", [PY, "-c", "import chat; import eva_flow; print('import ok')"]),
    ("import ws_transport", [PY, "-c", "import core.ws_transport.chitchat_api, core.ws_transport.ws_chat_loop; print('ws import ok')"]),
    ("test_matcher", [PY, "test_matcher.py"]),
    ("test_live", [PY, "test_live.py"]),
    ("test_fuzz", [PY, "test_fuzz.py"]),
    ("test_flow", [PY, "test_flow.py"]),
    ("demo_chat", [PY, "demo_chat.py"]),
    ("test_diagnostics", [PY, "test_diagnostics.py"]),
    ("test_ws_transport", [PY, "test_ws_transport.py"]),
    ("session_chat --list", [PY, "-m", "core.session_chat", "--list"]),
    ("gui import (stubbed)", [PY, "tools/gui_import_check.py"]),
]


def run(name, cmd):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                           timeout=300, encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        code = p.returncode
    except subprocess.TimeoutExpired:
        out, code = "timeout after 300s", 124
    last = next((l.strip() for l in reversed(out.splitlines()) if l.strip()), "")
    return code, time.time() - t0, last


def main() -> int:
    rows = []
    for name, cmd in STEPS:
        code, secs, last = run(name, cmd)
        rows.append((name, code, secs, last))
        status = "PASS" if code == 0 else "FAIL"
        print(f"{status}  {name:<24} {secs:6.1f}s  {last[:70]}", flush=True)
    failed = [r for r in rows if r[1] != 0]
    print(f"\nGATE: {len(rows) - len(failed)}/{len(rows)} steps passed"
          + ("" if not failed else "  -> FAILED: " + ", ".join(r[0] for r in failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
