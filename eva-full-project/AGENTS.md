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
tools/verify_gate.py       → §5 gate এক কমান্ডে (`python tools/verify_gate.py`), প্রতি step PASS/FAIL
tools/project_map_check.py → project.map.json-এর সব ফাইল ক্লাসিফাই হয়েছে কি না যাচাই
tools/build_zip.py         → clean release zip এক কমান্ডে (§6)
tools/gui_import_check.py  → entry.main stubbed PyQt6/winsound-এ import হয় কি না (sandbox-এ GUI render নয়)
tools/secret_scan.py       → dependency-free secret pattern scan (`--selftest` সহ); মান প্রিন্ট করে না
tools/critical_guard.py    → CRITICAL_CORE ফাইল বদলে test_*.py না বদলালে FAIL (git diff; gate-এ নেই)
tools/rules_coverage.py    → chat/rules.py line coverage (`coverage` package লাগে; `--floor`)
test_rules_characterization.py → chat/rules.py contract/invariant test (reply wording নয়)
project.map.json           → machine-readable file map: প্রতিটা ফাইলের risk class (CRITICAL_CORE/RUN_AND_SETUP/DATA_MAPPING/SUPPORT_MODULES/TOOLS_AND_TESTS/DOCS) ও কোন test চালাতে হবে
test_*.py                  → test (নিচে §5)
docs/                      → FLOW_SPEC.md (একমাত্র active spec),
skills/                    → task-ভিত্তিক playbook (নিচে §3)
```

**নিয়ম:** data-র path কখনো hard-code করবে না — `entry/paths.py`-র `data_dir()`
বা `project_root()` ব্যবহার করো।

---

## 3. SKILLS — কোন কাজে কোন skill পড়বে

**Risk class অনুযায়ী routing** (ফাইল কোন class-এ, সেটা `project.map.json`-এ; নিয়ম ও test সেখান থেকে):

| তুমি যা বদলাচ্ছ | Class | আগে কী | পরে কী |
|---|---|---|---|
| reply engine, session/WS, browser automation, GUI main | CRITICAL_CORE (HIGH) | TDD: আগে failing test; snap/greeting/middle-chat-এ অনুমোদন; `tools/critical_guard.py` | `tools/verify_gate.py` PASS |
| install/run/test .bat, config loader, requirements | RUN_AND_SETUP (MEDIUM) | script পড়ে যাচাই (sandbox-এ .bat চলে না) | gate + কারণ স্পষ্ট করে লেখা |
| data pool (input/output/local_db), snap data | DATA_MAPPING (LOW) | snap ফাইল → অনুমোদন | `test_matcher.py`, `test_flow.py` |
| helper/support module | SUPPORT_MODULES (LOW) | নাম/public API stable রাখো | সংশ্লিষ্ট test |
| tools, tests, skills, docs | TOOLS_AND_TESTS / DOCS (NONE) | — | `tools/project_map_check.py` |

নতুন ফাইল যোগ করলে `project.map.json`-এ class যোগ করো, না হলে `project_map_check` FAIL দেবে।


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
11. **কখনো বানিয়ে বলবে না (NO FABRICATION) — এটা সবচেয়ে বড় নিয়ম।**
    - শুধু **এই মুহূর্তে** tool/command-এর আউটপুট দেখে যা জানা গেছে, সেটাই বলবে।
    - ফাইল পড়েছ, পেয়েছ, চালিয়েছ, pass করেছে — এমন দাবি করবে **শুধু** তখন, যখন tool call সফল হয়েছে এবং আউটপুট দেখেছ।
    - ফাইল/attachment না পেলে, পথ না পেলে, command ব্যর্থ হলে — সেটা সরাসরি বলবে। কল্পিত বিষয়বস্তু, কল্পিত লাইন নম্বর, কল্পিত test ফলাফল, কল্পিত ফাইলের ভিতরের তথ্য লিখবে না।
    - জানা না থাকলে সরাসরি বলবে "জানি না / এখনো যাচাই করিনি"। অনুমানকে তথ্য হিসেবে উপস্থাপন করবে না।
    - আগের session-এর তথ্য (memory/summary) এখনকার বাস্তব অবস্থা হিসেবে ধরবে না; দরকার হলে আগে আবার যাচাই করবে।
    - Gate, test, build "পাস" লেখার আগে সেটা এই session-এ চালানো হয়েছে কি না নিশ্চিত হও।

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
python test_rules_characterization.py  # chat/rules.py contract + invariants (33 checks, v26)
python test_ws_transport.py  # ws codec, nonce guard, loop safety, worker cleanup (32 checks)
python test_config_loader.py  # config save keeps decimals; nan/inf refused (12 checks, v27)
```
**এক কমান্ডে সব (রেকমেন্ডেড):** `python tools/verify_gate.py` — উপরের সব step + project map + GUI stub import চালায় এবং শেষে `GATE: N/M steps passed` দেখায়। v26: `test_rules_characterization`, `secret_scan --selftest` + `secret_scan`, `pip-audit -r data/requirements.txt` যোগ; optional `gitleaks` (binary না থাকলে SKIP), `pyflakes`, `rules_coverage --floor 50` (module না থাকলে SKIP) — SKIP কখনো FAIL নয়, তবে রিপোর্টে লিখতে হবে।

