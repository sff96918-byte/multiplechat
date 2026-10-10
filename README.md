# multiplechat — Chitchat.gg Live WS Chat Bot

Bot logs in with **your own chitchat.gg browser session** (cookies), matches with
live random users over the real Socket.IO protocol, chats automatically, skips,
and moves to the next person. Everything is built from **real captured traffic** —
no guessing (protocol evidence: `eva/transport/protocol_manifest.json`).

## Quick start (dashboard — recommended)

```bash
pip install aiohttp PyQt6                 # dependencies
run_dashboard.bat                         # or: python -m eva.gui.dashboard
```

Then in the mood dashboard:
1. **Pick a MOOD** — 🌐 Live Browser (visible browser + auto session save) or
   🔑 Session Chat (collect a live session / reuse a saved one)
2. **⚙️ Bot Setup** → pick engine (flow/fixed), snap.txt, fixed script → SAVE
3. **START** → live matching/chatting, stats + logs update live
4. Trouble? → **🐞 Export Debug Report** and share the generated txt (secrets masked)

## Quick start (CLI alternative)

```bash
pip install aiohttp
python -m ops.tools.extract_session            # manual cookie paste
python -m ops.tools.socket_smoke_test          # expect 24/24
python -m ops.tools.session_smoke_test         # expect 7/7
python -m eva.transport.ws_bot --debug --max-matches 1
```

## What it does

```
python -m eva.transport.ws_bot --debug

15:04:00 [ok] session valid — logged in as rheumatic rifleman
15:04:00 [ok] moderation standing = good
15:04:01 bot running — WS live, queue joined
15:04:02 POST /match -> matched=True
15:04:02 MATCHED #1 conv=6ac82704... partner=Michael (m)
15:04:03 US      : 'hey Michael :)'
15:04:07 PARTNER Michael: 'Hey m24'
15:04:09 US      : '24m'
15:04:20 match closed (reason=INTENTIONAL by=partner)   ← they skipped
15:04:22 next match in 3.4s ...
```

## Configuration

- `configs/chitchat_bot.json` — persona (name/age/gender/country), reply templates,
  loop tuning (skip idle, delays, typing indicator). Copy from
  `configs/chitchat_bot.example.json`.
- `configs/session.json` — **secret**, gitignored. Your cookie session.

## Layout

| Path | What |
|---|---|
| `eva/transport/` | capture-backed protocol implementation (see module docstrings) |
| `eva/dashboard/cdp_session.py` | CDP browser launch + cookie pull (session setup) |
| `eva/debugtools.py` | file logging + one-click share-safe debug report |
| `docs/CHITCHAT_PROTOCOL.md` | full protocol analysis with captured evidence |
| `ops/tools/socket_smoke_test.py` | offline verification against exact captured frames |
| `ops/skills/ws-debug.md` | troubleshooting guide |
| `TASK_PROMPT.md` | sorted task spec for agents (Bengali) |
| `project/` | the original multi-site-bot (other sites, dashboard) |

## Safety notes

- One bot instance per account. Opening the site in another tab at the same time
  can get your socket kicked (server sends `41`).
- The bot auto-backs-off 10 minutes if the server answers `403 Flagged`.
- Requests are spaced ~350ms+ and well under the observed rate limit
  (`x-ratelimit-remaining: 499 / 60s`).
