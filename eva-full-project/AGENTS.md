# AGENTS.md — EVA Bot (root project) — প্রতিটা agent এটা আগে পড়বে

এই ফাইল হলো এই প্রজেক্টের **মূল গাইড**। নতুন agent বা নতুন session শুরু হলে
এখান থেকে শুরু করবে। ইউজার বাংলায় কথা বলেন — উত্তর বাংলায় দেবে (টেকনিক্যাল
শব্দ ইংরেজিতে থাকতে পারে)। ইউজার অপ্রয়োজনীয় কথা, বানানো setup, বা কাজ না-করা
জিনিস পছন্দ করেন না — তাই ছোট, সরাসরি, যাচাই-করা পরিবর্তন দাও।

---

## 0. AUTONOMOUS ENGINEER LOOP (প্রতিটা কাজে বাধ্যতামূলক)

**Mission:** EVA Bot-এর কাজ (build/fix/feature/debug) নির্ভুলভাবে শেষ করা — zero known bug, ভালো performance, নিরাপদ code।

1. **Analyze** — কোড বদলানোর আগে: সংশ্লিষ্ট ফাইল ও function পড়ো; tech stack-এর জন্য দরকার হলে latest docs দেখো
   (sandbox-এ শুধু github, npm, pypi, files.pythonhosted.org reachable — অন্য সাইটে না গেলে সেটা রিপোর্টে লেখো)। Finding-কে CONFIRMED / LIKELY / UNKNOWN ভাগ করো।
2. **Plan** — কোড লেখার আগে ছোট technical plan লেখো: কোন ফাইল/function বদলাবে, কেন, কী ঝুঁকি, কী test হবে।
   (ছোট fix-এও ৩–৫ লাইন যথেষ্ট; বড় feature হলে ইউজারকে approach জিজ্ঞেস করো — `ask_user`।)
3. **TDD** — প্রতিটা নতুন feature-এর জন্য test script আগে বা একসাথে লেখো। Bug fix-এ একটা regression check যোগ করো
   (যেখানে bug ধরা পড়ত)। Existing test (`test_flow.py`, `test_live.py`, `test_fuzz.py`, `test_matcher.py`, `demo_chat.py`) বাড়াও; নতুন test ফাইল root-এ রাখো।
4. **Execute** — clean, modular, minimal change। Unrelated code reformat করবে না। Hard rules (§4) মানো।
5. **Debug** — পরিবর্তনের পর চালাও (sandbox-এ যা সম্ভব: py_compile, import, unit/flow/fuzz/demo, stubbed GUI import — §5)।
   Error হলে console/log পড়ো (`data/logs/`, Dashboard LIVE LOG), root cause খোঁজো, fix করো, আবার চালাও।
   Live chitchat network sandbox-এ নেই — সেটা "UNVERIFIED (live)" হিসেবে লেখো।
6. **Verify (final audit)** — পরিবর্তিত ফাইলের security check: secret/token log বা zip-এ যাচ্ছে কিনা (§4 rule 5),
   unbounded loop/timeout/retry, path hard-code, unhandled exception। `python -m pyflakes <files>` দিয়ে undefined name দেখো (unused import blocking নয়)।
   তারপর §5 verify gate পুরো চালাও।
7. **Output** — শেষে দাও: (ক) কী বদলেছে (ফাইল + function), (খ) **test report** — প্রতিটা command, pass/fail সংখ্যা, এবং কী চালানো যায়নি,
   (গ) remaining risk, (ঘ) প্রয়োজনে zip + path। "done" বলার আগে §5 gate PASS হতে হবে; একটাও FAIL থাকলে done নয়।

**Memory:** কাজ শেষে `python -m ops.tools.memory add session/bug/decision/question ...` (root AGENTS.md §0/§4 — mandatory)।

---

## 1. ৩০ সেকেন্ডে প্রজেক্ট

EVA Bot একটি Python (PyQt6 GUI) অ্যাপ। chitchat.gg-তে random stranger-দের সাথে
**auto match → chat → reply → skip → next** করে। দুই ভাবে চলে:

| Mood | কীভাবে | কোড |
|---|---|---|
| 🌐 **LIVE BROWSER** | Camoufox browser automation (login, UI chat) | `browser/browser_automation.py` |
| ⚡ **SESSION CHAT** | Browser ছাড়া — account session/token দিয়ে সরাসরি WebSocket chat | `core/session_chat.py` + `core/ws_transport/` |

