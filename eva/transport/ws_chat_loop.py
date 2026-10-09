"""WS-only chat loop: queue → matched → chat → (partner skip | we skip) → next.

State machine driven by real captured events:

  POST /match  ──►  matchUpdate(closure.closed=false)  ⇒ MATCHED (conversation id)
  chatMessage(author != self)  ⇒ reply via REST (typing → delay → POST message)
  matchUpdate(closure.closed=true, closeReason=INTENTIONAL) ⇒ partner skipped
  idle_timeout / max_messages  ⇒ PATCH /match/disconnect ⇒ POST /match (next)

Own-message WS echoes are filtered by author.id == self_id (capture-proven).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

from .chitchat_api import ChitchatApi, FlaggedError
from .chitchat_socket import ChitchatSocket
from ..replies import ReplyEngine

log = logging.getLogger("eva.ws_chat_loop")


class LoopState(str, Enum):
    IDLE = "IDLE"
    QUEUING = "QUEUING"
    CHATTING = "CHATTING"
    STOPPED = "STOPPED"


@dataclass
class LoopConfig:
    auto_next: bool = True              # rejoin queue after a match ends
    next_delay_s: (int, int) = (2, 5)   # human-ish pause before requeueing
    skip_idle_s: float = 90.0           # partner silent this long -> skip
    skip_after_msgs: int = 25           # safety cap per match
    min_reply_delay_s: float = 1.0
    typing_indicator: bool = True
    opener_delay_s: (int, int) = (1, 3)
    queue_timeout_s: float = 120.0      # in queue this long -> re-POST /match


@dataclass
class Partner:
    id: str = ""
    username: str = ""
    profile: dict = field(default_factory=dict)

    def display(self) -> str:
        return f"{self.username or self.id or '?'}"


@dataclass
class LoopStats:
    matches: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    partner_skips: int = 0
    our_skips: int = 0
    flagged_403: int = 0
    started_at: float = field(default_factory=time.time)

    def snapshot(self) -> dict:
        d = dict(self.__dict__)
        d["uptime_s"] = round(time.time() - self.started_at, 1)
        return d


class WsChatLoop:
    """Owns one socket + one api client and runs the full match lifecycle."""

    def __init__(
        self,
        api: ChitchatApi,
        socket: ChitchatSocket,
        reply_engine: Optional[ReplyEngine] = None,
        config: Optional[LoopConfig] = None,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.api = api
        self.socket = socket
        self.engine = reply_engine or ReplyEngine()
        self.cfg = config or LoopConfig()
        self.on_event = on_event            # UI hook: (event, data)

        self.self_id: str = ""
        self.state: LoopState = LoopState.IDLE
        self.partner: Optional[Partner] = None
        self.conversation_id: str = ""
        self.history: List[dict] = []

        self._inbox: asyncio.Queue = asyncio.Queue()
        self._match_events: asyncio.Queue = asyncio.Queue()
        self._tasks: List[asyncio.Task] = []
        self._running = False
        self._last_partner_msg_t: float = 0.0
        self._partner_typing: bool = False
        self._stop_reason: str = ""
        self.stats = LoopStats()

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.socket.set_event_handler(self._on_socket_event)
        await self.socket.start()

        self.self_id = await self.api.self_id()
        log.info("authenticated as self_id=%s", self.self_id)

        self._tasks = [
            asyncio.create_task(self._dispatcher(), name="loop-dispatcher"),
            asyncio.create_task(self._match_runner(), name="loop-runner"),
        ]

    async def stop(self, reason: str = "manual stop") -> None:
        self._running = False
        self._stop_reason = reason
        try:
            if self.conversation_id:
                await self.api.leave_match()
        except Exception:  # noqa: BLE001
            pass
        await self.socket.stop()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self.state = LoopState.STOPPED

    # ------------------------------------------------------------ ws events

    async def _on_socket_event(self, name: str, args: List[dict]) -> None:
        """Called from socket recv context — just enqueue, work happens in dispatcher."""
        if name == "chatMessage" and args:
            await self._inbox.put(("chatMessage", args[0]))
        elif name == "matchUpdate" and args:
            await self._inbox.put(("matchUpdate", args[0]))
        elif name == "typing" and args:
            await self._inbox.put(("typing", args[0]))
        # other events (onlineFriends, updateRelationship, messageEdited) ignored

    async def _dispatcher(self) -> None:
        while self._running:
            try:
                kind, payload = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                if kind == "chatMessage":
                    await self._handle_chat_message(payload)
                elif kind == "matchUpdate":
                    await self._match_events.put(payload)
                    await self._handle_match_update_fast(payload)
                elif kind == "typing":
                    await self._handle_typing(payload)
            except Exception:  # noqa: BLE001
                log.exception("dispatcher error on %s", kind)

    # ------------------------------------------------------------ match flow

    async def _match_runner(self) -> None:
        while self._running:
            try:
                await self._run_one_match_cycle()
            except FlaggedError as exc:
                self.stats.flagged_403 += 1
                log.error("account Flagged (403 /match): %s — waiting 10 min", exc)
                await asyncio.sleep(600)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.exception("match cycle failed: %s", exc)
                await asyncio.sleep(10)

    async def _run_one_match_cycle(self) -> None:
        # clear stale match events
        while not self._match_events.empty():
            self._match_events.get_nowait()

        self.state = LoopState.QUEUING
        self._emit("queuing", {})
        matched = await self.api.join_match_queue()
        log.info("POST /match -> matched=%s", matched)

        # capture-proven: matchUpdate (closed=false) arrives over WS either
        # instantly with matched=true (~40ms) or later when a partner is found.
        try:
            payload = await asyncio.wait_for(self._match_events.get(),
                                             timeout=self.cfg.queue_timeout_s)
        except asyncio.TimeoutError:
            log.warning("queue timeout %.0fs — retrying", self.cfg.queue_timeout_s)
            return
        await self._enter_match_if_open(payload)
        if not self.conversation_id:
            return  # closed event while waiting; loop again

        # ---------------- chatting phase
        await self._chat_until_closed()

        # ---------------- after match
        self.state = LoopState.IDLE
        if not self._running:
            return
        if self.cfg.auto_next:
            delay = random.uniform(*self.cfg.next_delay_s)
            log.info("next match in %.1fs", delay)
            await asyncio.sleep(delay)

    async def _handle_match_update_fast(self, payload: dict) -> None:
        match = payload.get("match") or {}
        closure = match.get("closure") or {}
        if closure.get("closed"):
            self.stats.partner_skips += 1
            closed_by = closure.get("closedBy", "")
            who = "partner" if closed_by and closed_by != self.self_id else "us"
            log.info("match closed (reason=%s by=%s)", closure.get("closeReason"), who)
            self._emit("match_closed", {"closedBy": closed_by, "conversationId": self.conversation_id})

    async def _enter_match_if_open(self, payload: dict) -> None:
        match = payload.get("match") or {}
        closure = match.get("closure") or {}
        if closure.get("closed"):
            return
        conv = match.get("conversation") or {}
        self.conversation_id = conv.get("id", "")
        partner_profile = self.api.extract_partner(payload, self.self_id)
        self.partner = Partner(
            id=partner_profile.get("id", ""),
            username=partner_profile.get("username", ""),
            profile=partner_profile,
        )
        self.history = []
        self._last_partner_msg_t = time.time()
        self.stats.matches += 1
        self.state = LoopState.CHATTING
        log.info("MATCHED #%d conv=%s partner=%s (%s)",
                 self.stats.matches, self.conversation_id,
                 self.partner.display(), partner_profile.get("gender", "?"))
        self._emit("matched", {
            "conversationId": self.conversation_id,
            "partner": partner_profile,
            "match_no": self.stats.matches,
        })

        # opener with human delay
        await asyncio.sleep(random.uniform(*self.cfg.opener_delay_s))
        if self.conversation_id and self.state == LoopState.CHATTING:
            opener = self.engine.opener(self.partner.__dict__ | {"username": self.partner.username})
            await self._send(opener)

    async def _chat_until_closed(self) -> None:
        while self._running and self.conversation_id:
            await asyncio.sleep(0.5)
            idle = time.time() - self._last_partner_msg_t
            if idle > self.cfg.skip_idle_s and not self._partner_typing:
                log.info("partner idle %.0fs — skipping", idle)
                self.stats.our_skips += 1
                self._emit("we_skip", {"conversationId": self.conversation_id})
                try:
                    await self.api.leave_match()
                except Exception:  # noqa: BLE001
                    log.exception("leave_match failed")
                await asyncio.sleep(1.0)
                break
            # drain match-closed events
            while not self._match_events.empty():
                payload = self._match_events.get_nowait()
                closure = (payload.get("match") or {}).get("closure") or {}
                if closure.get("closed"):
                    self.conversation_id = ""
                    return

    # ------------------------------------------------------------ messaging

    async def _handle_chat_message(self, payload: dict) -> None:
        msg = payload.get("message") or {}
        author = (msg.get("author") or {}).get("id", "")
        if author == self.self_id:
            return  # own echo (capture-proven behavior)
        if msg.get("conversationId") != self.conversation_id:
            return  # stale/other conversation
        content = msg.get("content", "")
        self.history.append({"from": "partner", "text": content, "t": time.time()})
        self.stats.messages_received += 1
        self._last_partner_msg_t = time.time()
        self._partner_typing = False
        log.info("PARTNER %s: %r", self.partner.display() if self.partner else "?", content[:80])
        self._emit("partner_message", {"conversationId": msg.get("conversationId"), "text": content})

        if len(self.history) >= self.cfg.skip_after_msgs * 2:
            log.info("message cap reached — skipping match")
            try:
                await self.api.leave_match()
            except Exception:  # noqa: BLE001
                pass
            self.conversation_id = ""
            return

        reply = self.engine.reply(self.partner.__dict__ | {"username": self.partner.username} if self.partner else {}, content)
        await self._send(reply)

    async def _send(self, text: str) -> None:
        if not (self.conversation_id and text):
            return
        delay = max(self.cfg.min_reply_delay_s, self.engine.delay_for(text))
        if self.cfg.typing_indicator:
            try:
                await self.api.send_typing(self.conversation_id)
            except Exception:  # noqa: BLE001
                log.exception("typing POST failed (continuing)")
        await asyncio.sleep(delay)
        try:
            sent = await self.api.send_message(self.conversation_id, text)
        except Exception as exc:  # noqa: BLE001
            log.error("send_message failed: %s", exc)
            return
        self.history.append({"from": "us", "text": text, "t": time.time()})
        self.stats.messages_sent += 1
        self._last_partner_msg_t = time.time()
        log.info("US      : %r (nonce=%s)", text[:80], (sent or {}).get("nonce", "-")[:8])
        self._emit("our_message", {"conversationId": self.conversation_id, "text": text})

    async def _handle_typing(self, payload: dict) -> None:
        if payload.get("conversationId") == self.conversation_id:
            self._partner_typing = True
            self._last_partner_msg_t = max(self._last_partner_msg_t, time.time() - 5)
            self._emit("partner_typing", {"conversationId": payload.get("conversationId")})

    # ------------------------------------------------------------ misc

    def _emit(self, event: str, data: dict) -> None:
        if self.on_event:
            try:
                self.on_event(event, data)
            except Exception:  # noqa: BLE001
                log.exception("on_event hook failed")
