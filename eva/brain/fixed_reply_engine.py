"""FixedReplyEngine — একটা fixed txt ফাইল থেকে line-by-line reply (ইউজারের
পুরনো Fixed SMS মোডের মতো)।

নিয়ম:
  * ফাইলের প্রতিটা non-empty line = একটা reply (আগে-পরে ক্রম অনুযায়ী)
  * `#` দিয়ে শুরু হলে comment — skip
  * প্রতি partner-এর নিজস্ব pointer: opener = ১ম line, প্রতিটা partner SMS-এ পরের line
  * line শেষ হয়ে গেলে reply "" দেয় → chat loop match skip করে (script ফুরানো = next)
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..paths import project_root
from .flow_reply_engine import DEFAULT_TIMING

DEFAULT_SCRIPT = project_root() / "configs" / "fixed_script.txt"


class FixedReplyEngine:
    name = "fixed"

    def __init__(self, script_path: Optional[Path] = None,
                 timing: Optional[Dict[str, Any]] = None) -> None:
        path = Path(script_path) if script_path else DEFAULT_SCRIPT
        if not path.is_absolute():
            path = project_root() / path
        self.script_path = path

        if not path.exists():
            raise RuntimeError(
                f"Fixed script ফাইল নেই: {path}\n"
                f"  (configs/fixed_script.txt বানাও — প্রতি লাইনে একটা reply, '#' = comment)")
        self.lines: List[str] = [
            l.strip() for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        if not self.lines:
            raise RuntimeError(f"Fixed script খালি: {path}")

        self._idx: Dict[str, int] = {}
        self.timing: Dict[str, Any] = dict(DEFAULT_TIMING)
        if timing:
            self.timing.update(timing)

    # ------------------------------------------------ API used by WsChatLoop

    def opener(self, partner: dict) -> str:
        return self._next((partner or {}).get("id"))

    def reply(self, partner: dict, incoming: str,
              history: Optional[List[dict]] = None) -> str:
        return self._next((partner or {}).get("id"))

    def forget(self, partner_id: str) -> None:
        self._idx.pop(partner_id, None)

    def delay_for(self, incoming: str) -> float:
        t = self.timing
        cps = random.uniform(*t["typing_speed_cps"])
        pause = random.uniform(*t["reaction_pause_s"])
        read = random.uniform(*t["read_reply_s"])
        total = pause + read + min(len(incoming or "hi") / max(cps, 1.0), 12.0)
        if random.random() < float(t.get("micro_idle_chance", 0.25)):
            total += random.uniform(*t["micro_idle_s"])
        return round(total, 2)

    def opener_delay(self) -> float:
        return round(random.uniform(*self.timing.get("new_chat_delay_s", [3.0, 6.0])), 2)

    # ---------------------------------------------------------------- status

    def finished(self, partner_id: str) -> bool:
        return self._idx.get(partner_id, 0) >= len(self.lines)

    def remaining(self, partner_id: str) -> int:
        return max(0, len(self.lines) - self._idx.get(partner_id, 0))

    # -------------------------------------------------------------- internals

    def _next(self, pid: Optional[str]) -> str:
        pid = pid or "?"
        i = self._idx.get(pid, 0)
        self._idx[pid] = i + 1
        if i >= len(self.lines):
            return ""          # script ফুরানো → loop match skip করবে
        return self.lines[i]