দুই mood-ই **একই reply engine** (`chat/rule_bot.py` → `ChatRuleBot`, ভিতরে
`eva_flow.py` funnel) এবং **একই timing config** (`data/config.json`) ব্যবহার করে।
Reply content আসে `data/input/` (ইউজার কী লিখল → trigger) আর `data/output/`
(bot কী লিখবে → reply লাইন) এর `.txt` ফাইল থেকে।

---

## 2. ফোল্ডার ম্যাপ

```
run.vbs                    → Windows GUI launcher (pythonw -m entry.main, console নেই)
run_console.bat            → একই GUI, CMD window সহ (debug)
install.bat / forceinstall.bat → venv + packages + Playwright/Camoufox setup
test.bat → Windows test runner (matcher + live + fuzz + demo + tools/live_chat)
entry/main.py              → PyQt6 GUI (pages: Dashboard, Live Chat, Sessions, Accounts, Settings) ~2600 লাইন।
                             Logs একটাই জায়গায়: Dashboard-এর "LIVE LOG" panel (`_build_logs_panel`)।
                             Settings → CHAT TIMING: "New Chat Delay (s)" (একটাই field, default 5) + "Silence timeout (s)" (default 90)।
entry/thread_manager.py    → browser mode worker orchestration (QThread + signals)
entry/cli_runner.py        → CLI runner (GUI ছাড়া)
entry/paths.py             → project_root(), data_dir()  ← সব path এখান থেকে
core/session_chat.py       → SESSION CHAT: source discovery, token resolve, _ChatRuleEngine, SessionChatWorker(QThread)
core/ws_transport/         → chitchat.gg WebSocket protocol:
    socketio_codec.py        Engine.IO v4 / Socket.IO v5 frame codec
    chitchat_socket.py       WS client          chitchat_api.py   REST client
    ws_chat_loop.py          state machine (queue → matched → chat → skip → next)
    protocol.py              capture-derived constants
    protocol_manifest.json   protocol SOURCE OF TRUTH (সব fact + evidence)
core/config_loader.py      → config.json loader: load_chat_timing(), load_runtime_config(), load_human_behavior(),
                             save_config_sections() (section merge — অন্য key অক্ষত থাকে)
core/engine_bridge.py      → engine ↔ worker bridge
core/account_manager.py    → account list / session store helpers
core/resource_governor.py  → CPU/RAM watchdog (psutil)
browser/browser_automation.py → LIVE BROWSER chat lifecycle (Camoufox/Chromium) — বড় ও fragile
browser/browser_engine.py  → Camoufox বা Chromium launch abstraction (Playwright)
browser/context_pool.py    → একটা browser, অনেক isolated context
browser/account_session_store.py → account session persistence (storage_state.json, metadata.json …)
browser/human_behavior.py  → typing / pause / read-time helpers
chat/rule_bot.py           → ChatRuleBot (public reply API) — EVA_ENGINE env (default flow)
eva_flow.py                → funnel state machine (EvaFlowBot) ← মূল flow logic। EVA_MAX_REPLIES (default 0 = cap off)
chat/rules.py              → legacy RuleEngine (EVA_ENGINE=legacy) + TXT matcher + middle-chat pool loader
chat/common_scan.py        → regex classifier (gender/age/country)
chat/geo_handler.py        → country / geo detection
chat/style_analyzer.py     → user typing style mirror
chat/persona.py            → persona layer (legacy engine)
chat/tg_brain.py           → reference TG stage rules (optional fallback)
chat/horny_flirty_db.py    → horny / flirty keyword DB (আলাদা file)
chat/database/loader.py    → DB loader (optional বড় DB; না থাকলে skip, crash নয়)
data/config.json           → SETTINGS: chat_timing, human_behavior, background_tabs, performance, ban_detection,
                             replies, website_visits, context_pool, engine_config, resource_governor, runtime
data/input/*.txt           → trigger keywords (ইউজার কী বলল) + input/middle_chat/
data/output/*.txt          → reply lines (bot কী বলবে) + output/middle_chat/
data/local_db/             → extra DB + stage_rules/*.json (বড়; optional)
data/snap_ids.txt          → snapchat ID pool (round-robin)
data/unique_sites.txt, urls.txt → background-tab sites
data/logs/                 → chat_debug.log, gui_console.log (zip-এ নেই, runtime এ তৈরি)
account_sessions/<key>/    → storage_state.json (TOKEN!), metadata.json, fingerprint.json (zip-এ নেই)
configs/session.json       → (optional) manual session/token source — SECRET (zip-এ নেই)
run_chat.py                → interactive REPL: নিজে stranger হয়ে bot-এর সাথে chat
demo_chat.py / demo_flow.py → scripted stranger → END demo
tools/live_chat.py         → interactive REPL (test.bat থেকে চলে)
tools/coverage_check.py    → TXT matcher DB coverage checker
test_*.py                  → test (নিচে §5)
docs/                      → FLOW_SPEC.md (একমাত্র active spec),
skills/                    → task-ভিত্তিক playbook (নিচে §3)
```

