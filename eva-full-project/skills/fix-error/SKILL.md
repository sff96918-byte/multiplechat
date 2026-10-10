---
name: fix-error
description: যেকোনো error, traceback, crash, EXE/DLL লোড ব্যর্থতা, বা "কাজ করছে না" সমস্যা triage ও fix করার নির্দিষ্ট পদ্ধতি। যেকোনো bug-এর শুরুতে এটা পড়ো।
---

# SKILL: Fix error (triage → root cause → minimal fix → verify)

## 1. Error কোথা থেকে পাবে
- Traceback: ইউজারের paste করা text (সবচেয়ে গুরুত্বপূর্ণ — শেষ লাইন ও ফাইল:লাইন)।
- Log: `data/logs/gui_console.log` (windowless `pythonw`-এ stdout এখানে যায়),
  `data/logs/chat_debug.log` (reply decision), Dashboard-এর LIVE LOG panel।
- ইউজার কী ক্লিক/চালিয়েছিল — LIVE BROWSER নাকি SESSION CHAT?

## 2. Error-type ম্যাপ
| Symptom | সম্ভাব্য কারণ | কোথায় দেখবে |
|---|---|---|
| `Failed to load Python DLL ... python3xx.dll` (EXE) | পুরনো/ভাঙা `build/` বা `dist/`, বা venv-এর ভুল Python | build ফোল্ডার, `build_exe.bat` (এই root project-এ EXE build script নেই — `run.vbs`/`run_console.bat` ব্যবহৃত) |
| `ModuleNotFoundError: aiohttp` / `PyQt6` | dependency নেই | `install.bat` / `data/requirements.txt` |
| `KeyError` / `AttributeError` in reply | state dict-এর key বা `pending_replies` ভুল ব্যবহার | `chat/rule_bot.py`, `eva_flow.py` |
| GUI খুলে বন্ধ | `sys.stdout is None` (pythonw) বা Qt thread-এ UI touch | `entry/main.py` `main()` (redirect ব্লক) |
| `No module named chat` | ভুল working directory | launcher ও `sys.path` (`run_chat.py` দেখো) |
| Unicode/Bangla error Windows-এ | console encoding | `PYTHONIOENCODING=utf-8` |
| Session token error | §session-chat-debug | |

## 3. Procedure (এই ক্রমে, লাফ দিয়ো না)
1. **Reproduce:** সম্ভব হলে offline (test/demo/unit) দিয়ে পুনরুৎপাদন করো। Sandbox-এ live site নেই।
2. **Trace:** traceback-এর শেষ project-file থেকে উপরে যাও; প্রতিটা ফাইল পড়ো।
3. **Root cause:** CONFIRMED/LIKELY/UNKNOWN আলাদা লেখো। LIKELY হলে প্রমাণ জোগাড় করো আগে fix করো না।
4. **Minimal fix:** শুধু সেই লাইন/function। আশেপাশের refactor না।
5. **Regression test:** যদি সম্ভব, একটা ছোট check যোগ করো (যেমন `test_*.py`-তে একটা case)।
6. **Verify:** `skills/verify/SKILL.md`-এর gate চালাও।
7. **রিপোর্ট:** Result / Root cause / Changes / Verification / Remaining risk (AGENTS.md §9)।

## 4. যা করবে না
- Error suppress করতে bare `except:` বা `except Exception: pass` বসাবে না (log করো)।
- Bug লুকাতে feature বন্ধ করবে না।
- Verify না করে "ঠিক হয়ে গেছে" বলবে না।
- EXE/DLL সমস্যায় system Python বা অন্য Python version install করতে বলবে না — এটা build/path সমস্যা।

## 5. Windows EXE/DLL সমস্যা — বিশেষ নোট
- `python314.dll` ধরনের error = বর্তমান কোডের নয়, পুরনো build artefact বা ভুল Python।
- সমাধান: পুরনো build folder মুছে নতুন করে build; অথবা (ইউজার যদি EXE না চায়) `run.vbs` (windowless) চালাতে বলো।
