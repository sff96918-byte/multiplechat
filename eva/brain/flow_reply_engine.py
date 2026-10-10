"""FlowReplyEngine — adapter that plugs the legacy EVA flow engine
(eva_flow.py + data/input|output txt banks, from the user's original project)
into the capture-backed WS chat loop.

The flow engine is the user's own funnel:
    greeting -> age/gender -> country -> flirty -> share snap -> END
fully customizable by editing txt files — no code.

Also exposed for the GUI: per-partner stage + last routing reason.
"""

from __future__ import annotations

import logging
import random
from collections import deque
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import eva_flow

log = logging.getLogger("eva.flow_engine")


def resolve_snap_usernames(cfg: dict) -> List[str]:
    """Config theke snap username list ber kore.

    Priority: cfg["snap_file"] (txt, prottek line e ekta username, '#'=comment)
              > cfg["snap_usernames"] (comma list).
    File na thakle/empty hole comma list fallback.
    """
    from ..paths import project_root
    f = (cfg.get("snap_file") or "").strip()
    if f:
        p = Path(f)
        if not p.is_absolute():
            p = project_root() / p
        if p.exists():
            names = [l.strip() for l in p.read_text(encoding="utf-8").splitlines()
                     if l.strip() and not l.strip().startswith("#")]
            if names:
                return names
    return [s.strip() for s in (cfg.get("snap_usernames") or []) if s and s.strip()]


def write_snap_ids(data_dir: Path, snap_usernames: List[str]) -> None:
    """Refresh data/snap_ids.txt (round-robin pool used by %username%)."""
    names = [s.strip() for s in (snap_usernames or []) if s and s.strip()]
    if not names:
        return
    (data_dir / "snap_ids.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
    idx = data_dir / ".snap_ids.idx"
    try:
        idx.unlink()
    except OSError:
        pass


# ইউজারের পুরনো প্রজেক্টের data/config.json থেকে নেওয়া ডিফল্ট (human behavior)
DEFAULT_TIMING = {
    "reaction_pause_s": [0.5, 1.2],    # message দেখে react করার আগে
    "typing_speed_cps": [6.0, 12.0],   # typing speed (chars/sec)
    "read_reply_s": [1.0, 3.0],        # reply পড়তে সময়
    "micro_idle_chance": 0.25,         # মাঝে মাঝে ছোট থামা (মানুষের মতো)
    "micro_idle_s": [0.5, 2.0],
    "new_chat_delay_s": [3.0, 6.0],    # নতুন match-এ opener-এর আগে
}


class FlowReplyEngine:
    """Drop-in replacement for the simple template ReplyEngine."""

    name = "flow"

    def __init__(self, root: Optional[Path] = None,
                 snap_usernames: Optional[List[str]] = None,
                 timing: Optional[Dict[str, Any]] = None) -> None:
        root = Path(root) if root else Path(__file__).resolve().parent
        write_snap_ids(root / "data", snap_usernames or [])
        self.bot = eva_flow.EvaFlowBot(root=str(root))
        self._states: Dict[str, Dict[str, Any]] = {}
        self._decisions: deque = deque(maxlen=200)   # debug ring buffer
        self.timing: Dict[str, Any] = dict(DEFAULT_TIMING)
        if timing:
            self.timing.update(timing)

    # ------------------------------------------------------------ API used by WsChatLoop

    def opener(self, partner: dict) -> str:
        state = self._state_for(partner)
        reply = self.bot.reply("hi", state)  # force the greeting pool
        self._decisions.append({
            "t": time.strftime("%H:%M:%S"),
            "partner": (partner or {}).get("id", "?"),
            "stage": state.get("stage", "?"), "reason": self.last_reason(),
            "in": "hi", "out": (reply or "")[:60],
        })
        log.debug("opener via %s (%s)", self.bot.last_file, self.bot.last_reason)
        return reply

    def reply(self, partner: dict, incoming: str,
              history: Optional[List[dict]] = None) -> str:
        pid = (partner or {}).get("id", "?")
        state = self._states.get(pid) or self._state_for(partner)
        reply = self.bot.reply(incoming or "hi", state)
        self._decisions.append({
            "t": time.strftime("%H:%M:%S"), "partner": pid,
            "stage": state.get("stage", "?"), "reason": self.last_reason(),
            "in": (incoming or "")[:60], "out": (reply or "")[:60],
        })
        log.debug("flow %r -> %r | stage=%s reason=%s", (incoming or "")[:40],
                  (reply or "")[:60], state.get("stage"), self.last_reason())
        return reply

    def farewell(self, partner: dict) -> str:
        return "nice talking! take care"

    def forget(self, partner_id: str) -> None:
        self._states.pop(partner_id, None)

    def delay_for(self, incoming: str) -> float:
        """Human timing: reaction pause + read + typing@cps, মাঝে মাঝে micro idle.
        সব range config-এর `timing` section থেকে (ইউজারের পুরনো মান ডিফল্ট)।"""
        t = self.timing
        cps = random.uniform(*t["typing_speed_cps"])
        pause = random.uniform(*t["reaction_pause_s"])
        read = random.uniform(*t["read_reply_s"])
        total = pause + read + min(len(incoming or "hi") / max(cps, 1.0), 12.0)
        if random.random() < float(t.get("micro_idle_chance", 0.25)):
            total += random.uniform(*t["micro_idle_s"])
        return round(total, 2)

    def opener_delay(self) -> float:
        """নতুন match-এ opener পাঠানোর আগে (config: timing.new_chat_delay_s)।"""
        return round(random.uniform(*self.timing.get("new_chat_delay_s", [3.0, 6.0])), 2)

    # ------------------------------------------------------------ GUI info

    def stage(self, partner_id: str) -> str:
        st = self._states.get(partner_id)
        return (st or {}).get("stage", "NEW")

    def last_reason(self) -> str:
        return getattr(self.bot, "last_reason", "")

    def decisions(self) -> List[dict]:
        """Debug ring buffer — প্রতিটা SMS-এ কী match হলো কী উত্তর গেল।"""
        return list(self._decisions)

    def last_file(self) -> str:
        return getattr(self.bot, "last_file", "")

    # ------------------------------------------------------------ internals

    def _state_for(self, partner: dict) -> Dict[str, Any]:
        pid = (partner or {}).get("id") or "?"
        if pid not in self._states:
            self._states[pid] = self.bot.new_conversation()
        return self._states[pid]
