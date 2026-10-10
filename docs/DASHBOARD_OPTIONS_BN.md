# EVA DASHBOARD — A to Z Options Guide (বাংলা)
**EXE/Desktop Dashboard:** `run_dashboard_exe.vbs` বা `dist\EVA Dashboard\EVA Dashboard.exe`
**GUI চালু:** `run_dashboard.bat` double-click (PyQt6 auto-install)

---

## 🏠 MOOD SYSTEM — HOME (v8)

EXE চালু করলে প্রথমে **HOME** পেজ — এখানে ২টা MOOD card। **যেটা select করবে, সেই mood-এর সম্পূর্ণ আলাদা dashboard খুলবে** (main dashboard-এর ভিতরেই ২টা mood dashboard)। উপরের `← Home` দিয়ে যেকোনো সময় ফেরা যায়।

| Mood | কী |
|------|-----|
| 🌐 **LIVE BROWSER MOOD** | ব্রাউজার চোখের সামনে চলবে — বট লাইভ auto-reply করবে (পুরনো মোডের মতো) + browser-এর **session auto-save** হবে |
| 🔑 **SESSION CHAT MOOD** | Session পেজ — ২টা অপশন: লাইভ ব্রাউজার থেকে session collect, অথবা পুরনো saved session দিয়ে headless চ্যাট |

---

## 🖥️ MOOD 1 — 🌐 LIVE BROWSER DASHBOARD

| # | Option | কী করে | Config key |
|---|--------|--------|------------|
| 1 | **🚀 Browser খোলো (live)** | আসল Chrome/Edge window খোলে (dedicated profile `data/chrome-profile`, debug port 9222) → chitchat.gg খোলে। এই ব্রাউজারই চোখের সামনে থাকে — বট chat করলে তা ব্রাউজারেও লাইভ দেখা যায় | — |
| 2 | **💾 Session Save now** | চালু browser থেকে cookies টেনে `configs/session.json`-এ সেভ (CDP `Storage.getCookies` → verify `/users/me`) | session.json |
| 3 | **☑ Session auto-save (প্রতি 60s)** | ON থাকলে বট চলাকালীন প্রতি 60 সেকেন্ডে লাইভ browser থেকে session রি-সেভ হয় (token rotate হলেও ধরা পড়বে)। বিটি বন্ধ থাকলেও browser page-এ থাকলে 60s পর পর auto-save চেষ্টা হয় | `browser_autosave`: `true`/`false` |
| 4 | **START (browser mood)** | চাপার সাথে সাথে লাইভ browser থেকে cookies নিয়ে session.json সেভ → বট চালু। **browser খোলা + login থাকতে হবে** | — |
| 5 | **ENGINE & SNAP / FIXED SCRIPT / LOOP SETTINGS** | নিচে Common sections দেখো (দুই mood-এই একই রকম, sync হয়) | engine/snap_usernames/fixed_file/loop.* |

---

## 🖥️ MOOD 2 — 🔑 SESSION CHAT DASHBOARD (Session পেজে ২টা অপশন)

| # | Option | কী করে | Config key |
|---|--------|--------|------------|
| 1 | **🆕 Option 1 — লাইভ ব্রাউজার চালু করে session collect** | `🚀 Browser খোলো` → window-এ chitchat.gg LOGIN করো → `💾 Pull Session` → cookies verify হয়ে সেভ। একবার হলেই profile login মনে রাখে | session.json **তৈরি হয় এখানেই** |
| 2 | **💾 Option 2 — পুরনো saved session দিয়ে চ্যাট শুরু** | `configs/session.json` আগে থেকেই থাকলে (আগের দিনের/কোনো দিনের) — browser ছাড়াই headless চ্যাট। `🔄 চেক করো` দিয়ে দেখো কে saved আছে (`✓ user: …` সবুজ = verified) | session.json পড়ে |
| 3 | **START (session mood)** | session.json check → preflight (`GET /users/me`, 401 হলে বাংলায় "SESSION মেয়াদ শেষ" guidance) → WS connect → queue join | — |
| 4 | **ENGINE & SNAP / FIXED SCRIPT / LOOP SETTINGS** | নিচে Common sections দেখো | engine/snap_usernames/fixed_file/loop.* |

---

## ⚙️ BOT SETUP — এক জায়গায় সব সেটিংস (দুই mood থেকেই খোলে)

**কোথায় কী করব?** — উত্তর: mood dashboard গুলোতে শুধু সেই mood-এর কাজের বাটন (browser/session/START)। **Engine, fixed sms txt, snap.txt — এসব একটাই shared BOT SETUP পেজে** (প্রতিটা mood dashboard-এর ডান-উপরে `⚙️ Bot Setup` বাটন)। কারণ দুই mood-ই একই bot engine আর একই `configs/chitchat_bot.json` ব্যবহার করে — আলাদা করে দুই জায়গায় সেট করার দরকার নেই, ভুলও হয় না।

