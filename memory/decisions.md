# DECISIONS (কেন এমন বানানো হলো — newest first)

**নিয়ম:** এখানকার decision ভাঙতে চাইলে আগে নতুন entry লিখে justify করো।

## 2026-10-10 | Browser rest বন্ধ করা হয়েছে

ইউজার নির্দেশ: rest off. Settings থেকে আগেই সরানো ছিল, এখন code+config থেকেও সরানো. Rest চাইলে ফেরানো যাবে (আগের logic: commit 65ba433 বা picccccccfull-project-v20.zip-এর browser_automation.py).
## 2026-10-10 | Rest Interval/Duration: UI থেকে সরানো, config.json-এ রেখে দেওয়া

কারণ: user v17-এ Dashboard rest fields বাদ চেয়েছিলেন; Settings-এও একটাই New Chat Delay চেয়েছেন. Browser mode-এ rest এখনো config মান (8–15 min কাজ, 2–3 min বিরতি) অনুযায়ী চলে. বিকল্প: rest logic বন্ধ করা — ইউজারের সিদ্ধান্ত অপেক্ষায় (open_questions).
## 2026-10-10 | No reply cap; silence timeout is the only idle rule

Reason: skip before snap share was caused by Max Replies 8 (dashboard + engine), which counted greeting/age/country replies. Chosen: cap off by default, chat until snap share; silence timeout 90s visible in Settings. Alternatives rejected: skip at 6-9s silence (kills slow-replying good chats), raise cap to 20 (still arbitrary). Safety: no hard ceiling now; EVA_MAX_REPLIES available if user wants one back.
## 2026-10-10 | AGENTS.md + skills live inside root project zip, not only in repo

Reason: user runs the root project eva-full-project on Windows; agents working on the deliverable must see its rules. Repo eva/ is R&D workspace and only points to root project. Alternative considered: put skills only in repo - rejected because deliverable zip would lack them.
## 2026-10-10 | v10: report share-safe rule

Debug report NEVER contains session.json content (only exists/has_token booleans + cookie NAMES) and WS frame previews scrub socket cookie values. mask_secrets masks any key containing token/cookie/password/authorization/secret. Regression test asserts secret value absent from report text.
## 2026-10-10 | v9: settings ek jaygay (BOT SETUP)

Architecture answer: mood dashboards e shudhu mood-specific controls (browser/session/START); shared settings (engine, fixed_file, snap_file/snap_usernames, loop) ek BOT SETUP page e -- karon dui mood ek config file chalay. Duplicated per-page widget sets er sync bug risk mone rakhe ek set e naamano hoyeche.
## 2026-10-10 | v8 mood architecture

Mood = separate dashboard pages in one QStackedWidget (HOME + browser + session). Qt constraint: same widget cannot be in two layouts -> per-page engine/loop widget sets kept in sync via collect_engine/apply_engine_all. Browser mood bot still uses WS transport (captured protocol); visible browser shows chats live via site's own socket -- no new protocol guessing.
## 2026-10-10 | v7 engine model: flow|fixed only

Reply engine options final: flow = legacy funnel (input/output txt banks, snap_usernames) ar fixed = fixed txt line-by-line (user-er purano Fixed SMS mode)। Persona/template engine UI+config theke sorano; eva/replies.py module rakha hoyeche shudhu test compat-er jonno।
## 2026-10-10 | Human pacing from legacy config, not hardcoded

- ইউজারের পুরনো প্রজেক্টের human_behavior/chat_timing মানগুলো config-এর `timing` section-এ সরানো হলো (DEFAULT_TIMING fallback)। কারণ: realism টিউন করা ইউজার code ছাড়াই পারবে; মানগুলো তার নিজের প্রজেক্টে proven।

## 2026-10-10 | No python-socketio library — raw wire protocol on aiohttp
- Socket.IO v4/Engine.IO সরাসরি `eva/transport/socketio_codec.py`-তে implement করা।
- কারণ: full control, capture-exact behavior, zero extra deps, fully testable offline। ইউজারের পুরনো প্রজেক্টের AGENTS.md-ও এটাই বলত ("Do not guess" era)।

## 2026-10-10 | Reply engine: flow (txt banks) default, simple fallback
- ইউজারের মূল সম্পদ = তার `data/input|output` txt bank funnel। Config-এ `"engine": "flow"` দিলে EvaFlowBot চলে; `"simple"` হলে persona templates।
- FlowReplyEngine (`eva/brain/flow_reply_engine.py`) adapter pattern: WsChatLoop শুধু opener/reply/forget/delay_for চেনে।

## 2026-10-10 | Desktop dashboard = PyQt6 (ইউজারের পছন্দ), web = alternative
- ইউজার স্পষ্ট বলেছিল "exe dashboard aro professional" — তার পুরনো প্রজেক্টও PyQt6 ছিল।
- GUI thread-এ Qt, bot আলাদা thread-এ asyncio loop (BotWorker); QTimer polling snapshot() দিয়ে — thread-safe।

