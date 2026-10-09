# PROJECT MAP — multi-site-bot
**Locked Project Root:** `C:\Users\papi\Desktop\multi-site-bot`

## Overview
Async multi-site chat bot system. Connects to multiple chat sites (Joingy via HTTP API, iSexyChat via Playwright/KiwiIRC), auto-replies using a local template engine (no LLM), and shares a Snapchat username after N messages to generate leads. FastAPI dashboard for control + live stats. SQLite for persistence. Proxy rotation supported.

## Tech Stack
- Python 3.10+ (asyncio)
- aiohttp / aiohttp_socks (HTTP + SOCKS5 proxy clients)
- Playwright (browser automation for KiwiIRC sites)
- aiosqlite (async SQLite)
- Textual (TUI dashboard)
- websockets (IRC-over-WS testing)
- External dep: `../chitchat/chitchat/engine` (template engine imported via sys.path hack in `reply_engine.py`)

---

## File Map (with purpose + key line refs)

### CORE (edit these for bot logic)
| File | Purpose | Key Symbols |
|------|---------|-------------|
| `src/main.py` | Entry point. CLI flags: `--debug` (verbose log), `--health-interval N` (auto-health-check). Autostart + health loop. Also initializes DbReplyEngine, MoodManager, ThreadManager. | `main()` :42, `parse_args()` :15 |
| `src/config.json` | Single source of truth. Snap username, delays, per-site config (method/enabled/max_sessions). | `sites` :14 |
| `src/db.py` | Async SQLite. Tables: users, messages, snap_leads, site_stats, live_logs, fixed_sms_state, fixed_sms_file_pool, +3 new tables (db_reply_state, mood_state, thread_state). | `Database` :105, `SCHEMA` :12 |
| `src/reply_engine.py` | Local template engine adapter (NO LLM). State machine: GREETING→AGE_GENDER→COUNTRY→MIDDLE_CHAT→SHARE_SNAP→END. | `ReplyEngine` :43, `reply()` :129 |
| `src/db_reply_engine.py` | **NEW** — DB-backed persistent conversation state. Wraps ReplyEngine, stores state in `db_reply_state` table. Survives restarts. | `DbReplyEngine` :51, `reply()` :61, `get_stats()` :123 |
| `src/mood_manager.py` | **NEW** — Per-site mood/tone selector. Moods: FLIRTY, DIRECT, SHY, AGGRESSIVE, RANDOM. Auto-cycle support. `mood_state` table. | `MoodManager` :62, `get_mood()` :90, `cycle()` :116 |
| `src/thread_manager.py` | **NEW** — Session/pool concurrency coordinator. Per-site semaphore limits. `thread_state` table persists active/completed/error sessions. | `ThreadManager` :59, `acquire()` :87, `get_pool_stats()` :140 |
| `src/proxy_manager.py` | Loads/rotates proxies (socks5/http). Tracks uses/fails, marks dead after 5 fails. | `ProxyManager` :32, `get()` :87 |
| `src/debug_utils.py` | Structured debug infrastructure. `DebugLogger` (rotating JSONL + console, runtime level via `set_debug_level`/`change_level`, full tracebacks), `read_jsonl` (safe file tail), `TraceCapture` (HTTP ring buffer + `stats()` latency/error rates, session/direction filters), `CrashTracker` (per-session crash history + backoff, `flapping()` detection, `reset()`/`clear()`), `StateInspector` (live session state, `touch()` activity, `stats()`), `export_debug_dump()` (one-file JSON snapshot for reporting). | `set_debug_level`, `DebugLogger`, `TraceCapture`, `CrashTracker`, `StateInspector`, `export_debug_dump` |
| `src/fixed_sms_engine.py` | Fixed SMS mode: random txt file per session, line-by-line reply. | `FixedSmsEngine` :23, `get_reply()` :87 |

### SITES (edit these for per-site behavior)
| File | Purpose | Key Symbols |
|------|---------|-------------|
| `sites/__init__.py` | Empty package marker. | — |
| `sites/joingy.py` | Joingy HTTP API bot. `/start` → `/event` poll → `/boop` send → `/disconnect`. Multi-session + crash recovery (3 retries, exponential backoff) + health check. Debug instrumentation: trace capture, state inspector. | `JoingySession` :41, `JoingyBot` :335, `_event_loop()` :129, `_run_session()` :355 |
| `sites/isexychat.py` | iSexyChat Playwright bot. KiwiIRC web client. DOM scrape `.kiwi-messagelist-*`, type in `.kiwi-inputbar-input`. Crash recovery (2 retries) + health check. Debug instrumentation. | `IsexychatSession` :32, `IsexychatBot` :278, `_chat_loop()` :142, `_run_session()` :319 |

