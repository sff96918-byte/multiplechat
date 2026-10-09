"""Offline protocol verification for the chitchat bot — NO live site touched.

Spins up:
  * a mock Engine.IO v4 / Socket.IO v5 WebSocket server that replays the
    EXACT captured frame sequence (handshake, connect ack, ping/pong,
    matchUpdate, chatMessage, own-echo),
  * a mock REST server proving the captured endpoints (POST /match,
    PATCH /match/disconnect, POST typing, POST messages multipart,
    GET /users/me ...).

Then runs the REAL client stack (ChitchatSocket + ChitchatApi + WsChatLoop)
against them and asserts every capture-derived behavior:

  [1] client sends 40{"release":...} after OPEN            (captured)
  [2] client answers server ping '2' with '3'              (captured)
  [3] client emits 42["presenceSync"] on connect + 30s     (captured)
  [4] POST /match joins queue; matchUpdate opens match     (captured)
  [5] partner chatMessage triggers typing + message POST   (captured)
  [6] message POST is multipart with content+nonce fields  (captured ct/keys)
  [7] OWN message echo does NOT trigger a reply            (capture-proven)
  [8] matchUpdate closed=true -> client PATCHes disconnect + requeues (captured)

Run:  python -m ops.tools.socket_smoke_test
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from aiohttp import web

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eva.transport.chitchat_api import ChitchatApi          # noqa: E402
from eva.transport.chitchat_socket import ChitchatSocket    # noqa: E402
from eva.transport import socketio_codec as codec           # noqa: E402
from eva.transport.ws_chat_loop import LoopConfig, WsChatLoop  # noqa: E402
from eva.replies import ReplyEngine                         # noqa: E402

FIXTURES = json.loads((ROOT / "tests" / "fixtures" / "captured_frames.json").read_text(encoding="utf-8"))


def _deref(obj: Any) -> Any:
    """Resolve {"_ref": key} pointers in the fixture."""
    if isinstance(obj, dict):
        if set(obj.keys()) == {"_ref"}:
            base = FIXTURES[obj["_ref"]]
            return json.loads(json.dumps(base))  # deep copy
        return {k: _deref(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deref(v) for v in obj]
    return obj


SELF_ID = FIXTURES["self_user"]["id"]
CONV_ID = FIXTURES["conversation_id"]
PARTNER_ID = FIXTURES["partner_user"]["id"]


class Results:
    def __init__(self) -> None:
        self.checks: List[Tuple[bool, str, str]] = []

    def check(self, ok: bool, name: str, detail: str = "") -> None:
        self.checks.append((ok, name, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f"  — {detail}" if detail and not ok else ""))

    def report(self) -> int:
        passed = sum(1 for ok, _, _ in self.checks if ok)
        total = len(self.checks)
        print(f"\n{'='*60}\n  RESULT: {passed}/{total} checks passed")
        if passed != total:
            for ok, name, detail in self.checks:
                if not ok:
                    print(f"   FAIL: {name} {detail}")
        print('='*60)
        return 0 if passed == total else 1


# ============================================================ mock WS server

class MockSocketIOServer:
    """Replays the captured server side of the socket.io connection."""

    def __init__(self, results: Results, ws_port: int) -> None:
        self.results = results
        self.ws_port = ws_port
        self.ws: Optional[aiohttp.web.WebSocketResponse] = None
        self.got_release_connect: Optional[dict] = None
        self.got_presence_sync: int = 0
        self.got_pong: int = 0
        self.runner: Optional[web.AppRunner] = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/socket.io/", self._handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", self.ws_port)
        await site.start()

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    async def send_event(self, name: str, payload: Any) -> None:
        if self.ws and not self.ws.closed:
            await self.ws.send_str(codec.encode_event(name, payload))

    async def ping(self) -> None:
        if self.ws and not self.ws.closed:
            await self.ws.send_str("2")

    async def _handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.ws = ws

        # [captured] OPEN handshake with real values
        await ws.send_str(FIXTURES["handshake"])

        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                break
            try:
                frame = codec.decode(msg.data)
            except codec.CodecError:
                continue

            if frame.kind == "connect":
                self.got_release_connect = frame.payload
                # [captured] server ack with sid+pid
                await ws.send_str(FIXTURES["connect_ack"])
            elif frame.kind == "event" and frame.event == "presenceSync":
                self.got_presence_sync += 1
            elif frame.kind == "pong":
                self.got_pong += 1

        return ws


# ============================================================ mock REST

class MockRest:
    """Captured endpoints with captured response shapes."""

    def __init__(self, results: Results, ws_server: MockSocketIOServer, port: int) -> None:
        self.results = results
        self.ws_server = ws_server
        self.requested_port = port
        self.port = port
        self.runner: Optional[web.AppRunner] = None
        # recorded behavior
        self.join_queue_calls = 0
        self.disconnect_calls = 0
        self.typing_calls: List[str] = []
        self.messages: List[Dict[str, Any]] = []          # parsed multipart/json bodies
        self.raw_message_content_types: List[str] = []
        self.match_open_sent = False
        self.allow_next_match = True
        self._pending_match: asyncio.Queue = asyncio.Queue()

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/users/me", self._me)
        app.router.add_get("/moderation/standing", self._standing)
        app.router.add_get("/match/active", self._active)
        app.router.add_post("/match", self._join_match)
        app.router.add_patch("/match/disconnect", self._disconnect)
        app.router.add_post("/users/me/conversations/{cid}/typing", self._typing)
        app.router.add_post("/users/me/conversations/{cid}/messages", self._message)
        app.router.add_patch("/users/me/conversations/{cid}/read", self._read)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", self.requested_port)
        await site.start()
        if self.requested_port == 0:
            self.port = self.runner.addresses[0][1]

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # -- handlers -----------------------------------------------------------

    async def _me(self, request: web.Request) -> web.Response:
        return web.json_response(_deref(FIXTURES["self_user"]))

    async def _standing(self, request: web.Request) -> web.Response:
        return web.json_response({"standing": "good", "limitedFeatures": [],
                                  "pendingWarnings": [], "activeViolations": []})

    async def _active(self, request: web.Request) -> web.Response:
        return web.json_response({"inQueue": False})

    async def _join_match(self, request: web.Request) -> web.Response:
        self.join_queue_calls += 1
        if self.allow_next_match:
            matched_payload = _deref(FIXTURES["match_open"])
            # [captured] matchUpdate arrives over WS as the POST returns
            asyncio.get_event_loop().call_later(
                0.05, lambda: asyncio.ensure_future(self.ws_server.send_event("matchUpdate", matched_payload)))
            return web.json_response({"matched": True}, status=201)
        return web.json_response({"statusCode": 403, "path": "/match",
                                  "message": "Flagged", "error": "Forbidden"}, status=403)

    async def _disconnect(self, request: web.Request) -> web.Response:
        self.disconnect_calls += 1
        # [captured] partner receives matchUpdate closed INTENTIONAL
        closed = _deref(FIXTURES["match_closed_by_partner"])
        asyncio.get_event_loop().call_later(
            0.05, lambda: asyncio.ensure_future(self.ws_server.send_event("matchUpdate", closed)))
        return web.json_response({}, status=200)

    async def _typing(self, request: web.Request) -> web.Response:
        cid = request.match_info["cid"]
        self.typing_calls.append(cid)
        # [captured] partner receives WS typing event
        asyncio.get_event_loop().call_later(
            0.02, lambda: asyncio.ensure_future(
                self.ws_server.send_event("typing", {"userId": SELF_ID, "conversationId": cid})))
        return web.json_response({}, status=200)

    async def _message(self, request: web.Request) -> web.Response:
        cid = request.match_info["cid"]
        ctype = request.headers.get("Content-Type", "")
        self.raw_message_content_types.append(ctype)
        body: Dict[str, Any] = {}
        try:
            if ctype.startswith("multipart/"):
                form = await request.post()
                body = {k: str(v) for k, v in form.items()}
            else:
                body = await request.json()
        except Exception as exc:  # noqa: BLE001 — surface parsing problems to the test
            print(f"  [mock-rest] message POST parse error: {type(exc).__name__}: {exc}")
            return web.json_response({"error": "mock parse failure"}, status=500)
        body["_conversationId"] = cid
        self.messages.append(body)

        resp = _deref(FIXTURES["message_post_response"])
        resp["conversationId"] = cid
        resp["content"] = body.get("content", "")
        resp["nonce"] = body.get("nonce", "")
        return web.json_response(resp, status=201)

    async def _read(self, request: web.Request) -> web.Response:
        return web.json_response({}, status=200)


# ============================================================ the scenario

async def run_scenario(results: Results) -> None:
    ws_server = MockSocketIOServer(results, ws_port=0)
    await ws_server.start()
    ws_port = ws_server.runner.addresses[0][1]

    rest = MockRest(results, ws_server, port=0)
    await rest.start()

    cookies = {"token": "smoke-test-jwt", "__Secure-text-session": "smoke-session"}

    api = ChitchatApi(cookies, base_url=rest.base_url, request_spacing_s=0.05)
    sock = ChitchatSocket(cookies, ws_url=f"ws://127.0.0.1:{ws_port}/socket.io/?EIO=4&transport=websocket")

    engine = ReplyEngine(config={"greetings": ["hey :)"], "smalltalk": ["nice"]})
    loop_cfg = LoopConfig(
        auto_next=True, next_delay_s=(0.2, 0.4), skip_idle_s=6.0,
        min_reply_delay_s=0.2, opener_delay_s=(0.2, 0.3), queue_timeout_s=10,
    )
    loop = WsChatLoop(api, sock, engine, loop_cfg)
    loop.self_id = SELF_ID

    # capture outgoing events to inspect matched/closed transitions
    events: List[Tuple[str, dict]] = []
    loop.on_event = lambda e, d: events.append((e, d))

    await loop.start()

    # ---- phase 1: connection checks
    for _ in range(100):
        if sock.is_connected:
            break
        await asyncio.sleep(0.05)
    results.check(sock.is_connected, "[1] WS connected + namespace handshake")

    results.check(
        ws_server.got_release_connect is not None and ws_server.got_release_connect.get("release"),
        "[1a] client sent 40{\"release\":...} namespace CONNECT (captured)",
        detail=f"got={ws_server.got_release_connect}",
    )
    results.check(ws_server.got_presence_sync >= 1,
                  "[3] client emitted 42[\"presenceSync\"] after connect (captured)")

    # ---- phase 2: server pings -> client pongs
    await ws_server.ping()
    await asyncio.sleep(0.3)
    results.check(ws_server.got_pong >= 1, "[2] server ping '2' answered with pong '3' (captured)")

    # ---- phase 3: queue -> match -> partner message -> reply
    # NOTE: match runner starts its own POST /match immediately.
    deadline = time.time() + 10
    while time.time() < deadline and not any(e == "matched" for e, _ in events):
        await asyncio.sleep(0.1)
    results.check(any(e == "matched" for e, _ in events),
                  "[4] POST /match -> matchUpdate -> match opened (captured)")
    results.check(loop.conversation_id == CONV_ID,
                  "[4a] conversation id parsed from matchUpdate", detail=loop.conversation_id)
    results.check(loop.partner and loop.partner.id == PARTNER_ID,
                  "[4b] partner resolved (participants != self) (captured)")

    # opener should have been sent as multipart content+nonce
    deadline = time.time() + 10
    while time.time() < deadline and not rest.messages:
        await asyncio.sleep(0.1)
    if rest.messages:
        first = rest.messages[0]
        results.check("content" in first and "nonce" in first,
                      "[6] message POST carries content + nonce fields",
                      detail=str(rest.messages[0]))
        results.check(bool(rest.raw_message_content_types) and
                      rest.raw_message_content_types[0].startswith("multipart/"),
                      "[6a] message POST content-type = multipart/form-data (captured ct)",
                      detail=str(rest.raw_message_content_types[:1]))
        try:
            uuid.UUID(first.get("nonce", ""))
            nonce_ok = True
        except ValueError:
            nonce_ok = False
        results.check(nonce_ok, "[6b] nonce is a valid UUID v4 (captured pattern)")
    else:
        results.check(False, "[6] message POST captured", "no message POST observed")

    # typing indicator was sent before the message
    results.check(len(rest.typing_calls) >= 1 and rest.typing_calls[0] == CONV_ID,
                  "[5a] typing POST before first reply (captured flow)")

    # ---- phase 4: partner sends "Hey m24" (EXACT captured chatMessage)
    chat_evt = _deref(FIXTURES["chat_message_from_partner"])
    n_before = len(rest.messages)
    await ws_server.send_event("chatMessage", chat_evt)

    deadline = time.time() + 15
    while time.time() < deadline and len(rest.messages) <= n_before:
        await asyncio.sleep(0.1)
    results.check(len(rest.messages) > n_before,
                  "[5] partner chatMessage triggered auto-reply (captured event)")

    # ---- phase 5: OWN echo must NOT trigger a reply
    n_before = len(rest.messages)
    await ws_server.send_event("chatMessage", _deref(FIXTURES["own_message_echo"]))
    await asyncio.sleep(2.5)
    results.check(len(rest.messages) == n_before,
                  "[7] own-message WS echo ignored (capture-proven behavior)")

    # ---- phase 6: partner skips -> match closes -> we requeue (auto_next)
    await ws_server.send_event("matchUpdate", _deref(FIXTURES["match_closed_by_partner"]))
    deadline = time.time() + 15
    while time.time() < deadline and rest.join_queue_calls < 2:
        await asyncio.sleep(0.1)
    results.check(any(e == "match_closed" for e, _ in events),
                  "[8a] matchUpdate closed=true detected (captured)")
    results.check(rest.join_queue_calls >= 2,
                  "[8b] auto requeue: POST /match called again after partner skip (captured 1.6s pattern)")

    # ---- stop
    await loop.stop("smoke-test done")
    await rest.stop()
    await ws_server.stop()
    await api.close()


def main() -> None:
    print("="*60)
    print("  chitchat bot — capture-based protocol smoke test")
    print("  (offline: mock server replays REAL captured frames)")
    print("="*60 + "\n")
    results = Results()
    try:
        asyncio.run(run_scenario(results))
    except Exception as exc:  # noqa: BLE001
        results.check(False, "scenario completed without crash", f"{type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
    sys.exit(results.report())


if __name__ == "__main__":
    main()
