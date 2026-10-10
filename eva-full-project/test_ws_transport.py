"""
test_ws_transport.py — unit checks for core/ws_transport (no network).

Covers the Socket.IO codec, matchUpdate partner extraction, and the v22
send_message safety net: after an ambiguous failure (timeout / 5xx / socket
drop) the bot checks the conversation for its own nonce before re-sending.
All payloads are synthetic. No real chat content is stored here.

Run:  python test_ws_transport.py
Exit: 0 on success, 1 on any failure.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.ws_transport import socketio_codec as codec  # noqa: E402
from core.ws_transport import chitchat_api as api_mod  # noqa: E402
from core.ws_transport.chitchat_api import ApiError, ChitchatApi  # noqa: E402

_results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))


# ---------------------------------------------------------------- codec
def test_codec() -> None:
    print("\n[codec]")
    f = codec.decode('2')
    check("ping frame", f.kind == "ping")
    f = codec.decode('3')
    check("pong frame", f.kind == "pong")
    f = codec.decode('0{"sid":"abc","pingInterval":25000,"pingTimeout":20000}')
    check("engine.io open payload parsed", f.kind == "open" and f.payload["pingInterval"] == 25000)
    f = codec.decode('40{"sid":"ns1"}')
    check("socket.io connect ack", f.kind == "connect" and f.payload.get("sid") == "ns1")
    f = codec.decode('42["chatMessage",{"message":{"id":"m1","conversationId":"c1"}}]')
    check("chatMessage event name", f.kind == "event" and f.event == "chatMessage")
    check("chatMessage event args", f.args and f.args[0]["message"]["id"] == "m1")
    f = codec.decode('42["typing",{"userId":"u1","conversationId":"c1"}]')
    check("typing event", f.kind == "event" and f.event == "typing")
    try:
        codec.decode('42not-json')
        check("bad EVENT raises CodecError", False, "no exception")
    except codec.CodecError:
        check("bad EVENT raises CodecError", True)
    f = codec.decode('9weird')
    check("unknown engine.io type surfaces as raw", f.kind == "raw")


# ---------------------------------------------------------------- partner
def test_partner() -> None:
    print("\n[matchUpdate partner]")
    payload = {"match": {"conversation": {"id": "c1", "participants": [
        {"profile": {"id": "me", "username": "self"}},
        {"profile": {"id": "p1", "username": "partner"}},
    ]}}}
    p = ChitchatApi.extract_partner(payload, "me")
    check("partner is the non-self participant", p.get("id") == "p1")
    check("no partner -> empty dict", ChitchatApi.extract_partner({}, "me") == {})


# ---------------------------------------------------------------- nonce lookup
def test_find_by_nonce() -> None:
    print("\n[find message by nonce]")
    msgs = [{"id": "m1", "nonce": "n-1"}, {"id": "m2", "nonce": "n-2"}]
    check("list: found", api_mod.find_message_by_nonce(msgs, "n-2") == msgs[1])
    check("dict wrapper {messages:[...]}: found",
          api_mod.find_message_by_nonce({"messages": msgs}, "n-1") == msgs[0])
    check("missing nonce -> None", api_mod.find_message_by_nonce(msgs, "zz") is None)
    check("empty nonce never matches", api_mod.find_message_by_nonce(msgs + [{"id": "x"}], "") is None)
    check("garbage response -> None", api_mod.find_message_by_nonce("oops", "n-1") is None)


# ---------------------------------------------------------------- send_message
class _Stub(ChitchatApi):
    """ChitchatApi with the HTTP layer replaced by a scripted queue."""

    def __init__(self, script, history=None, **kw):
        super().__init__({}, request_spacing_s=0.0, **kw)
        self.script = list(script)
        self.calls = []
        self.history = list(history or [])

    async def _request(self, method, path, **kw):
        self.calls.append((method, path, kw.get("json"), kw.get("data") is not None))
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def fetch_messages(self, conversation_id, limit=50, offset=0):
        self.calls.append(("GET", "messages", None, False))
        return list(self.history)


def test_send_message() -> None:
    print("\n[send_message safety net]")

    async def run():
        # 1) multipart rejected with 400 -> JSON retry, same nonce
        s = _Stub([ApiError(400, "/m", None), {"id": "ok1", "nonce": "fixed"}])
        out = await s.send_message("c1", "hi", nonce="fixed")
        check("400 on multipart retries once as JSON", s.calls[-1][2] == {"content": "hi", "nonce": "fixed"},
              str(s.calls))
        check("JSON retry returns the server message", out.get("id") == "ok1")

        # 2) timeout, but our nonce IS in the conversation -> no duplicate send
        s = _Stub([asyncio.TimeoutError()],
                  history=[{"id": "srv", "nonce": "n-timeout", "content": "hi"}],
                  message_body_format=api_mod.P.MESSAGE_BODY_FORMAT_JSON)
        out = await s.send_message("c1", "hi", nonce="n-timeout")
        posts = [c for c in s.calls if c[0] == "POST"]
        check("timeout + nonce landed -> treated as sent", out.get("id") == "srv", str(out))
        check("timeout + nonce landed -> no second POST", len(posts) == 1, str(len(posts)))

        # 3) timeout and nonce NOT in conversation -> the error propagates
        s = _Stub([asyncio.TimeoutError()], history=[{"id": "x", "nonce": "other"}],
                  message_body_format=api_mod.P.MESSAGE_BODY_FORMAT_JSON)
        raised = False
        try:
            await s.send_message("c1", "hi", nonce="n-missing")
        except asyncio.TimeoutError:
            raised = True
        check("timeout + nonce absent -> error propagates", raised)

        # 4) 4xx other than 400 is definitive -> no history lookup, error propagates
        s = _Stub([ApiError(422, "/m", None)], history=[{"id": "x", "nonce": "n-4"}],
                  message_body_format=api_mod.P.MESSAGE_BODY_FORMAT_JSON)
        raised = False
        try:
            await s.send_message("c1", "hi", nonce="n-4")
        except ApiError:
            raised = True
        check("422 is not second-guessed", raised and not any(c[0] == "GET" for c in s.calls))

    asyncio.run(run())


# ---------------------------------------------------------------- reply timing
def test_reply_timing() -> None:
    """Reply floor follows the human reference captured in weebbsssc (v23 evidence:
    inbound chatMessage -> reply 4.5-11.8 s, median 6.3 s, n=10). The floor is
    LoopConfig.min_reply_delay_s; the engine delay is added on top only when larger."""
    print("\n[reply timing]")
    from core.ws_transport import ws_chat_loop as wcl

    check("default reply floor = 4.5 s (capture minimum)",
          wcl.LoopConfig().min_reply_delay_s == 4.5, str(wcl.LoopConfig().min_reply_delay_s))

    class _Eng:
        def __init__(self, d): self.d = d
        def delay_for(self, text): return self.d

    class _Api:
        async def send_typing(self, cid): return None
        async def send_message(self, cid, text): return {"nonce": "n"}

    async def sleeps_for(engine_delay):
        loop = wcl.WsChatLoop(_Api(), None, _Eng(engine_delay), wcl.LoopConfig(typing_indicator=False))
        loop.conversation_id = "c1"
        recorded = []
        real = wcl.asyncio.sleep
        async def fake(d, *a, **k):
            recorded.append(d)
        wcl.asyncio.sleep = fake
        try:
            await loop._send("hi")
        finally:
            wcl.asyncio.sleep = real
        return recorded[-1] if recorded else None

    check("short engine delay -> floor 4.5 applied", asyncio.run(sleeps_for(0.5)) == 4.5)
    check("long engine delay -> engine value kept", asyncio.run(sleeps_for(7.0)) == 7.0)


# ---------------------------------------------------------------- loop safety (v26)
def test_loop_safety() -> None:
    """v26 regression tests (written BEFORE the fix, must fail first):
    (a) a send-failure streak must not follow the bot into the next match;
    (b) a reply must never go to a conversation that changed during the delay."""
    print("\n[loop safety]")
    from core.ws_transport import ws_chat_loop as wcl
    from core.ws_transport.chitchat_api import ChitchatApi

    class _Api:
        extract_partner = staticmethod(ChitchatApi.extract_partner)
        def __init__(self):
            self.sent = []
            self.fail_next = 0
        async def send_typing(self, cid): return None
        async def leave_match(self): return None
        async def send_message(self, cid, text):
            if self.fail_next > 0:
                self.fail_next -= 1
                raise RuntimeError("simulated send failure")
            self.sent.append((cid, text))
            return {"nonce": "n"}

    class _Eng:
        def delay_for(self, text): return 0.0
        def reply(self, partner, content): return "ok"
        def opener(self, partner): return ""
        def forget(self, pid): return None

    async def no_sleep(d, *a, **k):
        return None

    real_sleep = wcl.asyncio.sleep
    wcl.asyncio.sleep = no_sleep
    try:
        # (a) three failures, then a NEW match must still get replies
        async def streak_then_new_match():
            api = _Api()
            cfg = wcl.LoopConfig(typing_indicator=False, opener_delay_s=(0, 0))
            loop = wcl.WsChatLoop(api, None, _Eng(), cfg)
            loop.self_id = "me"
            loop.conversation_id = "c1"
            loop.partner = wcl.Partner(id="p1", username="a")
            api.fail_next = 3
            for _ in range(3):
                await loop._send("x")
            streak = loop._send_failures
            new_match = {"match": {"conversation": {"id": "c2", "participants": [
                {"profile": {"id": "me"}}, {"profile": {"id": "p2", "username": "b"}}]}}}
            await loop._enter_match_if_open(new_match)
            await loop._handle_chat_message({"message": {"author": {"id": "p2"},
                                                         "conversationId": "c2",
                                                         "content": "hi"}})
            return streak, api.sent
        streak, sent = asyncio.run(streak_then_new_match())
        check("setup: 3 consecutive failures recorded", streak == 3, str(streak))
        check("v26: failure streak does not block the next match's reply",
              ("c2", "ok") in sent, f"sent={sent}")

        # (b) conversation ends during the reply delay -> nothing sent to it
        async def conv_changes_during_delay(new_conv):
            api = _Api()
            loop = wcl.WsChatLoop(api, None, _Eng(), wcl.LoopConfig(typing_indicator=False))
            loop.conversation_id = "c1"
            loop.partner = wcl.Partner(id="p1", username="a")
            async def moving_sleep(d, *a, **k):
                loop.conversation_id = new_conv   # match ended / next match started
            wcl.asyncio.sleep = moving_sleep
            try:
                await loop._send("hello")
            finally:
                wcl.asyncio.sleep = no_sleep
            return api.sent, getattr(loop.stats, "dropped_replies", None)

        sent_empty, dropped_empty = asyncio.run(conv_changes_during_delay(""))
        check("v26: no send to an empty conversation after match end",
              sent_empty == [], f"sent={sent_empty}")
        sent_other, dropped_other = asyncio.run(conv_changes_during_delay("c9"))
        check("v26: no send to a different partner's conversation",
              all(cid != "c9" for cid, _ in sent_other), f"sent={sent_other}")
        check("v26: dropped reply is counted in stats (visible in session stat line)",
              dropped_empty == 1 and dropped_other == 1,
              f"dropped={dropped_empty},{dropped_other}")
    finally:
        wcl.asyncio.sleep = real_sleep


# ---------------------------------------------------------------- session worker cleanup (v26)
def test_worker_cleanup() -> None:
    """v26: if WsChatLoop.start() fails (e.g. self_id lookup), the API session
    must still be closed. Written before the fix; must fail first."""
    print("\n[session worker cleanup]")
    from core import session_chat as sc

    closed = {"api": False}

    class _Api:
        def __init__(self, cookies, user_agent=""):
            pass
        async def me(self):
            return {"username": "tester", "id": "me"}
        async def self_id(self):
            raise RuntimeError("simulated self_id failure")
        async def close(self):
            closed["api"] = True

    class _Socket:
        def __init__(self, *a, **k):
            pass
        def set_event_handler(self, h):
            pass
        async def start(self):
            return None
        async def stop(self):
            return None

    class _Engine:
        def __init__(self):
            pass

    orig = (sc.ChitchatApi, sc.ChitchatSocket, sc._ChatRuleEngine)
    sc.ChitchatApi, sc.ChitchatSocket, sc._ChatRuleEngine = _Api, _Socket, _Engine
    try:
        w = sc.SessionChatWorker.__new__(sc.SessionChatWorker)
        w._cookies, w._ua, w._label = {"token": "x"}, "ua", "t"
        w._max_matches, w._stop_requested = 0, False
        w._loop, w._chat_loop = None, None
        w.log_signal = type("S", (), {"emit": lambda self, m: None})()
        w.session_signal = type("S", (), {"emit": lambda self, *a: None})()
        try:
            asyncio.run(w._amain())
            raised = False
        except RuntimeError:
            raised = True
        check("setup: start failure propagates", raised)
        check("v26: API session closed when loop start fails", closed["api"])
    finally:
        sc.ChitchatApi, sc.ChitchatSocket, sc._ChatRuleEngine = orig


def main() -> int:
    test_codec()
    test_partner()
    test_find_by_nonce()
    test_send_message()
    test_reply_timing()
    test_loop_safety()
    test_worker_cleanup()
    failed = [n for n, ok in _results if not ok]
    print(f"\nRESULT: {len(_results) - len(failed)}/{len(_results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