**নিয়ম:** data-র path কখনো hard-code করবে না — `entry/paths.py`-র `data_dir()`
বা `project_root()` ব্যবহার করো।

---

## 3. SKILLS — কোন কাজে কোন skill পড়বে

| কাজ | পড়ো |
|---|---|
| প্রজেক্ট বুঝতে চাও / কোথায় কী আছে | `skills/project-map/SKILL.md` |
| ⚡ SESSION CHAT চালু হচ্ছে না / live chat বন্ধ / token সমস্যা | `skills/session-chat-debug/SKILL.md` |
| যেকোনো error / traceback / EXE-এর DLL error / crash | `skills/fix-error/SKILL.md` |
| bot-এর reply বদলাতে / নতুন line যোগ করতে / funnel বুঝতে | `skills/reply-content/SKILL.md` |
| GUI page / button / Qt signal যোগ বা বদল | `skills/gui-dashboard/SKILL.md` |
| chitchat.gg WebSocket protocol বদলাতে হলে | `skills/chitchat-protocol/SKILL.md` |
| কাজ শেষে যাচাই (কোন test কখন চালাবে) | `skills/verify/SKILL.md` |

একই সময়ে একাধিক skill লাগতে পারে। সবসময় **verify** skill-এর gate দিয়ে শেষ করো।

---

## 4. কাজের নিয়ম (HARD RULES)

1. **Read first.** কোড বদলানোর আগে সংশ্লিষ্ট ফাইল ও function পড়ো। অনুমান
   করে edit করবে না। Finding-কে **CONFIRMED** (কোড/log থেকে প্রমাণিত),
   **LIKELY** (প্রমাণ আংশিক), **UNKNOWN** (জানা নেই) — এভাবে আলাদা করে বলো।
2. **Minimal change.** শুধু দরকারি জিনিস বদলাও। working architecture, public API,
   বা অন্য feature ভাঙবে না। unrelated file reformat করবে না।
3. **No new setup/launcher.** ইউজার আলাদা `.bat`/session-mode/setup চান না।
   নতুন feature সবসময় এই project-এর ভিতরে যাবে (GUI page বা existing engine)।
4. **Graceful fallback.** optional subsystem (Camoufox, ContextPool, PyQt বা
   aiohttp না থাকলে) ভাঙলে যেন পুরো app না পড়ে — error message দেখিয়ে degrade করো।
5. **Secrets কখনো log/zip/git-এ নয়।** `account_sessions/`, `storage_state.json`,
   `configs/session.json`, cookie, JWT, proxy credential — এগুলো কখনো print,
   log, বা zip-এ দেবে না। Debug output-এ শুধু boolean/নাম দেখাও (যেমন `has_token: true`).
6. **Protocol guess নিষেধ।** chitchat.gg wire protocol-এর প্রতিটা behavior
   `core/ws_transport/protocol_manifest.json`-এর capture evidence থেকে আসবে।
   না জানলে ইউজারের কাছে নতুন capture চাও।
7. **Bounded everything.** network-এ timeout, retry-এ backoff (অসীম loop নয়),
   log file rotate, queue bound।
8. **Verify না করে "done" বলবে না।** §5 এর gate পাস না হলে কাজ শেষ নয়। যা চালাওনি
   তা "পাস" বলবে না। Static check আর runtime check আলাদা করে লেখো।
9. **Windows-aware.** ইউজার Windows-এ `C:\Users\...\Downloads\...` থেকে চালায়।
   path-এ `os.path`/`pathlib` ব্যবহার করো; `\` hard-code করবে না; console encoding
   UTF-8 (`PYTHONIOENCODING=utf-8`) মাথায় রাখো। `pythonw` (windowless) এ `sys.stdout`
   `None` হতে পারে — `print` করার আগে check করো।
10. **Sandbox-এ chitchat.gg network নেই।** live chat test ইউজারের PC-তে হয়। Sandbox-এ
    শুধু offline/mock/unit test দিয়ে যাচাই হবে — এবং সেটা স্পষ্ট করে বলবে।

---

## 5. VERIFY GATE (কাজ শেষে বাধ্যতামূলক)

Root project-এ (এই folder থেকে):

```bash
python -m py_compile entry/main.py entry/thread_manager.py entry/paths.py \
    browser/browser_automation.py core/config_loader.py core/session_chat.py \
    core/ws_transport/ws_chat_loop.py
