# OPEN QUESTIONS (এখনো মীমাংসা হয়নি)

## 2026-10-10 | Shared zip contains account_sessions token

Earlier root-project zips (v14 and before) contained account_sessions/*/storage_state.json with a live chitchat token. v15 excludes it. Open: user should rotate/logout that account session if the zip was shared publicly; old zip still exists in git history on branch.
## 2026-10-10 | multipart field names live-এ unverified
- `content`/`nonce` field names response keys থেকে inferred; capture tool-এ request body ছিল না।
- **Resolve করবে:** ইউজার live test চালালে debug log-এ "retrying once as JSON" দেখলে multipart reject হচ্ছে বোঝা যাবে। তখন ইউজারকে DevTools-এ POST /messages-এর request body দিতে বলো → `send_message()` update → smoke test [6] update।

## 2026-10-10 | 403 Flagged-এর আসল behavior live-এ untested
- Backoff 10min ধরা আছে; কিন্তু Flagged হলে কতক্ষণ থাকে / কী করলে ছাড়ে — জানা নেই।
- **Resolve করবে:** live-এ Flagged দেখা গেলে /moderation/standing response ইউজারকে দেখাও, capture করো।

## 2026-10-10 | Queue wait behavior unknown
- Capture-এ সব match instant ছিল; খালি queue-তে কী হয় (inQueue কতক্ষণ, কোন event-এ cancel হয়) capture নেই।
- বর্তমান handling: /match/active poll (safe)। live-এ queue wait হলে log দেখে verify করো।

## 2026-10-10 | Multi-account support করবে কি না
- ইউজারের পুরনো README-তে browser-account note ছিল; আলাদাভাবে চাননি এখনো। চাইলে: configs/sessions/*.json + account rotate in BotWorker — বড় change, আগে decisions.md-এ justify করো।

## 2026-10-10 | Proxy support
- ইউজারের legacy project-এ proxy_manager আছে; chitchat bot-এ এখনো নেই। বানাতে চাইলে aiohttp_socks (আছে src/requirements.txt) + loop-level connector। কিন্তু ইউজার চাওয়ার আগে বানিয়ো না।
