# ChitChat Direct Capture

এই tool নিজে Chrome খুলবে। আপনি login করে নিজে chat করবেন। সব কিছু (HTTP, WebSocket, chat DOM, আপনার Enter/click, screenshot) নিজে থেকে save হবে। শেষে একটা ফাইল `share_bundle.json` পাবেন, সেটা আমাকে দিলে আমি bot-কে সাইটের বর্তমান অবস্থার সাথে মিলিয়ে update করতে পারব।

## ১. প্রথমবার setup

Windows-এ শুধু `run_capture.bat` দু'বার double-click করুন। প্রথমবার Playwright ও Chromium download হবে।

অথবা terminal-এ:
```
pip install -r requirements.txt
python -m playwright install chromium
```

Google Chrome installed থাকলে tool সেটাই ব্যবহার করবে।

## ২. Capture চালানো

```
python capture_direct.py
```

- Chrome খুললে `https://app.chitchat.gg` এ login করুন (প্রথমবারই লাগবে, login profile `browser_profile/`-এ থাকবে)।
- Text chat শুরু করুন, নিজে message পাঠান, partner-এর reply আসতে দিন।
- Skip, Enter, যেকোনো button যা চাপেন সব record হয়।
- কোনো বিশেষ মুহূর্ত চিহ্নিত করতে terminal-এ লিখুন: `note skip চাপলাম`
- ছবি চাইলে: `shot`
- শেষ করতে terminal-এ: `quit` (অথবা Chrome বন্ধ করুন, অথবা Ctrl+C)

পরিমাণ: ১০–১৫ মিনিট চালালে বেশিরভাগ ধরন ধরা পড়ে। যতবেশি scenario (skip, partner চুপ থাকা, snap দেওয়া, নতুন user) ততভালো।

অথবা নির্দিষ্ট সময় পর নিজে বন্ধ হতে:
```
python capture_direct.py --minutes 15
```

## ৩. কী শেয়ার করবেন, কী করবেন না

`capture_out/session_<time>/` ফোল্ডারে:

| ফাইল | শেয়ার? | কারণ |
|---|---|---|
| **`share_bundle.json`** | ✅ হ্যাঁ | Token redacted, message text ও username masked (`--keep-text` ছাড়া), structure ও প্রমাণ, multipart field নাম |
| **`REPORT.md`** | ✅ হ্যাঁ | মানুষের পড়ার সারাংশ |
| `summary.json` | ✅ হ্যাঁ | একই তথ্য, machine-readable |
| `events.jsonl` | ❌ না | পূর্ণ chat text আছে (ব্যক্তিগত) |
| `dom/`, `screens/` | ❌ না | পূর্ণ page HTML ও screenshot, chat text আছে |
| `browser_profile/` | ❌ কখনো না | Login cookie আছে |

**Redaction-এর সঠিক সীমা (v23-এ সংশোধিত):**
- কোড যা করে: request/response body-তে token-জাতীয় key-এর মান, JWT, email, এবং URL query-র `token`/secret মান মask করে (`redact_*`, `redact_text`); cookie/header-এর মানের বদলে শুধু নাম রাখে।
- `--keep-text` না দিলে `share_bundle.json`-এ message text (`text`/`content`/`body` key) ও username মask থাকে। multipart send body-তে field নাম ও ধরন থাকে, `content`-এর মান মask থাকে, `nonce`-এর মান থাকে।
- `events.jsonl`, `dom/*.html`, `dom/*.json`, `screens/`-এ পূর্ণ chat text ও username থাকতে পারে। এগুলো তাই **local-only**।
- `summary.json` ও `REPORT.md` কে আমরা "সব সময় পুরোপুরি মask" বলছি না। শেয়ারের আগে সেগুলোও একবার দেখে নিন। অর্থাৎ শেয়ার করুন শুধু `share_bundle.json` ও `REPORT.md`।

## ৪. Site update হলে কী করবেন

1. আবার `run_capture.bat` চালান (একই profile, আর login লাগবে না যদি session এখনো valid থাকে)।
2. কয়েকটা message ও skip চালান।
3. নতুন `share_bundle.json` আমাকে দিন।

## ৫. Output-এর মানে (`REPORT.md`)

- **Selector health:** bot যে selector দিয়ে message খোঁজে তার hit rate। `NOT FOUND` মানে site বদলে গেছে, bot ওই অংশে পড়তে পারবে না।
- **HTTP endpoints:** কোন API call কোন status দিয়েছে, request ও response-এর structure।
- **WebSocket events:** `chatMessage`, `matchUpdate` ইত্যাদির নাম ও structure।
- **UI action → next HTTP:** আপনার Enter বা button চাপার পর কোন request গেল। এটা দিয়ে send-এর আসল request ধরা যায়।
- **Partner message → our send delay:** partner message এর পর bot-এর send-এর আগে কতটা সময় লাগল।

## ৬. সীমাবদ্ধতা

- Tool শুধু আপনার নিজের browser-এ আপনার দেখা চ্যাট capture করে। অন্য কোনো account বা site-এ যায় না।
- DOM selector জানা অংশগুলোই health-check হয়। নতুন element চিনতে `dom/` ফোল্ডারের HTML ও outline দরকার, যেটা শুধু আপনার কাছে থাকবে।
- Playwright দিয়ে চালানো হয়েছে; site যদি automation শনাক্ত করে, সেটা আলাদা সমস্যা। তখন `REPORT.md`-তে তার চিহ্ন (block page, captcha) দেখা যাবে।
