"""Diagnostics helpers: crash log + secret redaction (v21 debug pass).

* ``install_excepthooks()`` — main thread AND worker threads: any uncaught
  exception is written (with traceback, redacted) to ``data/logs/crash.log``.
  Windowless (pythonw) runs have no console, so this file is the only trace.
* ``redact()`` — masks JWTs, e-mails, bearer tokens and ``token=/password=/cookie=``
  values. Every diagnostic output must pass through it.

Never raises: diagnostics must not break the app they are meant to debug.
"""
from __future__ import annotations

import datetime as _dt
import platform
import re
import sys
import threading
import traceback
from pathlib import Path

_LOG_NAME = "crash.log"
_MAX_BYTES = 2 * 1024 * 1024          # rotate crash.log above 2 MB (bounded)

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")
_KV_RE = re.compile(
    r"(?i)((?:token|password|passwd|secret|cookie|authorization|api[_-]?key|session)"
    r"[\"']?\s*[:=]\s*[\"']?)([^\s\"',;&}]+)")


def redact(text: str) -> str:
    """Mask secrets in *text*. Safe to call on any string."""
    try:
        text = _JWT_RE.sub("<JWT>", text)
        text = _BEARER_RE.sub(r"\1<redacted>", text)
        text = _KV_RE.sub(r"\1<redacted>", text)
        text = _EMAIL_RE.sub("<email>", text)
    except Exception:
        return "<redaction failed: output suppressed>"
    return text


def _logs_dir() -> Path:
    from entry.paths import data_dir
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_crash(where: str, exc_type, exc, tb) -> None:
    """Append one redacted crash record to data/logs/crash.log (never raises)."""
    try:
        path = _logs_dir() / _LOG_NAME
        if path.exists() and path.stat().st_size > _MAX_BYTES:
            path.replace(path.with_suffix(".log.1"))   # keep one old copy only
        body = "".join(traceback.format_exception(exc_type, exc, tb))
        head = (f"\n===== {_dt.datetime.now().isoformat(timespec='seconds')} | {where} | "
                f"py {sys.version.split()[0]} | {platform.system()} {platform.release()} =====\n")
        with path.open("a", encoding="utf-8", errors="replace") as fh:
            fh.write(redact(head + body))
    except Exception:
        pass


def install_excepthooks() -> None:
    """Route uncaught exceptions (main + worker threads) to crash.log."""
    prev_sys = sys.excepthook

    def _sys_hook(exc_type, exc, tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            write_crash("main-thread", exc_type, exc, tb)
        prev_sys(exc_type, exc, tb)

    def _thread_hook(args):
        if args.exc_type is not SystemExit:
            write_crash(f"thread:{getattr(args.thread, 'name', '?')}",
                        args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook


def tail_crash_summary(max_entries: int = 5) -> list[str]:
    """Return the header lines of the most recent crash entries (redacted)."""
    try:
        path = _logs_dir() / _LOG_NAME
        if not path.exists():
            return []
        heads = [ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
                 if ln.startswith("===== ")]
        return [redact(h) for h in heads[-max_entries:]]
    except Exception:
        return []
