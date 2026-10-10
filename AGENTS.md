# AGENTS.md — এই ফাইল প্রতিটা agent session-এর শুরুতে পড়ো (এটা mandatory)

> **⚠ আগে এটা পড়ো:** ইউজারের মূল চালানোর project হলো
> **`eva-full-project/`** (এই repo-র ভিতরে plain folder, v20 থেকে; zip: `picccccccfull-project-v19-NO-PICTURES.zip`)
> (entry/, core/, chat/, data/ …)। সেখানকার **`AGENTS.md` + `skills/`** হলো মূল গাইড —
> reply engine, SESSION CHAT, GUI, error fix, verify gate সব সেখানে।
> এই repo-র `eva/` ফোল্ডার হলো protocol R&D/আগের workspace; এখানকার নিয়মগুলো
> (memory protocol, protocol guess-নিষেধ) সেগুলোর সাথেও প্রযোজ্য।
> Verify (এই repo): `python3 -m pytest tests/ -q` (38) · `python3 -m ops.tools.socket_smoke_test` (24/24) · `python3 -m ops.tools.session_smoke_test` (7/7)

তুমি এই repo-তে **নতুন করে** এসেছো। তোমার আগের agent-রা অনেক কাজ করে গেছে —
তাদের জ্ঞান `memory/` ফোল্ডারে জমানো। নিচের ৬টা ধাপ মানো, তাহলেই তুমি
আগের চেয়ে অনেক দ্রুত ও নির্ভুল কাজ করতে পারবে।

---

## 0) MEMORY PROTOCOL — সবচেয়ে গুরুত্বপূর্ণ নিয়ম

### Task শুরুর আগে (১ মিনিট):
```bash
python -m ops.tools.memory recent 6        # সর্বশেষ কী ঘটেছে
python -m ops.tools.memory search <topic>  # task-related কিছু আগে হয়েছে কিনা
```
এরপর দরকারমতো পড়ো:
- `memory/sessions.md` — শেষ ২-৩ session (কী হয়েছে, কোথায় আছি)
- `memory/bugs_fixed.md` — debug করলে **অবশ্যই** (হয়তো bug-টা আগেই fix হয়েছে)
- `memory/decisions.md` — architecture change করলে (ভাঙা decision ভাঙবে না)
- `memory/protocol_facts.md` — chitchat.gg protocol নিয়ে কাজ হলে
- `memory/open_questions.md` — কাজ শেষে / নতুন কাজ বাছতে
- `memory/user_preferences.md` — প্রথমবার এলে (কীভাবে কথা বলতে হবে, কী deliver করতে হবে)

### Task শেষে (বাধ্যতামূলক — না করলে ধরা যাবে):
```bash
python -m ops.tools.memory add session "v5: <যা করলে>" --body "<কী হলো, কোন ফাইল, কোন test result>"
python -m ops.tools.memory add bug "title" --body "Symptom: ... Cause: ... Fix: <file> ... Verified: <test>"
python -m ops.tools.memory add decision "title" --body "কী করলে কেন + কারণ + বিকল্প ছিল কী"
python -m ops.tools.memory add question "title" --body "কী জানা নেই + কীভাবে resolve হবে"
```
**কমপক্ষে ১টা `session` entry প্রতিটা কার্যকর session-এ।** Bug পেলে/fix করলে `bug`,
সিদ্ধান্ত নিলে `decision`, অমীমাংসিত বিষয় থাকলে `question` — বাদ দিও না।

---

## 0) AUTONOMOUS ENGINEER LOOP (প্রতিটা কাজে বাধ্যতামূলক)

মূল project (`eva-full-project/`) নিয়ে কাজ হলে ওর `AGENTS.md` §0 পড়ো — সেখানে পূর্ণ loop আছে:
Analyze → Plan → TDD (test আগে/সাথে) → Execute (minimal, modular) → Debug (চালিয়ে log পড়ো, root cause, fix) → Verify (security + efficiency audit, gate) → Output (ফাইল + test report)।
Root-এর কাজেও একই ধাপ: test report ছাড়া "done" নয়; সব verify command ও pass/fail সংখ্যা লেখো; sandbox-এ যা চলে না তা "UNVERIFIED" লেখো।