Windows-এ একসাথে: `test.bat` (matcher + live + fuzz + demo)।

Session chat বদলালে অতিরিক্ত:
```bash
QT_QPA_PLATFORM=offscreen python -m core.session_chat --list   # source discovery
QT_QPA_PLATFORM=offscreen python -m core.session_chat --help   # CLI ঠিক আছে কি
python -m core.session_chat --save                    # token যাচাই (hidden prompt) → configs/session.json
python -m core.session_chat --run --max-matches 3     # browserless live chat (GUI লাগে না)
python -m core.session_chat --import <path>/session_cookies.LOCAL.json   # browser capture-এর cookie → যাচাই → configs/session.json
```
(network ছাড়া live connect ব্যর্থ হওয়া স্বাভাবিক — কিন্তু error পরিষ্কার হতে হবে, crash নয়।)

GUI বদলালে: `QT_QPA_PLATFORM=offscreen python -c "import entry.main"` (import-level check)।

**Result রিপোর্টে লেখো:** কোন command চালানো হয়েছে, pass/fail সংখ্যা, এবং কী চালানো যায়নি (যেমন live chat)।

---

## 6. ডেলিভারি / ZIP

- zip-এ **থাকবে:** সব source, `data/` (config/txt), `docs/`, `skills/`, `AGENTS.md`, `README.md`।
- zip-এ **থাকবে না:** `account_sessions/` (login token), `configs/session.json`,
  `data/logs/`, `__pycache__/`, `*.pyc`, `build/`, `dist/`, `.venv/`, পুরনো `*.zip`।
