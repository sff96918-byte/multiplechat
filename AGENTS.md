# AGENTS.md — rules for AI agents working in this repo

Read `TASK_MAP.md` (multi-site legacy) and `TASK_PROMPT.md` (chitchat WS bot) first.

## Non-negotiable rules

1. **No guessing protocol behavior.** chitchat.gg facts live in
   `eva/transport/protocol_manifest.json` — every fact has a capture evidence note.
   Anything in `unknowns_DO_NOT_GUESS` stays unimplemented until a new capture proves it.
2. **No new WS/Socket.IO dependencies.** The wire protocol is implemented on
   `aiohttp` in `eva/transport/socketio_codec.py` + `chitchat_socket.py`. Do not
   add `python-socketio` or similar.
3. **Secrets never committed.** `configs/session.json`, cookies, JWTs — gitignored.
   If a user pastes a token in chat, do not write it into any tracked file.
4. **Verification gate.** After ANY change under `eva/` run:
   - `python -m unittest tests.test_protocol_units`
   - `python -m ops.tools.socket_smoke_test` (must stay 24/24)
   If you changed protocol behavior intentionally, update
   `tests/fixtures/captured_frames.json` + the manifest together, and say why.
5. **Rate discipline.** Keep request spacing >= 250ms in `ChitchatApi`
   (`request_spacing_s`). Do not remove the 403-Flagged backoff.

## Verification commands

```bash
python -m unittest tests.test_protocol_units -v
python -m ops.tools.socket_smoke_test      # 24/24
python -m ops.tools.session_smoke_test     # 7/7 (dashboard session flow)
```

## Dashboard

- `eva/dashboard/server.py` (web UI + bot control), `cdp_session.py` (browser
  launch + cookie pull via CDP). Default bind 127.0.0.1 — do NOT change to
  0.0.0.0 by default (dashboard controls the bot).
- `configs/session.json` is written by the dashboard Save Session button.

## Where things are

- Protocol truth: `eva/transport/protocol_manifest.json`, `docs/CHITCHAT_PROTOCOL.md`
- Bot runtime: `eva/transport/ws_bot.py` (CLI), `ws_chat_loop.py` (state machine)
- Captured frames for tests: `tests/fixtures/captured_frames.json`
- Legacy multi-site system: `project/` (see `project/TASK_MAP.md`)