| Option | কী করে | Config key |
|--------|--------|------------|
| **ENGINE combo** | `flow — SMS detect → input/output matching reply` = funnel logic (greeting→age→country→flirty→snap) [DEFAULT] / `fixed — একটা fixed txt ফাইল, line-by-line reply` = পুরনো Fixed SMS মোড | `engine`: `"flow"` বা `"fixed"` |
| **SNAP — Usernames** | কমা দিয়ে একাধিক; reply-র `%username%` এখান থেকে rotate হয় | `snap_usernames`: `["name1","name2"]` |
| **SNAP — Snap file** | `configs/snap.txt` — প্রতি লাইনে একটা username, `#`=comment। **ফাইল থাকলে comma লিস্টের চেয়ে এটার priority বেশি**। (এডিট করতে: `configs/snap.txt.example` → copy করে `configs/snap.txt`) | `snap_file`: `"configs/snap.txt"` |
| **FIXED SMS TXT — File + Browse** | শুধু fixed engine-এ: প্রতি লাইন = একটা reply, opener = ১ম লাইন, প্রতি partner-এর pointer আলাদা, ফুরালে skip | `fixed_file`: `"configs/fixed_script.txt"` |
| **FIXED SMS TXT — 📖 এডিটরে খোলো** | script txt ফাইলটা সরাসরি ডিফল্ট এডিটরে খুলে দেয় (আগে auto-save হয়) | — |
| **FIXED preview** | নিচে দেখায় কতগুলো reply পাওয়া গেছে + প্রথম লাইনগুলো (ফাইল ঠিক আছে কিনা সাথে সাথে বোঝা যায়) | — |
| **SNAP status** | দেখায় কতগুলো username কাজ করবে + কোন উৎস থেকে (snap.txt নাকি comma লিস্ট) | — |
| **LOOP — Skip idle (sec)** | Partner এত সেকেন্ড চুপ থাকলে skip (typing করলে থামবে) | `loop.skip_idle_s` (15–600, default 90) |
| **LOOP — Typing indicator** | পাঠানোর আগে `POST .../typing` — partner-এর স্ক্রিনে "typing..." দেখবে | `loop.typing_indicator` |
| **LOOP — Auto next match** | Match শেষে 2–5s পর আবার queue | `loop.auto_next` |
| **💾 SAVE SETUP** | সব একসাথে সেভ — mood dashboard-গুলোর উপরে সবসময় সামার দেখা যায়: `⚙️ engine: … • snap pool: … • script: …` | `configs/chitchat_bot.json` |

**চ্যাট বট চালানোর ধাপ (দুই mood-এই একই):**
1. HOME → mood বাছাই
2. ডান-উপরে `⚙️ Bot Setup` → engine বাছাই + ফাইল সেট (fixed engine = fixed_script.txt; flow engine = snap.txt/username) → SAVE
3. mood dashboard-এ ফিরে এসে START
4. browser mood-এ আগে `🚀 Browser খোলো` (+login); session mood-এ Option 1 (session নেই হলে) বা Option 2

---

## 🐞 DEBUG ও PROBLEM REPORT (v10)

| Option | কী করে |
|--------|--------|
| **🐞 Debug mode** (BOT SETUP → LOOP group) | ON করলে console/GUI log-এ সব বিস্তারিত যায়: প্রতিটা WS frame, প্রতিটা API request (status + ms), engine decision (কোন SMS-এ কী match হলো কী reply গেল), delay breakdown | `debug`: `true`/`false` |
| **Log ফাইল** | `logs/eva.log` — **সবসময়** DEBUG level-এ লেখা হয় (Debug mode অফ থাকলেও), 1MB × 5 backup। পুরনো trail এখানেই থাকে | — |
| **🐞 Export Debug Report** (দুই mood dashboard-এর নিচেই) | এক ক্লিকে `logs/debug_report_<সময়>.txt` বানায়: config (secrets masked) + session status (শুধু has_token true/false — **content কখনো যায় না**) + bot stats + শেষ 300 WS frame (cookie value scrub করা) + API requests + engine decisions + শেষ 400 log লাইন | — |

**সমস্যা হলে যা পাঠাবে:** শুধু export করা `debug_report_*.txt` ফাইলটা — এটা share-safe (token/cookie মাস্ক করা)। CLI তে: `python -m eva.transport.ws_bot --debug` (stop করলে শেষ 15টা engine decision প্রিন্ট হয়)।

---

## 🧩 অন্যান্য COMMON জিনিস (দুই mood dashboard-এই একই)

| Option | কী করে |
|--------|--------|
| **STATS** | Matches / Sent / Recv / Skips / WS frames / Uptime — লাইভ (1s) |
| **CURRENT MATCH** | এখন কার সাথে চ্যাট, flow engine হলে কোন stage-এ |
| **LIVE LOG** | প্রতিটা কাজের লগ (মিনিট-বাই-মিনিট) |
| **CPU / RAM** | লাইভ সিস্টেম মিটার |

> 💡 **দুই mood-এর Settings sync হয়** — যেকোনো এক পেজে বদলালে (START চাপলে auto-save হয়) অন্য পেজেও সেটাই দেখাবে।

---

### 📁 CONFIG FILE (`configs/chitchat_bot.json`) — GUI-র বাইরের সেটিংস

| Key | মানে | Default |
|-----|------|---------|
| `engine` | flow বা fixed | `"flow"` |
| `browser_autosave` | browser mood-এর session auto-save on/off | `true` |
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