- **এক কমান্ডে zip (রেকমেন্ডেড):** `python tools/build_zip.py --out EVA_Bot_FINAL.zip` — runtime ফাইল মুছে, `project_map_check --release` (runtime/secret থাকলে থামে), zip (eva-full-project + capture_tool), testzip ও forbidden-path scan। শেষে `BUILD: OK` না দেখা পর্যন্ত ইউজারকে zip দেবে না।
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
- **v25 (risk-class setup):** `project.map.json` (ফাইল → risk class, 137 ফাইল সব ক্লাসিফাইড), `tools/project_map_check.py` (unclassified/stale/never-ship/missing-test চেক; probe ফাইলে FAIL ও cleanup-এ OK যাচাই), `tools/verify_gate.py` (13 step; negative test: exit code পাস হয়), `tools/gui_import_check.py` (ad-hoc stub থেকে repo tool-এ)। AGENTS §3-এ risk routing টেবিল। External spec-এর TypeScript/Next/Prisma/K8s অংশ এই Python desktop project-এ প্রযোজ্য নয় — ইচ্ছাকৃতভাবে বাদ। GitHub auto skill-discovery ও স্বয়ংক্রিয় deploy বাদ (অযাচাইযোগ্য, sandbox-এ GitHub search/CI চালানো যায় না)।
- **v26 (debug-pass, approved "recommended" set 1–4):** (1) pyflakes 51 → 0: unused import/variable মুছে, placeholder-less f-string ঠিক করা হয়েছে; availability probe (`sync_playwright`, `Camoufox`, `QtWidgets`) আচরণ অপরিবর্তিত রেখে `importlib`/`del`-এ রাখা হয়েছে। `chat/rules.py`-তে unused `st` লাইন মুছেছে (`flirty_state` init-এ সবসময় থাকে)। (2) `test_rules_characterization.py` (33 check): helper, init shape, decide_reply contract, edge input, blocked/END, 300-message soak। Seed-determinism দাবি করা হয়নি — `data/.*.idx` round-robin cursor disk-এ থাকে। Coverage (`tools/rules_coverage.py`): এই test একা 52%, test_live+test_flow সহ 57%। (3) `tools/critical_guard.py`: CRITICAL_CORE পরিবর্তন + test পরিবর্তন না হলে FAIL — test করা হয়েছে clone-এ (FAIL exit 1, `--allow` exit 0)। Gate-এ নেই। TDD ক্রম যাচাই করে না। (4) gitleaks: sandbox-এ binary পাওয়া যায়নি (GitHub release CDN ব্লকড, PyPI/npm-এ নেই) → gate-এ optional SKIP; বদলে dependency-free `tools/secret_scan.py` সবসময় চলে (selftest সহ, 1টি test fixture-এ `secretscan: ignore`)। pip-audit `data/requirements.txt`: No known vulnerabilities। Gate: 19/19 pass, 1 skip (gitleaks)। **বাকি (অনুমোদন ছাড়া করা হয়নি):** GitHub Actions CI, decision log। **Observation (পরিবর্তন করা হয়নি):** reply pool-এ `what is ur name` প্রশ্নে `lick out me @ ...` ধরনের অসংলগ্ন/অনুপযোগী reply আসতে পারে — reply content ও snap logic-এর জন্য অনুমোদন লাগবে।
- **v27 (line-by-line debug pass, user request):** automated scan (ruff bug rules, vulture, AST open()-encoding scan) + manual read of the live session path: `socketio_codec`, `chitchat_api`, `chitchat_socket`, `ws_chat_loop`, `session_chat`, `config_loader` save/load, Settings save in `entry/main.py`.
  - **FIXED (TDD: test failed first, then passed):**
    1. `ws_chat_loop`: send-failure streak was never reset → after 3 failures every later match skipped at its first message. Now reset per match (`_enter_match_if_open`).
    2. `ws_chat_loop._send`: conversation read after the human delay → a reply could go to an empty/other conversation if the match changed. Now pinned at entry; dropped replies counted (`stats.dropped_replies`).
    3. `session_chat`: `WsChatLoop.start()` ran outside the `try`, so the API session was not closed if start failed. Moved inside.
    4. `config_loader.save_config_sections`: value was coerced to the type already on disk → hand-edited int `90` turned a saved `120.5` into `120`. Numbers now stored as float.
    5. `config_loader.save_config_sections`: `nan`/`inf` saved as "saved ✓", then silently replaced by defaults on load. Now refused (returns False, file untouched).
  - **Narrowed (no logic change on the normal path):** bare `except:` → `except Exception:` in `browser_automation.py` (4) and `entry/main.py` (1). Bare except also caught KeyboardInterrupt/SystemExit.
  - **Encoding:** `entry/main.py` devnull fallback stream now `encoding='utf-8'` (Windows cp1252 would raise on Bengali print).
  - **Debug:** session `[stat]` line now shows `dropped=` and `send_fail_streak=`.
  - **Gate:** `test_config_loader` added; `project.map.json` tests updated; `runtime_local` now also ignores `.ruff_cache/`, `.coverage`, `.mypy_cache/` (cache folders must not ship).
  - **FOUND, NOT CHANGED (needs your approval):**
    a. **Snap-share leak in matcher (snap logic → approval needed):** `chat/rules.py` pass 4 (token-subset) drops tokens shorter than 3 chars. Trigger `ur sc name` in `share_snap.txt` reduces to {your, name}, so "what is ur name" can get `data/output/share_snap.txt` lines (reproduced: 11 of 200 seeds). Line 16 of that file contains the crude line `lick out me @ %username%`, which is also sent as a reply to ordinary questions. Proposed fix: keep 2-char tokens in the subset check for snap triggers, and remove or rewrite the crude line. Waiting for your yes.
    b. **GUI race (entry/main.py):** `_on_session_done` clears `session_worker` even if a new session was started just after the old one ended. Needs a Windows GUI test (sandbox has no libGL).
    c. `parse_handshake` crashes on a non-dict OPEN payload (unlikely with the real server; not hardened).
    d. Dead code (vulture ≥60%): e.g. `chat/rules.py` `_wait_step_reply`, `_first_sms_reply`, `_middle_reply`; `browser/*` helpers; `ws` diagnostics `mark_read`, `moderation_standing`. Not removed (no approval for removal of non-trivial code).
  - **Sandbox limits:** no GUI (libGL), no Windows, no live chitchat.gg, no Playwright browser. Session path verified with synthetic fakes and the real `ChatRuleBot` engine only.
  - Gate: 20/20 pass, 1 optional skip (gitleaks). Coverage of `chat/rules.py`: 57% (unchanged).
