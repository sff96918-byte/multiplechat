"""EVA Bot doctor — একবার চালালে বলে দেয় কোথায় সমস্যা।

    python -m tools.doctor

Windows-এ এভাবে চালান (project folder থেকে):  python -m tools.doctor
প্রতিটা check: PASS / WARN / FAIL। কোনো FAIL থাকলে exit code 1।
Output → data/logs/doctor_report.txt (secret masked; token-এর শুধু সংখ্যা/true-false দেখায়)।
Token, cookie, password কখনো print বা লেখা হয় না।
"""
from __future__ import annotations

import importlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.diagnostics import redact, tail_crash_summary  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []   # (level, name, detail)


def rec(level: str, name: str, detail: str = "") -> None:
    RESULTS.append((level, name, redact(detail)))


def check_python() -> None:
    v = sys.version_info
    if v >= (3, 10):
        rec("PASS", "Python version", f"{v.major}.{v.minor}.{v.micro}")
    else:
        rec("FAIL", "Python version", f"{v.major}.{v.minor} — Python 3.10+ লাগবে")
    rec("PASS" if platform.system() == "Windows" else "WARN", "OS",
        f"{platform.system()} {platform.release()} (app মূলত Windows-এ চলে)")


def check_packages() -> None:
    need = {
        "PyQt6": ("FAIL", "GUI"), "aiohttp": ("FAIL", "session chat"),
        "requests": ("FAIL", "session login"), "psutil": ("WARN", "resource governor"),
        "playwright": ("WARN", "LIVE BROWSER mode"), "camoufox": ("WARN", "Camoufox mode (optional)"),
    }
    for mod, (lvl, why) in need.items():
        try:
            m = importlib.import_module(mod)
            rec("PASS", f"package {mod}", getattr(m, "__version__", "ok"))
        except Exception as e:
            rec(lvl, f"package {mod}", f"নেই ({why}): {type(e).__name__}: pip install {mod}")
    if platform.system() == "Windows":
        try:
            importlib.import_module("winsound")
            rec("PASS", "winsound", "ok")
        except Exception as e:
            rec("FAIL", "winsound", str(e))


def check_qt_display() -> None:
    try:
        from PyQt6.QtWidgets import QApplication
        del QApplication  # import is the check
        rec("PASS", "Qt widgets load", "QtWidgets import ok")
    except Exception as e:
        rec("FAIL", "Qt widgets load", f"{type(e).__name__}: {e}  (Windows-এ সাধারণত PyQt6 reinstall করলে ঠিক হয়)")


def check_files() -> None:
    critical = [
        "entry/main.py", "entry/thread_manager.py", "entry/paths.py", "entry/cli_runner.py",
        "browser/browser_automation.py", "core/config_loader.py", "core/session_chat.py",
        "core/diagnostics.py", "core/ws_transport/ws_chat_loop.py", "core/ws_transport/chitchat_api.py",
        "chat/rule_bot.py", "eva_flow.py", "data/config.json", "data/snap_ids.txt",
    ]
    missing = [f for f in critical if not (ROOT / f).exists()]
    if missing:
        rec("FAIL", "critical files", "নেই: " + ", ".join(missing))
    else:
        rec("PASS", "critical files", f"{len(critical)}/{len(critical)} আছে")
    for d in ("data/input", "data/output"):
        n = len(list((ROOT / d).rglob("*.txt"))) if (ROOT / d).is_dir() else 0
        rec("PASS" if n else "FAIL", f"{d}", f"{n} txt file")


def check_config() -> None:
    try:
        with open(ROOT / "data" / "config.json", encoding="utf-8") as fh:
            json.load(fh)
        rec("PASS", "data/config.json", "valid JSON")
    except Exception as e:
        rec("FAIL", "data/config.json", f"{type(e).__name__}: {e}")
        return
    try:
        from core.config_loader import load_chat_timing
        t = load_chat_timing()
        rec("PASS", "chat timing",
            f"New Chat Delay {t['new_chat_delay_min_seconds']:g}s, Silence timeout {t['silence_timeout_seconds']:g}s")
    except Exception as e:
        rec("FAIL", "chat timing", f"{type(e).__name__}: {e}")


def check_engine() -> None:
    try:
        from chat import ChatRuleBot
        bot = ChatRuleBot()
        st = bot.new_conversation()
        out = bot.reply("hi", st)
        pend = st.get("pending_replies") or []
        first = out or (pend[0] if pend else "")
        if first:
            rec("PASS", "reply engine", f"'hi' -> reply পেয়েছি ({len(first)} অক্ষর)")
        else:
            rec("FAIL", "reply engine", "'hi' এর কোনো reply আসেনি — data/output/greeting.txt দেখো")
    except Exception as e:
        rec("FAIL", "reply engine", f"{type(e).__name__}: {e}")


def check_sessions() -> None:
    try:
        from core.session_chat import discover_session_sources
        src = discover_session_sources()
        if src:
            rec("PASS", "session sources", f"{len(src)}টা পাওয়া গেছে (token দেখানো হয় না)")
        else:
            rec("WARN", "session sources", "কোনো account_sessions/ বা configs/session.json নেই — SESSION CHAT-এর আগে login/token দরকার")
    except Exception as e:
        rec("FAIL", "session sources", f"{type(e).__name__}: {e}")


def check_logs() -> None:
    logs = ROOT / "data" / "logs"
    try:
        logs.mkdir(parents=True, exist_ok=True)
        probe = logs / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        rec("PASS", "logs folder writable", str(logs))
    except Exception as e:
        rec("FAIL", "logs folder writable", f"{type(e).__name__}: {e}")
    crashes = tail_crash_summary()
    if crashes:
        rec("WARN", "previous crashes", f"crash.log-এ {len(crashes)}টা সাম্প্রতিক entry (নিচে)")
        for c in crashes:
            RESULTS.append(("INFO", "  crash", c))
    else:
        rec("PASS", "previous crashes", "crash.log খালি/নেই")


def main() -> int:
    for fn in (check_python, check_packages, check_qt_display, check_files,
               check_config, check_engine, check_sessions, check_logs):
        try:
            fn()
        except Exception as e:   # the doctor itself must never crash
            rec("FAIL", fn.__name__, f"doctor check crashed: {type(e).__name__}: {e}")
    lines = [f"EVA Bot doctor — {platform.system()} py{sys.version.split()[0]}", ""]
    for lvl, name, detail in RESULTS:
        lines.append(f"[{lvl:4}] {name}: {detail}" if lvl != "INFO" else f"       {name}: {detail}")
    fails = sum(1 for r in RESULTS if r[0] == "FAIL")
    warns = sum(1 for r in RESULTS if r[0] == "WARN")
    lines += ["", f"SUMMARY: {fails} FAIL, {warns} WARN"]
    text = "\n".join(lines)
    print(text)
    try:
        (ROOT / "data" / "logs").mkdir(parents=True, exist_ok=True)
        (ROOT / "data" / "logs" / "doctor_report.txt").write_text(text + "\n", encoding="utf-8")
        print("\nReport saved: data/logs/doctor_report.txt")
    except Exception:
        pass
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