## 2026-10-10 | CDP login: dedicated profile + Storage.getCookies (page fallback)
- Browser profile: `data/chrome-profile` (login একবার হলে থেকে যায়)।
- Cookie pull: ব্রাউজার-level `Storage.getCookies` → fail করলে page-level `Network.getAllCookies`। Filter: domain-এ 'chitchat.gg' + নাম token/__Secure-text-session।
- Save-এর আগে live verify (GET /users/me) — না মিললেও save হয় কিন্তু 'unverified' দেখায়।

## 2026-10-09 | Empty 0-byte body on /match, typing, disconnect, read
- Capture proof: POST /match 32×, typing 14×, PATCH disconnect 18× — সব body_size=0, শুধু Content-Type: application/json header।
- কাজের জায়গা: `chitchat_api.py` — `headers={"Content-Type": "application/json"}`, `json={}` নয়।

## 2026-10-09 | Message send = REST multipart, NOT WebSocket
- Capture: POST /users/me/conversations/{id}/messages, ct=multipart/form-data, response 201 Message object with nonce echo।
- Multipart field names (content, nonce) response keys থেকে inferred (tool-এ body capture হয়নি) — তাই 400 হলে JSON body fallback আছে (`message_body_format` config)।

## 2026-10-09 | ONE socket per account (browser চালায় দুটো, আমরা একটা)
- Capture-এ প্রতিটা event দুবার আসত (দুই socket)। Server প্রতি user-এ dedupe করে; capture-এ `41` (server disconnect) দেখা গেছে duplicate-এর সময়। তাই bot সবসময় single socket।

## 2026-10-09 | Auth = cookies only (token JWT + __Secure-text-session)
- WS CONNECT payload-এ শুধু {"release": sha} — auth নেই। REST-ও cookie-চালিত। Browser UA copy করা হয় capture থেকে (Chrome 155 Win)।

## 2026-10-09 | Queue-wait: poll GET /match/active, blind re-POST নয়
- Queue wait capture-এ ছিল না (সব match instant)। Blind re-POST করলে server-side already-inQueue conflict হতে পারে। তাই 15s interval-ে /match/active poll; inQueue=false হলে তবেই re-POST।

## 2026-10-09 | Own-message + own-typing echo filter (author/userId == self_id)
- Capture-proven: নিজের message-ও chatMessage হয়ে ফিরে আসে। self_id = GET /users/me থেকে। এটা না ফিল্টার করলে bot নিজের সাথেই চ্যাট করে বসে / কখনো idle-skip করে না।

## 2026-10-09 | Reply pacing: typing indicator → engine delay → send
- Capture flow: typing POST আসে message POST-এর ঠিক আগে (~0.5s)। Flow engine delay = reaction(0.5-1.2) + read(1-3) + typing@6-12cps (ইউজারের config.json ranges থেকে)।

## 2026-10-10 | v18: END without snap -> farewell once, then next user
- Problem (v17): snap না হয়ে engine END হলে প্রতিটা partner message-এ closer যেত ("ttyl, snap me") — chat কখনো শেষ হতো না।
- Fix: eva_flow.reply() — stage END এবং farewell_sent=True হলে "" ফেরত; farewell প্রথমবার END-এ গেলে sets farewell_sent. Browser: empty reply → chat শেষ → পরের user. ws_chat_loop আগে থেকেই empty reply-তে পরের user-এ যায়।
- Snap rules অপরিবর্তিত (_should_share, share/ask flow, stage functions). test_flow 126/0, test_live 44/44 (legacy engine, unchanged), test_fuzz 4/4.
- Shipped: picccccccfull-project-v18-END-FAREWELL-ONCE.zip (v17 zip removed).

## 2026-10-10 | v19: Picture sender সম্পূর্ণ সরানো
- কারণ: user চেয়েছে picture option dashboard ও project থেকে পুরোপুরি বাদ দিতে।
- সরানো হয়েছে: Dashboard PICTURE SENDER group + "PICS SENT"/"Pics" stat ও column, Pictures page ও sidebar entry, Settings-এর picture config load/save, browser (`_setup_pic_pool`, `_next_pic_file`, `_send_picture`, `_maybe_click_send_after_upload`, middle-chat-point block), thread_manager ও ThreadManager/ChitchatAutomation-এর pic পরামিতি, session feed 'pic' line, log parsing।
- অপরিবর্তিত: chat engine (eva_flow.py, chat/*, data/*), যার মধ্যে "send pic" keyword detection ও pic_mood_reply_rules.json আছে — এগুলো picture sender নয়।
- যাচাই: py_compile, pyflakes (নতুন issue নেই), test_flow 126/0, test_live 44/44, test_fuzz 4/4, ChitchatAutomation ও ThreadManager constructor stub-সহ চালু (PyQt6/winsound sandbox-এ নেই, তাই GUI launch হয়নি)।
- Shipped: picccccccfull-project-v19-NO-PICTURES.zip (v18 zip removed).