- **v31 (Primary goal: Task 1 `--save` intercept + Task 2 browser-free `--run`):**
  - `tools/chitchat_capture/capture_session.py`: browser-এর নিজের খোলা `wss://` WebSocket URL intercept (`page.on("websocket")`) করে এবং `navigator.userAgent` নেয়। শুধু chitchat.gg host গ্রহণ (অনুমান নয়)। `capture_out/session_<time>/session_meta.LOCAL.json` লেখে (0600, token নেই)।
  - `core/session_chat.py`: `--import` meta ফাইল পড়ে `ws_url` ও `user_agent` `configs/session.json`-এ রাখে (অবৈধ URL বাদ)। `_socket_for()` সেভ করা URL ব্যবহার করে, না থাকলে protocol-এর captured URL।
  - `--run` পথে browser module লোড হয় না (যাচাই: `playwright`/`camoufox` import নেই)।
  - `test_session_save.py`: 31 check (আগের 21 + URL validation ও socket URL 10)। Gate 21/21।
  - **Spec-এর সাথে পার্থক্য:** spec-এর উদাহরণ `wss://chitchat.gg/...`; এই project-এ captured ও ব্যবহৃত URL `wss://api.chitchat.gg/...` (capture-এ এটিই দেখা গেছে)। Spec-এর `connect.sid` কুকি এই site-এর capture-এ নেই; auth cookie হলো `token` ও `__Secure-text-session`।
  - **Sandbox limit:** browser চালিয়ে আসল intercept এখানে হয়নি, live chitchat.gg-তে connect হয়নি।
  - **Spec-এর `main.py` বা আলাদা `websocket_bot.py` বানানো হয়নি** — project-এ `core/session_chat.py` একই কাজ করে (নিয়ম 3: নতুন runner নয়)।
- **v30 (browser → session bridge, user request "2"):**
  - `tools/chitchat_capture/capture_direct.py`: browser বন্ধ হওয়ার আগে chitchat.gg cookie export → `capture_out/<session>/session_cookies.LOCAL.json` (0600, শুধু cookie নাম/সংখ্যা print)। Selftest: 3 নতুন check, মোট 30 pass।
  - `core/session_chat.py --import <file>`: cookie file (Playwright storage_state বা cookie list) পড়ে chitchat cookie নেয়, `token` না থাকলে থামে, `/users/me` দিয়ে যাচাই করে সব chitchat cookie `configs/session.json`-এ লেখে (socket-এর জন্য `__Secure-text-session` সহ)। 401 বা নেটওয়ার্ক fail হলে কিছু লেখে না।
  - `tools/build_zip.py`: forbidden pattern-এ `session_cookies` যোগ (zip-এ যেন কখনো না যায়)।
  - `test_session_save.py`: 21 check (আগের 12 + import 9)। Gate 21/21 pass (চালানো হয়েছে)।
  - **Sandbox limit:** Chrome/Playwright browser চালিয়ে আসল capture এখানে চলেনি, live chitchat.gg-তে connect হয়নি। Export ও import আলাদাভাবে synthetic input দিয়ে যাচাই হয়েছে।
  - **এখনো নেই:** `--run` সরাসরি capture ফাইল থেকে চলে না; আগে `--import` করতে হয়।
