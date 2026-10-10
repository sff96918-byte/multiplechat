---
name: gui-dashboard
description: PyQt6 GUI (entry/main.py) এ নতুন page, button, setting, বা Qt signal যোগ/বদল করার নিয়ম। GUI বা worker-thread সংক্রান্ত কাজে এটা পড়ো।
---

# SKILL: GUI dashboard (PyQt6)

## Structure
- `entry/main.py` `main()` — app start; `sys.stdout is None` (pythonw) হলে `data/logs/gui_console.log`-এ redirect।
- Sidebar + `QStackedWidget` (`self.pages`): Dashboard, Live Chat, Sessions, Accounts, Settings। (Picture sender v19-এ সম্পূর্ণ সরানো হয়েছে।)
- **Settings → CHAT TIMING:** "New Chat Delay (s)" (একটাই field, default 5) + "Silence timeout (s)" (default 90)। Rest Interval/Duration UI-তে নেই (config.json-এ আছে)। Dashboard-এ timing field নেই।
- **Logs একটাই জায়গায়** — Dashboard page-এর ভিতরে "LIVE LOG" panel (`_build_logs_panel`)। আলাদা Logs page/sidebar button নেই। `self.log_text` = All Logs tab (একই widget); log লেখার সময় একবারই append করো, দুই জায়গায় নয়।
- Live Chat feed: `on_chat_message(thread_id, who, text)` — unknown thread_id নিরাপদ;
  session chat-এর thread_id = 97 (`[S97]`)।
- Session box (SESSIONS page): source combo + 🔄 + token field + ▶/■ ; wired:
  `log_message`, `on_chat_message`, `_session_state`, `_update_session_row`।

## Worker pattern (বাধ্যতামূলক)
- Background কাজ = `QThread` subclass + `pyqtSignal`। UI widget-এ সরাসরি অন্য thread থেকে হাত দেবে না।
- Signal দিয়ে UI update: `self.log_signal.emit(...)` → main-thread slot।
- Stop: `request_stop()` (asyncio loop-এ thread-safe ভাবে যায়); `wait()` দিয়ে join।
- Preflight error হলে cleanup (যেমন `api.close()`) নিশ্চিত করো — leak না হয়।

## নতুন page/button যোগ করার ধাপ
1. দরকার হলে নতুন builder method (যেমন `_build_xxx_page()`) — existing builder বদলাবে না।
2. `self.pages.addWidget(page)` ও sidebar button-এর সাথে সংযোগ।
3. Config পড়া/লেখা `core/config_loader.py` বা existing `data/config.json` section দিয়ে —
   নতুন আলাদা config file বানাবে না।
4. ইউজার যেখানে চায় সেখানেই (আলাদা launcher নয়)।

## Verify
```bash
python -m py_compile entry/main.py
QT_QPA_PLATFORM=offscreen python -c "import entry.main; print('gui import ok')"
```
Sandbox-এ এটা `libGL.so.1` না থাকায় ব্যর্থ হতে পারে — সেটা project-এর bug নয় (system library নেই)। তখন শুধু `py_compile` দিয়ে যাচাই করো এবং রিপোর্টে "GUI import: sandbox-এ চালানো যায়নি (libGL)" লেখো। আসল click/UX ইউজারের PC-তে দেখতে হবে।
