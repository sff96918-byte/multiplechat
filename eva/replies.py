"""Pluggable reply engine for the chitchat WS bot.

Default: persona-driven template engine (no LLM, no external deps) with a
light greeting → age/gender → chat flow, human-like delays.

Integration: subclass ReplyEngine and pass to WsChatLoop (hook_reply_engine
in config) — the loop only calls `reply(partner, history, incoming) -> str`.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Persona:
    name: str = "Alex"
    age: int = 24
    gender: str = "m"          # what we answer when asked m/f
    country: str = "Germany"
    interests: List[str] = field(default_factory=lambda: ["music", "games", "movies"])


DEFAULT_PERSONA = Persona()


class ReplyEngine:
    """Template + state machine. Deterministic-safe, fully offline."""

    def __init__(self, persona: Optional[Persona] = None, config: Optional[dict] = None) -> None:
        self.persona = persona or DEFAULT_PERSONA
        cfg = config or {}
        self.greetings: List[str] = cfg.get("greetings", [
            "hey {name} :)", "hi! how's it going?", "hey there", "hii",
        ])
        self.gender_answers: List[str] = cfg.get("gender_answers", [
            "{gender}", "{gender} u?", "{gender}, you?",
        ])
        self.age_answers: List[str] = cfg.get("age_answers", [
            "{age}", "{age} u?", "{age}, you?",
        ])
        self.smalltalk: List[str] = cfg.get("smalltalk", [
            "nice :) what's up?", "haha true", "oh cool, tell me more",
            "same here tbh", "what do you do for fun?", "sounds fun",
            "hbu?", "lol yeah", "interesting.. go on",
        ])
        self.interest_questions: List[str] = cfg.get("interest_questions", [
            "so what are you into?", "any hobbies?", "music taste? :)",
        ])
        self.bye: List[str] = cfg.get("bye", ["nice talking! take care", "cya :)"])
        self.topic_memory: Dict[str, Dict[str, float]] = {}
        self._stage: Dict[str, str] = {}     # partner_id -> "greeted"|"aged"|"chat"

    # ------------------------------------------------------------------ API

    def opener(self, partner: dict) -> str:
        pid = partner.get("id", "?")
        self._stage[pid] = "greeted"
        return self._fmt(random.choice(self.greetings), partner)

    def reply(self, partner: dict, incoming: str, history: Optional[List[dict]] = None) -> str:
        pid = partner.get("id", "?")
        text = (incoming or "").strip()
        low = text.lower()
        stage = self._stage.get(pid, "greeted")

        answer = self._match_question(low, partner)
        if answer:
            self._stage[pid] = "chat"
            return answer

        if stage == "greeted":
            self._stage[pid] = "aged"
            return self._fmt(random.choice(self.interest_questions), partner)

        self._stage[pid] = "chat"
        return self._fmt(random.choice(self.smalltalk), partner)

    def farewell(self, partner: dict) -> str:
        return self._fmt(random.choice(self.bye), partner)

    def forget(self, partner_id: str) -> None:
        """Drop per-partner state when a match ends (prevents stale stage on
        rematch + unbounded memory growth in long runs)."""
        self._stage.pop(partner_id, None)
        self.topic_memory.pop(partner_id, None)

    def delay_for(self, incoming: str) -> float:
        """Human-like reply delay: typing speed ~ 5.2 chars/sec + jitter."""
        base = 1.2 + min(len(incoming) * 0.075, 6.0)
        return base + random.uniform(0.2, 1.4)

    # -------------------------------------------------------------- internals

    def _match_question(self, low: str, partner: dict) -> Optional[str]:
        if any(k in low for k in ("m or f", "m/f", "male or female", "gender")) or \
           (low.strip() in ("m?", "f?", "m or f", "m or f?")):
            return self._fmt(random.choice(self.gender_answers), partner)
        if any(k in low for k in ("age", "how old", "asl")):
            return self._fmt(random.choice(self.age_answers), partner)
        if any(k in low for k in ("where are you from", "which country", "where u from", "location")):
            return self.persona.country
        if low.strip() in ("hi", "hey", "hello", "heyy", "hii", "howdy", "hlw", "helo"):
            if self._stage.get(partner.get("id", "?")) == "greeted":
                return self._fmt(random.choice(self.greetings), partner)
            return self._fmt(random.choice(self.interest_questions), partner)
        return None

    def _fmt(self, template: str, partner: dict) -> str:
        name = partner.get("username") or "there"
        return template.format(
            name=name.split()[0] if name.split() else "there",
            age=self.persona.age,
            gender=self.persona.gender,
            country=self.persona.country,
        )
