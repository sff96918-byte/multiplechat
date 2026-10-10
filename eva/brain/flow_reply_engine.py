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
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import eva_flow

log = logging.getLogger("eva.flow_engine")


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


class FlowReplyEngine:
    """Drop-in replacement for the simple template ReplyEngine."""

    name = "flow"

    def __init__(self, root: Optional[Path] = None,
                 snap_usernames: Optional[List[str]] = None) -> None:
        root = Path(root) if root else Path(__file__).resolve().parent
        write_snap_ids(root / "data", snap_usernames or [])
        self.bot = eva_flow.EvaFlowBot(root=str(root))
        self._states: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------ API used by WsChatLoop

    def opener(self, partner: dict) -> str:
        state = self._state_for(partner)
        reply = self.bot.reply("hi", state)  # force the greeting pool
        log.debug("opener via %s (%s)", self.bot.last_file, self.bot.last_reason)
        return reply

    def reply(self, partner: dict, incoming: str,
              history: Optional[List[dict]] = None) -> str:
        pid = (partner or {}).get("id", "?")
        state = self._states.get(pid) or self._state_for(partner)
        reply = self.bot.reply(incoming or "hi", state)
        log.debug("flow %r -> %r | stage=%s", (incoming or "")[:40],
                  (reply or "")[:60], state.get("stage"))
        return reply

    def farewell(self, partner: dict) -> str:
        return "nice talking! take care"

    def forget(self, partner_id: str) -> None:
        self._states.pop(partner_id, None)

    def delay_for(self, incoming: str) -> float:
        """Human timing from the user's config.json ranges:
        reaction pause 0.5-1.2s + read reply 1-3s + typing at 6-12 cps."""
        cps = random.uniform(6.0, 12.0)
        pause = random.uniform(0.5, 1.2)
        read = random.uniform(1.0, 3.0)
        return round(pause + read + min(len(incoming or "hi") / cps, 12.0), 2)

    # ------------------------------------------------------------ GUI info

    def stage(self, partner_id: str) -> str:
        st = self._states.get(partner_id)
        return (st or {}).get("stage", "NEW")

    def last_reason(self) -> str:
        return getattr(self.bot, "last_reason", "")

    def last_file(self) -> str:
        return getattr(self.bot, "last_file", "")

    # ------------------------------------------------------------ internals

    def _state_for(self, partner: dict) -> Dict[str, Any]:
        pid = (partner or {}).get("id") or "?"
        if pid not in self._states:
            self._states[pid] = self.bot.new_conversation()
        return self._states[pid]
