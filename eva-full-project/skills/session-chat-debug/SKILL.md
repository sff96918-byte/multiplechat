---
name: session-chat-debug
description: SESSION CHAT (token/session দিয়ে browser-ছাড়া live chat) চালু না হওয়া, token/session error, worker বন্ধ/থেমে যাওয়া, বা live chat-এ reply না যাওয়ার সমস্যা debug করতে এটা পড়ো।
---

# SKILL: Session chat debug

## Step 1 — কোন অবস্থায় আটকেছে? (log থেকে)
| `[session]` লাইন | মানে | ব্যবস্থা |
|---|---|---|
| `কোনো session পাওয়া যায়নি` | `account_sessions/*/storage_state.json` ও `configs/session.json` কোথাও নেই | browser mode-এ একবার login (session তৈরি হবে), অথবা Token field-এ acc token paste |
| `chitchat 'token' cookie নেই` | storage_state-এ domain chitchat-এর `token` নেই | ওই account আবার login করে session refresh |
| `[X] ... network/ connect` | sandbox বা PC-তে chitchat.gg পৌঁছায় না | PC-র internet/firewall/VPN চেক; sandbox-এ এটা স্বাভাবিক |
| `[X] /users/me` 401/403 | token expired/invalid | নতুন token নাও; অন্য account try |
| `token valid — logged in as X` তারপর কিছু নেই | WS connect হয়েছে কিন্তু match নেই | `[stat]` লাইন দেখো (state কী); moderation/queue সমস্যা হতে পারে |
| `[done] matches=0` | কোনো partner পায়নি | পরে আবার চালাও; `max-matches` setting চেক |

## Step 2 — Source ও token যাচাই (sandbox/PC উভয়ে চলে)
```bash
QT_QPA_PLATFORM=offscreen python -m core.session_chat --list
```
এটা শুধু source list দেখায় (token/cookie value দেখায় না — boolean/label)। token সমস্যা হলে
`--debug` দিয়ে চালাও:
```bash
QT_QPA_PLATFORM=offscreen python -m core.session_chat --debug --max-matches 1
```
**Secret নিয়ম:** log/output-এ token বা cookie value কখনো কপি করবে না, শুধু আছে/নেই লিখবে।

## Step 3 — Code path (কোথায় দেখতে হবে)
- `core/session_chat.py`
  - `discover_session_sources()` — source list (storage_state + configs/session.json)
  - `resolve_session()` — token field থাকলে সেটাই priority
  - `_cookies_from_storage_state()` — `token` cookie বের করে
  - `_ChatRuleEngine` — reply + `pending_replies` + delay (`delay_for`, `opener_delay`)
  - `SessionChatWorker.run()` → `_amain()` — asyncio loop, preflight `/users/me`, stat প্রতি 5s
  - `request_stop()` — GUI ■ বাটন
- `core/ws_transport/ws_chat_loop.py` — state machine (queue → match → chat → skip → next)
- `core/ws_transport/chitchat_api.py` / `chitchat_socket.py` — REST ও WS client
- `entry/main.py` — `on_chat_message` (thread_id 97), `log_message`, `_session_state`,
  `_update_session_row`, SESSIONS page box

## Step 4 — Reply-এ সমস্যা (connect হয়, কথা হয় না)
1. `data/logs/chat_debug.log` দেখো — কোন category match হয়েছে (`data/input` → `data/output`)।
2. `python tools/live_chat.py` দিয়ে একই message দিয়ে reply মেলাও — engine ঠিক কিনা।
3. Reply খালি হলে: `data/output/<category>.txt` ফাঁকা কিনা, বা `state["pending_replies"]` pop হয়েছে কিনা।
4. Multi-line reply: `"\n"` জোড়া করা হয়; প্রতিটা লাইন আলাদা delay-তে যায়।

## Step 5 — Fix-এর পর verify
```bash
python -m py_compile core/session_chat.py core/ws_transport/ws_chat_loop.py
QT_QPA_PLATFORM=offscreen python -c "import core.session_chat as s; print(s.SESSION_THREAD_ID)"
python test_live.py && python demo_chat.py
```
Live (chitchat.gg) পরীক্ষা শুধু ইউজারের PC-তে সম্ভব — রিপোর্টে সেটা স্পষ্ট লেখো।

## ইউজারের কাছে কী চাইবে
GUI-র **Logs** page বা `data/logs/gui_console.log` থেকে `[session]` লাইনগুলো (token ছাড়া)।
Token-সহ কোনো ফাইল/লাইন চাইবে না।

## Browserless flow (v29)
1. Token সেভ: `python -m core.session_chat --save` — hidden prompt, `/users/me` দিয়ে যাচাই, তারপর `configs/session.json` (0600)। 401 হলে নতুন token নাও।
2. Live chat (GUI ছাড়া): `python -m core.session_chat --run [--max-matches N]`। PyQt6 লাগে না।
3. Token কোথাও print বা log করো না; শুধু user নাম দেখাও।
4. Socket drop-এর পরে match recovery এখনো নেই — live test-এ দেখলে সেটা জানাও (capture লাগবে)।