### DASHBOARD (edit for UI/API)
| File | Purpose | Key Symbols |
|------|---------|-------------|
| `dashboard/cli.py` | Textual TUI dashboard. Tabs: Overview, Control, Settings, Logs, Fixed SMS, **MODE**, **DB BANK**, **THREADS**, **PROXY**, **SNAP**, **SMS**, Debug, Leads. Debug tab shows live session states, crash history, proxy health, trace errors. Health Check + Force GC buttons. MODE tab has mood selector. | `BotDashboard` :49, `_refresh_mode()` :965, `_refresh_dbbank()` :1036, `_refresh_threads()` :1059, `_refresh_proxy_tab()` :1080, `_refresh_snap_tab()` :1100, `_refresh_sms_tab()` :1133 |

### CAPTURE/TEST SCRIPTS (reference only — DO NOT edit for features)
| File | Purpose |
|------|---------|
| `capture_test.py` | Round 1: live protocol capture (iSexyChat IRC, Joingy API, Chatib, AdultChat, ChatRandom). |
| `capture_test2.py` | Round 2: KiwiIRC webirc gateway WS test, Joingy full flow, HTML parsing. |
| `capture_test3.py` | Round 3: Joingy full conversation + iSexyChat Playwright. |
| `capture_isc_direct.py` | iSexyChat direct Playwright (no proxy), WS/console capture. |
| `capture_isexychat.py` | iSexyChat Playwright with HTTP proxy auth. |
| `test_irc.py` | Direct IRC (irc.freechat.zone:6697) + webirc.bb.chat WS tests. |

### DATA/ARTIFACTS (generated, ignore)
- `bot_data.db` — SQLite DB (runtime state)
- `capture_*.html`, `capture_*.txt`, `capture_*.png` — capture script outputs
- `__pycache__/` — bytecode
- `dashboard/static/` — empty
- `requirements.txt` — deps: aiohttp, aiohttp_socks, aiosqlite, playwright, PySocks, websockets, textual
- `logs/` — **NEW** rotating JSONL debug logs (`joingy.jsonl`, `isexychat.jsonl`, etc.)

---

## Architecture Flow
```
main.py
  ├─ load config.json
  ├─ ReplyEngine      ──imports──> ../chitchat/chitchat/engine (external)
  ├─ DbReplyEngine    ──wraps──> ReplyEngine (persistent state)
  ├─ MoodManager      ──manages──> mood_state table
  ├─ ThreadManager    ──manages──> thread_state table + semaphores
  ├─ ProxyManager     ──reads──> proxy.txt
  ├─ Database         ──writes──> bot_data.db
  ├─ sites.joingy.JoingyBot     (HTTP API, aiohttp, proxy, crash recovery)
  │    └─ debug_utils: trace, crash, state inspector
  ├─ sites.isexychat.IsexychatBot (Playwright, DOM, crash recovery)
  │    └─ debug_utils: trace, crash, state inspector
  ├─ FixedSmsEngine   ──reads──> folder/*.txt
  └─ dashboard.cli.BotDashboard (Textual TUI, 13 tabs)
       └─ debug_utils: reads TraceCapture, CrashTracker, StateInspector
```

## Key Behaviors
- **Snap share:** after `snap_share_after_n_messages` (default 3) the template engine injects `snap_username`; detected in outgoing msg -> logged as lead (`db.log_snap_lead`).
- **Reply delay:** random `reply_delay_min_sec`..`reply_delay_max_sec` (2-6s) to seem human.
- **Dedup:** `ReplyEngine` tracks `global_used` + per-conv `conv_used` sets.
- **Proxy fail:** 5 fails -> `available=False` (dead).
- **Joingy session cap:** `max_sessions=20`; iSexyChat `max_sessions=5`.
- **Crash recovery:** sessions auto-retry up to 3x (Joingy) / 2x (iSexyChat) with exponential backoff.
- **Health check:** auto-removes dead/stale sessions every `--health-interval` seconds (default 60).
- **Debug logs:** `logs/*.jsonl` — rotating JSONL files (5MB, 3 backups) per site module.

