# PROJECT MAP — multi-site-bot
**Project Root:** `C:\Users\papi\Desktop\multi-site-bot`

## Quick Nav — Task → File

| Task | File |
|------|------|
| Change reply logic / state machine | `src/reply_engine.py` |
| Change snap username / config | `src/config.json` |
| Add new site bot | `sites/<name>.py` + `src/config.json` + `src/main.py` dispatch :103 |
| Fix Joingy (HTTP API: poll/send) | `sites/joingy.py` |
| Fix iSexyChat (Playwright DOM) | `sites/isexychat.py` |
| Fix DB schema / queries | `src/db.py` |
| Fix proxy rotation / auth | `src/proxy_manager.py` |
| Fix Fixed SMS mode | `src/fixed_sms_engine.py` |
| Fix dashboard UI | `dashboard/cli.py` |
| Fix debug logging / tracing | `src/debug_utils.py` |
| Change reply templates | External: `data_dir` in config → `input/*.txt` / `output/*.txt` |
| Change snap trigger threshold | `src/config.json` `snap_share_after_n_messages` |
| Run tests | `python tests/test_fixed_state.py` `python tests/test_fixed_integration.py` |
| Run bot | `cd src && python main.py [--debug] [--health-interval N]` |

---

## Directory Map

```
multi-site-bot/
├── src/                       ← ALL CORE CODE (edit these)
│   ├── main.py                Entry point, --debug flag, health loop, autostart
│   ├── config.json            All settings: snap, delays, sites, proxy
│   ├── db.py                  SQLite schema + all queries (async)
│   ├── reply_engine.py        State machine: GREETING→END (8 stages)
│   ├── proxy_manager.py       Proxy load/rotate/fail tracking
│   ├── fixed_sms_engine.py    Fixed SMS mode (line-by-line from txt files)
│   ├── debug_utils.py         DebugLogger (runtime levels+console), TraceCapture (stats/filters),
│   │                          CrashTracker (flapping/reset), StateInspector (touch/stats), export_debug_dump
│   └── requirements.txt       pip deps
│
├── sites/                     ← PER-SITE BOT MODULES
│   ├── joingy.py              HTTP API bot: /start→/event→/boop→/disconnect
│   └── isexychat.py           Playwright + KiwiIRC DOM bot
│
├── dashboard/                 ← TUI
│   └── cli.py                 Textual dashboard (7 tabs incl Debug)
│
├── tests/                     ← TEST SUITE
│   ├── test_fixed_state.py    DB table tests (15 pass)
│   ├── test_fixed_integration.py  FixedSmsEngine integration (21 pass)
│   └── test_irc.py            IRC connection test (manual)
│
├── scripts/                   ← REFERENCE ONLY (capture/recon, do not edit for features)
│   ├── capture_test.py        Round 1: live protocol capture
│   ├── capture_test2.py       Round 2: KiwiIRC WS + Joingy flow
│   ├── capture_test3.py       Round 3: Joingy conv + iSexyChat Playwright
│   ├── capture_isc_direct.py  iSexyChat direct (no proxy)
│   ├── capture_isexychat.py   iSexyChat with proxy auth
│   ├── capture_protocol.py    Multi-site API/WS interceptor
│   ├── capture_deep.py        Deep capture: load forms, click buttons
│   └── read_capture.py        JSON capture reader
│
├── captures/                  ← CAPTURED TRAFFIC DATA (11 JSON files, reference)
├── docs/                      ← DOCUMENTATION
│   ├── PROJECT_MAP.md         This file
│   └── PROTOCOL_ANALYSIS.md   iSexyChat Socket.IO, Chatib/Coomeet, EmeraldChat analysis
├── tools/                     ← install.bat, run.bat
├── data/                      ← bot_data.db (runtime, gitignored)
└── .gitignore
```

---

## Architecture Flow

```
src/main.py
  ├─ load src/config.json
  ├─ src/reply_engine.py        → external chitchat engine for templates
  ├─ src/proxy_manager.py       → proxy.txt
  ├─ src/db.py                  → data/bot_data.db
  ├─ src/fixed_sms_engine.py    → folder/*.txt
  ├─ sites/joingy.py            (HTTP API, crash recovery 3x)
  │    └─ src/debug_utils.py
  ├─ sites/isexychat.py         (Playwright DOM, crash recovery 2x)
  │    └─ src/debug_utils.py
  └─ dashboard/cli.py           (Textual TUI, 7 tabs)
       └─ src/debug_utils.py
```

---

## Key Behaviors

- **Snap share:** after `snap_share_after_n_messages` (default 3), template engine injects `snap_username` → logged as lead
- **Reply delay:** random 2-6s between messages
- **Dedup:** global + per-conv used sets in reply engine
- **Proxy fail:** 5 fails → `available=False`
- **Crash recovery:** 3 retries (Joingy) / 2 retries (iSexyChat) with exponential backoff
- **Health check:** auto-removes dead/stale sessions every `--health-interval` seconds
- **Debug logs:** `src/logs/*.jsonl` rotating JSONL (5MB, 3 backups)
- **Sessions:** Joingy max=20, iSexyChat max=5

---

## State Machine (reply_engine.py)

```
GREETING → AGE_GENDER → COUNTRY → COUNTRY_REPLY → MIDDLE_CHAT → SHARE_SNAP → END
                                                         ├─ horny_question (2 replies + ask_snap)
                                                         ├─ horny (reply + ask_snap)
                                                         ├─ flirty (reply + ask_snap)
                                                         ├─ how_are_you → stay
                                                         ├─ warm → stay
                                                         ├─ busy → stay
                                                         ├─ normal → stay (max 8 loops then ask_snap)
                                                         └─ max_loops → ask_snap
```
