# BUGS FIXED (আর খুঁজতে হবে না — newest first)


Symptom: x
Cause: y
Fix: z


Symptom: x
Cause: y
Fix: z


Symptom: x
Cause: y
Fix: z


Symptom: x
Cause: y
Fix: z
**Format:** Symptom → Cause → Fix (file) → Verified। নতুন bug debug করার আগে এখানে খোঁজো!

## 2026-10-10 | GUI: walrus-in-lambda + junk statement + wrong relative import
- Symptom: dashboard module কিংবা do_launch crash/সিনট্যাক্স সমস্যা।
- Cause: do_launch-এ ভাঙা walrus expression (`if (browser_path := "")`), poll_stats-এ `sb.moveCursor if False else None` অবশেষ, `from .paths` কিন্তু paths ছিল `eva/paths.py` (এক level উপরে)।
- Fix: plain `cdp_launch_blocking()` call; junk লাইন মুছে; `from ..paths import project_root`। ROOT resolution: `parents[1]` (eva/ থেকে repo root)।
- Verified: module import + ast.parse + BotWorker.snapshot() headless।

## 2026-10-10 | aiohttp টেক্সট-only FormData-কে urlencoded করে ফেলত (multipart হারায়)
- Symptom: mock server-এ Content-Type application/x-www-form-urlencoded — capture ছিল multipart/form-data।
- Cause: aiohttp optimization — text-only fields হলে urlencoded পাঠায়।
- Fix: প্রতিটা field-এ `content_type="text/plain; charset=utf-8"` দিলে multipart enforce হয় (`chitchat_api.send_message`)।
- Verified: smoke test [6a] multipart ct PASS।

## 2026-10-09 | BUG#10: own typing echo → idle-skip কখনো ফায়ার করত না
- Symptom: (mock test [11] ধরেছে) bot partner-কে চিরতরে "typing" ভাবত।
- Cause: আমাদের নিজের typing POST-এর echo ফিরে আসে `_partner_typing=True` set করে; sticky bool কখনো clear হত না।
- Fix: `userId == self_id` typing ignore + sticky bool → `_partner_typing_until = now+6s` (auto-expire)।
- Verified: smoke test [11] PASS।

## 2026-10-09 | BUG#1: write endpoints-এ json={} পাঠাত (capture: 0-byte empty)
- Symptom: protocol mismatch (live-এ server reject করতে পারত)।
- Cause: capture body_size=0 ছিল, আমরা `"{}"` (2 bytes) পাঠাচ্ছিলাম।
- Fix: POST /match, typing, PATCH disconnect, read — সব `headers={"Content-Type": "application/json"}` + খালি body।
- Verified: smoke test [9][9a][10a]।

## 2026-10-09 | BUG#2: নিজের skip-ও partner_skips-এ গণনা হতো
- Cause: closedBy চেক ছিল না। Fix: `closed_by != self_id` guard। Verified [10][11b]।

## 2026-10-09 | BUG#3: auto_next=False → infinite hot loop (POST /match storm)
- Cause: _match_runner-এ else branch ছাড়া ছিল। Fix: `await asyncio.sleep(1.0)`।

## 2026-10-09 | BUG#4: queue timeout-এ blind re-POST /match (double-queue conflict)
- Fix: `_wait_for_open_match()` — 15s পর GET /match/active poll; inQueue=true হলে wait চালিয়ে যায়। Verified [4]।

## 2026-10-09 | BUG#5: send_message বারবার fail → bot চুপচাপ idle বসে থাকত
- Fix: consecutive failure counter; 3 হলে match skip।

## 2026-10-09 | BUG#6: Windows Ctrl+C-তে cleanup skip
- Cause: ProactorEventLoop signal handler NotImplementedError + exception path-এ finally ছিল না।
- Fix: KeyboardInterrupt catch + `try/finally` এ stop()+api.close()+stats print।

## 2026-10-09 | BUG#7: reply engine per-partner state leak
- Fix: `ReplyEngine.forget(pid)` + `_end_match()` থেকে call। Verified [11d]।

## 2026-10-09 | BUG#8: নিজের skip-এর পর conversation_id থেকে যেত → duplicate disconnect
- Fix: single `_end_match()` cleanup point (state=conversation_id/partner/typing reset) — stop() আর cycle দুই জায়গায়ই ব্যবহার হয়। Verified [11a][11c]।

## 2026-10-09 | BUG#9: handshake wait-এ server 41/44 এলে timeout পর্যন্ত hang
- Fix: `_expect()`-এ disconnect/connect_error frame পেলে সাথে ConnectionError raise → reconnect loop।

## 2026-10-09 | matched=true হলেও matchUpdate-এর জন্য অপেক্ষা করত না
- Symptom: mock test [4] FAIL।
- Cause: কোড শুধু matched=false হলে wait করত; কিন্তু capture অনুযায়ী matched=true হলেও matchUpdate WS-এ আসে (~40ms)।
- Fix: matched যা-ই হোক, সবসময় `_wait_for_open_match()`।

## 2026-10-09 | chitchat_socket: aiohttp ws_connect-এ cookies kwarg নেই
- Cause: aiohttp version difference। Fix: Cookie header ম্যানুয়ালি বানানো (browser behavior-এর মতোই)।

## 2026-10-09 | mock servers port 0 → 127.0.0.1:0 connect fail
- Fix: TCPSite-এর পর `runner.addresses[0][1]` থেকে actual port read।