## Task Targeting Guide
- **Change reply logic/LLM:** `reply_engine.py` (currently template-only; LLM hook would go here)
- **Add new site:** create `sites/<name>.py` with `<Name>Bot` class, add to `config.json` sites + `main.py` dispatch (:64-83)
- **Change snap trigger:** `config.json` `snap_share_after_n_messages` + template engine
- **Fix Joingy send/poll:** `sites/joingy.py` `_event_loop()` :129, `_send()` :251
- **Fix iSexyChat DOM:** `sites/isexychat.py` `_chat_loop()` :142 (selectors), `_send()` :199
- **Dashboard UI:** `dashboard/cli.py` + tabs: Overview, Control, Settings, Logs, Fixed SMS, Debug, Leads
- **Debug tab:** `dashboard/cli.py` `_refresh_debug()` :876, `_run_health_check()` :921
- **Add debug instrumentation:** `debug_utils.py` — `DebugLogger`, `TraceCapture`, `CrashTracker`, `StateInspector`
- **View crash history:** `logs/*.jsonl` files + Dashboard Debug tab > Recent Crashes table
- **DB schema/queries:** `db.py` `SCHEMA` :12
- **Proxy handling:** `proxy_manager.py`
- **Config/credentials:** `config.json` ONLY (never hardcode in .py)
- **Run with debug logging:** `python main.py --debug --health-interval 30`

---

# REPLY ENGINE — STATE MACHINE MAP (Start to End Chat)

## Data Source
All input (detection) and output (reply) TXT files live in the **papipapi-2.2** project:
```
Root: C:\Users\papi\Desktop\ZRR ==============\chatrbot\New folder (2)\papipapi-2.2\data\
├── input/          ← detection rules (what user says)
│   ├── greeting.txt
│   ├── age_gender.txt
│   ├── country.txt
│   ├── horny.txt
│   ├── horny_answer.txt
│   ├── how_are_you.txt
│   ├── share_snap.txt
│   ├── snapchat.txt
│   ├── english_only.txt
│   ├── your_age.txt
│   └── middle_chat/
│       ├── flirty_reply.txt
│       ├── warm_reply.txt
│       └── busy_later.txt
├── output/         ← reply templates (what bot sends)
│   ├── greeting.txt
│   ├── age_gender.txt
│   ├── country.txt
│   ├── flirty_questions.txt
│   ├── horny.txt
│   ├── horny_answer.txt
│   ├── how_are_you.txt
│   ├── ask_snap.txt
│   ├── share_snap.txt       ← has %username% placeholder
│   ├── snapchat.txt          ← has %username% placeholder
│   ├── your_age.txt
│   ├── english_only.txt
│   ├── age_ask.txt
│   ├── gender_ask.txt
│   ├── agreement_ack.txt
│   ├── agreement_breaker.txt
│   ├── answer_ack.txt
│   ├── answer_followup.txt
│   ├── info_ack.txt
│   ├── retry_nudge.txt
│   ├── closer.txt
│   ├── ask_snap_backup.txt
│   └── middle_chat/
│       ├── flirty_reply.txt
│       ├── warm_reply.txt
│       ├── new_topic.txt
│       └── busy_later.txt
```

