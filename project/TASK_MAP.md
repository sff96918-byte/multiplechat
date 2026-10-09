# TASK MAP — multi-site-bot (AI quick-scope index)
**Read this file FIRST on every task.** It routes you to the exact files in ~1s.
Full detail lives in `docs/PROJECT_MAP.md`; user guide in `DASHBOARD_GUIDE.txt`.

**Project:** Multi-site chat bot system (adult chat sites) — async Python bots + Textual TUI dashboard.
**Stack:** Python 3.14, asyncio, aiohttp+aiohttp-socks, aiosqlite, Playwright (chromium), Textual. Deps: `src/requirements.txt`.
**Root:** `C:\Users\papi\Desktop\multi-site-bot`

---

## ⚡ TASK → FILE ROUTER (the 1-second table)

| Task keywords | READ these files |
|---|---|
| Add / change a new site bot | `src/main.py:150-169` (dispatch), `sites/<name>.py` (copy joingy.py or isexychat.py), `src/config.json` `sites{}` |
| Reply logic, chat flow, conversation stages | `src/reply_engine.py` (state machine) |
| Change detection triggers / reply templates | external `data_dir` (config) → `input/*.txt` (triggers) + `output/*.txt` (templates) |
| Snap username, snap-after-N, delays | `src/config.json` + per-bot `update_config()` in `sites/joingy.py:431` / `sites/isexychat.py:411` |
| Joingy bugs (HTTP API: /start /event /boop /disconnect) | `sites/joingy.py` |
| iSexyChat bugs (Playwright, KiwiIRC DOM, IRC) | `sites/isexychat.py`; protocol notes `docs/PROTOCOL_ANALYSIS.md` |
| DB schema / queries / stats / leads / logs | `src/db.py` (class `Database`, schema `:12-102`) |
| Proxy load/rotate/fail/connectors | `src/proxy_manager.py` |
| Fixed SMS mode (txt file line-by-line replies) | `src/fixed_sms_engine.py`, DB tables `fixed_sms_state` / `fixed_sms_file_pool` |
| Mood / tone (FLIRTY/DIRECT/SHY/AGGRESSIVE) | `src/mood_manager.py` |
| Thread/session pool concurrency | `src/thread_manager.py` |
| DB-persisted reply state / reply bank | `src/db_reply_engine.py` (2 classes: `DbReplyEngine` async wrapper + `DBReplyEngine` sync sqlite bank) |
| Dashboard UI / tabs / buttons | `dashboard/cli.py` (class `BotDashboard(App)`, ~1330 lines) |
| Debug logging, JSONL logs, crash tracking, traces | `src/debug_utils.py` (`DebugLogger`, `TraceCapture`, `CrashTracker`, `StateInspector`) |
| Tests | `tests/test_fixed_state.py`, `tests/test_fixed_integration.py`, `tests/test_debug_utils.py`, `tests/test_db_reply_engine.py` |
| Setup / launch | `tools/install.bat`, `tools/run.bat` |

**Never edit:** `scripts/` (protocol capture/recon, reference only), `captures/` (raw traffic JSON), `data/`, `__pycache__/`.

---

## 📁 File inventory — CORE (`src/`)

