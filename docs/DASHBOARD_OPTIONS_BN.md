# EVA DASHBOARD — A to Z Options Guide (বাংলা)
**EXE/Desktop Dashboard:** `run_dashboard_exe.vbs` বা `dist\EVA Dashboard\EVA Dashboard.exe`
**Web Dashboard (বিকল্প):** `run_dashboard.bat` → http://127.0.0.1:8800

---

## 🖥️ EXE DASHBOARD LAYOUT (উপরে থেকে নিচে)

### 📌 SIDEBAR (বাম কলাম)

| # | Option | কী করে | Config-এ mapping |
|---|--------|--------|------------------|
| 1 | **SESSION status label** | ৩ রকম দেখায়: `✓ username` (সবুজ = session valid + verified) / `saved (unverified)` (হলুদ = save হয়েছে কিন্তু verify হয়নি) / `✗ নেই` (লাল = আগে Pull করতে হবে) | `configs/session.json` আছে কিনা + `GET /users/me` verify |
| 2 | **🚀 Launch Browser & Login** | আসল Chrome/Edge window খোলে (dedicated profile: `data/chrome-profile`, debug port 9222) → chitchat.gg খুলবে → আপনি সেখানে LOGIN করবেন। একবার login থাকলে profile মনে রাখে। CDP already চালু থাকলে attach করে। | session.json লেখে না — শুধু browser চালু |
| 3 | **💾 Pull Session** | চালু browser থেকে cookies টেনে আনে (CDP `Storage.getCookies` → fail হলে page-level `Network.getAllCookies`) → শুধু `token` + `__Secure-text-session` (chitchat.gg domain) নেয় → `GET /users/me` দিয়ে verify → `configs/session.json` লেখে (permission 0600) | **session.json তৈরি হয় এখানেই** |
| 4 | **CPU / RAM labels** | আপনার PC-র লাইভ CPU/RAM (2.5s পর পর) | — |
| 5 | **▶ START** | Bot চালু: আগে Settings auto-save → session.json check → thread-এ asyncio bot → preflight (`GET /users/me`, 401 হলে বাংলায় "SESSION মেয়াদ শেষ" guidance) → WS connect → queue join | — |
| 6 | **■ STOP** | Bot বন্ধ + `PATCH /match/disconnect` (thik moto leave) + socket close + stats | — |

### 📌 MAIN PANEL (ডান অংশ, উপরে থেকে)

| # | Group / Option | কী করে | Config key |
|---|----------------|--------|------------|
| 7 | **ENGINE combo** | `flow — SMS detect → input/output matching reply` = আপনার পুরনো funnel logic (greeting→age→country→flirty→snap) [DEFAULT] / `fixed — একটা fixed txt ফাইল, line-by-line reply` = পুরনো Fixed SMS মোড | `engine`: `"flow"` বা `"fixed"` |
| 8 | **Snap** | Snap username (কমা দিয়ে একাধিক দিলে round-robin ঘুরবে)। Reply-র `%username%` placeholder এখান থেকে বসে। লেখা হয় `eva/brain/data/snap_ids.txt`। ⚠️ flow engine-এ এটা অবশ্যই লাগবে | `snap_usernames`: `["name1","name2"]` |
| 9 | **FIXED SCRIPT** (file + Browse) | শুধু `fixed` engine-এ কাজ করে — txt ফাইলের প্রতি লাইন = একটা reply, ক্রম অনুযায়ী যাবে। opener = ১ম লাইন, প্রতিটা partner SMS-এ পরের লাইন। লাইন ফুরালে bot match skip করে next-এ যায়। `#` = comment | `fixed_file`: `"configs/fixed_script.txt"` |
| 10 | **Skip idle (sec)** | Partner এত সেকেন্যু চুপ থাকলে আমরা skip করে next-এ যাব (typing করলে থামবে; আপনার নিজের typing echo গোনা হয় না) | `loop.skip_idle_s` (15–600, default 90) |
| 11 | **Typing indicator** | ON হলে message পাঠানোর আগে `POST .../typing` যাবে (partner-এর screen-এ "typing..." দেখবে — realistic) | `loop.typing_indicator` (true/false) |
| 12 | **Auto next match** | ON হলে এক match শেষ (partner skip/আমাদের skip) → 2–5s পর আবার queue। OFF হলে এক match শেষে থেমে থাকবে | `loop.auto_next` (true/false) |
| 13 | **Max matches (0=∞)** | এই সংখ্যক match হলে auto-stop (প্রথম test-এ 1 দিন!) | CLI `--max-matches` এর GUI রূপ |
| 14 | **💾 Save Settings** | উপরের সব দেখা UI value → `configs/chitchat_bot.json`-এ লেখে (START চাপলেও auto-save হয়) | — |
| 15 | **CURRENT MATCH** | লাইভ দেখায়: `State` (QUEUING/CHATTING/IDLE/STOPPED/ERROR) + `Partner` (username) + `Flow` (funnel stage + কারণ, যেমন `MIDDLE · ask snap -> ask_snap.txt`) | — |
| 16 | **STATS** | Matches / Sent / Recv / Skips T,U (তারা/আমরা) / WS in,out (frames) / Uptime — 1s refresh | — |
| 17 | **LIVE LOG** | সব লগ লাইভ স্ট্রিম: WS handshake, matchUpdate, PARTNER message, US reply (nonce সহ), skip, error — debug-এর প্রধান জায়গা | — |

