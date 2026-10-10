"""Debug toolkit — ফাইল-লগ, গোপন তথ্য মাস্কিং, আর এক-ক্লিক debug report।

কী পাওয়া যায়:
  * setup_debug_logging(debug)  — logs/eva.log-এ সবসময় DEBUG trail লেখা হয়
                                  (1MB × 5 backup); debug=True হলে console/GUI-ও verbose
  * mask_secrets(obj)           — token/cookie/password মান মুছে দেয় (report-এ যায় না)
  * export_debug_report(...)    — logs/debug_report_<time>.txt: config (masked) +
                                  session status (শুধু boolean) + bot stats + শেষ 300
                                  WS frame + engine decisions + শেষ log lines
                                  → এই একটা ফাইল শেয়ার করলেই debugging সহজ
"""

from __future__ import annotations

import json
import logging
import platform
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .paths import project_root

ROOT = project_root()
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "eva.log"

SECRET_KEY_HINTS = ("token", "cookie", "password", "authorization", "secret", "session_key")
MASK = "…MASKED"


def setup_debug_logging(debug: bool = False) -> Path:
    """ফাইল-লগ সবসময় চালু (DEBUG level)। debug=True হলে eva logger-ই DEBUG হয়,
    ফলে console/GUI তেও সব বিস্তারিত আসে। Idempotent — বারবার ডাকলে duplicate হয় না।"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("eva")
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5,
                                 encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s",
            datefmt="%H:%M:%S"))
        root.addHandler(fh)
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    return LOG_FILE


def mask_secrets(obj: Any) -> Any:
    """Recursive — key-তে token/cookie/password/secret/authorization থাকলে মান মাস্ক।"""
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            if any(h in str(k).lower() for h in SECRET_KEY_HINTS):
                s = str(v)
                out[k] = (s[:4] + MASK) if len(s) > 4 else MASK
            else:
                out[k] = mask_secrets(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [mask_secrets(x) for x in obj]
    return obj


def _fmt_frames(frames: Iterable[dict]) -> List[str]:
    lines = []
    for f in frames:
        lines.append(f"{f.get('t','?')} {f.get('dir','?'):>3} len={f.get('len',0)} "
                     f"{f.get('preview','')}")
    return lines


def export_debug_report(out_dir: Optional[Path] = None, *,
                        config: Optional[dict] = None,
                        session_path: Optional[Path] = None,
                        stats: Optional[dict] = None,
                        socket: Any = None,
                        api: Any = None,
                        engines: Iterable[Any] = (),
                        log_tail: Iterable[str] = ()) -> Path:
    """সব diagnostic এক টেক্সট ফাইলে। session.json-এর CONTENT কখনো যায় না —
    শুধু আছে কিনা (boolean)। ফাইল শেয়ার করা safe (secrets masked)।"""
    out_dir = Path(out_dir) if out_dir else LOG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"debug_report_{ts}.txt"

    L: List[str] = []
    L.append("=" * 70)
    L.append(f"EVA BOT DEBUG REPORT  —  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    L.append("=" * 70)
    L.append(f"python   : {sys.version.split()[0]} ({platform.platform()})")
    L.append(f"root     : {ROOT}")
    L.append(f"log file : {LOG_FILE}")

    L.append("\n" + "-" * 70 + "\nCONFIG (secrets masked)")
    L.append("-" * 70)
    L.append(json.dumps(mask_secrets(config or {}), indent=2, ensure_ascii=False))

    L.append("\n" + "-" * 70 + "\nSESSION (শুধু status — content কখনোই এখানে আসে না)")
    L.append("-" * 70)
    if session_path is not None:
        sp = Path(session_path)
        exists = sp.exists()
        L.append(f"exists={exists} path={sp.name}")
        if exists:
            try:
                data = json.loads(sp.read_text(encoding="utf-8"))
                cks = data.get("cookies") or {}
                L.append(f"has_token={'token' in cks} "
                         f"cookie_names={sorted(cks.keys())} "
                         f"has_user_agent={bool(data.get('user_agent'))}")
            except Exception as exc:  # noqa: BLE001
                L.append(f"(unreadable: {type(exc).__name__})")
    else:
        L.append("session path দেওয়া হয়নি")

    if stats:
        L.append("\n" + "-" * 70 + "\nBOT STATS")
        L.append("-" * 70)
        L.append(json.dumps(stats, indent=2, ensure_ascii=False, default=str))

    if socket is not None and hasattr(socket, "recent_frames"):
        L.append("\n" + "-" * 70 + "\nWS RECENT FRAMES (শেষ 300, preview 180 chars)")
        L.append("-" * 70)
        frames = socket.recent_frames()
        L.extend(_fmt_frames(frames) or ["(কোনো frame নেই — বট চালু হয়নি)"])

    if api is not None and hasattr(api, "recent_requests"):
        L.append("\n" + "-" * 70 + "\nAPI RECENT REQUESTS (শেষ 200)")
        L.append("-" * 70)
        for r in api.recent_requests():
            L.append(f"{r.get('t','?')} {r.get('req','?')} -> {r.get('status')} "
                     f"{r.get('ms')}ms {r.get('bytes')}B")

    for eng in engines:
        if eng is None or not hasattr(eng, "decisions"):
            continue
        L.append("\n" + "-" * 70 + f"\nENGINE DECISIONS — {getattr(eng, 'name', type(eng).__name__)}")
        L.append("-" * 70)
        decs = eng.decisions()
        if not decs:
            L.append("(এখনো কোনো decision নেই)")
        for d in decs:
            L.append(f"{d.get('t','?')} [{d.get('stage', d.get('line', '?'))}] "
                     f"reason={d.get('reason','')} "
                     f"in={d.get('in','')!r} -> out={d.get('out','')!r}")

    tail = [l for l in log_tail if l]
    if tail:
        L.append("\n" + "-" * 70 + "\nLOG TAIL (শেষ 400 লাইন)")
        L.append("-" * 70)
        L.extend(tail[-400:])

    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path
