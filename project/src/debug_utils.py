# -*- coding: utf-8 -*-
"""
Debug utilities — structured logging, trace capture, state inspector.
Provides:
  - set_debug_level / get_debug_level: global runtime log level
  - DebugLogger: rotating JSON file + human console, full context
  - read_jsonl: tail a JSONL log file for tooling
  - TraceCapture: request/response ring buffer with latency stats
  - CrashTracker: per-session crash history, backoff, flapping detection
  - StateInspector: live session state, activity touch, idle detection
  - export_debug_dump: one-file JSON snapshot of all debug state
"""
import json
import logging
import os
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent

logger = logging.getLogger("debug_utils")


# ═══ Structured Debug Logger ═══

class JsonLineFormatter(logging.Formatter):
    """Write each log record as a single JSON line."""

    def format(self, record):
        obj = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "lineno": record.lineno,
        }
        if record.exc_info and record.exc_info[1]:
            obj["exc"] = traceback.format_exception_only(
                record.exc_info[0], record.exc_info[1]
            )[-1].strip()
            tb_lines = traceback.format_tb(record.exc_info[2])
            if tb_lines:
                obj["tb"] = "".join(tb_lines[-8:])
        if getattr(record, "extra_data", None):
            obj["data"] = record.extra_data
        return json.dumps(obj, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable line: 12:00:00 [INFO ] debug.joingy msg k=v ..."""

    def format(self, record):
        ts = datetime.now().strftime("%H:%M:%S")
        parts = [f"{ts} [{record.levelname:<7}] {record.name}: {record.getMessage()}"]
        extra = getattr(record, "extra_data", None)
        if extra:
            for k, v in list(extra.items())[:6]:
                parts.append(f"{k}={v}")
            if len(extra) > 6:
                parts.append(f"+{len(extra) - 6} more")
        if record.exc_info and record.exc_info[1]:
            parts.append(traceback.format_exception_only(
                record.exc_info[0], record.exc_info[1])[-1].strip())
        return " ".join(parts)


class DebugLogger:
    """
    Per-module debug logger that writes to both console AND rotating JSON file.

    Usage:
        dlog = DebugLogger("joingy", Path("logs"))
        dlog.info("connected", extra={"uid": "abc123"})
        dlog.error("timeout", exc=e, extra={"session": "s1"})
    """

    def __init__(self, name: str, log_dir: Optional[Path] = None,
                 console: bool = True):
        self.name = name
        self.log_dir = Path(log_dir) if log_dir else HERE / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.log_dir / f"{name}.jsonl"
        self._logger = logging.getLogger(f"debug.{name}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        if not self._logger.handlers:
            json_handler = RotatingFileHandler(
                self.path,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            json_handler.setLevel(get_debug_level())
            json_handler.setFormatter(JsonLineFormatter())
            self._logger.addHandler(json_handler)
            self._file_handler = json_handler

            if console:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(get_debug_level())
                console_handler.setFormatter(ConsoleFormatter())
                self._logger.addHandler(console_handler)
                self._console_handler = console_handler

    @property
    def level(self) -> int:
        return getattr(self._file_handler, "level", logging.INFO)

    def change_level(self, level) -> int:
        """Set this logger's file + console level. Returns numeric level."""
        num = _level_value(level)
        self._file_handler.setLevel(num)
        if getattr(self, "_console_handler", None):
            self._console_handler.setLevel(num)
        return num

    def _log(self, level: int, msg: str, exc: Optional[Exception] = None, **kwargs):
        extra = kwargs
        if exc:
            extra["exc_type"] = type(exc).__name__
            extra["exc_msg"] = str(exc)[:500]
            if "tb" not in extra:
                extra["tb"] = "".join(
                    traceback.format_tb(exc.__traceback__)[-5:]
                )
        record = self._logger.makeRecord(
            self._logger.name, level, "(unknown)", 0, msg, None,
            (type(exc), exc, exc.__traceback__) if exc else None
        )
        record.extra_data = extra if extra else None
        self._logger.handle(record)

    def debug(self, msg, **kwargs):
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg, **kwargs):
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg, **kwargs):
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg, exc=None, **kwargs):
        self._log(logging.ERROR, msg, exc=exc, **kwargs)

    def critical(self, msg, exc=None, **kwargs):
        self._log(logging.CRITICAL, msg, exc=exc, **kwargs)

    def trace(self, msg, **kwargs):
        """Always-log trace point for critical paths."""
        self._log(logging.INFO, f"[TRACE] {msg}", **kwargs)


