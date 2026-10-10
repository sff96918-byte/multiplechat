"""chitchat.gg Socket.IO WebSocket client (real protocol, capture-backed).

Replaces the old observer-only foundation. Implements exactly what the
capture proves (see protocol_manifest.json):

  1. connect wss://api.chitchat.gg/socket.io/?EIO=4&transport=websocket
     with Cookie (token + __Secure-text-session) and Origin headers.
  2. IN  0{handshake}
  3. OUT 40{"release":"<release sha>"}
  4. IN  40{"sid":..., "pid":...}
  5. OUT 42["presenceSync"] immediately, then every 30s
  6. IN  2 -> OUT 3 (server pings, we pong)
  7. dispatch 42["chatMessage"|"matchUpdate"|"typing"|...] to handlers
  8. IN 41 / socket closed -> auto reconnect with backoff

No `socketio` pip package — we speak the wire protocol directly over aiohttp
WS (both already in src/requirements.txt).
"""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp

from . import socketio_codec as codec
from .protocol import (
    CHITCHAT_WS_URL,
    DEFAULT_ORIGIN,
    DEFAULT_UA,
    RELEASE_SHA,
    PRESENCE_SYNC_INTERVAL_S,
)

__all__ = ["ChitchatSocket", "SocketStats"]

log = logging.getLogger("eva.chitchat_socket")


@dataclass
class SocketStats:
    connected_at: float = 0.0
    reconnects: int = 0
    frames_in: int = 0
    frames_out: int = 0
    pings_ponged: int = 0
    events: Dict[str, int] = field(default_factory=dict)

    def snapshot(self) -> dict:
        return {
            "connected_at": self.connected_at,
            "uptime_s": round(time.time() - self.connected_at, 1) if self.connected_at else 0,
            "reconnects": self.reconnects,
            "frames_in": self.frames_in,
            "frames_out": self.frames_out,
            "pings_ponged": self.pings_ponged,
            "events": dict(self.events),
        }


Handler = Callable[[str, List[Any]], Awaitable[None]]


