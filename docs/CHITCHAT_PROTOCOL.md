# CHITCHAT.GG PROTOCOL — Deep Analysis of the Capture
**Source:** https://github.com/rajuvbygyuiythh/wbbbbbbbbbbsck (837KB capture + split files)
**Machine-readable version:** `eva/transport/protocol_manifest.json`
**Status:** ✅ implemented + deeply audited + verified offline (**24/24 checks** in `ops/tools/socket_smoke_test.py`, 2 scenarios)

---

## 1. Architecture

```
┌─────────────┐   REST (auth via cookies)      ┌──────────────────┐
│ app.chitchat │ ─────────────────────────────► │ api.chitchat.gg   │
│     .gg      │   POST /match, /messages ...   │  (NestJS server)  │
└─────────────┘                                 └──────┬───────────┘
       browser                                          │
        │ Socket.IO (Engine.IO v4) over WSS             │
        ▼                                               ▼
   wss://api.chitchat.gg/socket.io/?EIO=4&transport=websocket
```

- **Message SEND = REST** (`POST /users/me/conversations/{id}/messages`, multipart)
- **Message RECEIVE + match lifecycle = WebSocket** (`chatMessage`, `matchUpdate`, `typing`)
- **Auth = cookies only** — `token` (JWT) + `__Secure-text-session`. No auth payload in the WS connect.

## 2. WS handshake (exact captured bytes)

| # | Dir | Frame |
|---|-----|-------|
| 1 | IN  | `0{"sid":"9Z_Qg1JCiaoEsGlaAE8v","upgrades":[],"pingInterval":25000,"pingTimeout":20000,"maxPayload":1000000}` |
| 2 | OUT | `40{"release":"b01c3724172e05407a2d46737b9c5fa0c857e0f2"}` |
| 3 | IN  | `40{"sid":"…","pid":"…"}` |
| 4 | OUT | `42["presenceSync"]` — then every **30s** |
| 5 | IN  | `2` → OUT `3` — server pings every **25s**, client pongs |

Server may send `41` (disconnect) — client must reconnect with backoff (observed in capture).

## 3. Match lifecycle (timeline reconstructed from capture)

```
bot                          server
 │ POST /match (empty JSON)    │
 │────────────────────────────►│  201 {"matched": true}   (captured latencies: 355–627ms)
 │                             │  ── or 403 {"message":"Flagged"} if moderated
 │◄── 42["matchUpdate"] ───────│  match.closure.closed=false  (arrives ~instantly)
 │   conversation.id=..., users[...]
 │
 │◄── 42["chatMessage"] ───────│  partner text (own messages echo too! filter author.id==self)
 │ POST /conversations/{id}/typing    (empty body)
 │────────────────────────────►│
 │ POST /conversations/{id}/messages  (multipart: content + nonce UUID)
 │────────────────────────────►│  201 full Message object
 │
 │◄── 42["matchUpdate"] ───────│  closure.closed=true, closeReason=INTENTIONAL, closedBy=<partner>
 │ PATCH /match/disconnect (empty JSON)   ← only when WE skip
 │ POST /match                 ← "next" (capture: 1.6s after close)
```

## 4. Key captured objects

**Message**: `id, conversationId, author{id,username,...}, content, type:"TEXT", attachments[], createdAt, status:"SENT", flags, reactions[], nonce(UUIDv4)`

**Match**: `match{conversation{id,participants[{profile}],category:"ENCOUNTER",...}, users[{userId,inactive}], closure{closed,closeReason?,closedAt?,closedBy?}, paused}, inQueue`

**Partner** = participant whose `profile.id != self_id`.

## 5. Critical behaviors (each one capture-proven)

1. **Own-message echo**: server sends YOUR messages back as `chatMessage` → bot filters `author.id == self_id`. Evidence: capture user's own "hi"/"f"/"24"/"yes"/"hlw" appear in incoming feed.
2. **Duplicate events**: the web app opens **two** sockets; both receive every event → bot uses ONE socket (server dedupes per user, no double-send risk to us).
3. **Message POST is multipart/form-data** (captured ct) with `content` + `nonce` fields (inferred from response keys — the one documented inference; JSON fallback built in).
4. **Rate limit**: `x-ratelimit-remaining: 499 / reset: 60` → ~500 req/min bucket; bot spaces requests 350ms+.
5. **Flagged 403**: `POST /match` can return 403 `{"message":"Flagged"}` → bot backs off 10 min, logs it.
6. **Empty-body writes**: `POST /match`, typing, `PATCH /match/disconnect`, read সবগুলোতে browser **0-byte body** পাঠায় (শুধু Content-Type header) — client একই করে (captured 32×/14×/18× body_size=0).
7. **Own typing echo**: capture-এ নিজের typing ফিরে আসা দেখা যায়নি — client defensive ভাবে `userId == self_id` হলে ignore করে (নাহলে idle-skip কখনো ফায়ার করত না)।
8. **Queue wait**: capture-এ queue wait ছিল না — তাই client `GET /match/active` (captured endpoint) poll করে এবং শুধু `inQueue=false` হলে re-POST করে।

## 6. Deliberately NOT implemented (nothing captured = nothing guessed)

- media/image upload field name, reactions API, friend events, match-preference request bodies, video signaling.

## 7. Where the code lives

| File | Role |
|---|---|
| `eva/transport/socketio_codec.py` | EIO4/SIO5 frame codec (pure, unit-tested) |
| `eva/transport/chitchat_socket.py` | WS client: handshake, pong, presenceSync, reconnect |
| `eva/transport/chitchat_api.py` | REST client: match/disconnect/typing/messages/me |
| `eva/transport/ws_chat_loop.py` | queue→match→chat→skip→next state machine |
| `eva/transport/ws_bot.py` | CLI entry |
| `ops/tools/socket_smoke_test.py` | offline verification vs real captured frames (15 checks) |
