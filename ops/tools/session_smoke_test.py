"""Offline verification of the dashboard session flow — NO real Chrome needed.

Builds a FAKE Chrome DevTools Protocol server (HTTP /json/version + browser WS
answering Storage.getCookies exactly like real Chrome), then runs the real
CdpSessionManager.pull_and_save() against it and asserts:

  [S1] launch() attaches to an already-running CDP endpoint
  [S2] cookies pulled over CDP and filtered to chitchat.gg only
  [S3] configs/session.json written in the ws_bot-compatible format
  [S4] verify step hits /users/me and reports the username
  [S5] a browser WITHOUT login gives a clear error (no token cookie)

Run:  python -m ops.tools.session_smoke_test
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from aiohttp import web

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eva.dashboard.cdp_session import CdpSessionManager  # noqa: E402


class FakeChrome:
    """Minimal CDP: /json/version, /json, browser WS with Storage.getCookies."""

    def __init__(self, cookies: List[Dict[str, Any]], me: Dict[str, Any]) -> None:
        self.cookies = cookies
        self.me = me
        self.port = 0
        self.runner: web.AppRunner = None  # type: ignore[assignment]
        self._ws = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/json/version", self._version)
        app.router.add_get("/json", self._targets)
        app.router.add_get("/devtools/browser/fake123", self._ws_handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = self.runner.addresses[0][1]

    async def stop(self) -> None:
        await self.runner.cleanup()

    async def _version(self, _req: web.Request) -> web.Response:
        return web.json_response({
            "Browser": "Chrome/155.0.0.0 FAKE",
            "User-Agent": "TestUA/1.0",
            "webSocketDebuggerUrl": f"ws://127.0.0.1:{self.port}/devtools/browser/fake123",
        })

    async def _targets(self, _req: web.Request) -> web.Response:
        return web.json_response([{"type": "page", "url": "https://chitchat.gg/"}])

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws = ws
        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                break
            data = json.loads(msg.data)
            if data.get("method") == "Storage.getCookies":
                await ws.send_json({"id": data.get("id"),
                                    "result": {"cookies": self.cookies}})
        return ws


async def run(results) -> None:  # noqa: ANN001
    tmp = Path(tempfile.mkdtemp(prefix="eva-sess-test-"))

    # ---- case A: logged-in browser
    fake = FakeChrome(
        cookies=[
            {"name": "token", "value": "jwt-abc-123", "domain": ".chitchat.gg"},
            {"name": "__Secure-text-session", "value": "sess-xyz", "domain": "chitchat.gg"},
            {"name": "unrelated", "value": "no", "domain": "google.com"},
            {"name": "_pk_id", "value": "matomo", "domain": "chitchat.gg"},
        ],
        me={"id": "u1", "username": "dashboard_tester", "gender": "F"},
    )
    await fake.start()

    # mock REST for the verify step (dashboard hits real api normally)
    rest = web.Application()
    async def me_handler(_r):
        return web.json_response(fake.me)
    rest.router.add_get("/users/me", me_handler)
    fake_me_runner = web.AppRunner(rest)
    await fake_me_runner.setup()
    site = web.TCPSite(fake_me_runner, "127.0.0.1", 0)
    await site.start()
    me_port = fake_me_runner.addresses[0][1]

    mgr = CdpSessionManager(cdp_port=fake.port, session_path=tmp / "session.json",
                            verify_url=f"http://127.0.0.1:{me_port}/users/me")

    launch = await mgr.launch()
    results.check(launch["status"] == "already-running",
                  "[S1] launch() attaches to a running CDP endpoint (chrome open থাকলে attach)",
                  detail=str(launch))

    out = await mgr.pull_and_save()
    results.check(out.get("saved") is True and out.get("username") == "dashboard_tester",
                  "[S2+S4] cookies pulled via CDP Storage.getCookies + verified username",
                  detail=str(out))
    results.check(sorted(out.get("cookie_names", [])) == ["__Secure-text-session", "token"],
                  "[S2a] only chitchat.gg token+session cookies picked (domain filter)",
                  detail=str(out.get("cookie_names")))

    saved = json.loads((tmp / "session.json").read_text(encoding="utf-8"))
    results.check(saved.get("cookies", {}).get("token") == "jwt-abc-123"
                  and saved.get("user_agent") == "TestUA/1.0",
                  "[S3] session.json in ws_bot-compatible format (cookies + user_agent)",
                  detail=str(saved))

    await fake_me_runner.cleanup()
    await fake.stop()

    # ---- case B: browser open but NOT logged in
    fake2 = FakeChrome(cookies=[{"name": "_pk_id", "value": "x", "domain": "chitchat.gg"}],
                       me={})
    await fake2.start()
    mgr2 = CdpSessionManager(cdp_port=fake2.port, session_path=tmp / "session2.json",
                             verify_url="http://127.0.0.1:1/users/me", do_verify=False)
    try:
        await mgr2.pull_cookies()
        results.check(False, "[S5] not-logged-in browser -> clear error")
    except RuntimeError as exc:
        results.check("LOGGED IN" in str(exc).upper() or "token" in str(exc).lower(),
                      "[S5] not-logged-in browser -> clear 'login first' error",
                      detail=str(exc))
    await fake2.stop()

    # ---- case C: no CDP at all
    mgr3 = CdpSessionManager(cdp_port=59999, session_path=tmp / "s3.json", do_verify=False)
    try:
        await mgr3.pull_cookies()
        results.check(False, "[S6] no browser -> clear error")
    except RuntimeError as exc:
        results.check("Launch Browser" in str(exc),
                      "[S6] no CDP browser -> 'Launch Browser first' error")
    results.check(mgr3.session_status()["exists"] is False,
                  "[S7] session_status() correct when no session saved yet")


def main() -> None:
    print("=" * 60)
    print("  dashboard session flow — offline smoke test (fake CDP)")
    print("=" * 60 + "\n")

    class R:
        def __init__(self) -> None:
            self.checks = []
        def check(self, ok, name, detail=""):
            self.checks.append((ok, name, detail))
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))

    r = R()
    try:
        asyncio.run(run(r))
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        r.check(False, "scenario crash-free", f"{type(exc).__name__}: {exc}")
    passed = sum(1 for ok, _, _ in r.checks if ok)
    print(f"\n{'='*60}\n  RESULT: {passed}/{len(r.checks)} checks passed\n{'='*60}")
    sys.exit(0 if passed == len(r.checks) else 1)


if __name__ == "__main__":
    main()
