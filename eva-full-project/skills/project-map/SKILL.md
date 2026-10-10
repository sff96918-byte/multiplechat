---
name: project-map
description: EVA Bot root project-এর A-to-Z ফোল্ডার ও ফাইল মানচিত্র। নতুন কাজ শুরুর আগে, কোথায় কী আছে জানতে, বা কোন ফাইল কার উপর নির্ভর করে বুঝতে এটা পড়ো।
---

# SKILL: Project map (A–Z)

## File class (machine-readable)
`project.map.json` — প্রতিটা ফাইলের risk class (CRITICAL_CORE / RUN_AND_SETUP / DATA_MAPPING / SUPPORT_MODULES / TOOLS_AND_TESTS / DOCS) ও কোন test চালাতে হবে। নতুন ফাইল আনলে `python tools/project_map_check.py` চালাও।

## দুটো মূল flow
1. **LIVE BROWSER** — `entry/main.py` → `entry/thread_manager.py` → `browser/browser_automation.py`
   (Camoufox দিয়ে chitchat.gg UI চালায়) → reply চায় `chat/rule_bot.py`-র `ChatRuleBot`-এর কাছে।
2. **SESSION CHAT** — `entry/main.py` (SESSIONS page, ⚡ box) → `core/session_chat.py`
   `SessionChatWorker(QThread)` → `core/ws_transport/ws_chat_loop.py` (WebSocket + REST)
   → reply চায় `_ChatRuleEngine` (ভিতরে `ChatRuleBot`)।

## Reply engine chain
```
ChatRuleBot (chat/rule_bot.py)
  └─ _FlowEngine → eva_flow.EvaFlowBot (funnel state machine)
       ├─ data/input/*.txt   → ইউজারের message কোন category (trigger)
       └─ data/output/*.txt  → সেই category-র reply লাইন (+ middle_chat/)
API: bot.new_conversation() -> state ; bot.reply(text, state) ; state["pending_replies"] (multi-line, pop করে নিতে হয়)
Debug: bot.last_debug_summary(), bot.last_picked_info()
```
`EVA_ENGINE` env: default `flow`; `legacy` হলে পুরনো 6-flow `RuleEngine` (chat/rules.py)।
Test-গুলো `legacy` সেট করে।

## Config ও data
| কী | কোথায় | কে পড়ে |
|---|---|---|
| timing + human behavior | `data/config.json` | `core/config_loader.py` → `load_chat_timing()` (new_chat_delay: Settings-এর একটাই মান, default 5s; min=max), `load_runtime_config()["human_behavior"]` (typing, read_reply, micro_idle) |
| account session (token) | `account_sessions/<key>/storage_state.json` (cookie `token`) + `metadata.json` | `core/session_chat.py` `discover_session_sources()` |
| optional manual session | `configs/session.json` | একই discovery |
| snap pool | `data/snap_ids.txt` | `chat/rules.py` `SNAPUSER_FILE` |
| logs | `data/logs/chat_debug.log`, `data/logs/gui_console.log` | rules.py, entry/main.py |

## Path rule
সব path `entry/paths.py` থেকে: `project_root()`, `data_dir()`। Hard-coded `C:\...` বা `/home/...` নিষেধ।

## Session chat-এর log tag
`[session] [X]` error · `[session] [ok]` login/live · `[session] [chat]` নতুন partner ·
`[session] [stat]` প্রতি ৫ সেকেন্ড state · `[session] [done]` শেষ।
GUI-তে এগুলো Live Chat feed-এ `[S97]` হিসেবে দেখায় (`SESSION_THREAD_ID = 97`)।

## Fragile ফাইল (সাবধানে)
- `browser/browser_automation.py` (~3700 লাইন) — login/chat lifecycle; thread-safe ধরবে না।
- `entry/thread_manager.py` (~1250) — orchestration + Qt signal।
- `entry/main.py` (~2180) — GUI। Settings → CHAT TIMING: New Chat Delay (একটা field) + Silence timeout।
- `chat/rules.py` (~2140) — legacy engine + TXT matcher। Contract test: `test_rules_characterization.py`; coverage: `python tools/rules_coverage.py`।