---

## 1) PROJECT IN 30 SECONDS

**কী আছে:** chitchat.gg-তে ইউজারের নিজের account-এর session দিয়ে live stranger-দের
সাথে auto match → chat → reply → skip → next করা bot। **সব protocol fact
capture-backed** — ইউজারের নিজের browser traffic capture থেকে; guess নিষিদ্ধ।

**এক নজরে ফাইল মানচিত্র:**

| Path | কী |
|---|---|
| `eva/transport/` | protocol: `socketio_codec` (EIO4/SIO5 frames), `chitchat_socket` (WS), `chitchat_api` (REST), `ws_chat_loop` (state machine), `ws_bot` (CLI) |
| `eva/transport/protocol_manifest.json` | **protocol source of truth** — সব fact + evidence |
| `eva/brain/` | ইউজারের legacy flow engine (`eva_flow.py`) + txt banks (`data/input|output`) + `flow_reply_engine` adapter |
| `eva/gui/dashboard.py` | PyQt6 desktop dashboard (EXE-ready; ইউজারের প্রধান পছন্দ) |
| `eva/dashboard/` | web dashboard + `cdp_session.py` (browser login → cookie pull) |
| `ops/tools/` | `socket_smoke_test`, `session_smoke_test`, `extract_session`, `memory` |
| `tests/fixtures/captured_frames.json` | আসল captured frames — smoke test-এর ভিত্তি |
| `configs/` | `session.json` (SECRET, gitignored), `chitchat_bot.example.json` (engine/snap/persona/loop — example) |
| `eva-full-project/` | **মূল চালানোর project** (PyQt6 GUI, eva_flow, browser + session chat). নিজের `AGENTS.md` + `skills/` + `README.md` আছে — ওখানকার verify gate ব্যবহার করো |
| `tools/chitchat_capture/` | Playwright direct capture tool (browser চালিয়ে ইউজার নিজে chat করে, সব data JSON-এ save; `share_bundle.json` masked). README বাংলায়। **Token/cookie/chat text কখনো শেয়ার নয়** |
| `chitchat_capture_tool.zip` | উপরের tool-এর zip (download-এর জন্য) |
| `TASK_PROMPT.md` | বাংলায় সাজানো পুরো task spec (নতুন agent-কে দেওয়ার মতো) |
| `project/` | legacy multi-site bot (অন্য সাইট; আলাদা, বেশি ধরবে না) |

---

## 2) TASK ROUTER (কোন কাজে কোথায়)

| Task | পড়ো/ছোঁয়া |
|---|---|
| Bug fix | `memory/bugs_fixed.md` আগে → তারপর সংশ্লিষ্ট ফাইল → fix → test → `memory add bug` |
| Protocol behavior change | `protocol_manifest.json` + `protocol_facts.md` → fixture update → codec/client → smoke test → `memory add decision` |
| Reply/chat logic | `eva/brain/` (flow) বা `eva/replies.py` (simple) → `tests/test_flow_engine.py` |
| **মূল project (eva-full-project)** — reply, GUI, session, browser | `eva-full-project/AGENTS.md` পড়ো → তার verify gate চালাও |
| Capture tool (`tools/chitchat_capture`) | `tools/chitchat_capture/README.md` → `python3 capture_direct.py --selftest` |
| Dashboard/GUI | `eva/gui/dashboard.py` (desktop) / `eva/dashboard/server.py` (web) |
| New capture এলে | আগে পুরনো ফরম্যাট দেখো (`15_websocket_all.json` style) → facts বের করো → manifest+fixture update → tests চালাও |
| Release/zip | নিচে RELEASE CHECKLIST |

---

## 3) HARD RULES (ভাঙলে task fail)

