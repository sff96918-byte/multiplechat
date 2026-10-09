"""EVA chitchat.gg WS bot — CLI entry point.

Usage:
  python -m eva.transport.ws_bot --session configs/session.json --config configs/chitchat_bot.json --debug

Session file (configs/session.json):
  {
    "cookies": {
      "token": "<JWT from your logged-in chitchat.gg browser session>",
      "__Secure-text-session": "<value from DevTools → Application → Cookies>"
    },
    "user_agent": "Mozilla/5.0 ..."   (optional, copy from DevTools)
  }

Build the session file with:  python -m ops.tools.extract_session
Live-test with mock first:    python -m ops.tools.socket_smoke_test
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

from .chitchat_api import ChitchatApi
from .chitchat_socket import ChitchatSocket
from .protocol import DEFAULT_UA
from .ws_chat_loop import LoopConfig, WsChatLoop
from ..replies import Persona, ReplyEngine

ROOT = Path(__file__).resolve().parents[2]


def load_session(path: Path) -> dict:
    if not path.exists():
        sys.exit(
            f"[!] session file not found: {path}\n"
            f"    Create it with: python -m ops.tools.extract_session\n"
            f"    Format: {{\"cookies\": {{\"token\": \"<JWT>\", \"__Secure-text-session\": \"<val>\"}}}}"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    cookies = data.get("cookies") or {}
    if "token" not in cookies:
        sys.exit("[!] session file has no cookies.token (the JWT is required)")
    return data


async def run(args: argparse.Namespace) -> None:
    session = load_session(Path(args.session))
    cfg_data = {}
    cfg_path = Path(args.config)
    if cfg_path.exists():
        cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))

    persona = Persona(**{k: v for k, v in (cfg_data.get("persona") or {}).items()})
    engine = ReplyEngine(persona=persona, config=cfg_data.get("replies"))
    loop_cfg = LoopConfig(**{k: tuple(v) if isinstance(v, list) else v
                             for k, v in (cfg_data.get("loop") or {}).items()})

    ua = session.get("user_agent") or DEFAULT_UA
    cookies = session["cookies"]

    api = ChitchatApi(cookies, user_agent=ua,
                      message_body_format=cfg_data.get("message_body_format", "multipart"))
    socket = ChitchatSocket(cookies, user_agent=ua)

    # -- preflight: session valid? moderation ok?
    me = await api.me()
    print(f"[ok] session valid — logged in as {me.get('username')} (id={me.get('id')}, gender={me.get('gender')})")
    standing = await api.moderation_standing()
    if standing.get("standing") not in (None, "good"):
        print(f"[!] moderation standing = {standing.get('standing')} — bot may be limited: {standing}")
    active = await api.match_active()
    print(f"[ok] match/active inQueue={active.get('inQueue')}")

    loop = WsChatLoop(api, socket, engine, loop_cfg, on_event=lambda e, d: None)

    stop_evt = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, stop_evt.set)
        except NotImplementedError:  # windows
            pass

    await loop.start()
    print("[ok] bot running — WS live, queue joined. Ctrl+C to stop.\n")

    reporter = asyncio.create_task(_report_loop(loop))
    await stop_evt.wait()
    reporter.cancel()
    print("\n[.] stopping...")
    await loop.stop("ctrl-c")
    await api.close()
    print("[ok] stopped. stats:", json.dumps(loop.stats.snapshot(), indent=2))


async def _report_loop(loop: WsChatLoop) -> None:
    while True:
        await asyncio.sleep(30)
        s = loop.stats.snapshot()
        w = socket_stats(loop)
        state = loop.state.value
        partner = loop.partner.display() if loop.partner else "-"
        print(f"[stat] state={state} partner={partner} matches={s['matches']} "
              f"sent={s['messages_sent']} recv={s['messages_received']} "
              f"skips(us={s['our_skips']},them={s['partner_skips']}) ws={w}")


def socket_stats(loop: WsChatLoop) -> str:
    st = loop.socket.stats.snapshot()
    return (f"in={st['frames_in']} out={st['frames_out']} pong={st['pings_ponged']} "
            f"reconn={st['reconnects']}")


def main(argv: Optional[list] = None) -> None:
    ap = argparse.ArgumentParser(description="EVA chitchat.gg WebSocket bot")
    ap.add_argument("--session", default="configs/session.json", help="session json path")
    ap.add_argument("--config", default="configs/chitchat_bot.json", help="bot config json path")
    ap.add_argument("--debug", action="store_true", help="verbose protocol logging")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if args.debug:
        for noisy in ("aiohttp", "asyncio"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
