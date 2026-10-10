"""
verify_gate.py — runs the AGENTS.md §5 verify gate in one command.

Usage (from the project root):  python tools/verify_gate.py
Prints one line per step and a summary. Exit 0 only if every step passes.

Steps are exactly the sandbox-runnable checks. Optional steps (gitleaks, pyflakes,
coverage, pip-audit) are SKIPPED, not failed, when their tool is missing. Not covered (needs Windows/live):
GUI rendering, Playwright browser mode, live chitchat.gg chat, install.bat.
"""
import importlib.util
import os
import shutil
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
    ("test_rules_characterization", [PY, "test_rules_characterization.py"]),
    ("test_config_loader", [PY, "test_config_loader.py"]),
    ("session_chat --list", [PY, "-m", "core.session_chat", "--list"]),
    ("gui import (stubbed)", [PY, "tools/gui_import_check.py"]),
    ("secret scan selftest", [PY, "tools/secret_scan.py", "--selftest"]),
    ("secret scan", [PY, "tools/secret_scan.py"]),
    ("pip-audit requirements", [PY, "-m", "pip_audit", "-r", "data/requirements.txt", "--progress-spinner", "off"], "pip_audit"),
    ("gitleaks (optional)", ["gitleaks", "detect", "--no-git", "--source", ".", "--redact", "-q"], "gitleaks"),
    ("pyflakes (optional)", [PY, "-m", "pyflakes", "."], "pyflakes"),
    ("rules coverage (optional)", [PY, "tools/rules_coverage.py", "--floor", "50"], "coverage"),
]

# A step may name a tool; if that tool is not installed the step is SKIPPED
# (reported, not failed). Steps without a tool name always run.
OPTIONAL_MODULE = {"pip_audit": "pip_audit", "coverage": "coverage",
                   "pyflakes": "pyflakes"}
OPTIONAL_BIN = {"gitleaks": "gitleaks"}


def skip_reason(tool):
    if tool is None:
        return None
    if tool in OPTIONAL_MODULE:
        if importlib.util.find_spec(OPTIONAL_MODULE[tool]) is None:
            return f"{tool} not installed"
    if tool in OPTIONAL_BIN and shutil.which(OPTIONAL_BIN[tool]) is None:
        return f"{OPTIONAL_BIN[tool]} binary not on PATH"
    return None


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
    for step in STEPS:
        name, cmd = step[0], step[1]
        tool = step[2] if len(step) > 2 else None
        why = skip_reason(tool)
        if why:
            rows.append((name, None, 0.0, why))
            print(f"SKIP  {name:<24} {0.0:6.1f}s  {why}", flush=True)
            continue
        code, secs, last = run(name, cmd)
        rows.append((name, code, secs, last))
        status = "PASS" if code == 0 else "FAIL"
        print(f"{status}  {name:<24} {secs:6.1f}s  {last[:70]}", flush=True)
    ran = [r for r in rows if r[1] is not None]
    skipped = [r for r in rows if r[1] is None]
    failed = [r for r in ran if r[1] != 0]
    print(f"\nGATE: {len(ran) - len(failed)}/{len(ran)} steps passed"
          + (f"  ({len(skipped)} skipped: optional tool missing)" if skipped else "")
          + ("" if not failed else "  -> FAILED: " + ", ".join(r[0] for r in failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