## Complete Flow Diagram
```
START
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 1: GREETING                                               │
│  ──────────────────────────────────────────────────────────────  │
│  DETECT: input/greeting.txt (1894 lines)                         │
│    Triggers: hi, hii, hiii, hey, heyy, hello, hlw, hlww, yo,     │
│              sup, wassup, hlo, hola, hay, hy, heyo, heya, hiya,  │
│              + all punctuation/case/emoji variations              │
│              (hi!, hi?, hi~, hi..., hi :), hi 👋, hi bro, etc.)  │
│                                                                  │
│  REPLY: output/greeting.txt (65 lines)                           │
│    Examples: "hlw,,", "hey..", "hii..", "heyy.", "hiya",        │
│              "hi there", "hey there", "hi dear", "hey babe",     │
│              "whats up", "wassup", "yo", "sup"                   │
│                                                                  │
│  → NEXT: STAGE 2 (AGE_GENDER)                                    │
└──────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 2: AGE_GENDER                                             │
│  ──────────────────────────────────────────────────────────────  │
│  DETECT: input/age_gender.txt (199 lines)                        │
│    Triggers: m18, M19, 20m, m 21, F22, f-24, m30, f18, 19f,     │
│              m, M, f, F, m., M., hi m, hey m, iam m, etc.        │
│              (all age+gender combos 18-45, M/F, all formats)     │
│                                                                  │
│  REPLY: output/age_gender.txt (52 lines)                         │
│    Examples: "f21", "F.23", "19f", "f 25", "F19.", "21 F",      │
│              "f-23", "f 18", "f 19", "f 20", "im 20f", "20f"    │
│                                                                  │
│  → NEXT: STAGE 3 (COUNTRY)                                       │
└──────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 3: COUNTRY                                                │
│  ──────────────────────────────────────────────────────────────  │
│  DETECT: input/country.txt (180 lines)                           │
│    Triggers: "from?", "where u from?", "u from?", "where u live?",│
│              "what city u in?", "u local?", "what state?",       │
│              + country names: "from usa", "im from uk",          │
│              "from germany", "from india", "from bangladesh",    │
│              "from canada", "from australia", etc. (30+ countries)│
│                                                                  │
│  REPLY: output/country.txt (977 lines)                           │
│    Examples: "Moldova wbu?", "from wales wby?", "UKRAINE u?",   │
│              "spain you?", "from france u?", "germny u?",        │
│              "usa wbu?", "uk wbu", "usa hbu"                     │
│    Format: <country> + wbu?/wby?/u?/you?/hbu?                    │
│                                                                  │
│  → NEXT: STAGE 4 (COUNTRY_REPLY → FLIRTY_ASK)                    │
└──────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 4: COUNTRY_REPLY → FLIRTY_ASK                             │
│  ──────────────────────────────────────────────────────────────  │
│  User replies with their country (usa, uk, germany, etc.)        │
│  Bot does NOT reply with a country — it sends a FLIRTY QUESTION  │
│                                                                  │
│  REPLY: output/flirty_questions.txt (1004 lines)                 │
│    Examples: "wanna chat?", "up for a flirty talk?",             │
│              "wanna know a secret about me?", "you in?",         │
│              "whats the naughtiest thing on ur mind rn?",        │
│              "do u like being teased or being the teaser?",      │
│              "what would u do if i said come over?", etc.        │
│    Random line picked from 1004 options                          │
│                                                                  │
│  → NEXT: STAGE 5 (MIDDLE_CHAT — 3-path detection)                │
└──────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 5: MIDDLE_CHAT — 3-PATH DETECTION                         │
│  ═════════════════════════════════════════════════════════════  │
│  After bot sends flirty question, user replies.                  │
│  Bot detects user's reply into 3 paths (priority order):        │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  SPECIAL: HORNY_QUESTION (user asks bot "horny?")      │     │
│  │  DETECT: input/horny_answer.txt (81 lines)              │     │
│  │    Triggers: "horny?", "u horny?", "u dtf?", "wanna     │     │
│  │    fun?", "u down?", "u wet?", "in the mood?"           │     │
│  │  REPLY: 2 lines:                                        │     │
│  │    Line 1: output/horny_answer.txt (15 lines)           │     │
│  │      "yes", "yep", "yeah", "mhm", "kinda", "yes 🥵"    │     │
│  │    Line 2: output/horny.txt (47 lines)                  │     │
│  │      "little bit", "maybe", "yes baby", "what u think?" │     │
│  │  → NEXT: STAGE 6 (ASK_SNAP)                             │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  PATH A: HORNY (user says horny things)                │     │
│  │  DETECT: input/horny.txt (200 lines)                    │     │
│  │    Triggers: "im horny", "send nudes", "sext me",       │     │
│  │    "nudes", "horny rn", "feeling horny", "send pics",   │     │
│  │    "show me", "naked", "strip", "dick", "pussy",        │     │
│  │    "wanna fuck", "dtf", "down to fuck", "smash",        │     │
│  │    "what are u wearing", "ur boobs", "ur ass", "nsfw",  │     │
│  │    "18+", "onlyfans", "hookup", "aroused", "turned on"  │     │
│  │  REPLY: output/horny.txt (47 lines)                     │     │
│  │    Examples: "little bit", "maybe", "haha yes",         │     │
│  │    "yes baby", "what u think?", "yep,baby", "yes 🥵",  │     │
│  │    "kinda 👀", "maaaybe 😏", "depends who's asking 😏", │     │
│  │    "u first hmm", "too fast 🙈", "bold of u lol"       │     │
│  │  → NEXT: STAGE 6 (ASK_SNAP)                             │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  PATH B: FLIRTY (user says flirty/cute things)         │     │
│  │  DETECT: input/middle_chat/flirty_reply.txt (123 lines) │     │
│  │    Triggers: "ur cute", "u cute", "beautiful", "ur      │     │
│  │    gorgeous", "pretty", "u look good", "i like u",      │     │
│  │    "love u", "miss u", "babe", "baby", "cutie",         │     │
│  │    "wanna date", "wanna meet", "kiss me", "cuddle",     │     │
│  │    "u single", "flirting", "teasing", "naughty",        │     │
│  │    "ur charming", "so sweet", "ur adorable"             │     │
│  │  REPLY: output/middle_chat/flirty_reply.txt (40 lines)  │     │
│  │    Examples: "hehe you're cute tho 😏", "u always this  │     │
│  │    smooth?", "okay fine, I'm blushing a bit 🙈",        │     │
│  │    "tease me more lol", "thats sweet 🥰", "ur so smooth"│     │
│  │  → NEXT: STAGE 6 (ASK_SNAP)                             │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  PATH C: NORMAL (user says normal/casual things)       │     │
│  │  DETECT: input/normal.txt (122 lines)                   │     │
│  │    Triggers: "ok", "lol", "same", "true", "nice",       │     │
│  │    "cool", "haha", "hmm", "idk", "bored", "tired",      │     │
│  │    "wyd", "hru", "how are you", "sup", "yo",            │     │
│  │    "good morning", "good night", "gn", "gm",             │     │
│  │    "whats up", "anything new", "fr", "bet", "facts"     │     │
│  │  REPLY: output/normal.txt (30 lines)                    │     │
│  │    Examples: "lol", "same", "true", "nice", "cool",     │     │
│  │    "yeah", "fr", "bet", "facts", "ikr", "haha same",    │     │
│  │    "true that", "nice lol", "wow", "omg", "damn"        │     │
│  │  → NEXT: STAGE 6 (ASK_SNAP)                             │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  SUB-PATH: WARM_REPLY (user says ok/nice/cool ack)     │     │
│  │  DETECT: input/middle_chat/warm_reply.txt (92 lines)    │     │
│  │    Triggers: "ok", "okay", "kk", "nice", "cool", "wow", │     │
│  │    "omg", "damn", "lol", "lmao", "haha", "hehe", "hmm", │     │
│  │    "fr", "true", "same", "mood", "idk", "maybe", "aww", │     │
│  │    "gotcha", "alright", "aight", "fine", "good", "legit"│     │
│  │  REPLY: output/middle_chat/warm_reply.txt (20 lines)    │     │
│  │    Examples: "lol okay", "hehe okay", "ah nicee",       │     │
│  │    "mm hmm", "interesting lol", "lol fair", "nice one"  │     │
│  │  → NEXT: stays in MIDDLE_CHAT or moves to ASK_SNAP      │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  SUB-PATH: HOW_ARE_YOU (user asks "how are you")       │     │
│  │  DETECT: input/how_are_you.txt (307 lines)              │     │
│  │    Triggers: "how are you", "how r u", "hru", "how u    │     │
│  │    doing", "how's it going", "how are things",           │     │
│  │    "how's life", "how have you been", "how u feeling"   │     │
│  │  REPLY: output/how_are_you.txt (203 lines)              │     │
│  │    Examples: "just bored as hell u?", "bored outta my   │     │
│  │    mind u?", "in bed bored af wbu", "bored rn u?"       │     │
│  │  → NEXT: stays in MIDDLE_CHAT                             │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  SUB-PATH: BUSY_LATER (user says gtg/bye/brb)          │     │
│  │  DETECT: input/middle_chat/busy_later.txt (65 lines)    │     │
│  │    Triggers: "gtg", "g2g", "bye", "cya", "later",       │     │
│  │    "brb", "bbl", "leaving", "gotta go", "heading out",  │     │
│  │    "going to sleep", "tired", "sleepy", "night", "gn",  │     │
│  │    "busy", "working", "tmrw", "another time"            │     │
│  │  REPLY: output/middle_chat/busy_later.txt (6 lines)     │     │
│  │    Examples: "np, text me when free 😌", "okay take ur   │     │
│  │    time, I'll be here", "all good 🤙 hmu when ur not    │     │
│  │    busy"                                                 │     │
│  │  → NEXT: END or stays (user may come back)              │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  SUB-PATH: NEW_TOPIC (dry/short reply, topic shift)    │     │
│  │  REPLY: output/middle_chat/new_topic.txt (6 lines)      │     │
│  │    Examples: "wanna know smth fun? 👀", "u seem quiet   │     │
│  │    rn 😏 ok one question: whats ur type?", "bored? same │     │
│  │    lol. tell me ur fav movie", "truth or dare, u pick"  │     │
│  │  → NEXT: stays in MIDDLE_CHAT                             │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
│  → AFTER ANY PATH COMPLETES → STAGE 6 (ASK_SNAP)                │
└──────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 6: ASK_SNAP                                               │
│  ──────────────────────────────────────────────────────────────  │
│  Bot asks user for Snapchat. No input detection needed.         │
│                                                                  │
│  REPLY: output/ask_snap.txt (298 lines)                          │
│    Examples: "u on snp? 👻", "u got snp?", "add me on snp?",    │
│              "drop ur snp?", "whats ur snp?", "snp me?",        │
│              "lets chat on snp?", "swap snp?", "snp or nah?",   │
│              + variations: snp, sn-p, s.c, sc, gh, ghost, 👻    │
│              + "u on snap?", "whats ur snap?", "ur sc?"         │
│                                                                  │
│  → NEXT: STAGE 7 (SNAP_POSITIVE detection)                       │
└──────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 7: SNAP_POSITIVE → SHARE_SNAP                             │
│  ──────────────────────────────────────────────────────────────  │
│  DETECT: input/share_snap.txt (129 lines)                        │
│    Triggers: "yes", "yea", "yeah", "yep", "yess", "yeop",       │
│              "sure", "ofc", "im down", "say less", "fr",        │
│              "ur sc", "ur sc?", "ur snap", "ur snap?",           │
│              "ur @", "whats ur snap", "whats ur sc",             │
│              "snap?", "sc?", "snap plz", "give snap",            │
│              "add me on snap", "wanna snap", "lets snap",        │
│              "ok send", "send it", "i want it"                   │
│                                                                  │
│  REPLY: output/share_snap.txt (24 lines, has %username%)         │
│    Examples: "here's my 👉: %username%", "👉 %username%",       │
│              "a.dd me on snap -> %username%",                     │
│              "let's switch to sc -> %username%",                  │
│              "ok ad,d %username%", "hit me up anytime 👉 %username%",│
│              "@ %username%", "snap: %username%", "add %username%"│
│    %username% replaced with config snap_username                 │
│                                                                  │
│  → NEXT: STAGE 8 (END_CHAT)                                      │
└──────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 7b: USER_SHARES_THEIR_SNAP (alternative path)             │
│  ──────────────────────────────────────────────────────────────  │
│  If user shares their snap first (before bot asks):              │
│                                                                  │
│  DETECT: input/snapchat.txt (62 lines)                           │
│    Triggers: "my snap", "my sc", "my snap is", "my snapchat",    │
│              "heres my snap", "add me on snap", "snap me",       │
│              "my snp", "my ghost", "my s.c", "wanna snap"        │
│                                                                  │
│  REPLY: output/snapchat.txt (8 lines, has %username%)            │
│    Examples: "Added you on snap %username%",                     │
│              "just added u on snap %username%",                  │
│              "found u on snap %username%",                       │
│              "my snap is %username%, add me"                     │
│                                                                  │
│  → NEXT: STAGE 8 (END_CHAT)                                      │
└──────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 8: END_CHAT                                               │
│  ──────────────────────────────────────────────────────────────  │
│  Bot disconnects. Finds another user. Starts new conversation.   │
│  Cycle repeats from STAGE 1.                                     │
│                                                                  │
│  Joingy: POST /disconnect → new /start → new UID                 │
│  iSexyChat: browser close → new browser → new nick → rejoin      │
└──────────────────────────────────────────────────────────────────┘
```