1. **Guess নিষিদ্ধ** — chitchat.gg protocol-এর প্রতিটা behavior-এর capture evidence থাকতে হবে। নতুন behavior দরকার হলে ইউজারকে নতুন capture করতে বলো। Unknowns: `protocol_facts.md`।
2. **No WS/socket.io dependency** — wire protocol নিজেরাই বলে (`socketio_codec.py`)। `python-socketio` install করবে না।
3. **Secrets কখনো commit/zip হবে না** — `configs/session.json`, cookies, JWT।
4. **Verification gate** — `eva/` বদলালে এই ৪টা test চালাও, সব PASS না হলে কাজ complete না। `eva-full-project/` বদলালে তার নিজের `AGENTS.md` §5 gate চালাও:
```bash
python3 -m pytest tests/ -q                  # unit + flow + debugtools (38)
python3 -m ops.tools.socket_smoke_test       # protocol (24/24)
python3 -m ops.tools.session_smoke_test      # session flow (7/7)
```
5. **Rate discipline** — request spacing ≥ 250ms; 403-Flagged backoff remove করবে না।
6. **Memory write** — কাজ শেষে `ops.tools.memory` দিয়ে লিখবেই।

---

## 4) কমন কাজের RECIPE

### Bug পেলে
1. `memory search <symptom-keyword>` — আগে fix হয়ে থাকতে পারে
2. Reproduce করো (test/mock দিয়ে, live site-এ না)
3. Fix + নতুন check smoke/unit test-এ add করো
4. সব test PASS → `memory add bug ...`

### নতুন feature
1. `memory/decisions.md` — আগের related decision আছে কিনা
2. বড় হলে ইউজারকে approach জিজ্ঞেস করো (ask_user)
3. Implement + tests + docs update + `memory add decision/session`

### Release zip (ইউজার প্রতিবার চায়)
1. সব test PASS
2. Zip content: ইউজার-facing সব + `project/` + docs, EXCLUDE: `__pycache__/`, `*.pyc`, `configs/session.json`, `dist/`, `build/`, পুরনো `*.zip`
3. **Verify:** zip খুলে secret নেই কিনা + key files আছে কিনা + integrity
4. Git commit+push → GitHub API দিয়ে size confirm → raw link + byte size দাও
5. `memory add session`

### ইউজার সমস্যা নিয়ে ফিরে এলে
1. console output চাও যদি না দিয়ে থাকে
2. `memory/bugs_fixed.md` symptom table → সম্ভাব্য cause বাংলায় ব্যাখ্যা
3. Fix করে zip+link আবার দাও

---

## 5) COMMUNICATION

- বাংলায় লেখো (technical শব্দ ইংরেজি)। ইউজার "ভাই" সম্বোধন পছন্দ করেন।
- কাজ শেষে সবসময় সারাংশ টেবিল: bug/fix/test result।
- বড় ambiguity হলে `ask_user` দিয়ে option জিজ্ঞেস করো — নিজে অনুমান করে বড় কাজ করবে না।
- ইউজারের সময় মূল্যবান: কাজ করে তারপর জানাও; প্রতিটা ছোট ধাপে প্রশ্ন করে সময় নষ্ট করবে না।

---

## 6) CURRENT STATE SNAPSHOT (2026-10-10 অনুযায়ী — বিস্তারিত sessions.md)

- v4 পর্যন্ত complete: transport + loop + web dashboard + PyQt6 EXE dashboard + flow engine merge
- Tests: pytest 38, protocol smoke 24/24, session smoke 7/7 — সব সবুজ (sandbox-এ যাচাই)
- **v20 recheck (2026-10-10):** `eva-full-project/` repo-তে আনা হয়েছে; project-এর test (matcher ✓, live 44/44, fuzz 4/4, flow 126/126, demo ✓); `ws_transport` import fix; Settings-এর timing একটাই "New Chat Delay" (default 5); capture tool selftest পাস (live browser run sandbox-এ সম্ভব নয়, ইউজারের PC-তে বাকি)
- Capture tool (`tools/chitchat_capture`) weebbsssc repo-তে এখনো copy হয়নি — ইউজারের সিদ্ধান্ত অপেক্ষায়
- **Live test এখনো হয়নি** (ইউজারের PC-তে হবে) — প্রথম live report এলে `open_questions.md`-র জিনিসগুলো verify করো
- পরের সম্ভাব্য কাজ: live-debug, multi-account, proxy — ইউজার চাইলেই

*শেষ কথা: তুমি একা নও — আগের সব agent-দের নোট এই ফোল্ডারে। পড়ো, কাজ করো, লিখে যাও।*
