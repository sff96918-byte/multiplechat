# EVA Bot — Full Project (Diagram Flow Engine + Legacy Engine)

Complete EVA chitchat.gg bot: browser automation, PyQt6 GUI dashboard, CLI
runner, account/session management — now running the **updated diagram flow
logic** with **symmetric input/output txt categories**, plus the original
full engine kept as a selectable legacy option.

```
DEFAULT ENGINE (flow):   greeting -> age/gender -> country -> flirty
                         -> positive reply -> share snap -> END CHAT
LEGACY ENGINE:           EVA_ENGINE=legacy  (original 6-flow brain)
```

---

## The one rule (customizable without code)

```
data/input/<category>.txt   = WHAT THE USER SAYS   (trigger keywords)
data/output/<category>.txt  = WHAT THE BOT REPLIES (reply lines)

same file name = same category — edit the txt files, restart, done.
```

Example: user sends `m 21` → matches a line in `input/age_gender.txt` →
bot replies from `output/age_gender.txt` (`f19`).

| # | User says | Category | Next |
|---|-----------|----------|------|
| 1 | first SMS `hi` | `greeting.txt` | wait age/gender |
| 2 | `m21` | `age_gender.txt` | wait country |
| 3 | `from?` | `country.txt` | wait country answer |
| 4 | `usa` | → `flirty_questions.txt` | MIDDLE |
| 5a | `u horny?` / `send nudes` | `horny.txt` | MIDDLE |
| 5b | `ur cute` / `love u` | `middle_chat/flirty_reply.txt` | MIDDLE |
| 5c | `lol` / `ok` / `nice` | `middle_chat/warm_reply.txt` | MIDDLE |
| 5d | `gtg` / `bye` / `brb` | `middle_chat/busy_later.txt` | MIDDLE |
| 5e | `how are u` / `how old are u` | `how_are_you.txt` / `your_age.txt` | MIDDLE |
| 5f | **positive**: `yes` / `yeop` / `ur sc?` / `whats ur snap` | `share_snap.txt` | **END CHAT** |
| 5g | user offers snap: `my snap is…` | `snapchat.txt` | **END CHAT** |
| 5h | anything else | `flirty_questions.txt` | MIDDLE |
| 6 | partner silent past **Silence timeout** (Settings, default 90s) | — | **next user** |

Matching layers (one fails → next works): exact → substring →
slang-normalized → token-subset → smart fallback (regex, countries.txt).

**Bangla A-to-Z guide:** `data/output/info.txt` (কোন SMS পেলে কোন ফাইল
থেকে reply আসবে — সব বাংলায় ব্যাখ্যা করা)।

---

## ⚡ SESSION CHAT (token/live session — no browser)

**SESSIONS page → ⚡ SESSION CHAT box** — account session/token diye live chat,
browser automation chara. Reply engine = **ek e flow funnel** (ChatRuleBot →
eva_flow, data/input + data/output), Live Chat page-e [S97] hishebe dekha jay.

* **Session:** `account_sessions/*/storage_state.json` + `configs/session.json`
  theke auto list (🔄 refresh). Token field-e acc token paste korle setai use hobe.
* **Same engine, same timing** — human_behavior + chat_timing config-i kaj kore.
* Token kokhono log/hoy na (shudhu shesh 6 letter dekhay).
* Debug CLI: `python -m core.session_chat --list` / `--max-matches 2`

Token meyad sesh hole (401): browser mode-e abar login koro — notun session
save hoye jabe, tarpor Session Chat abar chalabe.

---
---

## Engine switch

```bash
python -m entry.main                # GUI (default = flow engine)
EVA_ENGINE=legacy python -m entry.main   # GUI with the original engine
python entry/cli_runner.py          # terminal runner
```

Both engines share `data/input/` + `data/output/` and the same
`ChatRuleBot` API, so the browser worker, GUI and tools work with either.

## Install & run (Windows)

```bat
install.bat      :: venv + all packages + Playwright Chromium (one run)
run.vbs          :: start the bot app (GUI, NO console window)
"EVA Bot" desktop :: created by install.bat - double-click app icon
run_console.bat  :: debug launcher (console visible)
test.bat         :: automated checks + demo + live REPL
```

Manual (any OS): `python -m venv .venv` → `pip install -r
data/requirements.txt` → `python -m playwright install chromium`.

## Test (all green)

| Script | Engine | Result |
|--------|--------|--------|
| `python test_flow.py` | flow | **58/58 passed** |
| `python demo_flow.py` | flow | **PASSED** (diagram walkthrough) |
| `python demo_chat.py` | flow | **ALL CHATS REACHED END** (failed on the original snapshot!) |
| `python test_live.py` | legacy | **44/44 passed** |
| `python test_fuzz.py` | legacy | **4/4 passed** |
| `python test_matcher.py` | legacy IO | **ALL CATEGORIES ROUND-TRIP OK** |
| `python tools/live_chat.py` | flow (default) | interactive REPL |

## Project layout

```
entry/      GUI dashboard (main.py), CLI runner, thread orchestration
browser/    Playwright/Camoufox automation, context pool, sessions,
            human behavior, device sign-in
chat/       rule_bot.py (engine switch) + rules.py (legacy engine)
core/       config loader, resource governor, engine bridge, accounts
data/       input/ + output/ categories, countries.txt, snap_ids.txt,
            local_db/, config.json (runtime behavior)
docs/       flow spec (FLOW_SPEC.md)
tools/      live_chat.py REPL, coverage check
eva_flow.py the diagram funnel engine (default)
run_chat.py / demo_flow.py / test_flow.py   flow-engine tools
install.bat / run.vbs / run_console.bat / test.bat   Windows helpers
```

## Behavior rules

- No line repeats within one conversation; never back-to-back
- No reply cap: chat runs until the **snap is shared** (then next user). Optional cap only if `EVA_MAX_REPLIES=N` is set
- Partner silent for **Silence timeout** seconds (Settings → Silence timeout, default 90) → next user
- Underage (<18) permanently blocks snap sharing (both engines)
- Snap usernames cycle round-robin via `data/snap_ids.txt`
- `%username%` / `{snap}` / `{country}` placeholders in reply lines
- Multi-line SMS: last line drives the machine

## Changes vs the original 22.zip snapshot

1. `data/input` + `data/output` renamed to direct symmetric names
   (`01_greeting.txt` → `greeting.txt`, …) + new categories
   (`middle_chat/` inputs, `share_snap.txt` triggers, `closer.txt`)
2. `chat/rule_bot.py`: engine switch (default flow, `EVA_ENGINE=legacy`)
3. `chat/rules.py`: filename refs updated + two fixes
   (punctuation-lossy trigger guard; minors never get IO snap reveals)
4. `eva_flow.py` + tools added (diagram engine, same API)
5. Legacy test scripts pinned to `EVA_ENGINE=legacy`
6. `data/countries.txt` added (editable country keywords)
7. `data/output/info.txt` — Bangla guide (A to Z)

Everything else (browser/, entry/, core/, docs/, bats) is
unchanged from the original project.
