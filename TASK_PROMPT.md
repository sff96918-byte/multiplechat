# TASK PROMPT — Chitchat.gg Live WS Chat Bot
> এই প্রম্পটটা যেকোনো agent-কে দিলে সে পুরো requirement টা বুঝে কাজ করতে পারবে।
> Status: **BUILD COMPLETE + OFFLINE-VERIFIED** — নিচে কী হয়েছে, কী বাকি, সব লেখা আছে।

---

## 🎯 মূল লক্ষ্য (এক লাইনে)

**chitchat.gg-তে আমার নিজের account-এর session দিয়ে bot-কে live random stranger-দের সাথে
automatically match → chat → reply → skip → next করাও — real captured protocol ব্যবহার করে,
কোনো guess ছাড়া।**

---

## 📦 Source of Truth (আর নতুন করে capture লাগবে না)

Capture repo: `https://github.com/rajuvbygyuiythh/wbbbbbbbbbbsck`
- `15_websocket_all.json` — raw Socket.IO frames (handshake, ping/pong, presenceSync, events)
- `05_incoming_messages.json` — real `chatMessage` payload
- `07_match_updates.json` — real `matchUpdate` (open + closed INTENTIONAL)
- `16_http_all.json` — REST + **response bodies** (`{"matched":true}`, message object with `nonce`, self profile)
- `17_endpoints_summary.json` — endpoint list + status codes

**সব analyzed fact এখন repo-র ভিতরে:**
- `eva/transport/protocol_manifest.json` ← এটা read করো, source of truth
- `docs/CHITCHAT_PROTOCOL.md` ← human-readable deep analysis

## 🧠 AGENT MEMORY (প্রথমে এটা)

তুমি (agent) নতুন — আগের সব কাজের নোট `memory/` ফোল্ডারে:
```bash
python -m ops.tools.memory recent 6      # শুরুতে চালাও
python -m ops.tools.memory search <topic> # task-related
# কাজ শেষে:
python -m ops.tools.memory add session "..." --body "..."
```
বিস্তারিত নিয়ম: **AGENTS.md (root)** — ওটা আগে পড়ো।

## ⚠️ HARD RULES (ভাঙলে task fail)

1. **কোনো `socketio` pip package নয়** — wire protocol সরাসরি `aiohttp` WS-এ implement করা (already done)
2. **Capture-এ নেই এমন কিছু guess করা যাবে না** — unknowns লিস্টেড আছে manifest-এর `unknowns_DO_NOT_GUESS`-এ
3. **Session/credential কখনো git-এ commit করা যাবে না** (`configs/session.json` gitignored)
4. প্রতিটা protocol behavior change-এর পর **`python -m ops.tools.socket_smoke_test` 24/24 PASS** করতে হবে

---

## ✅ যা ইতিমধ্যে BUILD হয়ে গেছে (আর বানাতে হবে না)

| Deliverable | File | Status |
|---|---|---|
| Socket.IO codec (EIO4/SIO5) | `eva/transport/socketio_codec.py` | ✅ unit-tested |
| WS client (handshake, pong, presenceSync, reconnect) | `eva/transport/chitchat_socket.py` | ✅ smoke-tested |
| REST client (match, disconnect, typing, messages, me) | `eva/transport/chitchat_api.py` | ✅ smoke-tested |
| Chat loop state machine (queue→match→chat→skip→next) | `eva/transport/ws_chat_loop.py` | ✅ smoke-tested |
| Reply engines: flow (txt-bank funnel) + fixed (line-by-line SMS) | `eva/brain/flow_reply_engine.py` + `eva/brain/fixed_reply_engine.py` | ✅ |
| CLI bot entry | `eva/transport/ws_bot.py` | ✅ |
| Offline verification (mock server replays REAL captured frames) | `ops/tools/socket_smoke_test.py` | ✅ **15/15 PASS** |
| Unit tests | `tests/test_protocol_units.py` | ✅ 12/12 PASS |
| Session builder tool (manual) | `ops/tools/extract_session.py` | ✅ |
| **Desktop mood dashboard (browser/session moods + CDP session setup)** | `eva/gui/dashboard.py` + `eva/dashboard/cdp_session.py` | ✅ **7/7 session tests** |
| Protocol docs | `docs/CHITCHAT_PROTOCOL.md` + manifest | ✅ |
| Debug skill | `ops/skills/ws-debug.md` | ✅ |

