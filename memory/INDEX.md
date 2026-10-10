# AGENT MEMORY INDEX
**এই ফোল্ডার = project-এর স্থায়ী স্মৃতি।** প্রতিটা agent session শুরুতে পড়ো,
কাজ শেষে লিখো। CLI: `python -m ops.tools.memory` (recent/search/add/stats)

## কোন ফাইলে কী আছে

| File | কখন পড়বে | কী আছে |
|---|---|---|
| `sessions.md` | **প্রতিটা task-এর শুরুতে** (শেষ ২-৩ entry) | কোন session-এ কী হলো |
| `decisions.md` | architecture/behavior change করার **আগে** | কেন এমন বানানো — ভাঙা decisions ভাঙবে না |
| `bugs_fixed.md` | নতুন bug debug করার **আগে** (হয়তো আগেই fix হয়েছে) | symptom→cause→fix সব bug-এর |
| `protocol_facts.md` | chitchat.gg protocol নিয়ে কাজ করলে | verified facts + gotchas |
| `open_questions.md` | task শেষে + নতুন কাজ বাছতে | এখনো মীমাংসা হয়নি যা |
| `user_preferences.md` | **প্রথম দিনই একবার** | ইউজার কীভাবে কাজ করতে চান |

## নিয়ম (মনে রাখার সহজ সূত্র)

1. **শুরুতে:** `python -m ops.tools.memory recent 6` + `sessions.md` শেষ ২ entry
2. **শেষে:** অন্তত ১টা `session` entry + হলে `bug`/`decision`/`question` entries
3. Entry format: **তারিখ | শিরোনাম** + প্রমাণ/কারণ/ফাইল — সংক্ষিপ্ত, ইংরেজিতে (agent-friendly)
4. Memory ভুয়া করার চেষ্টা করবে না — শুধু যা ঘটেছে যা

<!-- auto-appended by ops.tools.memory -->
| 2026-10-10 | `question` | Silence rule and Max Replies policy | Need user decision before fixing: (1) silence after partner msg: keep waiting (recommended) vs skip after X se |
| 2026-10-10 | `session` | v16 analysis: early skip before snap share (no code change) | User: dashboard New Chat Delay / Rest Every / Rest For auto fields remove; bot skips new user before snap shar |
| 2026-10-10 | `bug` | Logs shown twice (sidebar page + dashboard box) | Symptom: same log output in Dashboard LIVE LOG box and sidebar Logs page. Cause: two separate QTextEdit widget |
| 2026-10-10 | `session` | v16: Logs ek jaygay (Dashboard LIVE LOG panel) | User: logs option 2 jaygay. Fix: sidebar Logs page + nav button removed; full log panel (search, Clear, Export |
| 2026-10-10 | `question` | Shared zip contains account_sessions token | Earlier root-project zips (v14 and before) contained account_sessions/*/storage_state.json with a live chitcha |
| 2026-10-10 | `decision` | AGENTS.md + skills live inside root project zip, not only in repo | Reason: user runs the root project eva-full-project on Windows; agents working on the deliverable must see its |
| 2026-10-10 | `session` | v15: root project AGENTS.md + skills/ added (A-Z guide for any agent) | Root project eva-full-project got rewritten AGENTS.md (Bangla, project map, hard rules, verify gate, delivery  |
| 2026-10-10 | `session` | v14 FINAL: session chat deeply integrated into user's root project | Fresh updatec zip -> /tmp/orig/eva-full-project. Removed approach: run_session_bot.bat/session_mode/SESSION_MO |
| 2026-10-10 | `session` | v13: session mode added to user's root project (updatec zip) | Downloaded raju vbygyuiythh/updatec picccccccfull-project.zip (9,653,190 B, sha 5a226beb...) via api.github.co |
| 2026-10-10 | `session` | v12: EXE error fix (python314.dll) | User hit PyInstaller bootloader error running a stale broken exe from previous build on their PC (build/EVA_Da |
| 2026-10-10 | `bug` | smoke test imported deleted module | socket_smoke_test.py imported eva.replies.ReplyEngine; after v11 removal of eva/replies.py the smoke test cras |
| 2026-10-10 | `session` | v11: dead/broken stuff removed (user: 'useless none-work remove') | REMOVED: eva/replies.py (persona engine, persona already cut from UI), eva/dashboard/server.py (web dashboard  |
| 2026-10-10 | `decision` | v10: report share-safe rule | Debug report NEVER contains session.json content (only exists/has_token booleans + cookie NAMES) and WS frame  |
| 2026-10-10 | `session` | v10: debug upgrade (file log, ring buffers, export report) | New eva/debugtools.py: setup_debug_logging (logs/eva.log RotatingFile 1MBx5 ALWAYS DEBUG; eva logger level DEB |
| 2026-10-10 | `decision` | v9: settings ek jaygay (BOT SETUP) | Architecture answer: mood dashboards e shudhu mood-specific controls (browser/session/START); shared settings  |
| 2026-10-10 | `session` | v9: shared BOT SETUP page + snap.txt support | User asked: engine/fixed-sms-txt/snap settings main dashboard e na ki each mood e? Answer implemented: ekta sh |
| 2026-10-10 | `decision` | v8 mood architecture | Mood = separate dashboard pages in one QStackedWidget (HOME + browser + session). Qt constraint: same widget c |
| 2026-10-10 | `session` | v8: mood dashboards (browser/session) | GUI rewrite: HOME page e 2 ta mood card (LIVE BROWSER / SESSION CHAT) -> QStackedWidget e totally different da |
| 2026-10-10 | `decision` | v7 engine model: flow|fixed only | Reply engine options final: flow = legacy funnel (input/output txt banks, snap_usernames) ar fixed = fixed txt |
| 2026-10-10 | `session` | v7: persona removed, flow/fixed engine selector | PERSONA puro bad (GUI group, ws_bot/server Persona branch, config example, docs)। Engine selector: flow (SMS d |
| 2026-10-10 | `session` | v6.1: DASHBOARD_OPTIONS_BN.md (A-Z options mapping doc) | ইউজার চাইলেন dashboard-এর সব option + config mapping A-Z করে দেখাতে। docs/DASHBOARD_OPTIONS_BN.md বানানো হলো ( |
| 2026-10-10 | `bug` | rebase --ours took wrong side, v4 wiring lost silently | Symptom: grep-এ ws_bot/server-এ engine_name নেই যদিও v4 commit ছিল। Cause: AA conflict-এ git checkout --ours = |
| 2026-10-10 | `decision` | Human pacing from legacy config, not hardcoded | ইউজারের পুরনো প্রজেক্টের human_behavior/chat_timing মানগুলো config  section-এ সরানো হলো (DEFAULT_TIMING fallba |
| 2026-10-10 | `session` | v6: realistic timing + session-expiry handling (+rebase lost-wiring fix) | Found: rebase conflict resolution (--ours) silently reverted v4 wiring in ws_bot.py/server.py/config example — |
| 2026-10-10 | `session` | v5: agent memory system + AGENTS.md v2 | ইউজার চেয়েছিল: agents-দের জন্য memory + improved AGENTS.md |