### 📁 CONFIG FILE (`configs/chitchat_bot.json`) — GUI-র বাইরের সেটিংস

| Key | মানে | Default |
|-----|------|---------|
| `engine` | flow বা fixed | `"flow"` |
| `snap_usernames` | snap pool (rotate) | — |
| `fixed_file` | fixed engine-এর script txt-এর path | `"configs/fixed_script.txt"` |
| `loop.*` | উপরের 10–13 + `next_delay_s:[2,5]`, `min_reply_delay_s:1.0`, `opener_delay_s`, `queue_timeout_s:120`, `skip_after_msgs:25` | example অনুযায়ী |
| `message_body_format` | `"multipart"` (capture-backed) / `"json"` (fallback, multipart reject হলে auto-try-ও হয়) | `"multipart"` |
| `timing.*` | **মানুষের মতো pacing (v6)** — নিচে বিস্তারিত | legacy মান |

### ⏱️ `timing` (config file-এ এডিট করতে হয় — এটা GUI-তে নেই)

| Key | মানে | Default |
|-----|------|---------|
| `reaction_pause_s` | message পেয়ে react করার আগে থামা | [0.5, 1.2] |
| `typing_speed_cps` | টাইপিং গতি (chars/sec) — লম্বা reply = বেশি সময় | [6.0, 12.0] |
| `read_reply_s` | partner-এর message পড়তে সময় | [1.0, 3.0] |
| `micro_idle_chance` | মাঝে মাঝে অকারণে থামার সম্ভাবনা (মানুষের মতো) | 0.25 |
| `micro_idle_s` | সেই থামার সময়কাল | [0.5, 2.0] |
| `new_chat_delay_s` | নতুন match-এ opener-এর আগে অপেক্ষা | [3.0, 6.0] |

### 💬 REPLY BANKS (flow engine — ফাইল এডিট করলেই behavior বদলায়)

**fixed engine (line-by-line):** `configs/fixed_script.txt` — প্রতি non-empty লাইন একটা reply:

```
# comment লাইন skip হয়
hii :)
19 f, n u?
oh nice.. from?
```
opener = ১ম লাইন। প্রতিটা partner SMS-এ পরের লাইন। প্রতি partner-এর pointer আলাদা। লাইন ফুরালে bot ওই match skip করে next match-এ চলে যায়।

```
eva/brain/data/input/<category>.txt   = partner যা লিখলে ধরা পড়বে (trigger)
eva/brain/data/output/<category>.txt  = আমরা যা reply দেব
```
Flow: `greeting` → `age_gender` → `country` → `flirty_questions` → `horny`/`middle_chat/*` → `ask_snap` → `share_snap` (%username%) → **END** (`closer.txt`, 8 reply cap)।
নিজের নতুন category চাইলে: দুই ফোল্ডারেই একই নামে txt রাখুন — auto join হবে।

---

## 🌐 WEB DASHBOARD (বিকল্প, run_dashboard.bat → :8800)

একই কাজ web-এ: 🔑 Session panel (Launch Browser/Save Session/browser path) + 🤖 Bot control (Start/Stop, stats) + ⚙️ Config (engine, fixed file, skip idle, typing, auto next) + 📜 Live log (2.5s refresh)।

---

## ⌨️ CLI (GUI ছাড়া চালাতে)

```bash
python -m eva.transport.ws_bot --debug --max-matches 1
# --session configs/session.json  --config configs/chitchat_bot.json
python -m ops.tools.socket_smoke_test    # offline protocol check (24/24)
python -m ops.tools.session_smoke_test   # offline session check (7/7)
```

## 🩺 সমস্যা হলে (দ্রুত)

| লক্ষণ | সমাধান |
|---|---|
| "SESSION মেয়াদ শেষ (401)" | Browser-এ re-login → Pull Session |
| Launch-এ "browser-not-found" | Chrome/Edge install, বা GUI-র browser path field-এ exe path |
| "Snap Username দাও" error | Settings-এ snap লিখে Save → START |
| matches হয় কিন্তু message যায় না | log-এ "retrying once as JSON" দেখুন → browser থেকে POST /messages-এর payload আমাকে পাঠান |
| `403 Flagged` | account temp-block — bot 10min অপেক্ষা করে; `GET /moderation/standing` দেখুন |
