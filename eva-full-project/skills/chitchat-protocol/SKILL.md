---
name: chitchat-protocol
description: chitchat.gg WebSocket/Socket.IO protocol, REST endpoint, match/chat state machine নিয়ে কাজ করার নিয়ম। Protocol বদলানো, নতুন endpoint, বা WS সংক্রান্ত bug-এ এটা পড়ো।
---

# SKILL: chitchat.gg protocol

## Source of truth
- `core/ws_transport/protocol_manifest.json` — প্রতিটা fact + capture evidence + `unknowns_DO_NOT_GUESS`।
- `core/ws_transport/protocol.py` — constant ও frame builder।
- `core/ws_transport/socketio_codec.py` — Engine.IO v4 / Socket.IO v5 frame encode/decode (নিজস্ব, কোনো `python-socketio` নয়)।

## Module দায়িত্ব
| ফাইল | কাজ |
|---|---|
| `chitchat_socket.py` | WS handshake (`EIO4`), namespace connect (`40{...}`), ping/pong, presenceSync, reconnect |
| `chitchat_api.py` | REST: `/users/me`, `POST /match` (empty body), `GET /match/active`, `PATCH /match/disconnect`, typing, messages (multipart; fallback JSON) |
| `ws_chat_loop.py` | state machine: queue → matchUpdate → chat → closed (INTENTIONAL) → requeue |

## নিয়ম
1. **Guess নিষেধ।** নতুন behavior লাগলে আগে manifest-এ evidence খোঁজো; না থাকলে ইউজারকে নতুন browser capture করতে বলো।
2. Rate spacing ≥ 250ms; 403 `Flagged` হলে backoff — সরাবে না।
3. Own message WS echo ignore (`userId == self_id`) — capture-proven।
4. Skip stats: `closedBy == self` vs `partner` আলাদা।
5. `PATCH /match/disconnect` একবারই (`_end_match()` cleanup)।
6. Blind re-POST `/match` নয় — `GET /match/active` ও `inQueue` দেখে।

## Verify
Protocol offline test: `python -m unittest` বা repo-র `ops/tools/socket_smoke_test.py` (যদি এই root project-এ থাকে; না থাকলে repo `sff96918-byte/multiplechat`-এর `ops/tools` ব্যবহার করো)। Protocol বদলালে manifest + fixture একসাথে আপডেট।

## Log লাইন (core/ws_transport থেকে, `log.info` ফরম্যাট)
```
WS handshake sid=... pingInterval=25000ms     ← OPEN ok
WS namespace connected                         ← 40 ok
POST /match -> matched=True                    ← queue joined
MATCHED conv=... partner=...                   ← matchUpdate ok
PARTNER ...: '...'                             ← chatMessage in
match closed (reason=INTENTIONAL by=partner)   ← partner skip
```

## Session/token
Token চাওয়া/দেখানো নিষেধ। Debug-এ শুধু user label ও "token আছে/নেই"।

## v23 — send_message duplicate guard (ws_transport)
- `send_message` শুধু ambiguous failure-এ (timeout, socket drop, 5xx) `GET /users/me/conversations/{cid}/messages?limit=20` দিয়ে একই `nonce` খোঁজে। পেলে সেই message-কে সফল ধরে, আবার POST করে না।
- 4xx definitive, 403 `Flagged` → আগের মতোই raise (`FlaggedError`)।
- Unit test: `python test_ws_transport.py` (22 checks, synthetic fixture)।
- Open unknown (গোপনে ধরে নেবে না): send request-এর exact body/field name capture-এ নেই (14/14 POST body খালি)। `capture.py`-তে `Network.getRequestPostData` ডাকা হয় না — নতুন capture-এ এটা যাচাই করতে হবে।
- Timing evidence (এক session, n=10): inbound chatMessage → bot reply 4.5–11.8 s (median 6.3 s)। Timing পরিবর্তন এই evidence দিয়ে হবে না — আলাদা অনুমোদন লাগবে।