python -c "import chat; import eva_flow; print('import ok')"
python -c "import core.ws_transport.chitchat_api, core.ws_transport.ws_chat_loop; print('ws import ok')"
python test_matcher.py      # input → output pool round-trip
python test_live.py         # funnel state machine (44 checks)
python test_fuzz.py         # random input, state valid (4 checks)
python test_flow.py         # flow ও branch (126 checks)
python demo_chat.py         # scripted stranger → END
python test_diagnostics.py  # crash log + redaction + doctor (13 checks)
```
Windows-এ একসাথে: `test.bat` (matcher + live + fuzz + demo)।

Session chat বদলালে অতিরিক্ত:
```bash
QT_QPA_PLATFORM=offscreen python -m core.session_chat --list   # source discovery
QT_QPA_PLATFORM=offscreen python -m core.session_chat --help   # CLI ঠিক আছে কি
```
(network ছাড়া live connect ব্যর্থ হওয়া স্বাভাবিক — কিন্তু error পরিষ্কার হতে হবে, crash নয়।)

GUI বদলালে: `QT_QPA_PLATFORM=offscreen python -c "import entry.main"` (import-level check)।

**Result রিপোর্টে লেখো:** কোন command চালানো হয়েছে, pass/fail সংখ্যা, এবং কী চালানো যায়নি (যেমন live chat)।

---

## 6. ডেলিভারি / ZIP

- zip-এ **থাকবে:** সব source, `data/` (config/txt), `docs/`, `skills/`, `AGENTS.md`, `README.md`।
- zip-এ **থাকবে না:** `account_sessions/` (login token), `configs/session.json`,
  `data/logs/`, `__pycache__/`, `*.pyc`, `build/`, `dist/`, `.venv/`, পুরনো `*.zip`।
- zip বানানোর পর খুলে যাচাই করো: secret নেই, key file আছে, ফাইল সংখ্যা ও byte size লেখো।
- ইউজারকে দেবে: zip ফাইলের নাম, byte size, এবং download link।

---

## 7. ইউজারের সমস্যা এলে

0. প্রথমে ইউজারকে চালাতে বলো: `python -m tools.doctor` (project folder থেকে) — report সেভ হয় `data/logs/doctor_report.txt`-এ।
   আর `data/logs/crash.log` (সব uncaught error, GUI ও worker thread থেকে, token masked)।
1. আগে `skills/fix-error/SKILL.md` অনুযায়ী log চাও (`data/logs/`, Dashboard-এর LIVE LOG panel,
   বা `[session]` লাইন)।
2. সমস্যা কোন mood-এ — LIVE BROWSER নাকি SESSION CHAT — আগে নির্ধারণ করো।
3. Root cause বাংলায় ব্যাখ্যা করো → minimal fix → verify gate → zip + link।

---

## 8. বর্তমান অবস্থা (snapshot)

- **Timing (v17 + v20):** Settings-এ শুধু "New Chat Delay (s)" (একটাই মান, min=max, default 5) + "Silence timeout" (default 90)। Dashboard-এ কোনো timing field নেই। **Browser rest বন্ধ (v20)** — Rest interval/duration আর নেই (code ও config থেকে সরানো)।
- **Skip নিয়ম (v17):** Max Replies cap নেই — snap share পর্যন্ত chat চলে; partner চুপ থাকলে Settings-এর "Silence timeout" (default 90s) পর্যন্ত অপেক্ষা, তারপর পরের user। Engine END (snap ছাড়া, যেমন underage) হলে farewell একবার যায়, তারপর আর reply নেই → পরের user (v18, `farewell_sent`)। New Chat Delay শুধু chat-এর মাঝে wait (Settings থেকে)। Dashboard-এ timing override নেই।
- **Session chat:** ইন্টিগ্রেটেড (SESSIONS page-এ ⚡ box)। Sandbox-এ engine ও
  funnel চলে (`hi` → `hi there`, `m 21` → `f.25`, `usa` → `wanna be brave with me`);
  chitchat.gg network sandbox-এ ব্লকড — **final live test ইউজারের PC-তে বাকি।**
- **Browser mode:** আগের মতোই, একই ChatRuleBot।
- **Test (v20):** matcher ✓, live 44/44, fuzz 4/4, flow 126/126, demo ✓; `import core.ws_transport.*` ✓; Settings save logic (stubbed Qt) ✓ (sandbox-এ যাচাই)।
- **Known risk:** `chat/database/loader.py`-তে hard-coded DB path (`chat/chat_db.py` v22-তে মুছে ফেলা হয়েছে)
  আছে (`EVA_BOT_DB_ROOT` env দিয়ে override হয়)। `browser/browser_automation.py`
  বড় ও fragile — ছোঁয়ার আগে ভালো করে পড়ো।
- **Session data sensitivity:** zip-এ `account_sessions/` থাকলে তাতে login token
  থাকে — ডেলিভারি zip-এ এটা রাখা উচিত নয় (§6)।

---

## 9. Agent-কে শেষে যা লিখতে হবে

- **Result:** কী হলো (এক লাইনে)
- **Root cause:** CONFIRMED / LIKELY / UNKNOWN আলাদা করে
- **Changes:** ফাইল + function
- **Verification:** যেসব command সত্যি চালানো হয়েছে + pass/fail
- **Remaining risk:** কী যাচাই হয়নি (যেমন live network)

- **v19:** Picture sender সম্পূর্ণ সরানো হয়েছে — Dashboard-এর PICTURE SENDER group, Pictures page, Settings-এর picture config, browser/thread_manager-এর pic পরামিতি ও upload কোড। Chat engine (eva_flow / chat/*) অপরিবর্তিত; user-এর "send pic" কথার keyword detection engine-এ আছে, সেটা picture sender নয়।
- **v20 (recheck):** (1) `entry/main.py` Settings-এর New Chat Delay min/max + Rest UI → একটাই "New Chat Delay (s)" (default 5); save-এ rest key পাঠানো হয় না (config অক্ষত)। (2) `data/config.json` + `core/config_loader.py` default new_chat_delay 5/5। (3) `core/ws_transport/chitchat_api.py` `List` import ও `ws_chat_loop.py` অচেনা `ReplyEngine` type-hint ঠিক (আগে pyflakes-এ undefined name ছিল; runtime-এ lazy annotation-এর কারণে crash হতো না)। (4) `entry/main.py` unused `sms_enabled`। (5) `docs/FLOW_SPEC.md` Max Replies section আপডেট (cap off, horny 5-cap কোডে নেই)। (6) Gate-এ `ws import ok` লাইন যোগ। (7) Project folder repo-র ভিতরে `eva-full-project/` হিসেবে এলো। (8) Browser rest বন্ধ (`_schedule_next_rest`/`_maybe_take_rest`), rest config key সরানো, CLI-এর "Chat Timeout 30s" hard-code → আসল silence timeout দেখায়। (9) `config/eva_config.json` (কোনো code পড়ত না) মুছে ফেলা হয়েছে।
- **v22 (debug-pass cleanup):** dead module মুছে ফেলা: `_analyze.py`, `flow_reference.py`, `chat/chat_db.py`, `chat/content_filter.py`, `browser/device_signin.py`, `core/signin_window.py` (কোনো entry থেকে import নেই; `entry/main.py`-তে `signin_window` reference সরানো হয়েছে, আচরণ অপরিবর্তিত)। Junk মুছে: `browser/unique_sites.txt` (১০ লাখ লাইন, কোনো code পড়ে না — active list `data/unique_sites.txt`), `data/snapchat_fallback.txt`, `data/local_db/archive_flirty_questions.txt`, `data/local_db/keyword_db_*.zip` (কোনো reference নেই)। Installer/runner duplicate মুছে: `docs/INSTALL_SMOOTH.*`, `docs/RUN_SMOOTH.*`, `docs/start_bot.bat`, `test_matcher.bat` (test.bat-এ আছে)। Stale doc মুছে: `docs/Architecture.txt`, `docs/PROJECT_STATE.md`, `docs/TASKS.md`, `docs/readme.txt`, `docs/TG_REFERENCE/`। Runtime cache `data/.*.idx` নিজে থেকে আবার তৈরি হয় (round-robin position reset মাত্র)। Kept: `install.bat`, `forceinstall.bat`, `run.vbs`, `run_console.bat`, `test.bat`, `demo_flow.py`, `tools/coverage_check.py`, legacy engine-এর `data/local_db/stage_rules/`। Verify: gate সব PASS (§5), `tools/doctor` Qt widgets FAIL শুধু sandbox-এ libGL নেই বলে। 
