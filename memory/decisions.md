# DECISIONS (কেন এমন বানানো হলো — newest first)
**নিয়ম:** এখানকার decision ভাঙতে চাইলে আগে নতুন entry লিখে justify করো।

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
