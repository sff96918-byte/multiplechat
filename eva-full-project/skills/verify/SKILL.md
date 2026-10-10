---
name: verify
description: যেকোনো কোড/config/content বদলের পর কোন check কখন চালাতে হবে এবং কীভাবে রিপোর্ট করতে হবে। প্রতিটা কাজের শেষে এটা পড়ো ও চালাও।
---

# SKILL: Verify (done বলার আগে)

## এক কমান্ড (সবসময় প্রথমে)
```bash
python tools/verify_gate.py     # project map + compile + import + সব test + GUI stub import; শেষে GATE: N/M steps passed (optional tool না থাকলে SKIP, FAIL নয়)
```
FAIL দেখালে কোন step ব্যর্থ তা নাম ধরে দেখায়; সেই step-এর পুরো output আলাদা করে দেখো।

**v26 নতুন step:** `test_rules_characterization.py` (chat/rules.py contract, 33 check); `tools/secret_scan.py --selftest` + `tools/secret_scan.py` (secret pattern, মান প্রিন্ট হয় না); `pip-audit -r data/requirements.txt` (PyPI JSON, network লাগে)। Optional (SKIP হতে পারে): `gitleaks` (binary PATH-এ থাকলে), `pyflakes` (module থাকলে), `tools/rules_coverage.py --floor 50` (`coverage` package লাগে)।

**CRITICAL_CORE ফাইল বদলালে:** `python tools/critical_guard.py` — test_*.py পরিবর্তন ছাড়া CRITICAL ফাইল বদলালে FAIL। এটা gate-এ নেই (zip-এ git history নেই); commit-এর আগে হাতে চালাও। TDD-র ক্রম এটা যাচাই করে না।

## Tier 1 — সবসময় (ছোট পরিবর্তনও)
```bash
python -m py_compile <বদলানো ফাইলগুলো>
python -c "import chat; import eva_flow; print('import ok')"
python -c "import core.ws_transport.chitchat_api, core.ws_transport.ws_chat_loop; print('ws import ok')"
```
> py_compile NameError ধরে না — তাই import check দরকার। `python -m pyflakes <files>` দিয়ে undefined name দেখো (unused import আলাদা, blocking নয়)।

## Tier 2 — reply/content/engine বদলালে
```bash
python test_matcher.py      # ALL CATEGORIES ROUND-TRIP OK
python test_live.py         # RESULT: 44/44 passed
python test_fuzz.py         # RESULT: 4/4 passed
python test_flow.py         # RESULT: 126 passed, 0 failed
python demo_chat.py         # DEMO: ALL CHATS REACHED END
```
Windows: `test.bat` (matcher + live + fuzz + demo একসাথে)।

## Tier 3 — session chat / WS / GUI বদলালে
```bash
QT_QPA_PLATFORM=offscreen python -m core.session_chat --list
QT_QPA_PLATFORM=offscreen python -c "import entry.main; print('gui import ok')"   # sandbox-এ libGL না থাকলে ব্যর্থ — রিপোর্টে লেখো
```
+ Tier 2।

## Tier 4 — ZIP দেওয়ার আগে
1. zip বানাও (AGENTS.md §6 অনুযায়ী exclude সহ)।
2. zip খুলে যাচাই:
   - `account_sessions/`, `configs/session.json`, `data/logs/`, `__pycache__/` নেই
   - key ফাইল আছে: `entry/main.py`, `core/session_chat.py`, `core/ws_transport/`, `chat/rule_bot.py`, `data/config.json`, `AGENTS.md`, `skills/`
3. byte size ও ফাইল সংখ্যা লেখো।

## রিপোর্ট ফরম্যাট
| Check | Command | ফলাফল |
|---|---|---|
| ... | ... | PASS / FAIL / চালানো যায়নি (কারণ) |

- "চালানো যায়নি" আর "PASS" আলাদা রাখো।
- Sandbox-এ chitchat.gg network নেই — live test ইউজারের PC-তে; সেটা "UNVERIFIED (live)" হিসেবে লেখো।
- একটাও FAIL থাকলে "done" বলবে না।
