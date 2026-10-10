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
| 2026-10-10 | `session` | v5: agent memory system + AGENTS.md v2 | ইউজার চেয়েছিল: agents-দের জন্য memory + improved AGENTS.md |
