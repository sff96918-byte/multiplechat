# PROTOCOL FACTS (verified chitchat.gg behavior)


some body


some body


some body


some body
**Machine-readable source of truth:** `eva/transport/protocol_manifest.json`
**Full analysis:** `docs/CHITCHAT_PROTOCOL.md` — এখানে শুধু quick facts + gotchas।

**Facts (সব capture-proven):**

- WS: `wss://api.chitchat.gg/socket.io/?EIO=4&transport=websocket`, Engine.IO v4/Socket.IO v5 wire format
- Handshake: `0{sid,pingInterval:25000,pingTimeout:20000,maxPayload}` → OUT `40{"release":sha}` → IN `40{sid,pid}` → OUT `42["presenceSync"]` (30s পর পর)
- Server ping `2` → client অবশ্যই `3` pong
- Send message: `POST /users/me/conversations/{cid}/messages` **multipart** (content + nonce UUIDv4) → 201 Message object
- Match: `POST /match` (empty body) → 201 `{"matched":bool}`; match হলে WS-এ `matchUpdate` (closure.closed=false) ~instant
- Skip: `PATCH /match/disconnect` (empty body) → partner-এর কাছে matchUpdate closed=true, closedBy=<আমাদের id>
- closeReason এখন পর্যন্ত শুধু "INTENTIONAL" দেখা গেছে
- Auth: শুধু cookies (`token` JWT + `__Secure-text-session`) — WS payload-এ auth নেই
- Rate limit: login response-এ x-ratelimit-remaining 499 / reset 60 → ~500/min bucket

**Gotchas (এগুলো ভুললে bug হবে):**

- নিজের message-ও `chatMessage` হয়ে echo হয় → filter `author.id == self_id`
- নিজের typing echo-ও আসতে পারে → filter `userId == self_id` + typing কখনো sticky রাখবে না (expire দাও)
- এক event দুবার আসতে পারে (browser দুই socket চালায়) → আমরা single socket, তবু handler idempotent রাখো
- 403 `{"message":"Flagged"}` on POST /match → account temp-unmatchable; bot 10min backoff করে
- Server মাঝে মাঝে `41` পাঠায় → auto-reconnect backoff আছে; এক সাথে browser-এও site খুললে ঘন হয়
- Multipart fields (content/nonce) response keys থেকে inferred — live verify এখনো হয়নি (open_questions দেখো)

**Unknowns — GUESS করবে না:**

- image/media upload field, reactions API, friend events, match-preference request body, video signaling
- নতুন capture লাগলে: ইউজারের পুরনো CDP capture tool দিয়ে নতুন capture → `tests/fixtures/captured_frames.json` update → smoke test run