class ChitchatSocket:
    """Live Socket.IO connection for a logged-in chitchat.gg session."""

    def __init__(
        self,
        cookies: Dict[str, str],
        *,
        release: str = RELEASE_SHA,
        origin: str = DEFAULT_ORIGIN,
        user_agent: str = DEFAULT_UA,
        session_cookie_name: str = "__Secure-text-session",
        max_backoff_s: float = 60.0,
        ws_url: str = CHITCHAT_WS_URL,
    ) -> None:
        self._cookies = dict(cookies)
        self._release = release
        self._origin = origin
        self._ua = user_agent
        self._session_cookie_name = session_cookie_name
        self._max_backoff_s = max_backoff_s
        self._ws_url = ws_url

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._tasks: List[asyncio.Task] = []
        self._running = False
        self._connected = asyncio.Event()
        self._handshake: dict = {}

        self._handler: Optional[Handler] = None
        self.stats = SocketStats()
        self._recent: deque = deque(maxlen=300)   # debug ring buffer

    # ------------------------------------------------------------ public API

    def set_event_handler(self, handler: Handler) -> None:
        """handler(event_name, args) is awaited for every 42[..] event."""
        self._handler = handler

    def record_frame(self, direction: str, text: str) -> None:
        """Debug ring buffer — শেষ 300 frame (debug report-এ যায়)।
        নিজের cookie value preview থেকে মুছে দেওয়া হয় (report শেয়ার-safe)।"""
        clean = text or ""
        for v in self._cookies.values():
            if len(v or "") >= 8 and v in clean:
                clean = clean.replace(v, "…MASKED")
        self._recent.append({
            "t": time.strftime("%H:%M:%S"),
            "dir": direction,
            "len": len(clean),
            "preview": clean[:180],
        })

    def recent_frames(self) -> List[dict]:
        return list(self._recent)

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def handshake(self) -> dict:
        return dict(self._handshake)

    def cookie_header(self) -> str:
        """Cookie header string from the session cookie dict."""
        return "; ".join(f"{k}={v}" for k, v in self._cookies.items())

    async def start(self) -> None:
        """Start the connection loop (reconnects forever until stop())."""
        if self._running:
            return
        self._running = True
        self._tasks.append(asyncio.create_task(self._run_loop(), name="cchat-ws-loop"))

    async def stop(self) -> None:
        self._running = False
        self._connected.clear()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()

    async def emit(self, event: str, *args: Any) -> bool:
        """Send 42["event", ...] if connected."""
        if not (self._ws and self.is_connected):
            return False
        frame = codec.encode_event(event, *args)
        await self._ws.send_str(frame)
        self.stats.frames_out += 1
        self.record_frame("OUT", frame)
        log.debug("WS OUT %s", frame[:200])
        return True

    # ------------------------------------------------------------ internals

    def _build_headers(self) -> dict:
        return {
            "Origin": self._origin,
            "User-Agent": self._ua,
        }

    async def _run_loop(self) -> None:
        backoff = 1.0
        while self._running:
            try:
                await self._connect_once()
                backoff = 1.0  # clean disconnect after a successful session
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                log.warning("WS session ended: %s: %s", type(exc).__name__, exc)
            if not self._running:
                break
            sleep_s = backoff + random.uniform(0, backoff * 0.3)
            backoff = min(backoff * 2, self._max_backoff_s)
            self.stats.reconnects += 1
            log.info("Reconnecting in %.1fs (reconnect #%d)", sleep_s, self.stats.reconnects)
            await asyncio.sleep(sleep_s)

    async def _connect_once(self) -> None:
        timeout = aiohttp.ClientWSTimeout(ws_close=10.0)
        if self._session is None or self._session.closed:
            jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(cookie_jar=jar)

        log.info("WS connecting %s", self._ws_url)
        headers = self._build_headers()
        # browser attaches cookies on the wss upgrade; replicate exactly
        if self._cookies:
            headers["Cookie"] = self.cookie_header()
        async with self._session.ws_connect(
            self._ws_url,
            headers=headers,
            timeout=timeout,
            heartbeat=None,          # Engine.IO heartbeat handled at protocol level
            autoping=True,           # reply to protocol-level pings at TCP layer if any
            max_msg_size=2 * 1024 * 1024,
        ) as ws:
            self._ws = ws
            try:
                await self._handshake_and_serve(ws)
            finally:
                self._ws = None
                self._connected.clear()

    async def _handshake_and_serve(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        # -- 1. wait for OPEN 0{...}
        open_frame = await self._expect(ws, kinds=("open",))
        self._handshake = codec.parse_handshake(open_frame)
        log.info("WS handshake sid=%s pingInterval=%sms",
                 self._handshake["sid"], self._handshake["ping_interval_ms"])

        # -- 2. namespace CONNECT with release payload
        connect_frame = codec.encode_connect({"release": self._release})
        await ws.send_str(connect_frame)
        self.stats.frames_out += 1
        log.debug("WS OUT %s", connect_frame)

        # -- 3. server CONNECT ack 40{"sid","pid"}; meanwhile respond to early pings
        ack = await self._expect(ws, kinds=("connect",), service_frames=True)
        if ack.payload:
            log.info("WS namespace connected sid=%s pid=%s",
                     ack.payload.get("sid"), ack.payload.get("pid"))

        self._connected.set()
        self.stats.connected_at = time.time()

        # -- 4. presenceSync right away (captured behavior)
        await self.emit("presenceSync")

        # -- 5. heartbeat task + recv loop
        hb = asyncio.create_task(self._presence_loop(), name="cchat-presence")
        try:
            await self._recv_loop(ws)
        finally:
            hb.cancel()
            await asyncio.gather(hb, return_exceptions=True)

    async def _expect(self, ws: aiohttp.ClientWebSocketResponse, kinds: tuple,
                      service_frames: bool = False, timeout: float = 15.0) -> codec.Frame:
        """Receive frames until one of `kinds` arrives; pings are answered on the way.

        BUGFIX: a server DISCONNECT (41) / CONNECT_ERROR (44) while waiting now
        raises immediately instead of stalling until timeout."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for {kinds}")
            msg = await ws.receive(timeout=remaining)
            if msg.type == aiohttp.WSMsgType.TEXT:
                frame = codec.decode(msg.data)
                self.stats.frames_in += 1
                self.record_frame("IN", msg.data)
                if frame.kind == "ping":
                    await ws.send_str(codec.encode_pong())
                    self.stats.frames_out += 1
                    self.stats.pings_ponged += 1
                    continue
                if frame.kind in kinds:
                    return frame
                if frame.kind in ("disconnect", "connect_error"):
                    raise ConnectionError(
                        f"server ended namespace while waiting for {kinds}: "
                        f"{frame.kind} payload={frame.payload}")
                if service_frames and frame.kind == "event":
                    await self._dispatch(frame)
                    continue
                log.debug("WS frame while waiting for %s: %s", kinds, frame.kind)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                raise ConnectionError(f"ws closed while waiting for {kinds}: {msg}")
            # ignore other msg types (binary keepalive etc.)

    async def _presence_loop(self) -> None:
        while True:
            await asyncio.sleep(PRESENCE_SYNC_INTERVAL_S)
            try:
                await self.emit("presenceSync")
            except Exception:  # noqa: BLE001
                return

    async def _recv_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                self.stats.frames_in += 1
                try:
                    frame = codec.decode(msg.data)
                except codec.CodecError as exc:
                    log.warning("undecodable frame: %s", exc)
                    continue
                self.record_frame("IN", msg.data)
                log.debug("WS IN  %s", msg.data[:200])

                if frame.kind == "ping":
                    await ws.send_str(codec.encode_pong())
                    self.stats.frames_out += 1
                    self.stats.pings_ponged += 1
                elif frame.kind == "event":
                    await self._dispatch(frame)
                elif frame.kind == "disconnect":
                    log.info("server sent Socket.IO DISCONNECT (41)")
                    return
                elif frame.kind == "connect_error":
                    log.error("connect_error payload=%s", frame.payload)
                    return
                elif frame.kind == "open":
                    # server restarted -> full re-handshake needed
                    return
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                log.info("ws closed: %s", msg)
                return

    async def _dispatch(self, frame: codec.Frame) -> None:
        name = frame.event or ""
        self.stats.events[name] = self.stats.events.get(name, 0) + 1
        if self._handler:
            try:
                await self._handler(name, frame.args)
            except Exception:  # noqa: BLE001 — a handler bug must not kill the socket
                log.exception("event handler failed for %s", name)
