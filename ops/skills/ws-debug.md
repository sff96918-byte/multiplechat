# SKILL: chitchat.gg WebSocket bot — debug & verification

## Verify order (always this order, cheapest first)

```bash
# 1. Pure logic (codec + reply engine) — no network
python -m unittest tests.test_protocol_units -v

# 2. Full protocol vs captured frames (mock server, offline, ~10s)
python -m ops.tools.socket_smoke_test
#    → 24/24 must PASS. If any FAIL, the protocol layer is broken — fix before live.

# 3. Live session check (touches real api.chitchat.gg with YOUR cookies)
python -m eva.transport.ws_bot --debug
#    preflight prints: username, moderation standing, inQueue
```

## Symptom → cause table

| Symptom | Cause | Fix |
|---|---|---|
| `session file not found` | configs/session.json missing | `python -m ops.tools.extract_session` |
| preflight 401/403 on /users/me | JWT expired or wrong cookie name | re-copy cookies from a logged-in browser |
| `connect_error` right after `40{release}` | token cookie invalid/expired server-side | fresh login → new session.json |
| WS connects, no matchUpdate, POST /match 403 `Flagged` | account temporarily unmatchable (moderation) | bot waits 10 min automatically; check GET /moderation/standing in browser |
| matches happen but no messages sent | multipart rejected → check log line "retrying once as JSON body"; if both fail, capture the browser's POST /messages body field names | set `message_body_format: "json"` in config |
| bot replies to itself | self_id mismatch — preflight `/users/me` didn't match the session cookies | ensure `token` cookie belongs to the logged-in account |
| double replies | two bot instances running | only one instance per account (server allows one session; second socket gets `41`) |
| server sends `41` often | another browser tab/session open with same account | close other chitchat tabs |
| bot never skips idle partners | own typing echo treated as partner typing (old bug) | FIXED: `userId==self_id` typing events ignored; verify with smoke test [11] |
| duplicate `PATCH /match/disconnect` calls | conversation_id lingered after skip (old bug) | FIXED: `_end_match()` single cleanup; verify smoke test [11a] |
| stats show partner_skips increasing when WE skip | closedBy==self counted wrong (old bug) | FIXED: skip-stats guard; smoke test [11b] |
| rejoin queue storms when no partner online | blind re-POST /match on timeout (old bug) | FIXED: waits on captured `GET /match/active`; re-POST only when inQueue=false |

## Reading the logs

```
15:04:01 INFO  eva.chitchat_socket: WS handshake sid=... pingInterval=25000ms   ← OPEN ok
15:04:01 INFO  eva.chitchat_socket: WS namespace connected sid=... pid=...      ← 40/40 ok
15:04:02 INFO  eva.ws_chat_loop: POST /match -> matched=True                    ← queue joined
15:04:02 INFO  eva.ws_chat_loop: MATCHED #1 conv=6ac... partner=Michael (m)     ← matchUpdate ok
15:04:05 INFO  eva.ws_chat_loop: PARTNER Michael: 'Hey m24'                     ← chatMessage in
15:04:07 INFO  eva.ws_chat_loop: US      : '24m' (nonce=2ad1a75e)               ← message POST 201
15:04:20 INFO  eva.ws_chat_loop: match closed (reason=INTENTIONAL by=partner)   ← partner skipped
```

`--debug` adds every raw frame (`WS IN 42["chatMessage"...`) — compare any
suspicious frame against `tests/fixtures/captured_frames.json` structures.

## Session refresh (when JWT expires)

1. Browser → chitchat.gg → logged in
2. DevTools (F12) → Application → Cookies → `https://chitchat.gg`
3. Copy `token` + `__Secure-text-session` values (+ your User-Agent from Console: `navigator.userAgent`)
4. `python -m ops.tools.extract_session` → paste → re-run bot

## Re-capture protocol (if chitchat updates their protocol)

1. Dashboard → CDP Capture Browser → Launch & Capture (same tool as before)
2. Do: queue → chat → send message → skip → next → close
3. Share: `15_websocket_all.json`, `01_send_messages.json`, `04_typing_outgoing.json`,
   `16_http_all.json`, `17_endpoints_summary.json`
4. Update `tests/fixtures/captured_frames.json` → rerun smoke test → fix deltas