**Test evidence (deep-audit pass 2 — 10 bugs fixed):**
```
RESULT: 24/24 checks passed (2 scenarios)
  Scenario 1 — partner-chat flow:
  [PASS] WS handshake + 40{"release":...} connect (captured bytes)
  [PASS] presenceSync on connect, ping '2' -> pong '3' (captured)
  [PASS] POST /match (EMPTY 0-byte body) -> matchUpdate -> match opened
  [PASS] partner resolved from participants (id != self)
  [PASS] message POST multipart content+nonce UUID (captured ct)
  [PASS] typing POST before reply; partner chatMessage -> auto-reply
  [PASS] own-message WS echo ignored (capture-proven)
  [PASS] matchUpdate closed=true -> detected -> auto requeue
  [PASS] skip stats: closedBy=partner vs closedBy=self correct

  Scenario 2 — our-skip flow:
  [PASS] idle timeout -> exactly ONE disconnect POST (no duplicates)
  [PASS] closedBy==self NOT counted as partner skip
  [PASS] match state + reply-engine stage cleaned (no leak)
```

**Deep-audit-এ যে ১০টা bug fix হয়েছে (সব verify করা):**
1. match/typing/disconnect-এ `json={}` পাঠাত — capture বলে **0-byte empty body** → fixed
2. নিজের skip-ও partner_skips-এ গোনা হতো → fixed (closedBy guard)
3. `auto_next=false` হলে infinite hot-loop → fixed
4. queue timeout-এ blind re-POST (server-এ already inQueue থাকলে conflict) → fixed (GET /match/active poll)
5. send_message বারবার fail করলে ৯০ সেকেন্ড চুপচাপ বসে থাকত → fixed (3 fail = skip)
6. Windows Ctrl+C-তে cleanup skip হতো → fixed (KeyboardInterrupt path + finally)
7. reply-engine per-partner state leak → fixed (`forget()`)
8. নিজের skip-এর পর conversation_id থেকে যেত → duplicate disconnect → fixed (`_end_match()`)
9. handshake wait-এ server `41`/`44` এলে timeout পর্যন্ত hang → fixed
10. **নিজের typing echo**-তে bot চিরতরে "partner typing" ভাবত → idle-skip কখনো কাজ করত না → fixed (self-echo guard + 6s expiry)

**Dashboard (v11):** `run_dashboard.bat` (বা `python -m eva.gui.dashboard`) → mood dashboard (browser/session) →
Launch Browser (CDP) → chitchat.gg login → Save Session (auto cookie pull + verify) → Start Bot।
Session flow verified offline: `python -m ops.tools.session_smoke_test` (7/7, fake Chrome CDP server)।

---

## 🔑 USER-এর কাজ (Phase D — live test, agent এটা করতে পারবে না)

```bash
# 1. Session file বানাও (নিজের browser-এ login থাকা অবস্থায়):
python -m ops.tools.extract_session
#    → DevTools (F12) → Application → Cookies → chitchat.gg
#    → 'token' আর '__Secure-text-session' paste করো

# 2. আগে offline verify (optional but recommended):
python -m ops.tools.socket_smoke_test          # 24/24 আসতে হবে
python -m ops.tools.session_smoke_test         # 7/7 আসতে হবে (dashboard session flow)

# 3. LIVE run (debug দিয়ে):
python -m eva.transport.ws_bot --debug
#    preflight-এ দেখবে: "session valid — logged in as <username>"
#    তারপর: queuing → MATCHED #1 partner=... → chat শুরু
#    Ctrl+C দিলে stats print করে বন্ধ হবে
```

Windows-এ: `run_chitchat_bot.bat` double-click (session.json বানানো থাকতে হবে)।

---

## 🧩 যদি agent-কে নতুন কাজ দিতে চাও, এভাবে বলবে

**Template:**
> "eva/transport/-এর chitchat bot-এ নিচের change টা করো: **[change]**।
> Rules মানো: TASK_PROMPT.md-এর HARD RULES। Capture-backed protocol নিয়ে সন্দেহ
> থাকলে protocol_manifest.json দেখো। কাজ শেষে unittest + socket_smoke_test দুটোই PASS
> করাও। নতুন protocol behavior দরকার হলে আগে আমাকে capture থেকে evidence দেখাও,
> guess করবে না।"

**Valid উদাহরণ:**
- "Reply engine-এ mood system add করো (project/src/mood_manager.py pattern-এ)"
- "skip_idle_s আর next_delay config-কে dashboard control করাও"
- "Partner-এর gender/interest matchUpdate থেকে নিয়ে reply engine-কে condition দাও"
- "একাধিক account session rotate করার system দাও (configs/sessions/*.json)"

**Invalid (agent এগুলো করবে না):**
- ❌ "socketio library use করে simplify করো" (HARD RULE 1)
- ❌ "media/photo পাঠার feature add করো" (capture-এ নেই — HARD RULE 2)
- ❌ "session.json commit করে দাও" (HARD RULE 3)

---

## 🔄 যদি chitchat তাদের protocol বদলায়

লক্ষণ: live-এ handshake/connect কাজ করছে কিন্তু events match করছে না।
তখন: নতুন capture নাও (আগের tool দিয়েই) → `tests/fixtures/captured_frames.json` update করো
→ smoke test চালাও → যে check ভাঙে সেটাই বদলানো জায়গা। বিস্তারিত: `ops/skills/ws-debug.md`