## Detection Priority Order (when multiple matches possible)
```
1. HORNY_QUESTION  (input/horny_answer.txt)     — user asks "horny?" → 2-line reply
2. HORNY           (input/horny.txt)             — user says horny things → horny.txt
3. FLIRTY          (input/middle_chat/flirty_reply.txt) — user says cute/flirty → flirty_reply.txt
4. SHARE_SNAP      (input/share_snap.txt)        — user says yes/ur snap → share_snap.txt
5. USER_SNAP       (input/snapchat.txt)          — user shares their snap → snapchat.txt
6. HOW_ARE_YOU     (input/how_are_you.txt)       — user asks hru → how_are_you.txt
7. BUSY_LATER      (input/middle_chat/busy_later.txt) — user says bye/gtg → busy_later.txt
8. WARM_REPLY      (input/middle_chat/warm_reply.txt) — user says ok/nice → warm_reply.txt
9. NORMAL          (input/normal.txt)             — user says casual → normal.txt
10. GREETING        (input/greeting.txt)           — user says hi → greeting.txt
11. AGE_GENDER      (input/age_gender.txt)         — user says m21 → age_gender.txt
12. COUNTRY         (input/country.txt)            — user says from? → country.txt
```

## File Line Counts (for scale reference)
| File | Input Lines | Output Lines |
|------|------------|-------------|
| greeting.txt | 1894 | 65 |
| age_gender.txt | 199 | 52 |
| country.txt | 180 | 977 |
| flirty_questions.txt | — | 1004 |
| horny.txt | 200 | 47 |
| horny_answer.txt | 81 | 15 |
| how_are_you.txt | 307 | 203 |
| middle_chat/flirty_reply.txt | 123 | 40 |
| middle_chat/warm_reply.txt | 92 | 20 |
| middle_chat/busy_later.txt | 65 | 6 |
| middle_chat/new_topic.txt | — | 6 |
| normal.txt | 122 | 30 |
| ask_snap.txt | — | 298 |
| share_snap.txt | 129 | 24 |
| snapchat.txt | 62 | 8 |