| File | Purpose | Key anchors |
|---|---|---|
| `main.py` | Entry point. Init order: config → ReplyEngine → ProxyManager → Database → site settings → FixedSmsEngine → DbReplyEngine → MoodManager → ThreadManager → bots (dispatch) → BotDashboard → health loop → autostart | `main():44`, bot dispatch `:150-169`, health loop `:180-192`, autostart `:196-200` |
| `config.json` | ALL settings (see §Config below) | snap, delays, sites{}, fixed_sms, db_detect |
| `db.py` | `Database` — aiosqlite, schema + 40+ async methods | SCHEMA `:12-102` (users, messages, snap_leads, site_stats, site_settings, live_logs, fixed_sms_state, fixed_sms_file_pool); methods `:106-440` |
| `reply_engine.py` | `ReplyEngine` — in-memory state machine, dedup per conv, `%username%` fill | stages `:32-38`, `_load_data()` `:57`, `_match()` `:324`, `_pick()` `:345`, MAX_MIDDLE_CHAT_LOOPS=8 |
| `proxy_manager.py` | `ProxyManager` + `Proxy` dataclass — parse socks5/4/http, round-robin, 5 fails→dead | `_parse()` `:53`, `get()` `:87`, `release()` `:100`, `get_playwright_config()` `:110`, `get_aiohttp_connector()` `:119` |
| `fixed_sms_engine.py` | `FixedSmsEngine` — random txt per session, line-by-line, `%username%` replace, restart-safe | `set_folder()` `:50`, `get_reply()` `:87`; fallback chain: FixedSms → ReplyEngine → silent |
| `db_reply_engine.py` | TWO engines: `DbReplyEngine` (async wrapper, state → `db_reply_state` table) + `DBReplyEngine` (sync sqlite `reply_bank`, mood+stage+trigger weighted lookup) | `DbReplyEngine.reply()` `:59`; `DBReplyEngine.get_reply()` exact→LIKE→weighted→fallback |
| `mood_manager.py` | `MoodManager` + `Mood` enum (FLIRTY/DIRECT/SHY/AGGRESSIVE/RANDOM), cycle FLIRTY→DIRECT→SHY→AGGRESSIVE, `mood_state` table | `get_mood()` `:68`, `set_mood()` `:78`, `cycle()` `:110` |
| `thread_manager.py` | `ThreadManager` + `ThreadSlot` — per-site asyncio.Semaphore pools, `thread_state` table | `acquire()` `:80`, `get_pool_stats()`, `cleanup()` `:184` |
| `debug_utils.py` | `DebugLogger` (JSONL rotating 5MB×3 → `src/logs/<site>.jsonl`), `TraceCapture`, `CrashTracker` (retry/backoff/flapping), `StateInspector`; module singletons `get_trace_capture()` etc. | classes at `:74, :247, :366, :471` |

## 🌐 Sites (`sites/`)

| File | Class(es) | Protocol | Limits |
|---|---|---|---|
| `joingy.py` | `JoingySession` `:47`, `JoingyBot` `:321` | Pure HTTP POST to `back.joingy.com`: `/start`→UID, `/event` poll, `/boop` send, `/disconnect` | max_sessions=20, poll 1s, crash retry 3× |
| `isexychat.py` | `IsexychatSession` `:37`, `IsexychatBot` `:303` | Playwright chromium → KiwiIRC web client at chat.isexychat.com, channel `#ifap`, DOM-based | max_sessions=5, headless default, crash retry 2× |

Both bots: `start/stop/health_check/stats/update_config` interface; share `debug_utils` singletons; accept `fixed_engine` for Fixed SMS mode.

## 🖥️ Dashboard (`dashboard/cli.py`)
`BotDashboard(App)` `:48` — Textual TUI, ~1330 lines. Tabs: Overview, Control, Settings, Logs, Fixed SMS, Debug, Leads, Mode, DB Bank, Threads, Proxy, Snap, SMS. Key handlers: `on_mount` `:356`, `_refresh` `:480`, buttons `:761`, Fixed SMS `:906-983`, mood `:1048-1114`, proxies `:1185`, snap `:1217`, sms `:1258`. Shortcuts: Q=quit, R=refresh.

## 🧪 Tests / scripts / data
- `tests/` — `test_fixed_state.py`, `test_fixed_integration.py`, `test_debug_utils.py`, `test_db_reply_engine.py`, `test_irc.py` (manual IRC test)
- `scripts/` — capture_*.py protocol recon (READ-ONLY, do not edit for features)
- `captures/` — 11 live-traffic JSON captures (reference)
- `data/bot_data.db` — runtime SQLite (gitignored)
- `docs/PROJECT_MAP.md` (37KB full map), `docs/PROTOCOL_ANALYSIS.md` (iSexyChat Socket.IO, Chatib/Coomeet, EmeraldChat analysis)