- **v29 (browserless session chat — goal: saved session → WebSocket chat, no browser):**
  - `core/session_chat.py`: PyQt6 import optional → `--save` / `--run` CLI চলে GUI library ছাড়া (`test_session_save` PyQt6 block করে check করে)।
  - `--save`: token `GET /users/me` দিয়ে যাচাই করে `configs/session.json` লেখে (atomic, mode 0600)। 401 হলে কিছু লেখে না। Token কোথাও print হয় না; আগে শেষ 6 অক্ষর দেখাত — বন্ধ।
  - `--run`: `WsChatLoop.start()` এখন try-এর ভিতরে (আগে ব্যর্থ হলে API session বন্ধ হতো না)।
  - Gate: `test_session_save` (12 check) যোগ। `project.map.json` tests-এ যোগ।
  - **Known limit (not changed):** socket reconnect হলে chat loop জানে না; match server-side বন্ধ হয়ে গেলে bot silence timeout (90 s) পর্যন্ত অপেক্ষা করে। `GET /match/active`-এ match-এর তথ্য আছে কি না capture-এ নিশ্চিত নয় — তাই recovery যোগ করা হয়নি।
  - **Sandbox limit:** chitchat.gg-তে live connect হয় না; server response fake দিয়ে test করা হয়েছে।
- **v28 (thread_manager review, browser-mode orchestration, lines 1–1302 read):**
  - **FIXED:** `entry/thread_manager.py::stop_all_threads` built the "still closing" list by iterating the live `self.workers` dict on the shutdown thread, while the GUI thread removes finished workers. A concurrent removal could raise "dictionary changed size during iteration" and skip the force-cleanup block. Now iterates a `list(...)` snapshot. Reproduced the failure mode with a dict-mutation probe; the live thread path itself needs PyQt6 and was not run here.
  - **Lint only:** unused args/loop vars renamed (`cli_runner` signal handler, `test_ws_transport` stub, `thread_manager` loop).
  - **Checked, no bug:** account claim/proxy/worker creation, stagger, context pool acquire/release, governor wiring, engine heartbeat/drain, restart-after-failure path, GUI stop fallback (`shutdown_with_timeout` calls `on_all_threads_finished`).
  - **Low, not changed:** if the first thread finds no account while another starts later, `_start_single_thread` can emit `all_threads_finished` early (workers dict empty). Account exhaustion is run-wide, so this is rare; fix needs a Windows GUI run.
  - **Sandbox limits:** no PyQt6 GUI runtime here, so `thread_manager` has no executable test; verified by compile, read, and the dict probe.
  - Gate: 19/19 pass, 1 skip (gitleaks), exit 0.
- **v23 (ws_transport hardening):** `chitchat_api.send_message` — ambiguous failure (timeout / socket drop / 5xx) হলে একই `nonce` দিয়ে `GET …/messages?limit=20` থেকে message আছে কিনা দেখা হয়; থাকলে re-send হয় না (duplicate বন্ধ)। 4xx (422 ইত্যাদি) ও 403 Flagged আগের মতো সরাসরি raise। নতুন `find_message_by_nonce()` helper + `test_ws_transport.py` (22 checks)। Timing ও snap logic অপরিবর্তিত। Sandbox-এ live WebSocket যাচাই সম্ভব নয় (chitchat.gg allowlist-এ নেই) — শুধু fixture/unit।
- **v24 (approved, step-by-step):** (1) session reply floor `LoopConfig.min_reply_delay_s` 1.0 → 4.5 s (weebbsssc capture-এর human inbound→reply minimum, n=10, median 6.3 s, max 11.8 s); engine delay যদি বড় হয় তা রাখা হয়। `test_ws_transport.py` এখন 25 checks। (2) Root `tools/chitchat_capture/capture_direct.py`: multipart request body `post_data_buffer` থেকে পড়ে field নাম/ধরন বের করে (`parse_multipart`); text মান share-এ mask। selftest 28/28। README redaction সীমা সংশোধিত। **Unverified:** send-message body field নাম এখনো live capture-এ নিশ্চিত নয় — নতুন capture দরকার।