## Reply Engine Task Targeting
| Task | Target File(s) |
|------|----------------|
| Change greeting replies | `output/greeting.txt` |
| Change age/gender replies | `output/age_gender.txt` |
| Change country replies | `output/country.txt` |
| Change flirty questions | `output/flirty_questions.txt` |
| Change horny replies | `output/horny.txt` |
| Change horny answer (yes-type) | `output/horny_answer.txt` |
| Change flirty path replies | `output/middle_chat/flirty_reply.txt` |
| Change normal path replies | `output/normal.txt` |
| Change warm ack replies | `output/middle_chat/warm_reply.txt` |
| Change how_are_you replies | `output/how_are_you.txt` |
| Change busy/bye replies | `output/middle_chat/busy_later.txt` |
| Change topic shift lines | `output/middle_chat/new_topic.txt` |
| Change snap ask lines | `output/ask_snap.txt` |
| Change snap share lines | `output/share_snap.txt` (has %username%) |
| Change user-snap ack | `output/snapchat.txt` (has %username%) |
| Add new greeting triggers | `input/greeting.txt` |
| Add new age/gender triggers | `input/age_gender.txt` |
| Add new country triggers | `input/country.txt` |
| Add new horny triggers | `input/horny.txt` |
| Add new horny-question triggers | `input/horny_answer.txt` |
| Add new flirty triggers | `input/middle_chat/flirty_reply.txt` |
| Add new normal triggers | `input/normal.txt` |
| Add new warm triggers | `input/middle_chat/warm_reply.txt` |
| Add new how_are_you triggers | `input/how_are_you.txt` |
| Add new busy triggers | `input/middle_chat/busy_later.txt` |
| Add new snap-positive triggers | `input/share_snap.txt` |
| Add new user-snap triggers | `input/snapchat.txt` |
| Change detection priority | `reply_engine.py` (state machine logic) |
| Change state machine flow | `reply_engine.py` |
| Change %username% placeholder | `config.json` `snap_username` |