---

## 🔄 Architecture flow
```
src/main.py
 ├─ src/config.json
 ├─ src/reply_engine.py      ← data_dir/input/*.txt + data_dir/output/*.txt (external)
 ├─ src/proxy_manager.py     ← proxy.txt
 ├─ src/db.py                ← data/bot_data.db
 ├─ src/fixed_sms_engine.py  ← fixed_sms.folder txt files + snap_username_file
 ├─ src/db_reply_engine.py, src/mood_manager.py, src/thread_manager.py
 ├─ sites/joingy.py          (HTTP API)
 ├─ sites/isexychat.py       (Playwright)
 └─ dashboard/cli.py         (Textual TUI) ← all engines
```
Bot dispatch (`src/main.py:150-169`): `method=="http_api" and name=="joingy"` → JoingyBot; `method=="playwright" and name=="isexychat"` → IsexychatBot; else warn "not implemented" (chatrandom is `enabled:false`).

**State machine** (`reply_engine.py`): `GREETING → AGE_GENDER → COUNTRY → COUNTRY_REPLY → MIDDLE_CHAT → SHARE_SNAP → END`; MIDDLE_CHAT branches: horny/flirty → ASK_SNAP; how_are_you/warm/busy/normal → stay (max 8 loops → ask_snap).

**Reply mode priority:** Fixed SMS (if `fixed_sms.enabled`) → DB reply bank (if `db_detect.enabled`) → template `ReplyEngine`.

## ⚙️ Config keys (`src/config.json`)
- Global: `snap_username`, `data_dir` (external txt templates: `../New folder (2)/papipapi-2.2/data`), `template_dir`, `no_greeting`, `max_context_per_user=15`, `reply_delay_min_sec=2`, `reply_delay_max_sec=6`, `snap_share_after_n_messages=3`, `proxy_file`, `use_proxy`, `db_path`, `autostart=false`, `reply_mode="template"`, `mood="normal"`
- `db_detect`: `{enabled:false, db_path:"data/reply_bank.db", match_by:[mood,stage,trigger], fallback_mode:"template"}`
- `fixed_sms`: `{enabled:false, folder:"C:/Users/papi/Desktop/New folder", loop:true, pick_mode:"least_used_random", recursive:false, snap_username_file:"C:/Users/papi/Desktop/c t f/sc.txt"}`
- `sites.joingy`: enabled, api_base `https://back.joingy.com`, max_sessions 20, poll_interval_sec 1
- `sites.isexychat`: enabled, url `https://chat.isexychat.com/`, max_sessions 5, channel `#ifap`, headless true
- `sites.chatrandom`: enabled **false** (not implemented)

## 🧠 Key behaviors / constants
- Snap share: after N msgs (default 3), template engine injects `snap_username` → logged as lead (`log_snap_lead`)
- Reply delay: random 2–6s; dedup: global + per-conv used sets
- Proxy: 5 fails → `available=False`; round-robin `get()`, report `release(success)`
- Crash recovery: 3 retries (Joingy) / 2 retries (iSexyChat), exponential backoff via `CrashTracker.can_retry()`
- Health check: every `--health-interval` (default 60s) removes dead/stale sessions (stale = no msgs 3min, Joingy)
- Sessions: Joingy max 20, iSexyChat max 5
- Debug logs: `src/logs/*.jsonl` rotating (5MB, 3 backups)

## ▶️ Commands
- Run: `tools/run.bat` or `cd src && python main.py [--debug] [--health-interval N]`
- Install: `tools/install.bat`
- Tests: `python tests/test_fixed_state.py`, `python tests/test_fixed_integration.py`, `python tests/test_debug_utils.py`
- Module smoke tests: `python src/fixed_sms_engine.py`, `python src/mood_manager.py`, `python src/thread_manager.py`, `python src/db_reply_engine.py`

---
*Generated 2026-10-05. Update this map when files/anchors change.*