# ═══ Global debug level ═══

DEBUG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}

_debug_level = DEBUG_LEVELS.get(
    os.environ.get("BOT_DEBUG_LEVEL", "INFO").strip().upper(), logging.INFO
)
if _debug_level not in DEBUG_LEVELS.values():
    _debug_level = logging.INFO


def _level_value(level) -> int:
    if isinstance(level, int):
        return level
    name = str(level).strip().upper()
    if name in DEBUG_LEVELS:
        return DEBUG_LEVELS[name]
    try:
        return int(name)
    except ValueError:
        return logging.INFO


def get_debug_level() -> int:
    return _debug_level


def set_debug_level(level) -> int:
    """Set global debug level for all DebugLoggers (runtime). Returns int."""
    global _debug_level
    _debug_level = _level_value(level)
    for name, lg in logging.Logger.manager.loggerDict.items():
        if name.startswith("debug.") and isinstance(lg, logging.Logger):
            for h in lg.handlers:
                if isinstance(h, (RotatingFileHandler, logging.StreamHandler)):
                    h.setLevel(_debug_level)
    return _debug_level


def read_jsonl(path, tail: int = 200, max_bytes: int = 512 * 1024) -> list[dict]:
    """Read the last `tail` JSON objects from a .jsonl file (safe on big files)."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        size = p.stat().st_size
        with open(p, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()  # discard partial line
            raw = f.read().decode("utf-8", errors="replace")
    except Exception:
        return []
    out = []
    for line in raw.splitlines()[-tail:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


# ═══ Trace Capture (ring buffer) ═══

@dataclass
class TraceEntry:
    ts: float
    site: str
    session_id: str
    direction: str
    endpoint: str
    status: int
    latency_ms: float
    data_preview: str
    error: str = ""


class TraceCapture:
    """Ring buffer for HTTP/WS request-response pairs."""

    def __init__(self, max_entries: int = 500):
        self._buffer: deque[TraceEntry] = deque(maxlen=max_entries)

    def record(self, site: str, session_id: str, direction: str,
               endpoint: str, status: int, latency_ms: float,
               data_preview: str = "", error: str = ""):
        entry = TraceEntry(
            ts=time.time(),
            site=site,
            session_id=session_id,
            direction=direction,
            endpoint=endpoint,
            status=status,
            latency_ms=round(latency_ms, 1),
            data_preview=str(data_preview)[:200],
            error=str(error)[:500],
        )
        self._buffer.append(entry)

    def get_recent(self, site: Optional[str] = None, limit: int = 50,
                 session_id: Optional[str] = None,
                 direction: Optional[str] = None) -> list[dict]:
        entries = list(self._buffer)
        if site:
            entries = [e for e in entries if e.site == site]
        if session_id:
            entries = [e for e in entries if e.session_id == session_id]
        if direction:
            entries = [e for e in entries if e.direction == direction]
        result = []
        for e in list(entries)[-limit:]:
            result.append({
                "ts": _ts(e.ts),
                "site": e.site,
                "session": e.session_id,
                "dir": e.direction,
                "endpoint": e.endpoint,
                "status": e.status,
                "latency_ms": e.latency_ms,
                "data": e.data_preview,
                "error": e.error,
            })
        return result

    def session(self, site: str, session_id: str, limit: int = 50) -> list[dict]:
        """Full trace for one session (newest last)."""
        return self.get_recent(site=site, session_id=session_id, limit=limit)

    def errors_only(self, site: Optional[str] = None, limit: int = 50) -> list[dict]:
        entries = [e for e in self._buffer if e.status >= 400 or e.error]
        if site:
            entries = [e for e in entries if e.site == site]
        result = []
        for e in list(entries)[-limit:]:
            result.append({
                "ts": _ts(e.ts),
                "site": e.site,
                "session": e.session_id,
                "dir": e.direction,
                "endpoint": e.endpoint,
                "status": e.status,
                "error": e.error or f"HTTP {e.status}",
            })
        return result

    def clear(self):
        self._buffer.clear()

    def total(self) -> int:
        return len(self._buffer)

    def total_errors(self) -> int:
        return sum(1 for e in self._buffer if e.status >= 400 or e.error)

    def stats(self) -> dict:
        """Traffic + latency stats overall and per site."""
        total = len(self._buffer)
        errs = self.total_errors()
        lats = sorted(e.latency_ms for e in self._buffer)
        by_site: dict[str, dict] = {}
        for e in self._buffer:
            s = by_site.setdefault(e.site, {"requests": 0, "errors": 0, "_lats": []})
            s["requests"] += 1
            if e.status >= 400 or e.error:
                s["errors"] += 1
            s["_lats"].append(e.latency_ms)
        for s in by_site.values():
            l = sorted(s.pop("_lats"))
            s["error_rate"] = round(100 * s["errors"] / s["requests"], 1) if s["requests"] else 0
            s["latency_avg_ms"] = round(sum(l) / len(l), 1) if l else 0
            s["latency_p95_ms"] = l[int(len(l) * 0.95) - 1] if l else 0
        return {
            "total_requests": total,
            "total_errors": errs,
            "error_rate": round(100 * errs / total, 1) if total else 0,
            "latency_avg_ms": round(sum(lats) / len(lats), 1) if lats else 0,
            "latency_p50_ms": lats[len(lats) // 2] if lats else 0,
            "latency_p95_ms": lats[int(len(lats) * 0.95) - 1] if lats else 0,
            "by_site": by_site,
        }


# ═══ Crash Record ═══

@dataclass
class SessionCrash:
    site: str
    session_id: str
    exc_type: str
    exc_msg: str
    tb_preview: str
    ts: float = field(default_factory=time.time)
    recover_attempts: int = 0
    last_recover_ts: float = 0.0


class CrashTracker:
    """Track per-session crashes for recovery heuristics."""

    def __init__(self, max_history: int = 200):
        self._crashes: deque[SessionCrash] = deque(maxlen=max_history)
        self._lock = __import__("asyncio").Lock()

    async def record(self, site: str, session_id: str, exc: Exception):
        async with self._lock:
            tb_lines = traceback.format_tb(exc.__traceback__)
            crash = SessionCrash(
                site=site,
                session_id=session_id,
                exc_type=type(exc).__name__,
                exc_msg=str(exc)[:500],
                tb_preview="".join(tb_lines[-3:]),
            )
            self._crashes.append(crash)

    async def can_retry(self, site: str, session_id: str) -> tuple[bool, float]:
        """Return (should_retry, backoff_seconds)."""
        from itertools import islice
        async with self._lock:
            recent = [c for c in self._crashes
                      if c.site == site and c.session_id == session_id]
            if not recent:
                return True, 0.0
            latest = recent[-1]
            attempts = len(recent)
            backoff = min(2 ** attempts, 120)
            if time.time() - latest.ts < backoff:
                return False, backoff - (time.time() - latest.ts)
            return True, 0.0

    def get_recent(self, limit: int = 50, site: Optional[str] = None,
                 since: float = 0.0) -> list[dict]:
        result = []
        for c in list(self._crashes)[-limit:]:
            if site and c.site != site:
                continue
            if since and c.ts < since:
                continue
            result.append({
                "ts": _ts(c.ts),
                "site": c.site,
                "session": c.session_id,
                "exc": c.exc_type,
                "msg": c.exc_msg[:150],
                "attempts": c.recover_attempts,
            })
        return result

    def clear(self, site: Optional[str] = None):
        """Clear crash history (optionally for one site only)."""
        if site is None:
            self._crashes.clear()
        else:
            self._crashes = deque(
                (c for c in self._crashes if c.site != site),
                maxlen=self._crashes.maxlen,
            )

    def reset(self, site: str, session_id: str):
        """Forget crash history for a recovered session."""
        self._crashes = deque(
            (c for c in self._crashes
             if not (c.site == site and c.session_id == session_id)),
            maxlen=self._crashes.maxlen,
        )

    def crash_count_window(self, site: str, session_id: str,
                           window_sec: float = 300) -> int:
        """Crashes for one session in the last `window_sec` seconds."""
        cutoff = time.time() - window_sec
        return sum(1 for c in self._crashes
                   if c.site == site and c.session_id == session_id and c.ts >= cutoff)

    def flapping(self, threshold: int = 5, window_sec: float = 300) -> list[dict]:
        """Sessions that crashed >= threshold times in the window (worst first)."""
        seen: dict[tuple, int] = {}
        for c in self._crashes:
            key = (c.site, c.session_id)
            if c.ts >= time.time() - window_sec:
                seen[key] = seen.get(key, 0) + 1
        return [{"site": s, "session": sid, "crashes": n}
                for (s, sid), n in sorted(seen.items(), key=lambda kv: -kv[1])
                if n >= threshold]

    def stats(self) -> dict:
        total = len(self._crashes)
        by_site = {}
        by_exc = {}
        for c in self._crashes:
            by_site[c.site] = by_site.get(c.site, 0) + 1
            by_exc[c.exc_type] = by_exc.get(c.exc_type, 0) + 1
        return {
            "total": total,
            "by_site": by_site,
            "by_exception": by_exc,
            "flapping": self.flapping(),
        }


# ═══ State Inspector ═══

class StateInspector:
    """
    Queryable snapshot of all session states.
    Updated by bots on state changes.
    """

    def __init__(self):
        self._states: dict[str, dict] = {}
        self._lock = __import__("asyncio").Lock()

    async def update(self, site: str, session_id: str, state: dict):
        async with self._lock:
            key = f"{site}:{session_id}"
            merged = {**state}
            merged["site"] = site
            merged["session_id"] = session_id
            merged["state"] = state.get("state", "unknown")
            merged["messages_sent"] = state.get("sent", 0)
            merged["messages_received"] = state.get("recv", 0)
            merged["last_activity"] = time.time()
            self._states[key] = merged

    async def touch(self, site: str, session_id: str):
        """Bump last_activity only — call on every message in/out."""
        async with self._lock:
            entry = self._states.get(f"{site}:{session_id}")
            if entry is not None:
                entry["last_activity"] = time.time()

    async def remove(self, site: str, session_id: str):
        async with self._lock:
            self._states.pop(f"{site}:{session_id}", None)

    def snapshot(self, site: Optional[str] = None) -> list[dict]:
        states = list(self._states.values())
        if site:
            states = [s for s in states if s["site"] == site]
        return sorted(states, key=lambda s: s.get("last_activity", 0), reverse=True)

    def dead_sessions(self, idle_timeout_sec: float = 120) -> list[dict]:
        cutoff = time.time() - idle_timeout_sec
        return [s for s in self._states.values()
                if s.get("last_activity", 0) < cutoff]

    def stats(self, idle_timeout_sec: float = 120) -> dict:
        states = list(self._states.values())
        by_site: dict[str, int] = {}
        for s in states:
            by_site[s.get("site", "?")] = by_site.get(s.get("site", "?"), 0) + 1
        return {
            "total": len(states),
            "by_site": by_site,
            "idle": len(self.dead_sessions(idle_timeout_sec)),
            "total_sent": sum(int(s.get("messages_sent", 0) or 0) for s in states),
            "total_recv": sum(int(s.get("messages_received", 0) or 0) for s in states),
        }


# ═══ Helpers ═══

def _ts(ts_val):
    try:
        return datetime.fromtimestamp(float(ts_val)).strftime("%H:%M:%S")
    except Exception:
        return "-"


# ═══ Global instances ═══

_trace_capture: Optional[TraceCapture] = None
_crash_tracker: Optional[CrashTracker] = None
_state_inspector: Optional[StateInspector] = None


def get_trace_capture() -> TraceCapture:
    global _trace_capture
    if _trace_capture is None:
        _trace_capture = TraceCapture()
    return _trace_capture


def get_crash_tracker() -> CrashTracker:
    global _crash_tracker
    if _crash_tracker is None:
        _crash_tracker = CrashTracker()
    return _crash_tracker


def get_state_inspector() -> StateInspector:
    global _state_inspector
    if _state_inspector is None:
        _state_inspector = StateInspector()
    return _state_inspector


def export_debug_dump(path: Optional[Path] = None,
                      proxy_stats: Optional[dict] = None,
                      log_tail: int = 200) -> Path:
    """
    Snapshot all debug state to one JSON file (default: logs/debug_dump_<ts>.json).
    Includes: crash history, trace entries, session states, log file tails.
    """
    dump_path = Path(path) if path else (HERE / "logs") / f"debug_dump_{int(time.time())}.json"
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    ct = get_crash_tracker()
    tc = get_trace_capture()
    insp = get_state_inspector()
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "debug_level": logging.getLevelName(get_debug_level()),
        "sessions": {
            "stats": insp.stats(),
            "entries": insp.snapshot(),
        },
        "crashes": {
            "stats": ct.stats(),
            "recent": ct.get_recent(limit=100),
        },
        "trace": {
            "stats": tc.stats(),
            "errors": tc.errors_only(limit=100),
        },
        "proxy": proxy_stats or {},
        "logs": {},
    }
    log_dir = HERE / "logs"
    if log_dir.exists():
        for f in sorted(log_dir.glob("*.jsonl")):
            data["logs"][f.name] = read_jsonl(f, tail=log_tail)
    with open(dump_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return dump_path
