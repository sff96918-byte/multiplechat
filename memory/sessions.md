# SESSIONS (নতুন আগে — newest first)

## 2026-10-10 | v10: debug upgrade (file log, ring buffers, export report)

New eva/debugtools.py: setup_debug_logging (logs/eva.log RotatingFile 1MBx5 ALWAYS DEBUG; eva logger level DEBUG when cfg debug=true), mask_secrets (token/cookie/password/secret keys + whole cookies dict), export_debug_report (config masked + session boolean-only + stats + last300 WS frames + API requests + engine decisions + 400 log lines -> logs/debug_report_*.txt). Socket: _recent deque300 + record_frame scrubs own cookie values (>=8 chars) from previews; API: _recent200 with status/ms/bytes + log.debug per request + log.warning on >=400. Flow+fixed engines: _decisions deque200 incl opener entries, decisions() accessor. GUI: debug checkbox in LOOP group, gui_tail deque800, Export Debug Report buttons on both mood footers, QTextEdit maximumBlockCount 2000, setup_debug_logging on app start + on START. CLI ws_bot: log file path print + last 15 decisions on stop. Tests 42/42 (5 new debugtools incl secret-leak regression).
## 2026-10-10 | v9: shared BOT SETUP page + snap.txt support

User asked: engine/fixed-sms-txt/snap settings main dashboard e na ki each mood e? Answer implemented: ekta shared BOT SETUP page (dui mood thekei ⚙️ button e khule, back = origin mood). Snap nicher feature: resolve_snap_usernames(cfg) in flow_reply_engine -- snap_file (one per line, # comment) > snap_usernames comma list; wired in ws_bot + server + GUI worker; tests/test_snap_resolve.py 4 tests. Setup page: fixed script preview (count + first lines), open-in-editor button, snap status label, engine summary labels on mood headers. Suite 37/37, protocol 24/24, session 7/7, GUI audit 11/11.
## 2026-10-10 | v8: mood dashboards (browser/session)

GUI rewrite: HOME page e 2 ta mood card (LIVE BROWSER / SESSION CHAT) -> QStackedWidget e totally different dashboard per mood. Browser mood: CDP live browser visible, bot start pulls cookies live via pull_and_save, in-bot auto-save task every 60s (cfg browser_autosave), pre-start GUI auto-save timer too. Session mood: option 1 = live browser -> Pull Session, option 2 = old saved session.json headless. Loop settings group per page, synced via apply_engine_all. Max-matches spin dropped (was dead code, LoopConfig has no max_matches). Static audit green, tests 33/33.
## 2026-10-10 | v7: persona removed, flow/fixed engine selector

PERSONA puro bad (GUI group, ws_bot/server Persona branch, config example, docs)। Engine selector: flow (SMS detect -> input/output bank matching) | fixed (FixedReplyEngine, configs/fixed_script.txt, opener=line1, per-partner pointer, exhaust -> loop skips match via leave_match)। tests/test_fixed_engine.py 7 tests। Suite 33/33, protocol 24/24, session 7/7।
## 2026-10-10 | v6.1: DASHBOARD_OPTIONS_BN.md (A-Z options mapping doc)

- ইউজার চাইলেন dashboard-এর সব option + config mapping A-Z করে দেখাতে। docs/DASHBOARD_OPTIONS_BN.md বানানো হলো (17টা UI option + config keys + timing + txt banks + troubleshooting)। zip-এ docs/ ফোল্ডারে থাকবে।
## 2026-10-10 | v6: realistic timing + session-expiry handling (+rebase lost-wiring fix)

- Found: rebase conflict resolution (--ours) silently reverted v4 wiring in ws_bot.py/server.py/config example — engine selection was missing there (gui had it). Re-applied + added v6 on top.
- New: timing config section (reaction pause/typing cps/read/micro-idle/new-chat delay) — defaults from legacy project data/config.json human_behavior/chat_timing; FlowReplyEngine.delay_for + opener_delay() use it; loop opener uses engine.opener_delay when available.
- New: SessionExpiredError (401) in chitchat_api; ws_bot preflight prints Bengali fix steps; GUI maps to 'SESSION মেয়াদ শেষ...' message.
- Tests: unit(+2 expiry) all OK, protocol 24/24, session 7/7.

## 2026-10-10 | v5: agent memory system + AGENTS.md v2

- ইউজার চেয়েছিল: agents-দের জন্য memory + improved AGENTS.md
- built: memory/ (INDEX, sessions, decisions, bugs_fixed, protocol_facts, user_preferences, open_questions) — পুরো প্রজেক্ট ইতিহাস backfilled
- built: ops/tools/memory.py CLI (recent/search/add/stats) + tests/test_memory.py (5, temp-dir isolated)
- rewrote AGENTS.md: memory protocol (read first/write last), task router, hard rules, recipes (bug/feature/release), communication rules
- TASK_PROMPT.md: memory section added

## 2026-10-10 | v4: EXE desktop dashboard + legacy flow engine merged
- ইউজার তার পুরনো প্রজেক্ট (github.com/rajuvbygyuiythh/chatchat2222 → eva_bot_complete.zip) দেখিয়ে professional desktop dashboard চেয়েছিল।
- Merged: `eva_flow.py` funnel engine + `data/input|output` txt banks + countries + local_db + icon → `eva/brain/`
- Built `eva/gui/dashboard.py` (PyQt6, user's dark style: sidebar/CPU-RAM/START-STOP/session/engine/settings/match/stats/log)
- Build system: `EVA_Dashboard.spec` + `build_exe.bat` + `dashboard_main.py` (PyInstaller onedir, windowed, icon)
- Engine switch: flow (txt banks, DEFAULT) | simple (persona templates) — config `engine` key
- Tests: flow 7/7 (new `tests/test_flow_engine.py`), unit 12/12, protocol 24/24, session 7/7
- zip: eva-bot-v4-exe-dashboard.zip (1,499,348 bytes), pushed to branch

## 2026-10-10 | v3: web dashboard + CDP browser login/session
- ইউজার চেয়েছিল dashboard থেকেই browser চালিয়ে session save করা যাক।
- `eva/dashboard/cdp_session.py`: launch Chrome/Edge (dedicated profile data/chrome-profile, port 9222), cookie pull via CDP `Storage.getCookies` (page-level `Network.getAllCookies` fallback), verify via GET /users/me, save configs/session.json
- `eva/dashboard/server.py`: web dashboard (aiohttp, port 8800): session panel + bot start/stop + live stats/logs + config editor
- `ops/tools/session_smoke_test.py`: fake Chrome CDP server → 7/7 checks (attach, filter, save format, verify, no-login error, no-browser error)
- শিক্ষা: test-এ verify mock-এ route add করতে ভুল হয়েছিল — debug pattern: instrument verify() আলাদা করে চালিয়ে status দেখা

## 2026-10-09 | v2: deep audit — 10 runtime bugs fixed
- ইউজার চেয়েছিল "deeply fix, step by step"। Systematic code+capture audit → 10 bugs (বিস্তারিত bugs_fixed.md)।
- সবচেয়ে গুরুত্বপূর্ণ: empty-body endpoints (capture ছিল body_size=0), own-typing-echo guard ছাড়া idle-skip আর কাজ করত না।
- Smoke test scenario 2 (our-skip flow) add → 24/24 total.

## 2026-10-09 | v1: capture analysis + full WS bot build
- ইউজারের capture repo (rajuvbygyuiythh/wbbbbbbbbbbsck) deeply analyzed — RAW payloads পাওয়া গেছে (15_websocket_all.json raw frames, 16_http_all.json response bodies)।
- KEY discovery: message SEND হয় REST দিয়ে (multipart content+nonce), WS শুধু receive+match lifecycle। Auth = cookies only।
- Built: socketio_codec, chitchat_socket, chitchat_api, ws_chat_loop, ws_bot CLI, replies, extract_session, protocol_manifest.json, socket_smoke_test → 15/15।
- পুরনো assumption ভাঙা: "README says do not guess" — এখন সব capture-backed।
